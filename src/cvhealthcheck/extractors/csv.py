"""
cvhealthcheck.extractors.csv
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generic CSV extractor driven by extraction instructions stored in the
subject_section_sources table.

Two instruction formats are supported:

Format 1 — single_table (license_summary)
  format     : "single_table"
  column_map : [{"source": ..., "canonical": ..., "type": ...}, ...]
  null_values: ["N/A", "-", ""]
  output_as  : "table"

  Algorithm: scan rows top-to-bottom; find header row whose cells
  (case-insensitive) include all source names in column_map; collect
  data rows until blank line / EOF.

Format 2 — multi_section (client_growth, capacity_license)
  format            : "multi_section"
  section_separator : "blank_lines"
  section_label     : "Clients Count"  OR  section_index: 6
  column_map        : [...]
  null_values       : [...]
  output_as         : "table"

  Algorithm: split file by blank-line runs into sections; locate by
  section_label (case-insensitive first-cell match) or section_index;
  first row is header, remaining rows are data.

Fuzzy matching: when a column has fuzzy_match=true, the "None_" prefix is
stripped from the source name when matching against actual CSV headers.

Encoding: tries utf-8-sig first (handles BOM), then utf-8, then latin-1.
No exceptions raised to caller — problems go into ExtractionResult.warnings
or ExtractionResult.errors.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

from cvhealthcheck.extractors.html import ExtractionResult


class CSVExtractor:
    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self._db = db_conn

    def extract(self, file_path: Path, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id, source_type="csv")

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No CSV extraction instructions found for {subject_id} v{version}"
            )
            return result

        try:
            text = self._read_file(file_path)
        except OSError as exc:
            result.errors.append(f"Failed to read CSV file: {exc}")
            return result

        rows_raw = list(csv.reader(io.StringIO(text)))

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr["extraction_instructions"]

            if not extraction:
                result.warnings.append(f"Section '{section_id}' has no extraction instructions")
                continue

            fmt = extraction.get("format", "single_table")
            column_map = extraction.get("column_map", [])
            null_values = extraction.get("null_values", [])
            output_as = extraction.get("output_as", "table")
            status_to_severity = extraction.get("status_to_severity", {})

            if fmt == "single_table":
                rows, warnings = self._extract_single_table(
                    rows_raw, column_map, null_values, section_id
                )
            elif fmt == "multi_section":
                rows, warnings = self._extract_multi_section(
                    rows_raw, extraction, column_map, null_values, section_id
                )
            else:
                result.errors.append(f"Unknown CSV format '{fmt}' for section '{section_id}'")
                continue

            result.warnings.extend(warnings)

            if not rows:
                result.warnings.append(f"Section '{section_id}' has no data rows")

            # ADR 0004 findings: map the declared status text to a canonical
            # severity, exactly as HTMLExtractor does. status_to_severity is an
            # existing declarative instruction (not a new transform); the CSV
            # path simply hadn't emitted findings before. Without this every
            # CSV finding would default to "info" in _build_finding.
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
                ON ss.subject_id     = src.subject_id
               AND ss.subject_version = src.subject_version
               AND ss.section_id     = sss.section_id
            WHERE src.subject_id     = ?
              AND src.subject_version = ?
              AND src.source_type    = 'csv'
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
    # File reading
    # ------------------------------------------------------------------

    @staticmethod
    def _read_file(file_path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return Path(file_path).read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise OSError(f"Could not read {file_path} with any supported encoding")

    # ------------------------------------------------------------------
    # single_table
    # ------------------------------------------------------------------

    def _extract_single_table(
        self,
        rows_raw: list[list[str]],
        column_map: list[dict],
        null_values: list[str],
        section_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        sources_lower = {col["source"].lower() for col in column_map}

        header_idx: int | None = None
        for i, row in enumerate(rows_raw):
            cells_lower = {c.strip().lower() for c in row if c.strip()}
            if sources_lower and sources_lower.issubset(cells_lower):
                header_idx = i
                break

        if header_idx is None:
            warnings.append(f"Section '{section_id}': no header row matching column_map found")
            return [], warnings

        header_cells = [c.strip() for c in rows_raw[header_idx]]
        header_map: dict[str, int] = {c.lower(): idx for idx, c in enumerate(header_cells)}

        resolved = self._resolve_columns(column_map, header_map, section_id, warnings, fuzzy=False)

        result_rows: list[dict[str, Any]] = []
        for row in rows_raw[header_idx + 1:]:
            cells = [c.strip() for c in row]
            if not any(cells):
                break
            row_dict, row_warnings = self._extract_row(cells, resolved, null_values, section_id)
            warnings.extend(row_warnings)
            if row_dict:
                result_rows.append(row_dict)

        return result_rows, warnings

    # ------------------------------------------------------------------
    # multi_section
    # ------------------------------------------------------------------

    def _extract_multi_section(
        self,
        rows_raw: list[list[str]],
        extraction: dict,
        column_map: list[dict],
        null_values: list[str],
        section_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []

        # Split into sections by blank-line runs.
        sections: list[list[list[str]]] = []
        current: list[list[str]] = []
        for row in rows_raw:
            cells = [c.strip() for c in row]
            if not any(cells):
                if current:
                    sections.append(current)
                    current = []
            else:
                current.append(cells)
        if current:
            sections.append(current)

        section_label = extraction.get("section_label")
        section_index = extraction.get("section_index")

        target: list[list[str]] | None = None

        if section_label is not None:
            label_lower = section_label.strip().lower()
            for sec in sections:
                if sec and sec[0] and sec[0][0].lower() == label_lower:
                    target = sec
                    break
            if target is None:
                warnings.append(
                    f"Section '{section_id}': label '{section_label}' not found"
                )
                return [], warnings
        elif section_index is not None:
            if section_index < len(sections):
                target = sections[section_index]
            else:
                warnings.append(
                    f"Section '{section_id}': index {section_index} out of range"
                    f" (found {len(sections)} sections)"
                )
                return [], warnings
        else:
            warnings.append(
                f"Section '{section_id}': no section_label or section_index specified"
            )
            return [], warnings

        # target[0] is the section label/title; target[1] is the CSV header row.
        if len(target) < 3:
            warnings.append(f"Section '{section_id}': section has no data rows")
            return [], warnings

        header_cells = target[1]
        header_map: dict[str, int] = {c.lower(): idx for idx, c in enumerate(header_cells)}

        has_fuzzy = any(col.get("fuzzy_match") for col in column_map)
        resolved = self._resolve_columns(
            column_map, header_map, section_id, warnings, fuzzy=has_fuzzy
        )

        result_rows: list[dict[str, Any]] = []
        for row in target[2:]:
            row_dict, row_warnings = self._extract_row(row, resolved, null_values, section_id)
            warnings.extend(row_warnings)
            if row_dict:
                result_rows.append(row_dict)

        return result_rows, warnings

    # ------------------------------------------------------------------
    # Column resolution and row extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_columns(
        column_map: list[dict],
        header_map: dict[str, int],
        section_id: str,
        warnings: list[str],
        fuzzy: bool = False,
    ) -> list[tuple[str, str, str, int]]:
        resolved: list[tuple[str, str, str, int]] = []
        for col in column_map:
            source: str = col.get("source", "")
            canonical: str = col.get("canonical", source)
            col_type: str = col.get("type", "string")
            col_fuzzy: bool = fuzzy or bool(col.get("fuzzy_match"))

            col_idx = header_map.get(source.lower())

            if col_idx is None and col_fuzzy and source.startswith("None_"):
                stripped = source[5:]
                col_idx = header_map.get(stripped.lower())
                if col_idx is not None:
                    warnings.append(
                        f"Fuzzy-matched '{source}' → '{stripped}'"
                        f" for section '{section_id}'"
                    )

            if col_idx is None:
                warnings.append(
                    f"Column '{source}' not found in CSV headers"
                    f" for section '{section_id}'"
                )
                continue
            resolved.append((source, canonical, col_type, col_idx))
        return resolved

    @staticmethod
    def _extract_row(
        cells: list[str],
        resolved: list[tuple[str, str, str, int]],
        null_values: list[str],
        section_id: str,
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        row_dict: dict[str, Any] = {}
        for _source, canonical, col_type, col_idx in resolved:
            raw = cells[col_idx] if col_idx < len(cells) else ""
            value, warn = CSVExtractor._coerce(raw, col_type, null_values, _source, section_id)
            if warn:
                warnings.append(warn)
            row_dict[canonical] = value
        return row_dict, warnings

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
