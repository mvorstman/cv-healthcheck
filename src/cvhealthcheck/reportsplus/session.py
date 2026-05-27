"""
cvhealthcheck.reportsplus.session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HTTP session for Reports Plus dataset access.

AUDIT FINDINGS (2026-05-25):
  CASE 2 — Existing code handles auth and direct dataset GET via
  CommvaultApiClient / ReportsPlusClient (reportsplus/client.py), but
  no reportBuilder.do / init_report / cache_id pattern exists anywhere.

  CommvaultApiClient wraps requests.Session and requires Settings objects
  loaded from env vars; it is not suitable as a base class here because
  the collect route provides base_url and token directly (from Flask session).

  ReportsPlusClient.get_dataset_data() performs a direct GET to
  /datasets/{guid}/data — the same endpoint used here.

  This module adds init_report() (POST to reportBuilder.do) and a typed
  fetch_dataset() with pagination on top of the existing pattern.
  No Flask imports anywhere in this file.
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from requests import Session

logger = logging.getLogger(__name__)

_BASE = "/commandcenter/api/cr/reportsplusengine"
_REPORTBUILDER_PATH = f"{_BASE}/reportBuilder.do"
_DATASETS_BASE = f"{_BASE}/datasets"
_REPORTS_BASE = f"{_BASE}/reports"

# Keys that the Commvault API may use for the cache/session identifier.
_CACHE_ID_KEYS = ("cacheId", "sessionId", "id", "cache_id")


class CommvaultSessionError(RuntimeError):
    """Raised for session-level failures (missing cache_id, bad response)."""


class CommvaultSession:
    """
    Thin stateful HTTP session for Reports Plus.

    Direct dataset access (the default; no acquisition step needed):
        rows = session.fetch_dataset(guid, ...)
        # → GET /datasets/<guid>/data — CommCell auto-generates a cacheId
        #   in the response body, which is ignored here.

    Browser-style reportBuilder pattern (UI-session use, not the catalog-
    driven extractor's path):
        session.init_report(report_definition)  # POST → cache_id stored
        rows = session.fetch_dataset(guid, ...) # GET pages with cacheId

    fetch_dataset() works in both modes: with no cache_id set or passed it
    performs a direct GET (the ADR 0003 GET-only protocol); with a cache_id
    it includes it in the request params for UI-correlated rendering.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._http: Session = requests.Session()
        self._cache_id: str | None = None

    # ── context manager ──────────────────────────────────────────────────

    def __enter__(self) -> "CommvaultSession":
        return self

    def __exit__(self, *_args: Any) -> None:
        self._http.close()

    # ── internals ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Authtoken": self._token}

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    # ── public interface ─────────────────────────────────────────────────

    def get_report(self, report_id: str | int) -> dict:
        """
        GET the live report definition for `report_id`.

        Returns the parsed JSON dict from /reportsplusengine/reports/<id>.
        The Commvault response wraps the actual definition in a string-encoded
        `content` field (or a `pages[].body` field) — callers that need the
        walkable definition should pass the result through
        `cvhealthcheck.reportsplus.inventory.parse_content_field`.

        Raises:
            requests.HTTPError: on a non-2xx response.
            CommvaultSessionError: if the response body is not a JSON object.
        """
        url = self._url(f"{_REPORTS_BASE}/{report_id}")
        response = self._http.get(
            url,
            headers=self._headers(),
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise CommvaultSessionError(
                f"get_report({report_id!r}): expected JSON object, got "
                f"{type(data).__name__}"
            )
        return data

    def init_report(self, report_definition: dict) -> str:
        """
        POST report_definition to reportBuilder.do, store and return cache_id.

        Raises:
            requests.HTTPError: on a non-2xx response.
            CommvaultSessionError: if the response contains no recognised
                cache_id key (cacheId, sessionId, id, cache_id).
        """
        url = self._url(_REPORTBUILDER_PATH)
        response = self._http.post(
            url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=report_definition,
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data: Any = response.json()
        if isinstance(data, dict):
            for key in _CACHE_ID_KEYS:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    self._cache_id = value.strip()
                    return self._cache_id
        raise CommvaultSessionError(
            "init_report: no cache_id key found in response; "
            f"got keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )

    def fetch_dataset(
        self,
        dataset_guid: str,
        fields: list[str] | None = None,
        orderby: str | None = None,
        limit: int | None = None,
        parameters: dict[str, str] | None = None,
        cache_id: str | None = None,
    ) -> list[dict]:
        """
        GET rows from a dataset endpoint with automatic pagination.

        With no cache_id set on the session and none passed, performs a
        direct GET — the lab CommCell auto-generates a cacheId in the
        response body, which we ignore. With a cache_id (passed explicitly
        or stored by a prior init_report() call), the cacheId is included
        in the request params for UI-correlated rendering.

        Returns a flat list of row dicts. Handles both the list-of-lists
        (columns + records) and list-of-dicts (format=object) response shapes.
        """
        effective_cache_id = cache_id or self._cache_id

        page_size = limit if limit is not None else 1000
        all_records: list[dict] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "format": "object",
                "limit": page_size,
                "offset": offset,
            }
            if effective_cache_id is not None:
                params["cacheId"] = effective_cache_id
                # `fields` and `orderby` only work with a cacheId — the lab's
                # CacheDB rejects field-filtered or sorted requests in the
                # no-cacheId GET-only path with "Bad Request. Please check
                # the parameters." The catalog can declare both for
                # self-documentation; they just aren't sent to the server
                # when we don't have a cacheId.
                if fields:
                    params["fields"] = ",".join(fields)
                if orderby:
                    params["orderby"] = orderby
            if parameters:
                params.update(parameters)

            url = self._url(f"{_DATASETS_BASE}/{dataset_guid}/data")
            response = self._http.get(
                url,
                headers=self._headers(),
                params=params,
                verify=self._verify_ssl,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()

            records = _extract_records(data, fields or [])
            if not records:
                break

            all_records.extend(records)

            if limit is not None and len(all_records) >= limit:
                return all_records[:limit]

            # The lab returns totalRecordCount; some deployments return total.
            total = None
            if isinstance(data, dict):
                total = data.get("totalRecordCount", data.get("total"))
            offset += len(records)
            if total is not None and offset >= total:
                break
            if len(records) < page_size:
                break

        return all_records


def _extract_records(data: Any, fields: list[str]) -> list[dict]:
    """Normalise an API response to a list of row dicts."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return []
    records = data.get("records")
    if not isinstance(records, list) or not records:
        return []
    if isinstance(records[0], dict):
        return records
    # list-of-lists: zip with column names from response or from fields param
    columns: list[str] = data.get("columns") or fields
    return [
        dict(zip(columns, row))
        for row in records
        if isinstance(row, (list, tuple))
    ]
