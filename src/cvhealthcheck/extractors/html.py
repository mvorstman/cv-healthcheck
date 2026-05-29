"""
cvhealthcheck.extractors.html
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generic HTML extractor driven by extraction instructions stored in the
subject_section_sources table.

Two instruction patterns are supported (as seeded in migration 0003):

Pattern 1 — findings (security_assessment)
  section_title_selector : ".panel-table-title"
  section_title_match    : e.g. "Access Security"
  column_map             : [{"source": ..., "canonical": ..., "type": ...}, ...]
  status_to_severity     : {"Critical": "critical", "Warning": "warning", ...}
  output_as              : "findings"

Pattern 2 — table (license_summary)
  section_title_selector : ".reportstabletitle"
  section_title_match    : e.g. "Other Licenses"
  column_map             : [...]
  null_values            : ["N/A", "-", ""]
  output_as              : "table"

Section-finding algorithm:
  1. CSS-select all elements matching section_title_selector.
  2. Find the one whose stripped text equals section_title_match
     (case-insensitive).
  3. Walk up the DOM from its parent looking for an ancestor with a <table>
     (up to 5 levels).
  4. Extract table rows from that ancestor's first <table>.

No exceptions raised to caller — problems go into ExtractionResult.warnings
or ExtractionResult.errors.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag


@dataclass
class ExtractionResult:
    subject_id: str
    source_type: str = "html"
    sections: dict[str, list[dict]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # populated by the extractor; maps section_id → 'findings' | 'table'
    section_output_types: dict[str, str] = field(default_factory=dict)
    # populated by the extractor; maps section_id → human-readable title
    section_titles: dict[str, str] = field(default_factory=dict)
    # ADR 0004 conformance: maps section_id → structured failure record for
    # sections whose collected data failed schema conformance. A failed
    # section is recorded here instead of in `sections`; sibling sections
    # continue to collect. result_to_artifact emits these onto the artifact.
    section_failures: dict[str, dict] = field(default_factory=dict)


class HTMLExtractor:
    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self._db = db_conn

    def extract(self, file_path: Path, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id)

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No HTML extraction instructions found for {subject_id} v{version}"
            )
            return result

        try:
            html_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            result.errors.append(f"Failed to read HTML file: {exc}")
            return result

        soup = BeautifulSoup(html_text, "html.parser")
        for node in soup.find_all(["script", "style"]):
            node.decompose()

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr["extraction_instructions"]

            if not extraction:
                result.warnings.append(f"Section '{section_id}' has no extraction instructions")
                continue

            output_as = extraction.get("output_as", "table")
            title_selector = extraction.get("section_title_selector", "")
            title_match = extraction.get("section_title_match", "")
            column_map = extraction.get("column_map", [])
            null_values = extraction.get("null_values", [])
            status_to_severity = extraction.get("status_to_severity", {})

            container = self._find_section_container(
                soup,
                selector=title_selector,
                title_match=title_match,
                section_id=section_id,
                result=result,
            )
            if container is None:
                continue

            table = container.find("table")
            if table is None:
                result.errors.append(
                    f"Section '{title_match}' found but contains no table"
                )
                continue

            rows, row_warnings = self._extract_table_rows(
                table,
                column_map=column_map,
                null_values=null_values,
                section_title_match=title_match,
            )
            result.warnings.extend(row_warnings)

            if not rows:
                result.warnings.append(
                    f"Section '{title_match}' table has no data rows"
                )

            if output_as == "findings" and status_to_severity:
                for row in rows:
                    status_val = str(row.get("status") or "")
                    row["severity"] = status_to_severity.get(status_val, "info")

            result.sections[section_id] = rows
            result.section_output_types[section_id] = output_as
            result.section_titles[section_id] = section_title

        return result

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

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
                ON ss.subject_id    = src.subject_id
               AND ss.subject_version = src.subject_version
               AND ss.section_id    = sss.section_id
            WHERE src.subject_id     = ?
              AND src.subject_version = ?
              AND src.source_type    = 'html'
              AND src.extractable    = 1
            ORDER BY ss.sort_order
            """,
            (subject_id, version),
        ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            try:
                d["extraction_instructions"] = (
                    json.loads(d["extraction_instructions"])
                    if d["extraction_instructions"]
                    else None
                )
            except json.JSONDecodeError:
                d["extraction_instructions"] = None
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Section finding
    # ------------------------------------------------------------------

    def _find_section_container(
        self,
        soup: BeautifulSoup,
        selector: str,
        title_match: str,
        section_id: str,
        result: ExtractionResult,
    ) -> Tag | None:
        if not selector or not title_match:
            result.errors.append(
                f"Section '{section_id}' missing selector or title_match in instructions"
            )
            return None

        candidates = soup.select(selector)
        matched: Tag | None = None
        for elem in candidates:
            text = elem.get_text(" ", strip=True).strip()
            norm = title_match.strip().lower()
            if text.lower() == norm or text.lower().startswith(norm + " -") or text.lower().startswith(norm + ":"):
                matched = elem
                break

        if matched is None:
            result.errors.append(f"Section '{title_match}' not found")
            return None

        # Walk up DOM to find ancestor that contains a <table>.
        parent = matched.parent
        for _ in range(5):
            if parent is None:
                break
            if parent.find("table"):
                return parent
            parent = parent.parent

        result.errors.append(
            f"Section '{title_match}' found but contains no table"
        )
        return None

    # ------------------------------------------------------------------
    # Table row extraction
    # ------------------------------------------------------------------

    def _extract_table_rows(
        self,
        table: Tag,
        column_map: list[dict],
        null_values: list[str],
        section_title_match: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []

        # Locate header row and data rows.
        thead = table.find("thead")
        tbody = table.find("tbody")

        if thead is not None:
            header_row = thead.find("tr")
            data_rows_tag = tbody if tbody is not None else table
            data_rows = (
                data_rows_tag.find_all("tr", recursive=False)
                if data_rows_tag is not None
                else []
            )
        else:
            all_rows = table.find_all("tr")
            if not all_rows:
                return [], warnings
            header_row = all_rows[0]
            data_rows = all_rows[1:]

        if header_row is None:
            return [], warnings

        # Build lower-cased header text → column index mapping.
        header_cells = header_row.find_all(["th", "td"])
        header_map: dict[str, int] = {}
        for idx, cell in enumerate(header_cells):
            text = cell.get_text(" ", strip=True).strip().lower()
            header_map[text] = idx

        # Resolve column_map entries against actual headers.
        resolved: list[tuple[str, str, str, int]] = []  # (source, canonical, type, col_idx)
        for col in column_map:
            source: str = col.get("source", "")
            canonical: str = col.get("canonical", source)
            col_type: str = col.get("type", "string")
            col_idx = header_map.get(source.lower())
            if col_idx is None:
                warnings.append(
                    f"Column '{source}' not found in table headers"
                    f" for section '{section_title_match}'"
                )
                continue
            resolved.append((source, canonical, col_type, col_idx))

        # Extract data rows.
        result_rows: list[dict[str, Any]] = []
        for row in data_rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            row_dict: dict[str, Any] = {}
            for _source, canonical, col_type, col_idx in resolved:
                raw = cells[col_idx].get_text(" ", strip=True) if col_idx < len(cells) else ""
                value, warn = self._coerce(
                    raw, col_type, null_values, _source, section_title_match
                )
                if warn:
                    warnings.append(warn)
                row_dict[canonical] = value
            if row_dict:
                result_rows.append(row_dict)

        return result_rows, warnings

    # ------------------------------------------------------------------
    # Type coercion
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce(
        raw: str,
        col_type: str,
        null_values: list[str],
        col_name: str,
        section_name: str,
    ) -> tuple[Any, str | None]:
        stripped = raw.strip()

        if stripped in null_values:
            return None, None

        if col_type == "string":
            return stripped, None

        if col_type == "integer":
            try:
                return int(stripped), None
            except (ValueError, TypeError):
                return (
                    None,
                    f"Could not coerce '{stripped}' to integer"
                    f" (col='{col_name}', section='{section_name}')",
                )

        if col_type == "float":
            try:
                return float(stripped), None
            except (ValueError, TypeError):
                return (
                    None,
                    f"Could not coerce '{stripped}' to float"
                    f" (col='{col_name}', section='{section_name}')",
                )

        return stripped, None
