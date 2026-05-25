"""
cvhealthcheck.extractors.rest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generic REST extractor driven by extraction instructions stored in the
subject_section_sources table (source_type = 'rest').

AUDIT FINDINGS (2026-05-25):
  ExtractionResult dataclass and db query pattern taken from html.py.
  CommvaultSession (reportsplus/session.py) wraps dataset fetching.
  No Flask imports.

Instruction keys (from db for client_growth.monthly_table):
  dataset_guid      : str   GUID of the Reports Plus dataset
  fields            : list  Field names to request
  orderby           : str   e.g. "MonthStart Asc"
  limit             : int   Max rows to fetch
  parameters        : dict  Extra query-string params
  timestamp_fields  : list  Fields to convert to ISO strings
  timestamp_format  : str   "unix_seconds" | "unix_ms"
  null_values       : list  Values to coerce to None (JSON null → None)
  output_as         : str   "table" | "findings"
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from cvhealthcheck.extractors.html import ExtractionResult

logger = logging.getLogger(__name__)


class RESTExtractor:
    def __init__(self, db_conn: sqlite3.Connection, session: Any) -> None:
        self._db = db_conn
        self._session = session

    def extract(
        self,
        subject_id: str,
        version: int = 1,
        report_definition: dict | None = None,
    ) -> ExtractionResult:
        """
        Load REST instructions from db, optionally init the report,
        fetch each section dataset, and return an ExtractionResult.

        If report_definition is provided, session.init_report() is called
        first (which sets the cache_id for subsequent fetch_dataset calls).
        """
        result = ExtractionResult(subject_id=subject_id, source_type="rest")

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No REST extraction instructions found for {subject_id} v{version}"
            )
            return result

        if report_definition is not None:
            try:
                self._session.init_report(report_definition)
            except Exception as exc:
                result.errors.append(f"init_report failed: {exc}")
                return result

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}

            rows, warnings, errors = self._fetch_section(section_id, extraction)
            result.warnings.extend(warnings)

            if errors:
                result.errors.extend(errors)
                continue

            result.sections[section_id] = rows
            result.section_output_types[section_id] = extraction.get("output_as", "table")
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
              AND src.source_type     = 'rest'
            ORDER BY ss.sort_order
            """,
            (subject_id, version),
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

    def _fetch_section(
        self,
        section_id: str,
        instructions: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []

        dataset_guid = instructions.get("dataset_guid")
        if not dataset_guid:
            errors.append(f"Section '{section_id}': no dataset_guid in instructions")
            return [], warnings, errors

        fields: list[str] = instructions.get("fields") or []
        orderby: str | None = instructions.get("orderby")
        limit: int | None = instructions.get("limit")
        parameters: dict[str, str] | None = instructions.get("parameters")
        timestamp_fields: list[str] = instructions.get("timestamp_fields") or []
        timestamp_format: str = instructions.get("timestamp_format", "")
        null_values: list[Any] = instructions.get("null_values") or []

        try:
            raw_rows = self._session.fetch_dataset(
                dataset_guid,
                fields=fields or None,
                orderby=orderby,
                limit=limit,
                parameters=parameters,
            )
        except Exception as exc:
            errors.append(f"Section '{section_id}': fetch_dataset failed: {exc}")
            return [], warnings, errors

        rows = []
        for raw in raw_rows:
            row = dict(raw)
            for field in timestamp_fields:
                if field in row:
                    row[field] = _convert_timestamp(row[field], timestamp_format)
            for key, val in list(row.items()):
                if val in null_values:
                    row[key] = None
            rows.append(row)

        return rows, warnings, errors


def _convert_timestamp(value: Any, fmt: str) -> Any:
    if value is None:
        return value
    if fmt == "unix_seconds":
        try:
            return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
        except (TypeError, ValueError, OSError):
            return value
    if fmt == "unix_ms":
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=UTC).isoformat()
        except (TypeError, ValueError, OSError):
            return value
    return value
