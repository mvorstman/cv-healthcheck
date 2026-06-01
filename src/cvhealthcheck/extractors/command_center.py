"""
cvhealthcheck.extractors.command_center
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0007 Phase 2 — a SINGLE-OBJECT extractor for the Command Center API source
(``rest_command_center_api``). Unlike the Reports-Plus ``RESTExtractor`` (dataset
ROWS), this collects one nested identity OBJECT (``GET /commandcenter/api/CommServ``)
and presents it as a single record to the generic card path.

It does NOT reimplement the GET CommServ call — it wraps the existing
``get_commcell_identity`` (``quickhc/commcell.py``), which keeps writing
``commserv.json`` as raw provenance (the source of record). The single record is
that call's ``raw`` payload (the nested CommServ dict); the card spec from the
subject's ``rest_command_center_api`` binding then reads it with Phase-1's
nested-path field selector + ``hex`` coercion. The result feeds the unchanged
``result_to_artifact`` → ``save_artifact`` tail.

For offline tests an ``identity_provider`` callable can be injected (returning a
saved CommServ payload) so no network is needed.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from cvhealthcheck.db.rule_overrides import load_section_overrides
from cvhealthcheck.db.rules import load_rules_registry
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.quickhc.commcell import get_commcell_identity

# The subject_sources.source_type that routes a /collect to this extractor.
COMMAND_CENTER_SOURCE_TYPE = "rest_command_center_api"


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
        # Default: wrap get_commcell_identity (which writes commserv.json as raw
        # provenance). Injectable for offline tests.
        self._identity_provider = identity_provider or (
            lambda: get_commcell_identity(token=token)
        )

    def extract(self, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id, source_type=COMMAND_CENTER_SOURCE_TYPE)
        result.rules_registry = load_rules_registry(self._db)
        result.section_overrides = load_section_overrides(
            self._db, self._customer_id, self._project_id, subject_id, version
        )

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No command_center_api extraction instructions found for {subject_id} v{version}"
            )
            return result

        # One GET CommServ for the whole subject — a single nested identity object.
        payload = self._identity_provider()
        if not isinstance(payload, dict) or payload.get("http_status") not in (None, 200) or payload.get("error"):
            result.errors.append(
                f"GET CommServ failed (http_status={payload.get('http_status')!r}, "
                f"error={payload.get('error')!r})"
            )
            return result
        record = payload.get("raw") or {}
        if not isinstance(record, dict):
            record = {}

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}
            output_as = extraction.get("output_as", "card")
            if output_as == "card":
                result.section_card_specs[section_id] = extraction.get("card", {})
            # The single CommServ object is the one record fed to the card builder
            # (build_card_section reads rows[0]); nested fields resolve via the
            # Phase-1 dot-path selector.
            result.sections[section_id] = [record]
            result.section_output_types[section_id] = output_as
            result.section_titles[section_id] = section_title

        return result

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
