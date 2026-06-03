"""
cvhealthcheck.extractors.command_center
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The extractor for the Command Center API source (``rest_command_center_api``).
Unlike the Reports-Plus ``RESTExtractor`` (dataset ROWS), this collects directly
from a Command Center API endpoint declared by the subject's source binding.

ADR 0007 scoped it to a single nested identity OBJECT (``GET
/commandcenter/api/CommServ`` → one record → a card). ADR 0009 D1 generalizes it
along two axes, **without a parallel extractor** (ADR 0006 D4.1, one
canonicalization path):

  1. Endpoint — the relative endpoint comes from the binding's
     ``recognition_hints.endpoint`` (validated relative + read-only by
     ``cc_endpoint.validate_cc_endpoint``), defaulting to
     ``/commandcenter/api/CommServ`` when none is declared. For that default the
     existing ``get_commcell_identity`` path is kept verbatim (it still writes
     ``commserv.json`` as raw provenance), so ``environment`` is byte-for-byte
     unchanged; any other endpoint is a plain GET via ``CommvaultApiClient``.
  2. Shape — a section binding's ``output_as`` selects the emission: ``card``
     (single record, the ADR 0007 path) or ``table`` (a multi-record collection
     projected into rows). Multi-record projection is structural only (field
     selection / renaming via the shared nested-path resolver) — it adds no
     operator and does not widen CEL (ADR 0006 D2).

The result still feeds the unchanged ``result_to_artifact`` → ``save_artifact``
tail. For offline tests an ``identity_provider`` callable can be injected
(returning a saved payload dict with ``raw`` / ``http_status`` / ``error``) so
no network is needed.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from cvhealthcheck.db.rule_overrides import load_section_overrides
from cvhealthcheck.db.rules import (
    load_rules_registry,
    load_subject_row_rules,
    load_subject_section_scope,
)
from cvhealthcheck.extractors.cc_endpoint import (
    COMMAND_CENTER_SOURCE_TYPE,
    DEFAULT_CC_ENDPOINT,
    EndpointPolicyError,
    validate_cc_endpoint,
)
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.metric_section import _resolve_field_path
from cvhealthcheck.quickhc.commcell import get_commcell_identity

# COMMAND_CENTER_SOURCE_TYPE is defined in cc_endpoint (leaf, no project deps) and
# re-exported here for the existing importers (web.routes.quick_hc).
__all__ = ["CommandCenterExtractor", "COMMAND_CENTER_SOURCE_TYPE"]


class CommandCenterExtractor:
    def __init__(
        self,
        db_conn: sqlite3.Connection,
        *,
        token: str | None = None,
        customer_id: str = "default",
        project_id: str = "default",
        identity_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._db = db_conn
        self._token = token
        self._customer_id = customer_id
        self._project_id = project_id
        # An explicit provider (offline tests) overrides the network fetch
        # entirely. When None, extract() fetches from the binding's declared
        # endpoint via _fetch — the default CommServ endpoint keeps the
        # get_commcell_identity path (commserv.json provenance; `environment`
        # unchanged), any other endpoint is a plain GET.
        self._identity_provider = identity_provider

    def extract(self, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id, source_type=COMMAND_CENTER_SOURCE_TYPE)
        result.rules_registry = load_rules_registry(self._db)
        # ADR 0010: carry the subject's bound row_match rules + section scope so the
        # result_to_artifact compliance pass fires (scoped) on this collection.
        result.section_row_rules = load_subject_row_rules(self._db, subject_id, version)
        result.section_scope = load_subject_section_scope(self._db, subject_id, version)
        result.section_overrides = load_section_overrides(
            self._db, self._customer_id, self._project_id, subject_id, version
        )

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No command_center_api extraction instructions found for {subject_id} v{version}"
            )
            return result

        # ADR 0009 D1 axis 1: the relative endpoint is declared by the binding
        # (default CommServ). Re-validated here before collecting as a defence-in-
        # depth check (it was already validated relative + read-only at persist).
        try:
            endpoint = self._resolve_endpoint(subject_id, version)
        except EndpointPolicyError as exc:
            result.errors.append(
                f"Invalid Command Center endpoint for {subject_id} v{version}: {exc}"
            )
            return result

        payload = self._fetch(endpoint)
        if not isinstance(payload, dict) or payload.get("http_status") not in (None, 200) or payload.get("error"):
            result.errors.append(
                f"GET {endpoint} failed (http_status={(payload or {}).get('http_status')!r}, "
                f"error={(payload or {}).get('error')!r})"
            )
            return result
        raw = payload.get("raw")

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}
            output_as = extraction.get("output_as", "card")
            if output_as == "table":
                # ADR 0009 D1 axis 2: a multi-record collection projected into
                # rows. Structural projection only (field selection/renaming) —
                # no operators (ADR 0006 D2). Columns auto-derive from row keys
                # downstream unless the binding declares an explicit column map.
                table_spec = extraction.get("table", {})
                result.sections[section_id] = _project_table_rows(raw, table_spec)
                result.section_table_specs[section_id] = table_spec
            else:
                # card (ADR 0007 path): the single object is the one record fed to
                # the card builder (build_card_section reads rows[0]); nested
                # fields resolve via the shared dot-path selector.
                record = raw if isinstance(raw, dict) else {}
                result.section_card_specs[section_id] = extraction.get("card", {})
                result.sections[section_id] = [record]
            result.section_output_types[section_id] = output_as
            result.section_titles[section_id] = section_title

        return result

    def _resolve_endpoint(self, subject_id: str, version: int) -> str:
        """The relative endpoint this subject's CC-API source collects from.

        Read from the ``rest_command_center_api`` row's
        ``recognition_hints.endpoint``; defaults to CommServ when undeclared.
        Validated relative + read-only (raises ``EndpointPolicyError``)."""
        row = self._db.execute(
            "SELECT recognition_hints FROM subject_sources"
            " WHERE subject_id = ? AND subject_version = ? AND source_type = ?",
            (subject_id, version, COMMAND_CENTER_SOURCE_TYPE),
        ).fetchone()
        endpoint = None
        if row is not None and row["recognition_hints"]:
            try:
                hints = json.loads(row["recognition_hints"])
            except (json.JSONDecodeError, TypeError):
                hints = {}
            if isinstance(hints, dict):
                endpoint = hints.get("endpoint")
        return validate_cc_endpoint(endpoint)

    def _fetch(self, endpoint: str) -> dict[str, Any]:
        """Return the endpoint payload as ``{raw, http_status, error, ok}``.

        An injected ``identity_provider`` (tests) overrides everything. The
        default CommServ endpoint keeps the ``get_commcell_identity`` path
        verbatim (commserv.json provenance) so ``environment`` is unchanged; any
        other endpoint is a plain read-only GET via ``CommvaultApiClient``
        (ADR 0009 D4: still the app-side, in-process token path)."""
        if self._identity_provider is not None:
            return self._identity_provider()
        if endpoint == DEFAULT_CC_ENDPOINT:
            return get_commcell_identity(token=self._token)
        from cvhealthcheck.api_client import CommvaultApiClient

        api_result = CommvaultApiClient(token=self._token).get(endpoint)
        return {
            "raw": api_result.data,
            "http_status": api_result.status_code,
            "error": api_result.error,
            "ok": api_result.ok,
        }

    def _load_section_instructions(
        self, subject_id: str, version: int
    ) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT sss.section_id,
                   sss.extraction_instructions,
                   ss.section_type,
                   ss.title
            FROM subject_section_sources sss
            JOIN subject_sources src ON src.id = sss.source_id
            JOIN subject_sections ss
                ON ss.subject_id      = src.subject_id
               AND ss.subject_version  = src.subject_version
               AND ss.section_id      = sss.section_id
            WHERE src.subject_id      = ?
              AND src.subject_version  = ?
              AND src.source_type     = ?
            ORDER BY ss.sort_order
            """,
            (subject_id, version, COMMAND_CENTER_SOURCE_TYPE),
        ).fetchall()

        result = []
        for row in rows:
            try:
                extraction = (
                    json.loads(row["extraction_instructions"])
                    if row["extraction_instructions"]
                    else {}
                )
            except (json.JSONDecodeError, TypeError):
                extraction = {}
            result.append({
                "section_id": row["section_id"],
                "title": row["title"],
                "section_type": row["section_type"],
                "extraction_instructions": extraction,
            })
        return result


def _project_table_rows(raw: Any, table_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a multi-record Command Center response into table rows.

    Structural projection only (ADR 0006 D2): locate the record list (``raw`` if
    it is already a list, else ``raw[root_key]``), then either pass each record
    dict through unchanged (columns auto-derived from keys by result_to_artifact)
    or, when the binding declares ``columns`` ``[{"id", "field"}]``, select/rename
    each declared field via the shared nested-path resolver. No coercion, no
    operators. A non-dict element degrades to ``{"value": <element>}``; an
    unresolvable list yields ``[]`` (an empty table, not an error).

    NOTE (ADR 0009): ``root_key`` and any column ``field`` paths are UNVERIFIED
    until the Step-5 live ``/v4/servergroup`` capture — this function makes no
    assumption about a specific shape; the keys live entirely in the per-subject
    binding (test scaffolding), not here.
    """
    root_key = table_spec.get("root_key")
    if isinstance(raw, list):
        records: Any = raw
    elif isinstance(raw, dict) and root_key:
        records = raw.get(root_key)
    else:
        records = None
    if not isinstance(records, list):
        return []

    columns = table_spec.get("columns") or []
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            rows.append({"value": record})
            continue
        if columns:
            row: dict[str, Any] = {}
            for col in columns:
                col_id = col.get("id") or col.get("field")
                field = col.get("field") or col.get("id")
                if col_id is None or field is None:
                    continue
                row[col_id] = _resolve_field_path(record, field)
            rows.append(row)
        else:
            rows.append(record)
    return rows
