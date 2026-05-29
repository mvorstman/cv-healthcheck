"""
Tests for catalog section_type validation — the loud-failure path that
catches a catalog row declaring a section_type the runtime cannot honour.

ADR 0004 grows the runtime-supported set phase by phase: findings/table
(ADR 0003), metric (phase 2), chart (phase 3). Types that are modelled but
not yet produced/rendered (card, multi_section) must still fail loudly so a
catalog row can never silently render nothing. These tests pin chart as now
supported and use `card` (a not-yet-supported type) to exercise the
loud-failure mechanism.
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
    """findings/table/metric/chart are all produced + rendered as of ADR 0004
    phase 3; card / multi_section remain unsupported."""
    assert SUPPORTED_SECTION_TYPES == frozenset({"findings", "table", "metric", "chart"})


def test_validate_section_type_accepts_findings_table_metric_chart():
    for section_type in ("findings", "table", "metric", "chart"):
        validate_section_type(
            section_type, subject_id="x", section_id="x.y"
        )


def test_validate_section_type_rejects_unsupported_loudly():
    # `card` is modelled-but-not-yet-supported — the loud-fail mechanism still
    # guards against silent-render-nothing for types whose phase hasn't landed.
    with pytest.raises(UnsupportedSectionTypeError) as exc:
        validate_section_type(
            "card",
            subject_id="some_subject",
            section_id="some_subject.identity_card",
        )
    msg = str(exc.value)
    assert "some_subject" in msg
    assert "some_subject.identity_card" in msg
    assert "'card'" in msg
    assert "findings" in msg and "table" in msg and "metric" in msg and "chart" in msg


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


def test_proposal_with_unsupported_section_fails_loudly_at_insert():
    """An AI proposal declaring a not-yet-supported section type (card) is
    rejected before any rows are written."""
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
            {"section_id": "x.identity_card", "title": "Identity", "section_type": "card",
             "default_selected": True, "sort_order": 2},
        ],
        "extraction_instructions": {},
    }
    with pytest.raises(UnsupportedSectionTypeError) as exc:
        create_subject_from_proposal(db, proposal)
    assert "x.identity_card" in str(exc.value)

    # Transaction rolled back: no rows persisted.
    rows = db.execute("SELECT * FROM subjects WHERE subject_id='new_ai_subject'").fetchall()
    assert rows == []


def test_proposal_with_chart_section_now_succeeds():
    """ADR 0004 phase 3: chart is now a supported section type, so a proposal
    declaring a chart section inserts cleanly."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _minimal_schema(db)

    proposal = {
        "subject_id": "chart_ai_subject",
        "version": 1,
        "title": "Chart Subject",
        "category": "operations",
        "sections": [
            {"section_id": "c.trend", "title": "Trend", "section_type": "chart",
             "default_selected": True, "sort_order": 1},
        ],
        "extraction_instructions": {},
    }
    result = create_subject_from_proposal(db, proposal)
    assert result["subject_id"] == "chart_ai_subject"


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


def _seed_unsupported_typed_section(db):
    """Bypass the proposal-time validation by raw-SQL-inserting a
    not-yet-supported (card) section with extraction wiring — simulating a
    migration or direct DB edit that bypassed the proposal flow."""
    db.execute(
        "INSERT INTO subjects (subject_id, version, title, category, category_label)"
        " VALUES ('legacy_card_subject', 1, 'Legacy', 'storage', 'Storage')"
    )
    db.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type)"
        " VALUES ('legacy_card_subject', 1, 'rest')"
    )
    source_id = db.execute(
        "SELECT id FROM subject_sources WHERE subject_id='legacy_card_subject'"
    ).fetchone()["id"]
    db.execute(
        "INSERT INTO subject_sections (subject_id, subject_version, section_id, title,"
        " section_type, sort_order) VALUES (?, 1, ?, ?, 'card', 1)",
        ("legacy_card_subject", "legacy.identity_card", "Identity card"),
    )
    db.execute(
        "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
        " VALUES (?, ?, ?)",
        (source_id, "legacy.identity_card",
         '{"report_id":"146","dataset_name":"Health","output_as":"table"}'),
    )
    db.commit()


def test_rest_extract_fails_loudly_on_unsupported_section(db):
    """Collection-time guard: even if a not-yet-supported (card) section is in
    the catalog (migration, raw SQL, direct edit), the extractor refuses to run
    and emits a clear error rather than producing a half-shaped artifact."""
    _seed_unsupported_typed_section(db)

    session = MagicMock()
    session.get_report.return_value = {}
    session.fetch_dataset.return_value = []
    extractor = RESTExtractor(db, session, "c", "p")
    result = extractor.extract("legacy_card_subject", version=1)

    assert result.errors, "expected loud error, got none"
    combined = " ".join(result.errors)
    assert "legacy.identity_card" in combined
    assert "'card'" in combined
    # No fetch attempted — guard fires before report/dataset GETs
    session.get_report.assert_not_called()
    session.fetch_dataset.assert_not_called()
