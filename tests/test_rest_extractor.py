"""
Tests for RESTExtractor, CommvaultSession, and the generic collect route.
"""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

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


def _seed_subject(db, subject_id="test_subject", sections=None, source_type="rest"):
    """Seed a subject with one or more REST sections.

    sections: list of (section_id_suffix, title, instructions_dict). If None,
    a single default section with report_id "318" / dataset_name "DS1" is
    inserted.
    """
    if sections is None:
        sections = [(
            "section1",
            "My Section",
            {"report_id": "318", "dataset_name": "DS1", "fields": ["col1"]},
        )]
    db.execute(
        "INSERT INTO subjects (subject_id, version, title, category, category_label)"
        " VALUES (?, 1, 'Test Subject', 'operations', 'Operations')",
        (subject_id,),
    )
    db.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type)"
        " VALUES (?, 1, ?)",
        (subject_id, source_type),
    )
    source_id = db.execute(
        "SELECT id FROM subject_sources WHERE subject_id = ?", (subject_id,)
    ).fetchone()["id"]
    for index, (suffix, title, instructions) in enumerate(sections):
        section_id = f"{subject_id}.{suffix}"
        db.execute(
            "INSERT INTO subject_sections"
            " (subject_id, subject_version, section_id, title, section_type, sort_order)"
            " VALUES (?, 1, ?, ?, 'table', ?)",
            (subject_id, section_id, title, index),
        )
        db.execute(
            "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
            " VALUES (?, ?, ?)",
            (source_id, section_id, json.dumps(instructions)),
        )
    db.commit()
    return source_id


def _mock_session(report_payload=None, fetch_rows=None):
    """Return a MagicMock CommvaultSession with get_report/fetch_dataset wired up.

    The catalog-driven extractor uses only get_report + fetch_dataset
    (GET-only protocol per ADR 0003).
    """
    if report_payload is None:
        report_payload = {
            "components": [
                {
                    "type": "table",
                    "title": "Table One",
                    "dataSet": {"dataSetName": "DS1", "dataSetGuid": "guid-1"},
                },
                {
                    "type": "table",
                    "title": "Table Two",
                    "dataSet": {"dataSetName": "DS2", "dataSetGuid": "guid-2"},
                },
            ]
        }
    session = MagicMock()
    session.get_report.return_value = report_payload
    session.fetch_dataset.return_value = fetch_rows if fetch_rows is not None else []
    return session


# ── CommvaultSession tests ─────────────────────────────────────────────────────

def test_fetch_dataset_direct_get_when_no_cache_id():
    """Without a cache_id, fetch_dataset does a direct GET — the lab CommCell
    auto-generates a cacheId in the response body and we don't need it.
    """
    session = CommvaultSession("http://host", "tok")
    assert session._cache_id is None

    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"col1": "a"}]
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "get", return_value=mock_resp) as mock_get:
        rows = session.fetch_dataset("guid-xyz", limit=100)
    assert rows == [{"col1": "a"}]
    # The cacheId param must NOT be in the request when no cache_id is set.
    _, kwargs = mock_get.call_args
    params = kwargs.get("params") or {}
    assert "cacheId" not in params


def test_fetch_dataset_includes_cache_id_when_set():
    """When a cache_id is stored or passed, fetch_dataset includes it as a param."""
    session = CommvaultSession("http://host", "tok")
    session._cache_id = "C1"

    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"col1": "a"}]
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "get", return_value=mock_resp) as mock_get:
        session.fetch_dataset("guid-xyz", limit=100)
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["cacheId"] == "C1"


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


def test_fetch_dataset_terminates_on_totalRecordCount():
    """Pagination terminates when offset >= totalRecordCount (lab response key)."""
    session = CommvaultSession("http://host", "tok")
    # First page: 2 rows, totalRecordCount = 2 — should stop after first page.
    page = {"records": [{"col1": "a"}, {"col1": "b"}], "totalRecordCount": 2}
    mock_resp = MagicMock()
    mock_resp.json.return_value = page
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "get", return_value=mock_resp) as mock_get:
        rows = session.fetch_dataset("guid-xyz")
    assert rows == [{"col1": "a"}, {"col1": "b"}]
    # Only one HTTP call — pagination terminated on totalRecordCount.
    assert mock_get.call_count == 1


def test_get_report_returns_parsed_json():
    session = CommvaultSession("http://host", "tok")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"reportId": 318, "content": "{}"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "get", return_value=mock_resp) as mock_get:
        result = session.get_report("318")
    assert result == {"reportId": 318, "content": "{}"}
    mock_get.assert_called_once()


def test_get_report_raises_on_non_dict_response():
    session = CommvaultSession("http://host", "tok")
    mock_resp = MagicMock()
    mock_resp.json.return_value = ["not", "a", "dict"]
    mock_resp.raise_for_status = MagicMock()
    with patch.object(session._http, "get", return_value=mock_resp):
        with pytest.raises(CommvaultSessionError, match="expected JSON object"):
            session.get_report("318")


# ── RESTExtractor tests ────────────────────────────────────────────────────────

def test_extract_no_instructions_returns_error(db):
    session = _mock_session()
    extractor = RESTExtractor(db, session, customer_id="c1", project_id="p1")
    result = extractor.extract("no_such_subject", version=1)
    assert result.errors
    assert "No REST extraction instructions" in result.errors[0]
    session.get_report.assert_not_called()


def test_extract_calls_get_report_then_fetch(db):
    """GET-only protocol: one get_report + one fetch_dataset per section."""
    _seed_subject(db, "alpha")
    session = _mock_session(fetch_rows=[{"col1": "val1"}, {"col1": "val2"}])
    extractor = RESTExtractor(db, session, customer_id="c1", project_id="p1")
    result = extractor.extract("alpha", version=1)
    assert not result.errors
    assert "alpha.section1" in result.sections
    assert len(result.sections["alpha.section1"]) == 2

    session.get_report.assert_called_once_with("318")
    session.fetch_dataset.assert_called_once_with(
        "guid-1",
        fields=["col1"],
        orderby=None,
        limit=None,
        parameters=None,
    )


def test_extract_uses_dataset_name_resolution_not_hint(db):
    """The stored dataset_guid is a hint; the live definition wins."""
    _seed_subject(
        db,
        "beta",
        sections=[(
            "section1",
            "Beta",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "dataset_guid": "stale-hint-guid",  # should be ignored
                "fields": ["x"],
            },
        )],
    )
    session = _mock_session(fetch_rows=[])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("beta", version=1)
    assert not result.errors
    # Resolved from the live definition, not the stored hint
    args, kwargs = session.fetch_dataset.call_args
    assert args[0] == "guid-1"


def test_extract_falls_back_to_hint_when_name_not_in_definition(db):
    """If the live definition lacks the dataset_name, fall back to hint with a warning."""
    _seed_subject(
        db,
        "gamma",
        sections=[(
            "section1",
            "Gamma",
            {
                "report_id": "318",
                "dataset_name": "NotInDefinition",
                "dataset_guid": "hint-guid",
                "fields": ["x"],
            },
        )],
    )
    session = _mock_session(fetch_rows=[{"x": "v"}])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("gamma", version=1)
    assert not result.errors
    assert any("not found in live report definition" in w for w in result.warnings)
    args, _ = session.fetch_dataset.call_args
    assert args[0] == "hint-guid"


def test_extract_errors_when_name_missing_and_no_hint(db):
    _seed_subject(
        db,
        "delta",
        sections=[(
            "section1",
            "Delta",
            {"report_id": "318", "dataset_name": "UnknownDataset", "fields": ["x"]},
        )],
    )
    session = _mock_session(fetch_rows=[])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("delta", version=1)
    assert result.errors
    assert "could not resolve dataset_guid" in result.errors[0]


def test_extract_same_report_id_check_fails_on_mismatch(db):
    _seed_subject(
        db,
        "epsilon",
        sections=[
            ("section1", "S1", {"report_id": "318", "dataset_name": "DS1"}),
            ("section2", "S2", {"report_id": "999", "dataset_name": "DS2"}),
        ],
    )
    session = _mock_session()
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("epsilon", version=1)
    assert result.errors
    assert "must share the same report_id" in result.errors[0]
    assert "318" in result.errors[0] and "999" in result.errors[0]
    session.get_report.assert_not_called()


def test_extract_missing_report_id_returns_error(db):
    _seed_subject(
        db,
        "zeta",
        sections=[(
            "section1",
            "Zeta",
            {"dataset_name": "DS1", "fields": ["x"]},  # no report_id
        )],
    )
    session = _mock_session()
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("zeta", version=1)
    assert result.errors
    assert "missing report_id" in result.errors[0]


def test_extract_get_report_failure_returns_error(db):
    _seed_subject(db, "theta")
    session = _mock_session()
    session.get_report.side_effect = RuntimeError("network down")
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("theta", version=1)
    assert result.errors
    assert "get_report(318) failed" in result.errors[0]


def test_extract_fail_whole_on_fetch_error(db):
    """First section's fetch error aborts the whole collection (no partial artifact)."""
    _seed_subject(
        db,
        "iota",
        sections=[
            ("section1", "S1", {"report_id": "318", "dataset_name": "DS1"}),
            ("section2", "S2", {"report_id": "318", "dataset_name": "DS2"}),
        ],
    )
    session = _mock_session()
    session.fetch_dataset.side_effect = RuntimeError("boom")
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("iota", version=1)
    assert result.errors
    # Second section is never attempted: fetch_dataset called exactly once
    assert session.fetch_dataset.call_count == 1
    assert "iota.section1" not in result.sections
    assert "iota.section2" not in result.sections


def test_extract_output_as_card_keeps_first_row_only(db):
    _seed_subject(
        db,
        "kappa",
        sections=[(
            "section1",
            "Kappa",
            {"report_id": "318", "dataset_name": "DS1", "output_as": "card"},
        )],
    )
    session = _mock_session(
        fetch_rows=[{"k": "v1"}, {"k": "v2"}, {"k": "v3"}],
    )
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("kappa", version=1)
    assert not result.errors
    assert result.section_output_types["kappa.section1"] == "card"
    assert result.sections["kappa.section1"] == [{"k": "v1"}]


def test_extract_timestamp_conversion(db):
    _seed_subject(
        db,
        "lambda_",
        sections=[(
            "section1",
            "L",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "timestamp_fields": ["ts"],
                "timestamp_format": "unix_seconds",
            },
        )],
    )
    session = _mock_session(fetch_rows=[{"ts": 1000000000}])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("lambda_", version=1)
    assert not result.errors
    rows = result.sections["lambda_.section1"]
    assert "2001-09-09" in rows[0]["ts"]


def test_extract_multi_section_reuses_name_to_guid_map(db):
    """One get_report per subject; the name→guid map is reused across sections."""
    _seed_subject(
        db,
        "mu",
        sections=[
            ("section1", "S1", {"report_id": "318", "dataset_name": "DS1"}),
            ("section2", "S2", {"report_id": "318", "dataset_name": "DS2"}),
        ],
    )
    session = _mock_session(fetch_rows=[{"v": 1}])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("mu", version=1)
    assert not result.errors
    assert session.get_report.call_count == 1
    assert session.fetch_dataset.call_count == 2
    guids = [call.args[0] for call in session.fetch_dataset.call_args_list]
    assert guids == ["guid-1", "guid-2"]


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


# ── column_map + status_to_severity + HTML stripping (findings shape) ────────

def test_extract_applies_column_map_to_findings_rows(db):
    _seed_subject(
        db,
        "alpha",
        sections=[(
            "section1",
            "Findings",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "column_map": [
                    {"source": "Parameter", "canonical": "parameter", "type": "string"},
                    {"source": "Status", "canonical": "status", "type": "string"},
                    {"source": "Remarks", "canonical": "remarks", "type": "string"},
                ],
                "output_as": "findings",
            },
        )],
    )
    session = _mock_session(fetch_rows=[
        {"Parameter": "Two-factor auth", "Status": "1_Good",
         "Remarks": "Enabled.", "sys_rowid": 1, "Data Source": "cs01"},
    ])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("alpha", version=1)
    assert not result.errors
    rows = result.sections["alpha.section1"]
    assert rows == [{
        "parameter": "Two-factor auth",
        "status": "1_Good",
        "remarks": "Enabled.",
    }]
    # Non-mapped keys (sys_rowid, Data Source) are dropped.


def test_extract_applies_status_to_severity_for_findings(db):
    _seed_subject(
        db,
        "beta",
        sections=[(
            "section1",
            "Findings",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "column_map": [
                    {"source": "Parameter", "canonical": "parameter", "type": "string"},
                    {"source": "Status", "canonical": "status", "type": "string"},
                ],
                "status_to_severity": {
                    "1_Good": "good",
                    "2_Info": "info",
                    "3_Warning": "warning",
                    "4_Critical": "critical",
                },
                "output_as": "findings",
            },
        )],
    )
    session = _mock_session(fetch_rows=[
        {"Parameter": "A", "Status": "1_Good"},
        {"Parameter": "B", "Status": "4_Critical"},
        {"Parameter": "C", "Status": "unknown_value"},
    ])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("beta", version=1)
    assert not result.errors
    rows = result.sections["beta.section1"]
    assert [r["severity"] for r in rows] == ["good", "critical", "info"]


def test_extract_strips_html_from_findings_rows(db):
    _seed_subject(
        db,
        "gamma",
        sections=[(
            "section1",
            "Findings",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "column_map": [
                    {"source": "Parameter", "canonical": "parameter", "type": "string"},
                    {"source": "Remarks", "canonical": "remarks", "type": "string"},
                    {"source": "Action", "canonical": "action", "type": "string"},
                ],
                "output_as": "findings",
            },
        )],
    )
    session = _mock_session(fetch_rows=[{
        "Parameter": "Two-factor auth",
        "Remarks": "Disabled<br>Commvault recommends you enable this feature",
        "Action": '<a href="https://example.com/2fa" target="_blank">How to enable 2FA</a>',
    }])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("gamma", version=1)
    assert not result.errors
    row = result.sections["gamma.section1"][0]
    # parameter has no HTML — unchanged
    assert row["parameter"] == "Two-factor auth"
    # Remarks: <br> becomes a space
    assert row["remarks"] == "Disabled Commvault recommends you enable this feature"
    # Action: link text extracted, href dropped (the workspace renders text only)
    assert row["action"] == "How to enable 2FA"


def test_extract_does_not_strip_html_for_table_output(db):
    """HTML stripping is gated on output_as == 'findings'. Table output keeps raw."""
    _seed_subject(
        db,
        "delta",
        sections=[(
            "section1",
            "Raw table",
            {
                "report_id": "318",
                "dataset_name": "DS1",
                "output_as": "table",
            },
        )],
    )
    session = _mock_session(fetch_rows=[{"col": "<b>bold</b> text"}])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("delta", version=1)
    assert not result.errors
    assert result.sections["delta.section1"] == [{"col": "<b>bold</b> text"}]


def test_extract_no_column_map_preserves_raw_keys(db):
    """Without column_map, rows pass through with original keys (existing behavior)."""
    _seed_subject(db, "epsilon")  # default instructions, no column_map
    session = _mock_session(fetch_rows=[{"Parameter": "X", "Status": "1_Good"}])
    extractor = RESTExtractor(db, session, "c1", "p1")
    result = extractor.extract("epsilon", version=1)
    assert not result.errors
    # Default seeded instructions: output_as defaults to "table", no column_map.
    # Raw keys preserved.
    assert result.sections["epsilon.section1"] == [{"Parameter": "X", "Status": "1_Good"}]
