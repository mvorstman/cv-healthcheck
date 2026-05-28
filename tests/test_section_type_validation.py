"""
Tests for catalog section_type validation — the loud-failure path that
catches over-declaration of chart-type sections the runtime cannot honour.

ADR 0004 survey context: the canonical schema declares ChartSection but
no code instantiates it. Two AI-proposed subjects (storage_utilization,
cloud_storage_egress_ingress) and one system subject (client_growth) had
chart-typed catalog rows that silently rendered nothing. This validation
makes the mismatch loud at insert time AND at collection time without
deleting the existing rows.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from cvhealthcheck.db.section_types import (
    SUPPORTED_SECTION_TYPES,
    UnsupportedSectionTypeError,
    validate_section_type,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.extractors.rest import RESTExtractor


# ── validate_section_type unit tests ─────────────────────────────────────────

def test_supported_set_pins_today_runtime():
    """findings/table/metric are produced by the runtime today;
    chart is declared in the schema but not produced anywhere."""
    assert SUPPORTED_SECTION_TYPES == frozenset({"findings", "table", "metric"})


def test_validate_section_type_accepts_findings_table_metric():
    for section_type in ("findings", "table", "metric"):
        validate_section_type(
            section_type, subject_id="x", section_id="x.y"
        )


def test_validate_section_type_rejects_chart_loudly():
    with pytest.raises(UnsupportedSectionTypeError) as exc:
        validate_section_type(
            "chart",
            subject_id="cloud_storage_egress_ingress",
            section_id="cloud_egress.egress_pct_chart",
        )
    msg = str(exc.value)
    assert "cloud_storage_egress_ingress" in msg
    assert "cloud_egress.egress_pct_chart" in msg
    assert "'chart'" in msg
    assert "findings" in msg and "table" in msg and "metric" in msg
    assert "ADR 0004" in msg


# ── create_subject_from_proposal — insert-time enforcement ───────────────────

def _minimal_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY,
            subject_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            category_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL DEFAULT 'ai',
            change_notes TEXT,
            related_subjects TEXT
        );
        CREATE TABLE subject_sections (
            id INTEGER PRIMARY KEY,
            subject_id TEXT NOT NULL,
            subject_version INTEGER NOT NULL DEFAULT 1,
            section_id TEXT NOT NULL,
            title TEXT NOT NULL,
            section_type TEXT NOT NULL DEFAULT 'table',
            default_selected INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE subject_sources (
            id INTEGER PRIMARY KEY,
            subject_id TEXT NOT NULL,
            subject_version INTEGER NOT NULL DEFAULT 1,
            source_type TEXT NOT NULL,
            extractable INTEGER NOT NULL DEFAULT 1,
            non_extractable_reason TEXT,
            recognition_hints TEXT
        );
        CREATE TABLE subject_section_sources (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            section_id TEXT NOT NULL,
            extraction_instructions TEXT
        );
    """)


def test_proposal_with_chart_section_fails_loudly_at_insert():
    """An AI proposal declaring a chart-typed section is rejected
    before any rows are written."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _minimal_schema(db)

    proposal = {
        "subject_id": "new_ai_subject",
        "version": 1,
        "title": "Test Subject",
        "category": "operations",
        "sections": [
            {"section_id": "x.summary", "title": "Summary", "section_type": "metric",
             "default_selected": True, "sort_order": 1},
            {"section_id": "x.health_chart", "title": "Health chart", "section_type": "chart",
             "default_selected": True, "sort_order": 2},
        ],
        "extraction_instructions": {},
    }
    with pytest.raises(UnsupportedSectionTypeError) as exc:
        create_subject_from_proposal(db, proposal)
    assert "x.health_chart" in str(exc.value)

    # Transaction rolled back: no rows persisted.
    rows = db.execute("SELECT * FROM subjects WHERE subject_id='new_ai_subject'").fetchall()
    assert rows == []


def test_proposal_with_only_supported_sections_succeeds():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _minimal_schema(db)

    proposal = {
        "subject_id": "ok_subject",
        "version": 1,
        "title": "OK",
        "category": "operations",
        "sections": [
            {"section_id": "ok.table", "title": "Table", "section_type": "table",
             "default_selected": True, "sort_order": 1},
        ],
        "extraction_instructions": {},
    }
    result = create_subject_from_proposal(db, proposal)
    assert result["subject_id"] == "ok_subject"


# ── REST extractor — collection-time enforcement ─────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _minimal_schema(conn)
    return conn


def _seed_chart_typed_section(db):
    """Bypass the proposal-time validation by raw-SQL-inserting a chart-
    typed section with extraction wiring — simulating a migration or
    direct DB edit that bypassed the proposal flow."""
    db.execute(
        "INSERT INTO subjects (subject_id, version, title, category, category_label)"
        " VALUES ('legacy_chart_subject', 1, 'Legacy', 'storage', 'Storage')"
    )
    db.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type)"
        " VALUES ('legacy_chart_subject', 1, 'rest')"
    )
    source_id = db.execute(
        "SELECT id FROM subject_sources WHERE subject_id='legacy_chart_subject'"
    ).fetchone()["id"]
    db.execute(
        "INSERT INTO subject_sections (subject_id, subject_version, section_id, title,"
        " section_type, sort_order) VALUES (?, 1, ?, ?, 'chart', 1)",
        ("legacy_chart_subject", "legacy.health_chart", "Health chart"),
    )
    db.execute(
        "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
        " VALUES (?, ?, ?)",
        (source_id, "legacy.health_chart",
         '{"report_id":"146","dataset_name":"Health","output_as":"table"}'),
    )
    db.commit()


def test_rest_extract_fails_loudly_on_chart_section(db):
    """Collection-time guard: even if a chart-typed section is in the
    catalog (migration, raw SQL, direct edit), the extractor refuses
    to run and emits a clear error rather than producing a half-shaped
    artifact."""
    _seed_chart_typed_section(db)

    session = MagicMock()
    session.get_report.return_value = {}
    session.fetch_dataset.return_value = []
    extractor = RESTExtractor(db, session, "c", "p")
    result = extractor.extract("legacy_chart_subject", version=1)

    assert result.errors, "expected loud error, got none"
    combined = " ".join(result.errors)
    assert "legacy.health_chart" in combined
    assert "'chart'" in combined
    assert "ADR 0004" in combined
    # No fetch attempted — guard fires before report/dataset GETs
    session.get_report.assert_not_called()
    session.fetch_dataset.assert_not_called()
