"""
Tests for RESTExtractor, CommvaultSession, and the generic collect route.
"""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.rest import RESTExtractor, _convert_timestamp
from cvhealthcheck.reportsplus.session import CommvaultSession, CommvaultSessionError


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    return conn


def _seed_subject(db, subject_id="test_subject", source_type="rest", instructions=None):
    db.execute(
        "INSERT INTO subjects (subject_id, version, title, category, category_label)"
        " VALUES (?, 1, 'Test Subject', 'operations', 'Operations')",
        (subject_id,),
    )
    db.execute(
        "INSERT INTO subject_sections (subject_id, subject_version, section_id, title, section_type)"
        " VALUES (?, 1, ?, 'My Section', 'table')",
        (subject_id, f"{subject_id}.section1"),
    )
    db.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type)"
        " VALUES (?, 1, ?)",
        (subject_id, source_type),
    )
    source_id = db.execute(
        "SELECT id FROM subject_sources WHERE subject_id = ?", (subject_id,)
    ).fetchone()["id"]
    instr = instructions or {"dataset_guid": "abc-123", "fields": ["col1", "col2"]}
    db.execute(
        "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
        " VALUES (?, ?, ?)",
        (source_id, f"{subject_id}.section1", json.dumps(instr)),
    )
    db.commit()
    return source_id


# ── CommvaultSession tests ─────────────────────────────────────────────────────

def test_init_report_stores_cache_id():
    session = CommvaultSession("http://host", "tok")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"cacheId": "CACHE-001"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "post", return_value=mock_resp) as mock_post:
        result = session.init_report({"reportId": 1})
    assert result == "CACHE-001"
    assert session._cache_id == "CACHE-001"
    mock_post.assert_called_once()


def test_init_report_raises_when_no_cache_id():
    session = CommvaultSession("http://host", "tok")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"someOtherKey": "value"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "post", return_value=mock_resp):
        with pytest.raises(CommvaultSessionError, match="no cache_id key"):
            session.init_report({"reportId": 1})


def test_fetch_dataset_requires_cache_id():
    session = CommvaultSession("http://host", "tok")
    with pytest.raises(CommvaultSessionError, match="cache_id required"):
        session.fetch_dataset("guid-123")


def test_fetch_dataset_paginates():
    session = CommvaultSession("http://host", "tok")
    session._cache_id = "C1"

    page1 = [{"col1": "a"}, {"col1": "b"}]
    page2 = []
    responses = [
        MagicMock(json=MagicMock(return_value=page1), raise_for_status=MagicMock()),
        MagicMock(json=MagicMock(return_value=page2), raise_for_status=MagicMock()),
    ]
    with patch.object(session._http, "get", side_effect=responses):
        rows = session.fetch_dataset("guid-xyz", limit=100)
    assert rows == page1


# ── RESTExtractor tests ────────────────────────────────────────────────────────

def test_extract_no_instructions_returns_error(db):
    mock_session = MagicMock()
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("no_such_subject", version=1)
    assert result.errors
    assert "No REST extraction instructions" in result.errors[0]


def test_extract_calls_fetch_dataset(db):
    _seed_subject(db, "alpha", instructions={"dataset_guid": "d-guid", "fields": ["x"]})
    mock_session = MagicMock()
    mock_session.fetch_dataset.return_value = [{"x": "val1"}, {"x": "val2"}]
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("alpha", version=1)
    assert not result.errors
    assert "alpha.section1" in result.sections
    assert len(result.sections["alpha.section1"]) == 2
    mock_session.fetch_dataset.assert_called_once_with(
        "d-guid", fields=["x"], orderby=None, limit=None, parameters=None
    )


def test_extract_with_report_definition_calls_init_report(db):
    _seed_subject(db, "beta", instructions={"dataset_guid": "d-guid"})
    mock_session = MagicMock()
    mock_session.fetch_dataset.return_value = []
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("beta", version=1, report_definition={"reportId": 99})
    mock_session.init_report.assert_called_once_with({"reportId": 99})


def test_extract_init_report_failure_returns_error(db):
    _seed_subject(db, "gamma", instructions={"dataset_guid": "d-guid"})
    mock_session = MagicMock()
    mock_session.init_report.side_effect = RuntimeError("init failed")
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("gamma", version=1, report_definition={"reportId": 1})
    assert result.errors
    assert "init_report failed" in result.errors[0]


def test_extract_fetch_failure_skips_section(db):
    _seed_subject(db, "delta", instructions={"dataset_guid": "d-guid"})
    mock_session = MagicMock()
    mock_session.fetch_dataset.side_effect = RuntimeError("network error")
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("delta", version=1)
    assert result.errors
    assert "delta.section1" not in result.sections


def test_extract_timestamp_conversion(db):
    _seed_subject(
        db, "epsilon",
        instructions={
            "dataset_guid": "d-guid",
            "timestamp_fields": ["ts"],
            "timestamp_format": "unix_seconds",
        },
    )
    mock_session = MagicMock()
    mock_session.fetch_dataset.return_value = [{"ts": 1000000000}]
    extractor = RESTExtractor(db, mock_session)
    result = extractor.extract("epsilon", version=1)
    assert not result.errors
    rows = result.sections["epsilon.section1"]
    assert "2001-09-09" in rows[0]["ts"]


# ── _convert_timestamp tests ───────────────────────────────────────────────────

def test_convert_timestamp_unix_seconds():
    result = _convert_timestamp(0, "unix_seconds")
    assert "1970-01-01" in result


def test_convert_timestamp_unix_ms():
    result = _convert_timestamp(1000, "unix_ms")
    assert "1970-01-01" in result


def test_convert_timestamp_unknown_format_passthrough():
    assert _convert_timestamp("raw", "unknown") == "raw"


def test_convert_timestamp_none():
    assert _convert_timestamp(None, "unix_seconds") is None
