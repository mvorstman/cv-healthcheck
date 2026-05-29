"""ADR 0004 phase 2 (2g + 2d) — FixtureExtractor, the seeded _metric_test
subject, conformance on the metric path, and fixture-path sandboxing."""
import json
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import CanonicalArtifact, MetricSection
from cvhealthcheck.extractors.fixture import FixtureError, FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── End-to-end against the seeded migration-0010 subject ──

def test_metric_test_subject_collects_end_to_end(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_metric_test", 1)
    finally:
        conn.close()
    assert not result.errors
    assert result.section_output_types["_metric_test.capacity"] == "metric"

    artifact = result_to_artifact(result, "_metric_test", "Metric Section Test")
    CanonicalArtifact.model_validate(artifact.model_dump())
    sec = next(s for s in artifact.sections if isinstance(s, MetricSection))
    items = {i.id: i for i in sec.items}

    assert sec.render_mode == "metric"
    assert items["used"].value == 35.0
    assert items["purchased"].value == 50.0
    assert items["prev_active"].value is None              # -1 sentinel -> n/a
    assert items["utilisation_pct"].value == pytest.approx(70.0)
    assert items["utilisation_pct"].severity == FindingSeverity.warning
    assert items["utilisation_pct"].verdict_chain[0].reason


# ── Conformance on the metric path (phase 1 mechanism, 2d) ──

def test_metric_conformance_failure_records_section(migrated_db_path: Path, tmp_path: Path, monkeypatch):
    # Point the section at a malformed fixture (missing required fields) by
    # rewriting the seeded fixture path's contents is awkward; instead drive
    # the extractor with a deliberately malformed fixture through a temp file
    # inside the sandbox root.
    from cvhealthcheck.extractors import fixture as fx

    bad = fx.FIXTURE_ROOT / "_tmp_bad_metric.json"
    bad.write_text(json.dumps([{"month": "2024-08"}]), encoding="utf-8")  # missing required fields
    try:
        conn = _conn(migrated_db_path)
        try:
            # Repoint the seeded section's fixture_path at the malformed file.
            conn.execute(
                "UPDATE subject_section_sources SET extraction_instructions = "
                "replace(extraction_instructions, 'data/test_fixtures/metric_test.json', "
                "'data/test_fixtures/_tmp_bad_metric.json') "
                "WHERE section_id = '_metric_test.capacity'"
            )
            conn.commit()
            result = FixtureExtractor(conn).extract("_metric_test", 1)
        finally:
            conn.close()
    finally:
        bad.unlink(missing_ok=True)

    # Section is recorded as a conformance failure, not emitted as data.
    assert "_metric_test.capacity" in result.section_failures
    assert "_metric_test.capacity" not in result.sections
    failure = result.section_failures["_metric_test.capacity"]
    assert failure["reason"] == "missing_required_field"
    assert "used_capacity" in failure["delta"]["missing"]


# ── Fixture-path sandboxing ──

def test_fixture_path_sandbox_rejects_traversal():
    with pytest.raises(FixtureError):
        FixtureExtractor._resolve_fixture_path("data/test_fixtures/../../etc/passwd")


def test_fixture_path_sandbox_rejects_absolute():
    with pytest.raises(FixtureError):
        FixtureExtractor._resolve_fixture_path("/etc/passwd")


def test_fixture_path_inside_root_ok():
    p = FixtureExtractor._resolve_fixture_path("data/test_fixtures/metric_test.json")
    assert p.name == "metric_test.json"


def test_missing_fixture_path_is_error(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        conn.execute(
            "UPDATE subject_section_sources SET extraction_instructions = '{\"output_as\":\"metric\"}' "
            "WHERE section_id = '_metric_test.capacity'"
        )
        conn.commit()
        result = FixtureExtractor(conn).extract("_metric_test", 1)
    finally:
        conn.close()
    assert result.errors
    assert any("fixture" in e.lower() for e in result.errors)
