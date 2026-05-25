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


# Tests 10-13 (POST /quick-hc/import direct-save, ?stage=1, unrecognized,
# not-extractable) were deleted in session 4 of the unified-upload
# refactor. They exercised behavior specific to the deleted generic
# route (recognition-from-payload without an explicit subject_id in the
# URL), which the unified route /quick-hc/<subject_id>/import doesn't
# replicate. The dispatcher's recognition + extractability mechanics
# remain covered by the unit tests in this file (test_recognize_*,
# test_dispatcher_*) which exercise extract_file directly without
# going through any HTTP route. See docs/refactor_unified_upload_2026-05-31.md
# Section 5 for the original classification.
