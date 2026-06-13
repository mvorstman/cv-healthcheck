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


def build_ls_workload_heavy_html() -> str:
    """A real-shaped workload-heavy LS export: MORE THAN 2 tables, and the FIRST
    table's headers carry unit suffixes ("Available Total (TB)"). These are the two
    conditions the old recognition (table_count:2 + first_table_headers exact
    subset) rejected before extraction — the direct cause of the live HTML failure.
    """
    titles = ["Capacity Licenses", "Virtualization Licenses", "Other Licenses"]
    blocks = ""
    for t in titles:
        blocks += (
            f'<div class="reportstabletitle">{t}</div>'
            "<table><thead><tr>"
            "<th>License</th><th>Available Total (TB)</th><th>Used (TB)</th><th>Summary</th>"
            "</tr></thead><tbody></tbody></table>"
        )
    return (
        '<!DOCTYPE html><html><head><title>License summary</title></head>'
        f"<body>{blocks}</body></html>"
    )


def build_ls_h2_title_html() -> str:
    """LS export whose section title is a plain <h2> heading (no .reportstabletitle
    wrapper) — the sample-style markup. Recognition must accept the <h2> marker."""
    return (
        '<!DOCTYPE html><html><head><title>License summary</title></head><body>'
        "<h2>Other Licenses - current usage details</h2>"
        "<table><thead><tr>"
        "<th>License</th><th>Available Total</th><th>Used</th>"
        "</tr></thead><tbody></tbody></table>"
        "</body></html>"
    )


def build_ls_titleless_table_html() -> str:
    """A bare [License, Available Total, Used] table with NO title marker of any
    kind (no <title>/<h1>, no .reportstabletitle, no <h2>) — the scoped-out
    classifier-fixture shape. Recognition must NOT fall back to header shape."""
    return (
        "<html><body><table><thead><tr>"
        "<th>License</th><th>Available Total</th><th>Used</th>"
        "</tr></thead><tbody><tr><td>X</td><td>1</td><td>1</td></tr></tbody>"
        "</table></body></html>"
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


# ── ADR-0017 commit 3: broadened LS recognition (workload-heavy + h2) ─────────

def test_recognize_license_summary_workload_heavy_html(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    """The workload-heavy export (>2 tables, unit-suffixed first table) now passes
    recognition — it was rejected before by table_count:2 + first_table_headers."""
    f = tmp_path / "workload.html"
    f.write_text(build_ls_workload_heavy_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    assert result.subject_id == "license_summary"
    assert result.source_type == "html"
    assert result.extractable is True


def test_recognize_license_summary_h2_title_marker(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Recognition accepts an <h2> title marker (not only .reportstabletitle)."""
    f = tmp_path / "h2.html"
    f.write_text(build_ls_h2_title_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is not None
    assert result.subject_id == "license_summary"


def test_titleless_table_not_recognized_as_license_summary(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Recognition does NOT broaden to header shape: a bare
    [License, Available Total, Used] table with no title marker is NOT recognized
    (the scoped-out fixture class stays out — ADR-0017 D3)."""
    f = tmp_path / "titleless.html"
    f.write_text(build_ls_titleless_table_html(), encoding="utf-8")

    result = RecognitionEngine(recog_db).identify(f)

    assert result is None


def test_ls_upload_handler_unregistered_after_route_switch() -> None:
    """After commit 4b the bespoke LS handler is unregistered — LS upload falls
    through to the generic dispatcher."""
    from cvhealthcheck.web.routes.upload_dispatch import UPLOAD_HANDLERS, get_handler

    assert "license_summary" not in UPLOAD_HANDLERS
    assert get_handler("license_summary") is None


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
# ADR-0017 4a: generic dispatcher tolerates absent declared sections + threads
# the declared CommServe name (no single LS file has all declared sections).
# ---------------------------------------------------------------------------

def build_ls_other_agent_only_html() -> str:
    """other + agent tables, NO workload sections (the recipe's 6 workload sections
    are declared-but-absent here)."""
    return (
        '<html><head><title>License summary</title></head><body>'
        '<div class="reportstabletitle">Other Licenses - current usage details</div>'
        "<table><thead><tr><th>License</th><th>Available Total</th><th>Used</th></tr></thead>"
        "<tbody><tr><td>Dedup</td><td>25 TB</td><td>10 TB</td></tr></tbody></table>"
        '<div class="reportstabletitle">Agent and Feature Licenses</div>'
        "<table><thead><tr><th>License</th><th>Permanent Total</th><th>Permanent Used</th>"
        "<th>Term Total</th><th>Term Used</th></tr></thead>"
        "<tbody><tr><td>Database</td><td>25</td><td>8</td><td>5</td><td>2</td></tr></tbody></table>"
        "</body></html>"
    )


def test_extract_file_workload_only_produces_artifact(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "workload.html"
    f.write_text(build_ls_workload_heavy_html(), encoding="utf-8")

    result = extract_file(f, recog_db, subject_id="license_summary")

    # absent other/agent table sections are warnings, NOT fatal — artifact produced
    assert isinstance(result.artifact, CanonicalArtifact)
    assert not result.extraction_errors
    assert any("not found" in w for w in result.extraction_warnings)
    assert any(s.id == "capacity_licenses" for s in result.artifact.sections)


def test_extract_file_other_agent_only_produces_artifact(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "oa.html"
    f.write_text(build_ls_other_agent_only_html(), encoding="utf-8")

    result = extract_file(f, recog_db, subject_id="license_summary")

    # absent workload sections are warnings, NOT fatal — artifact produced
    assert isinstance(result.artifact, CanonicalArtifact)
    assert not result.extraction_errors
    assert any(s.id == "other_licenses" for s in result.artifact.sections)
    assert any("not found" in w for w in result.extraction_warnings)


def test_extract_file_threads_declared_commcell_name(
    recog_db: sqlite3.Connection, tmp_path: Path
) -> None:
    # ADR-0017 D2 top tier: a declared CommServe name reaches result_to_artifact
    # via extract_file → commcell_info shows the DECLARED name, not the placeholder.
    f = tmp_path / "workload.html"
    f.write_text(build_ls_workload_heavy_html(), encoding="utf-8")

    result = extract_file(
        f, recog_db, subject_id="license_summary", declared_commcell_name="DeclaredCS")

    ci = [s for s in result.artifact.sections if s.id == "commcell_info"]
    assert ci, "commcell_info enrichment did not fire on the dispatcher path"
    name = next(it.value for it in ci[0].items if it.id == "commcell_name")
    assert name == "DeclaredCS"


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
