"""ADR 0004 phase 3 (3g + 3c) — the seeded _chart_test subject collects both a
line and a pie chart from fixtures via FixtureExtractor, and chart sections run
the phase-1 conformance check."""
import json
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.enums import ChartType
from cvhealthcheck.artifacts.models import CanonicalArtifact, ChartSection
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_chart_test_subject_collects_line_and_pie(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_chart_test", 1)
    finally:
        conn.close()
    assert not result.errors
    assert result.section_output_types["_chart_test.trend"] == "chart"
    assert result.section_output_types["_chart_test.status"] == "chart"

    artifact = result_to_artifact(result, "_chart_test", "Chart Section Test")
    CanonicalArtifact.model_validate(artifact.model_dump())
    charts = {s.id: s for s in artifact.sections if isinstance(s, ChartSection)}
    assert len(charts) == 2

    line = charts["_chart_test.trend"]
    assert line.chart_type == ChartType.line
    assert len(line.series) == 2                       # Added + Total
    assert len(line.labels) == 6                       # 6 months
    assert all(len(s.data) == 6 for s in line.series)

    pie = charts["_chart_test.status"]
    assert pie.chart_type == ChartType.pie
    assert len(pie.series) == 1                         # single proportional series
    assert pie.labels == ["Completed", "Completed w/ errors", "Failed", "Running"]
    assert pie.series[0].data == [142.0, 17.0, 9.0, 4.0]


def test_chart_conformance_failure_records_section(migrated_db_path: Path):
    from cvhealthcheck.extractors import fixture as fx

    bad = fx.FIXTURE_ROOT / "_tmp_bad_chart.json"
    bad.write_text(json.dumps([{"month": "2024-08"}]), encoding="utf-8")  # missing added/total
    try:
        conn = _conn(migrated_db_path)
        try:
            conn.execute(
                "UPDATE subject_section_sources SET extraction_instructions = "
                "replace(extraction_instructions, 'data/test_fixtures/chart_test_trend.json', "
                "'data/test_fixtures/_tmp_bad_chart.json') "
                "WHERE section_id = '_chart_test.trend'"
            )
            conn.commit()
            result = FixtureExtractor(conn).extract("_chart_test", 1)
        finally:
            conn.close()
    finally:
        bad.unlink(missing_ok=True)

    # The line section fails conformance; the pie section still collects.
    assert "_chart_test.trend" in result.section_failures
    assert "_chart_test.trend" not in result.sections
    assert result.section_failures["_chart_test.trend"]["reason"] == "missing_required_field"
    assert "_chart_test.status" in result.sections
