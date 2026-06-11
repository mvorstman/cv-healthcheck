"""
cvhealthcheck.extractors.rest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generic REST extractor driven by extraction instructions stored in the
subject_section_sources table (source_type = 'rest').

Implements the ADR 0003 GET-only protocol: per collection run we GET the
live report definition once, walk it for a name→guid map, and GET each
section's dataset directly. The cacheId acquisition step (POST
reportBuilder.do) is a browser/UI concern and is not used here — the
dataset GET endpoint accepts requests without one.

Instruction keys (canonical form after migration 0006):
  report_id           : str   Commvault report id (e.g. "318") — required
  dataset_name        : str   display name of the dataset within the report —
                              required; the canonical reference
  dataset_guid        : str   optional cache hint; used as fallback only if the
                              live report definition doesn't yield a guid for
                              dataset_name
  fields              : list  Field names to request
  orderby             : str   e.g. "MonthStart Asc"
  limit               : int   Max rows to fetch
  parameters          : dict  Extra query-string params
  timestamp_fields    : list  Fields to convert to ISO strings
  timestamp_format    : str   "unix_seconds" | "unix_ms"
  null_values         : list  Values to coerce to None
  column_map          : list  [{"source": ..., "canonical": ..., "type": ...}, ...]
                              Renames raw response columns to canonical keys.
                              Mirrors the HTML extractor's pattern.
  status_to_severity  : dict  Maps the canonical "status" value to a severity
                              string ("critical"/"warning"/"good"/"info").
                              Applied when output_as == "findings".
  output_as           : str   "table" | "findings" | "card"
"""
from __future__ import annotations

import html as _html_module
import json
import logging
import sqlite3
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from cvhealthcheck.db.rule_overrides import load_section_overrides
from cvhealthcheck.db.rules import (
    load_rules_registry,
    load_subject_row_rules,
    load_subject_section_scope,
)
from cvhealthcheck.db.section_types import (
    UnsupportedSectionTypeError,
    validate_section_type,
)
from cvhealthcheck.extractors.conformance import check_conformance
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.reportsplus.extract_report import (
    discover_dataset_references,
    discover_widgets,
)
from cvhealthcheck.reportsplus.inventory import parse_content_field

logger = logging.getLogger(__name__)


class RESTExtractor:
    def __init__(
        self,
        db_conn: sqlite3.Connection,
        session: Any,
        customer_id: str,
        project_id: str,
    ) -> None:
        self._db = db_conn
        self._session = session
        self._customer_id = customer_id
        self._project_id = project_id

    def extract(self, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id, source_type="rest")
        # Phase 8 step 2: carry the rules registry so result_to_artifact can
        # resolve `ref`-based evaluative rules (catalog read, not evaluation).
        result.rules_registry = load_rules_registry(self._db)
        # ADR 0010: carry the subject's bound row_match rules + section scope so the
        # result_to_artifact compliance pass fires (scoped) on this collection.
        result.section_row_rules = load_subject_row_rules(self._db, subject_id, version)
        result.section_scope = load_subject_section_scope(self._db, subject_id, version)
        # Phase 8 step 3: carry the override layer for the active (customer,
        # project). Resolution into the verdict_chain is at canonicalization.
        result.section_overrides = load_section_overrides(
            self._db, self._customer_id, self._project_id, subject_id, version
        )

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No REST extraction instructions found for {subject_id} v{version}"
            )
            return result

        # Validate each wired section's declared type is runtime-supported.
        # Loud failure for unsupported types (today: only 'chart') rather
        # than silent render-nothing. See cvhealthcheck.db.section_types
        # and ADR 0004.
        for instr in instructions:
            try:
                validate_section_type(
                    instr["section_type"],
                    subject_id=subject_id,
                    section_id=instr["section_id"],
                )
            except UnsupportedSectionTypeError as exc:
                result.errors.append(str(exc))
                return result

        report_id = self._resolve_single_report_id(instructions, result)
        if report_id is None:
            return result

        try:
            report_payload = self._session.get_report(report_id)
        except Exception as exc:
            result.errors.append(f"get_report({report_id}) failed: {exc}")
            return result

        definition = parse_content_field(report_payload)
        name_to_guid = _build_name_to_guid_map(definition)

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}

            rows, warnings, errors = self._fetch_section(
                section_id, extraction, name_to_guid
            )
            result.warnings.extend(warnings)

            if errors:
                result.errors.extend(errors)
                # Fail-whole: abort on first section error so we don't write a
                # half-collected artifact. Subsequent sections are not attempted.
                # NB: this is a hard fetch/transport error — distinct from a
                # conformance failure, which is section-grained (below).
                return result

            output_as = extraction.get("output_as", "table")
            # ADR 0004 phase 4: output_as == "card" now means exactly one thing —
            # "this is a card section" (result_to_artifact emits a CardSection).
            # The "typically one row" selection is the card builder's concern
            # (build_card_section reads the card's row), not a generic row trim
            # here — so the earlier rows[:1] stub was removed to keep the token
            # doing one job.

            # ADR 0004 conformance: validate the collected shape against the
            # section's declared schema (if any). On failure, record a
            # structured failure record for this section and skip emitting its
            # data — sibling sections continue to collect.
            failure = check_conformance(rows, extraction.get("conformance"))
            if failure is not None:
                result.section_failures[section_id] = failure
                result.section_titles[section_id] = section_title
                continue

            # ADR 0004 phase 5: carry the per-section-type three-face spec from
            # the catalog extraction_instructions so result_to_artifact can build
            # the metric/chart/card section (phases 2-4 only did this in the
            # FixtureExtractor; this is the REST path's equivalent wiring).
            if output_as == "metric":
                result.section_metric_specs[section_id] = extraction.get("metric", {})
            elif output_as == "chart":
                result.section_chart_specs[section_id] = extraction.get("chart", {})
            elif output_as == "card":
                result.section_card_specs[section_id] = extraction.get("card", {})
            elif output_as == "table":
                result.section_table_specs[section_id] = extraction.get("table", {})

            result.sections[section_id] = rows
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

    def _resolve_single_report_id(
        self,
        instructions: list[dict[str, Any]],
        result: ExtractionResult,
    ) -> str | None:
        """Return the report_id shared by all REST sections, or None on error.

        All sections of a single subject must reference the same report_id
        because the report definition GET happens once per collection and
        its dataset name→guid map is reused across section fetches.
        Mismatches indicate catalog seeding bugs and are surfaced with the
        offending section_ids.
        """
        by_report: dict[str, list[str]] = {}
        missing: list[str] = []
        for instr in instructions:
            section_id = instr["section_id"]
            report_id = (instr.get("extraction_instructions") or {}).get("report_id")
            if not report_id:
                missing.append(section_id)
                continue
            by_report.setdefault(str(report_id), []).append(section_id)

        if missing:
            result.errors.append(
                "REST sections missing report_id in extraction_instructions: "
                + ", ".join(sorted(missing))
            )
            return None

        if len(by_report) > 1:
            summary = "; ".join(
                f"{rid}: [{', '.join(sorted(ids))}]"
                for rid, ids in sorted(by_report.items())
            )
            result.errors.append(
                "REST sections of a subject must share the same report_id; "
                f"found {summary}"
            )
            return None

        # exactly one report_id
        return next(iter(by_report))

    def _fetch_section(
        self,
        section_id: str,
        instructions: dict[str, Any],
        name_to_guid: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []

        dataset_name = instructions.get("dataset_name")
        hint_guid = instructions.get("dataset_guid")

        dataset_guid: str | None = None
        if dataset_name:
            dataset_guid = name_to_guid.get(dataset_name)
            if dataset_guid is None and hint_guid:
                warnings.append(
                    f"Section '{section_id}': dataset_name '{dataset_name}' "
                    f"not found in live report definition; falling back to "
                    f"stored dataset_guid hint"
                )
                dataset_guid = hint_guid
        else:
            # No dataset_name at all — only the hint is available. This is
            # legitimate for pre-0006 rows that never got dataset_name backfilled,
            # but after the catalog is fully seeded it shouldn't happen.
            dataset_guid = hint_guid

        if not dataset_guid:
            errors.append(
                f"Section '{section_id}': could not resolve dataset_guid "
                f"(dataset_name={dataset_name!r}, hint={hint_guid!r})"
            )
            return [], warnings, errors

        fields: list[str] = instructions.get("fields") or []
        orderby: str | None = instructions.get("orderby")
        limit: int | None = instructions.get("limit")
        parameters: dict[str, str] | None = instructions.get("parameters")

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

        return shape_dataset_rows(raw_rows, instructions), warnings, errors


def shape_dataset_rows(
    raw_rows: list[dict[str, Any]], instructions: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply the declarative row-shaping vocabulary to fetched dataset rows.

    Reads ``timestamp_fields`` / ``timestamp_format``, ``null_values``,
    ``column_map``, and (for ``output_as == "findings"``) HTML-stripping +
    ``status_to_severity`` from ``instructions``. Shared by the ``rest`` and
    ``reportsplus_dataset`` extractors — both speak the same dataset envelope,
    so the shaping vocabulary is implemented once.
    """
    timestamp_fields: list[str] = instructions.get("timestamp_fields") or []
    timestamp_format: str = instructions.get("timestamp_format", "")
    null_values: list[Any] = instructions.get("null_values") or []
    column_map: list[dict[str, Any]] = instructions.get("column_map") or []
    status_to_severity: dict[str, str] = instructions.get("status_to_severity") or {}
    output_as: str = instructions.get("output_as", "table")

    rows = []
    for raw in raw_rows:
        row = dict(raw)
        for field in timestamp_fields:
            if field in row:
                row[field] = _convert_timestamp(row[field], timestamp_format)
        for key, val in list(row.items()):
            if val in null_values:
                row[key] = None
        if column_map:
            row = _apply_column_map(row, column_map)
        if output_as == "findings":
            # Strip HTML from string values so the renderer doesn't show
            # raw <a href>/<br> markup. Mirrors what the HTML extractor
            # produces via BeautifulSoup-extracted cell text.
            for key, val in list(row.items()):
                if isinstance(val, str) and "<" in val:
                    row[key] = _strip_html(val)
            if status_to_severity:
                status_val = str(row.get("status") or "")
                row["severity"] = status_to_severity.get(status_val, "info")
        rows.append(row)

    return rows


class _HTMLTextExtractor(HTMLParser):
    """HTMLParser that collects text content, joining inline-break tags with spaces."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "li"}:
            self._parts.append(" ")

    @property
    def text(self) -> str:
        return " ".join(part for part in self._parts if part)


def _strip_html(value: str) -> str:
    """Return a plain-text rendering of an HTML-containing string.

    Used for findings rows where Status/Remarks/Action arrive from
    Reports Plus with markup the bespoke flow stripped via BeautifulSoup.
    """
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(_html_module.unescape(parser.text).split())


def _apply_column_map(
    row: dict[str, Any], column_map: list[dict[str, Any]]
) -> dict[str, Any]:
    """Project a raw row through a column_map.

    Each entry of the map declares ``source`` (the raw key) and
    ``canonical`` (the target key). The resulting dict has only the
    canonical keys. Sources that aren't present in ``row`` produce a
    missing canonical key (not a None) so downstream code that does
    ``row.get(...)`` keeps working.

    Matches the catalog pattern already used by the HTML extractor.
    """
    mapped: dict[str, Any] = {}
    for entry in column_map:
        source = entry.get("source")
        canonical = entry.get("canonical")
        if not isinstance(source, str) or not isinstance(canonical, str):
            continue
        if source in row:
            mapped[canonical] = row[source]
    return mapped


def _build_name_to_guid_map(definition: Any) -> dict[str, str]:
    """Walk a parsed report definition for dataset_name → dataset_guid pairs.

    Uses the same widget and dataset-reference discovery as `extract_report`
    so we agree on what counts as a dataset reference. Returns the first
    guid seen per name (definitions sometimes mention the same dataset in
    multiple widgets).
    """
    name_to_guid: dict[str, str] = {}
    for source in (discover_widgets(definition), discover_dataset_references(definition)):
        for entry in source:
            name = entry.get("dataset_name")
            guid = entry.get("dataset_guid")
            if name and guid and name not in name_to_guid:
                name_to_guid[name] = guid
    return name_to_guid


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
