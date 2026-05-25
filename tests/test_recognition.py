"""
Tests for RecognitionEngine, dispatcher (extract_file), and the generic
import route POST /quick-hc/import.

HTML and CSV are built inline — no files from data/imports/ are read.
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.extractors.dispatcher import DispatchResult, extract_file
from cvhealthcheck.extractors.recognition import RecognitionEngine
import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.web.app import create_app


# ---------------------------------------------------------------------------
# HTML / CSV builders
# ---------------------------------------------------------------------------

# All 6 SA section titles that match the DB extraction instructions (migration 0003)
_SA_SECTION_TITLES = [
    "Access Security",
    "Auditing",
    "Platform Security",
    "Company and Owners Security",
    "Capabilities",
    "Hardening",
]


def build_full_sa_html() -> str:
    """
    Security Assessment HTML that satisfies BOTH recognition hints and
    extraction (all 6 sections present with correct table structure).

    Recognition hints satisfied:
      title_contains: "Security Assessment"
      has_selector:   ".panel-table-title"
      grid_present:   true  (div.react-grid-layout present)
    """
    sections_html = ""
    for title in _SA_SECTION_TITLES:
        sections_html += (
            '<div class="exportTable">'
            f'<div class="panel-table-title">{title}</div>'
            "<table>"
            "<thead><tr>"
            "<th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th>"
            "</tr></thead>"
            "<tbody>"
            "<tr><td>Test param</td><td>Good</td><td>OK</td><td></td></tr>"
            "</tbody>"
            "</table>"
            "</div>"
        )
    return (
        '<!DOCTYPE html><html><head><title>Security Assessment</title></head>'
        f'<body><div class="react-grid-layout">{sections_html}</div></body></html>'
    )


def build_ls_recognition_html() -> str:
    """
    License Summary HTML that satisfies all 4 recognition hints:
      title_contains:       "License summary"
      has_selector:         ".reportstabletitle"
      table_count:          2
      first_table_headers:  ["License","Available Total","Used"]
    """
    return (
        '<!DOCTYPE html><html><head><title>License summary</title></head>'
        '<body>'
        '<div class="reportstabletitle">Other Licenses</div>'
        '<table><thead><tr>'
        '<th>License</th><th>Available Total</th><th>Used</th>'
        '</tr></thead><tbody></tbody></table>'
        '<div class="reportstabletitle">Agent and Feature Licenses</div>'
        '<table><thead><tr><th>License</th></tr></thead><tbody></tbody></table>'
        '</body></html>'
    )


def build_growth_and_trends_csv() -> str:
    """
    Growth and Trends CSV that matches client_growth recognition hints:
      first_line_contains: "Growth and Trends"
      section_label:       "Clients Count"
    """
    return (
        "Growth and Trends\n"
        "Generated on: 2026-05-24\n"
        "\n"
        "Clients Count\n"
        "MonthStart,None_Total,None_Removed,None_Added\n"
        "2026-01-01,150,5,10\n"
    )


def build_unknown_html() -> str:
    return (
        "<html><head><title>Unknown Report Type</title></head>"
        "<body><p>No recognizable content.</p></body></html>"
    )


def build_charts_only_html() -> str:
    """Growth and Trends HTML — matches client_growth/capacity_license hints (charts_only)."""
    return (
        '<!DOCTYPE html><html><head><title>Growth and Trends</title></head>'
        '<body><div class="react-grid-layout"><p>chart</p></div></body></html>'
    )


def build_simple_ls_csv() -> str:
    """Minimal license_summary CSV for dispatcher test with explicit subject_id."""
    return (
        "License summary\n"
        "\n"
        "Other Licenses\n"
        "License,Available Total,Used\n"
        "Lic A,10 TB,4 clients\n"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def recog_db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests 1–5: RecognitionEngine
# ---------------------------------------------------------------------------

def test_recognize_security_assessment_html(recog_db: sqlite3.Connection, tmp_path: Path) -> None:
    f = tmp_path / "report.html"
    f.write_text(build_full_sa_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    assert result.subject_id == "security_assessment"
    assert result.version == 1
    assert result.source_type == "html"
    assert result.extractable is True


def test_recognize_license_summary_html(recog_db: sqlite3.Connection, tmp_path: Path) -> None:
    f = tmp_path / "report.html"
    f.write_text(build_ls_recognition_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    assert result.subject_id == "license_summary"
    assert result.source_type == "html"


def test_recognize_growth_and_trends_csv(recog_db: sqlite3.Connection, tmp_path: Path) -> None:
    f = tmp_path / "export.csv"
    f.write_text(build_growth_and_trends_csv(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    # client_growth wins: score 2 (first_line_contains + section_label)
    # capacity_license only scores 1 (first_line_contains; section_index excluded)
    assert result.subject_id == "client_growth"
    assert result.source_type == "csv"


def test_recognize_unknown_file(recog_db: sqlite3.Connection, tmp_path: Path) -> None:
    f = tmp_path / "report.html"
    f.write_text(build_unknown_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is None


def test_recognize_charts_only(recog_db: sqlite3.Connection, tmp_path: Path) -> None:
    f = tmp_path / "growth.html"
    f.write_text(build_charts_only_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    assert result.extractable is False
    assert result.non_extractable_reason == "charts_only"


# ---------------------------------------------------------------------------
# Tests 6–9: dispatcher (extract_file)
# ---------------------------------------------------------------------------

def test_dispatcher_recognized_and_extracted(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "report.html"
    f.write_text(build_full_sa_html(), encoding="utf-8")

    result = extract_file(f, recog_db)

    assert result.recognized is True
    assert result.extractable is True
    assert isinstance(result.artifact, CanonicalArtifact)
    assert result.artifact.artifact_type == "security_assessment"


def test_dispatcher_not_recognized(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "report.html"
    f.write_text(build_unknown_html(), encoding="utf-8")

    result = extract_file(f, recog_db)

    assert result.recognized is False
    assert result.artifact is None
    assert result.subject_id is None


def test_dispatcher_not_extractable(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "growth.html"
    f.write_text(build_charts_only_html(), encoding="utf-8")

    result = extract_file(f, recog_db)

    assert result.recognized is True
    assert result.extractable is False
    assert result.artifact is None
    assert result.non_extractable_reason == "charts_only"


def test_dispatcher_with_explicit_subject_id(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "license.csv"
    f.write_text(build_simple_ls_csv(), encoding="utf-8")

    result = extract_file(f, recog_db, subject_id="license_summary")

    assert result.recognized is True
    assert result.subject_id == "license_summary"
    assert result.source_type == "csv"
    assert isinstance(result.artifact, CanonicalArtifact)


# ---------------------------------------------------------------------------
# Tests 10–13: import route POST /quick-hc/import
# ---------------------------------------------------------------------------

@pytest.fixture()
def import_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Yields (test_client, saved_artifacts_list, db_path)."""
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)

    saved: list[Any] = []

    class _FakeArtifactStore:
        def save_artifact(self, artifact: Any) -> Path:
            saved.append(artifact)
            return Path("/tmp/fake.json")

    monkeypatch.setattr(quick_hc_routes, "ArtifactStore", _FakeArtifactStore)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c, saved, migrated_db_path


def test_import_route_direct_save(import_client: Any) -> None:
    client, saved, _db = import_client
    html = build_full_sa_html().encode("utf-8")

    response = client.post(
        "/quick-hc/import",
        data={"file": (io.BytesIO(html), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(saved) == 1
    assert isinstance(saved[0], CanonicalArtifact)
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body


def test_import_route_staged(import_client: Any) -> None:
    client, saved, db_path = import_client
    html = build_full_sa_html().encode("utf-8")

    response = client.post(
        "/quick-hc/import?stage=1",
        data={"file": (io.BytesIO(html), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert saved == []  # ArtifactStore.save_artifact NOT called

    body = response.get_data(as_text=True)
    assert "staging" in body.lower()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM staged_artifacts ORDER BY created_at DESC LIMIT 1"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


def test_import_route_unrecognized(import_client: Any) -> None:
    client, saved, db_path = import_client
    html = build_unknown_html().encode("utf-8")

    response = client.post(
        "/quick-hc/import",
        data={"file": (io.BytesIO(html), "unknown.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert saved == []

    body = response.get_data(as_text=True)
    assert "not recognised" in body or "not recognized" in body.lower()

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM staged_artifacts").fetchone()[0]
    conn.close()
    assert count == 0


def test_import_route_not_extractable(import_client: Any) -> None:
    client, saved, _db = import_client
    html = build_charts_only_html().encode("utf-8")

    response = client.post(
        "/quick-hc/import",
        data={"file": (io.BytesIO(html), "growth.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert saved == []

    body = response.get_data(as_text=True)
    assert "not extractable" in body.lower() or "charts_only" in body
