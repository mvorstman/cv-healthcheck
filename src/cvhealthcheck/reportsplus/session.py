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

# Keys that the Commvault API may use for the cache/session identifier.
_CACHE_ID_KEYS = ("cacheId", "sessionId", "id", "cache_id")


class CommvaultSessionError(RuntimeError):
    """Raised for session-level failures (missing cache_id, bad response)."""


class CommvaultSession:
    """
    Thin stateful HTTP session for Reports Plus.

    Two-step reportBuilder pattern:
        session.init_report(report_definition)  # POST → cache_id stored
        rows = session.fetch_dataset(guid, ...) # GET pages with cacheId

    Direct dataset access (explicit cache_id):
        rows = session.fetch_dataset(guid, ..., cache_id="<known>")

    fetch_dataset() raises CommvaultSessionError if no cache_id is available
    (neither stored from init_report() nor passed explicitly).
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

        A cache_id is required — either passed explicitly or set by a prior
        call to init_report().  Raises CommvaultSessionError if neither is
        available.

        Returns a flat list of row dicts.  Handles both the list-of-lists
        (columns + records) and list-of-dicts (format=object) response shapes.
        """
        effective_cache_id = cache_id or self._cache_id
        if effective_cache_id is None:
            raise CommvaultSessionError(
                "fetch_dataset: cache_id required — call init_report() first "
                "or pass cache_id explicitly"
            )

        page_size = limit if limit is not None else 1000
        all_records: list[dict] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "format": "object",
                "cacheId": effective_cache_id,
                "limit": page_size,
                "offset": offset,
            }
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

            total = data.get("total") if isinstance(data, dict) else None
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
