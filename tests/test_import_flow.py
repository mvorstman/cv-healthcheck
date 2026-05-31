"""
Tests for Fix 1 (source actions wired from db), Fix 2 (subject_id param on
import route), Fix 3 (artifact_to_view and _build_generic_subject).
"""
from __future__ import annotations

import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    FindingsSection,
    Finding,
    MetricSection,
    MetricItem,
    SummaryMetric,
    TableColumn,
    TableSection,
)
from cvhealthcheck.quickhc.canonical_view import artifact_to_view
from cvhealthcheck.quickhc.registry import (
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    get_tiles,
)


_NOW = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)


# ── helpers ──────────────────────────────────────────────────────────────────

def _insert_generic_subject(
    conn: sqlite3.Connection,
    *,
    subject_id: str = "test_report",
    source_types: list[str] | None = None,
) -> None:
    """Insert a minimal non-system subject with the given source types."""
    conn.execute("""
        INSERT OR IGNORE INTO subjects
            (subject_id, version, title, description, category, category_label,
             status, created_by, preferred_source)
        VALUES (?, 1, 'Test Report', 'A test report.', 'operations', 'Operations',
                'active', 'user', 'html')
    """, (subject_id,))
    conn.execute("""
        INSERT OR IGNORE INTO subject_sections
            (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
        VALUES (?, 1, ?, 'Main table', 'table', 1, 1)
    """, (subject_id, f"{subject_id}.main_table"))

    for src_type in (source_types or ["html", "csv"]):
        conn.execute("""
            INSERT OR IGNORE INTO subject_sources
                (subject_id, subject_version, source_type, extractable)
            VALUES (?, 1, ?, 1)
        """, (subject_id, src_type))
    conn.commit()


# ── Fix 1: source actions wired from db source rows ──────────────────────────

def test_tile_has_import_actions_for_html_source(migrated_db_path: Path) -> None:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    try:
        _insert_generic_subject(conn, subject_id="test_html", source_types=["html"])
        tiles = get_tiles(conn)
        tile = next(t for t in tiles if t["id"] == "test_html")
        html_src = next(s for s in tile["sources"] if s["id"] == HTML_IMPORT_SOURCE_ID)
        assert html_src["extractable"] is True
        assert html_src["source_type"] == "html"
    finally:
        conn.close()


def test_tile_has_no_import_actions_for_rest_only_source(migrated_db_path: Path) -> None:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    try:
        _insert_generic_subject(conn, subject_id="test_rest_only", source_types=["rest"])
        tiles = get_tiles(conn)
        tile = next(t for t in tiles if t["id"] == "test_rest_only")
        assert len(tile["sources"]) == 1
        src = tile["sources"][0]
        assert src["id"] == REST_REPORTS_PLUS_SOURCE_ID
        assert src.get("extractable", True) is True
    finally:
        conn.close()


# test_import_route_passes_subject_id was deleted in session 4 of the
# unified-upload refactor. It exercised the deleted POST /quick-hc/import?
# subject_id=X route; the unified POST /quick-hc/<subject_id>/import always
# has subject_id in the URL path (no query-string variant to test). The
# tests in test_unified_upload_route.py cover the equivalent contract
# end-to-end via the new route.

# ── Fix 3: artifact_to_view + _build_generic_subject ─────────────────────────

def test_artifact_to_view_generic() -> None:
    artifact = CanonicalArtifact(
        artifact_type="test_report",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id="test_report", title="Test Report"),
        summary=ArtifactSummary(
            status=ArtifactStatus.good,
            metrics=[SummaryMetric(id="rows", label="Rows", value=5)],
        ),
        sections=[
            TableSection(
                type="table",
                id="main_table",
                title="Main Table",
                columns=[TableColumn(id="name", label="Name"), TableColumn(id="value", label="Value")],
                items=[{"name": "alpha", "value": "1"}, {"name": "beta", "value": "2"}],
            ),
        ],
    )

    view = artifact_to_view(artifact)

    assert view["id"] == "test_report"
    assert view["name"] == "Test Report"
    assert view["state"] == "ok"
    assert "5 rows" in view["subtitle"]
    assert len(view["sections"]) == 1
    sec = view["sections"][0]
    assert sec["id"] == "test_report.main_table"
    assert sec["type"] == "table"
    assert sec["columns"] == ["Name", "Value"]
    assert sec["rows"] == [["alpha", "1"], ["beta", "2"]]


def test_build_generic_subject_with_artifact(migrated_db_path: Path) -> None:
    from cvhealthcheck.quickhc.subject_data_service import _build_generic_subject

    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    try:
        _insert_generic_subject(conn, subject_id="custom_rpt", source_types=["html", "csv"])
        tiles = get_tiles(conn)
        tile = next(t for t in tiles if t["id"] == "custom_rpt")
    finally:
        conn.close()

    artifact = CanonicalArtifact(
        artifact_type="custom_rpt",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id="custom_rpt", title="Custom Report"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=[
            TableSection(
                type="table",
                id="summary",
                title="Summary",
                columns=[TableColumn(id="k", label="Key"), TableColumn(id="v", label="Value")],
                items=[{"k": "Total", "v": "42"}],
            ),
        ],
    )

    result = _build_generic_subject(tile, artifact)

    assert result["state"] == "ok"
    assert result["id"] == "custom_rpt"
    assert len(result["sections"]) == 1
    # Both html and csv sources should have upload actions
    html_src = next((s for s in result["sources"] if s["id"] == HTML_IMPORT_SOURCE_ID), None)
    csv_src = next((s for s in result["sources"] if s["id"] == CSV_IMPORT_SOURCE_ID), None)
    assert html_src is not None and html_src["status"] == "a"
    assert len(html_src["actions"]) == 1
    # Session 3 of the unified-upload refactor: the importUrl is now
    # /quick-hc/<subject_id>/import (path component) instead of
    # /quick-hc/import?subject_id=<id> (query string).
    assert html_src["actions"][0]["importUrl"] == "/quick-hc/custom_rpt/import"
    assert csv_src is not None and csv_src["status"] == "a"
