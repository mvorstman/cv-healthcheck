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

from cvhealthcheck.extractors.column_map import (
    extract_computed,
    extract_metadata_pairs,
    extract_row,
    resolve_columns,
    split_label_value,
)


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
    # ADR 0004 metric sections: maps section_id → the catalog `metric`
    # declaration (semantic / items / evaluative). Carried from the extractor
    # to result_to_artifact, which calls build_metric_section to compute
    # derived values and verdicts at collection time. Present only for
    # sections whose output_as == "metric".
    section_metric_specs: dict[str, dict] = field(default_factory=dict)
    # ADR 0004 chart sections: maps section_id → the catalog `chart`
    # declaration (chart_type, labels/series column mapping, axes). Carried to
    # result_to_artifact, which calls build_chart_section. Present only for
    # sections whose output_as == "chart".
    section_chart_specs: dict[str, dict] = field(default_factory=dict)
    # ADR 0004 card sections: maps section_id → the catalog `card` declaration
    # (items field-mapping, columns, optional evaluative rule). Carried to
    # result_to_artifact, which calls build_card_section. Present only for
    # sections whose output_as == "card".
    section_card_specs: dict[str, dict] = field(default_factory=dict)
    # ADR 0004 phase 7: maps section_id → the catalog `table` declaration
    # (currently just an optional presentational `empty_message`). Carried to
    # result_to_artifact for the default output_as == "table" path.
    section_table_specs: dict[str, dict] = field(default_factory=dict)
    # ADR 0010: maps section_id → a list of resolved `row_match` rule definitions
    # bound to that (table) section. result_to_artifact runs each over the
    # section's rows and emits a derived FindingsSection (the compliance pass).
    # Empty for every path with no row-scope rules bound (the default).
    section_row_rules: dict[str, list[dict]] = field(default_factory=dict)
    # ADR 0010 (scope slice): maps section_id → the section's evaluation SCOPE, a
    # list of AND-ed conditions. Rules run only on in-scope rows; out-of-scope rows
    # get verdict "not_evaluated". Absent ⇒ all rows in scope (unchanged default).
    section_scope: dict[str, list[dict]] = field(default_factory=dict)
    # ADR 0004 phase 8 step 2: the rules registry snapshot (rule_id -> definition)
    # loaded from the DB by the extractor and carried to result_to_artifact, where
    # build_metric_section/build_card_section resolve `ref`-based rules. Loading
    # is catalog-read (like the specs above); resolution + evaluation happen at
    # canonicalization, not here. Empty for paths with no rules (HTML/CSV).
    rules_registry: dict[str, dict] = field(default_factory=dict)
    # ADR 0004 phase 8 step 3: per-section override rows (layer="override") for
    # the active (customer, project), keyed section_id -> [{rule_id, severity,
    # reason}]. Loaded from rule_overrides by the extractor (catalog read);
    # resolution into the verdict_chain happens at canonicalization. Empty for
    # paths/subjects with no overrides.
    section_overrides: dict[str, list[dict]] = field(default_factory=dict)
    # Fix-4 identity comparand (namespace-precision): the wire CommServe csGUID,
    # supplied by the live-collect caller from the session /CommServ probe.
    # result_to_artifact verifies it against the customer's DECLARED csGUID (a
    # single stable namespace) — this REPLACED the cross-namespace CommCell-ID
    # compare (declared licensed vs wire internal, which false-mismatched).
    # Imports leave it None (no session) -> attested.
    wire_commserve_guid: str | None = None
    wire_commserve_guid_source: str | None = None


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

            if extraction.get("format") == "metadata_pairs":
                rows, mp_warnings = self._extract_metadata_pairs(
                    soup, extraction, extraction.get("null_values", []), section_id
                )
                result.warnings.extend(mp_warnings)
                if not rows:
                    result.warnings.append(
                        f"Section '{section_id}' metadata_pairs matched no labels"
                    )
                result.sections[section_id] = rows
                result.section_output_types[section_id] = output_as
                result.section_titles[section_id] = section_title
                continue

            if extraction.get("format") == "computed":
                comp_warnings: list[str] = []
                rows = extract_computed(extraction, result.sections, section_id, comp_warnings)
                result.warnings.extend(comp_warnings)
                result.sections[section_id] = rows
                result.section_output_types[section_id] = output_as
                result.section_titles[section_id] = section_title
                continue

            title_selector = extraction.get("section_title_selector", "")
            title_match = extraction.get("section_title_match", "")
            column_map = extraction.get("column_map", [])
            null_values = extraction.get("null_values", [])
            status_to_severity = extraction.get("status_to_severity", {})

            table = self._find_section_table(
                soup,
                selector=title_selector,
                title_match=title_match,
                section_id=section_id,
                result=result,
            )
            if table is None:
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

    def _find_section_table(
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
            # A declared-but-ABSENT section is not a failure — it is expected for
            # conditionally-present recipes (e.g. License Summary: a file carries
            # the table sections XOR the workload sections, never all). Record a
            # WARNING (like the CSV extractor) so the section is simply omitted,
            # not a fatal extraction error (ADR-0017 D4: empty ≡ absent). Genuine
            # misconfiguration (missing selector/title_match) and a malformed
            # title-without-table stay result.errors.
            result.warnings.append(f"Section '{title_match}' not found")
            return None

        # Walk up to the nearest ancestor that scopes a table (≤5 levels). This
        # bounds the search so a matched title with no table of its own cannot
        # silently borrow a later section's table.
        scope = matched.parent
        for _ in range(5):
            if scope is None:
                break
            if scope.find("table") is not None:
                break
            scope = scope.parent
        if scope is None or scope.find("table") is None:
            result.errors.append(
                f"Section '{title_match}' found but contains no table"
            )
            return None

        # A section title labels the table that FOLLOWS it in document order.
        # This handles both the tightly-wrapped export layout
        # (<div class="reportstabletitle">…</div><table>) and a sibling-heading
        # layout (<h2>…</h2><table>). Bounded to the scope so the title never
        # reaches past its own section into a later one; in the common
        # one-table-per-wrapper case this is the same table the scope holds.
        following = matched.find_next("table")
        if following is not None and following in scope.find_all("table"):
            return following
        return scope.find("table")

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

        # Resolve column_map entries against actual headers (shared coalesce-aware
        # resolver, identical to the CSV extractor — ADR-0016 slice 1).
        resolved = resolve_columns(
            column_map, header_map,
            section_id=section_title_match, warnings=warnings,
        )

        # Extract data rows.
        result_rows: list[dict[str, Any]] = []
        for row in data_rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            row_dict = extract_row(
                cell_texts, resolved, null_values, section_title_match, warnings
            )
            if row_dict:
                result_rows.append(row_dict)

        return result_rows, warnings

    # ------------------------------------------------------------------
    # metadata_pairs (ADR-0016 slice 5)
    # ------------------------------------------------------------------

    def _extract_metadata_pairs(
        self,
        soup: BeautifulSoup,
        extraction: dict,
        null_values: list[str],
        section_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        label_map = extraction.get("label_map", [])

        # Scattered "label: value" lines anywhere in the document text. First
        # occurrence wins (deterministic); exact-case label, trim only.
        pairs: dict[str, str] = {}
        for line in soup.get_text("\n", strip=True).splitlines():
            pv = split_label_value(line.strip())
            if pv is not None:
                pairs.setdefault(pv[0], pv[1])

        row = extract_metadata_pairs(
            pairs, label_map, section_id=section_id,
            null_values=null_values, warnings=warnings,
        )
        return ([row] if row else []), warnings
