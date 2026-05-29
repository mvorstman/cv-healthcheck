"""
cvhealthcheck.extractors.fixture
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 2 — collect a subject's data from a static JSON fixture shipped
with the project, instead of a live lab. Used by internal/test subjects (the
metric-section test subject) so the metric pipeline can be browser-verified
without a network dependency.

Mirrors RESTExtractor's role: it loads the subject's per-section
extraction_instructions from the catalog (the ``json`` source), reads rows
from the declared ``fixture_path``, runs the phase-1 conformance check per
section, and carries the metric spec through to result_to_artifact.

Security: ``fixture_path`` is resolved relative to the project root and MUST
resolve inside ``data/test_fixtures/`` — it cannot read arbitrary filesystem
paths. This is enforced in code, not by convention.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from cvhealthcheck.db.section_types import (
    UnsupportedSectionTypeError,
    validate_section_type,
)
from cvhealthcheck.extractors.conformance import check_conformance
from cvhealthcheck.extractors.html import ExtractionResult

logger = logging.getLogger(__name__)

# This file is src/cvhealthcheck/extractors/fixture.py — parents[3] is the
# project root. Fixtures live under data/test_fixtures/ and nowhere else.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = (_PROJECT_ROOT / "data" / "test_fixtures").resolve()


class FixtureError(Exception):
    """A fixture path was unsafe or its contents could not be loaded."""


class FixtureExtractor:
    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self._db = db_conn

    def extract(self, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(subject_id=subject_id, source_type="json")

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No JSON fixture extraction instructions found for {subject_id} v{version}"
            )
            return result

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

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}

            try:
                rows = self._load_fixture(extraction.get("fixture_path"))
            except FixtureError as exc:
                # A bad fixture path/content is a hard error for that section —
                # abort the whole collection rather than write a partial artifact.
                result.errors.append(f"Section '{section_id}': {exc}")
                return result

            # ADR 0004 conformance (phase 1 mechanism), section-grained.
            failure = check_conformance(rows, extraction.get("conformance"))
            if failure is not None:
                result.section_failures[section_id] = failure
                result.section_titles[section_id] = section_title
                continue

            output_as = extraction.get("output_as", "table")
            if output_as == "metric":
                result.section_metric_specs[section_id] = extraction.get("metric", {})
            elif output_as == "chart":
                result.section_chart_specs[section_id] = extraction.get("chart", {})
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
              AND src.source_type     = 'json'
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

    def _load_fixture(self, fixture_path: str | None) -> list[dict[str, Any]]:
        if not fixture_path:
            raise FixtureError("no fixture_path declared")
        target = self._resolve_fixture_path(fixture_path)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FixtureError(f"fixture file not found: {fixture_path}") from exc
        except json.JSONDecodeError as exc:
            raise FixtureError(f"fixture is not valid JSON: {exc}") from exc
        # Accept either a bare list of rows or {"records": [...]}.
        if isinstance(raw, dict):
            raw = raw.get("records", [])
        if not isinstance(raw, list):
            raise FixtureError("fixture must be a JSON array of row objects")
        return [dict(r) for r in raw if isinstance(r, dict)]

    @staticmethod
    def _resolve_fixture_path(fixture_path: str) -> Path:
        """Resolve fixture_path under the project root and reject anything that
        escapes data/test_fixtures/ (no absolute paths, no ../ traversal)."""
        target = (_PROJECT_ROOT / fixture_path).resolve()
        if not target.is_relative_to(FIXTURE_ROOT):
            raise FixtureError(
                f"fixture_path {fixture_path!r} resolves outside data/test_fixtures/"
            )
        return target
