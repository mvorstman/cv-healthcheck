"""ADR 0010 (layout slice) — the view carries per-row verdicts, the section pill
rolls up (excluding not_evaluated), and the renderer maps not_evaluated to an
EXPLICIT gray dot (never the info fallback). Data-layer + render-marker tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cvhealthcheck.artifacts.enums import (
    ArtifactStatus, FindingSeverity, FindingStatus, SourceType,
)
from cvhealthcheck.artifacts.models import (
    ArtifactSource, ArtifactSubject, ArtifactSummary, CanonicalArtifact,
    Finding, FindingsSection, TableColumn, TableSection,
)
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

NOW = datetime(2026, 6, 3, tzinfo=timezone.utc)


def _artifact(sections):
    return CanonicalArtifact(
        artifact_type="sg", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="sg", title="Server Groups"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=sections)


def _table(items):
    return TableSection(type="table", id="sg.rows", title="Server Groups",
        columns=[TableColumn(id="id", label="ID"), TableColumn(id="name", label="Name")],
        items=items)


def _view_table(items):
    view = artifact_to_view(_artifact([_table(items)]))
    return next(s for s in view["sections"] if s["type"] == "table")


# ── the pipe carries _verdict as row metadata, not a data column ──────────────

def test_table_view_carries_row_verdicts_row_aligned():
    sec = _view_table([
        {"id": 1, "name": "a", "_verdict": "warning"},
        {"id": 2, "name": "b", "_verdict": "good"},
        {"id": 3, "name": "c", "_verdict": "not_evaluated"},
    ])
    assert sec["row_verdicts"] == ["warning", "good", "not_evaluated"]
    # _verdict is NOT a visible data cell: only the 2 declared columns render
    assert sec["columns"] == ["ID", "Name"]
    assert all(len(row) == 2 for row in sec["rows"])

def test_table_pill_is_worst_verdict_excluding_not_evaluated():
    # not_evaluated must not drive the pill; warning wins here
    assert _view_table([
        {"id": 1, "name": "a", "_verdict": "not_evaluated"},
        {"id": 2, "name": "b", "_verdict": "warning"},
        {"id": 3, "name": "c", "_verdict": "good"},
    ])["sev"] == "warn"
    # all not_evaluated → no pill
    assert _view_table([{"id": 1, "name": "a", "_verdict": "not_evaluated"}])["sev"] is None
    # critical beats warning
    assert _view_table([
        {"id": 1, "name": "a", "_verdict": "warning"},
        {"id": 2, "name": "b", "_verdict": "critical"},
    ])["sev"] == "crit"

def test_table_without_verdicts_is_unchanged():
    sec = _view_table([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
    assert sec["row_verdicts"] == [None, None]   # absent → None (renderer falls back to info)
    assert sec["sev"] is None                    # no pill, no STATUS column


def test_compliance_findings_section_gets_worst_severity_pill():
    findings = [
        Finding(id="a", severity=FindingSeverity.warning, status=FindingStatus.open,
                category="sg.rows", title="w"),
        Finding(id="b", severity=FindingSeverity.critical, status=FindingStatus.open,
                category="sg.rows", title="c"),
    ]
    view = artifact_to_view(_artifact([
        FindingsSection(type="findings", id="sg.compliance", title="Compliance", items=findings)]))
    comp = next(s for s in view["sections"] if s["type"] == "findings_list")
    assert comp["sev"] == "crit"

def test_empty_findings_section_has_no_pill():
    view = artifact_to_view(_artifact([
        FindingsSection(type="findings", id="sg.compliance", title="Compliance", items=[])]))
    comp = next(s for s in view["sections"] if s["type"] == "findings_list")
    assert comp["sev"] is None


# ── render markers: not_evaluated is EXPLICIT gray, never the info fallback ────

_JS = (Path(__file__).resolve().parents[1] / "src/cvhealthcheck/web/static/quick_hc.js").read_text()
_CSS = (Path(__file__).resolve().parents[1] / "src/cvhealthcheck/web/static/quick_hc.css").read_text()

def test_renderer_maps_not_evaluated_to_gray_not_info():
    # explicit verdict → its own dot; not_evaluated has the gray vdot-na
    assert "not_evaluated:'vdot-na'" in _JS
    # the ONLY path to vdot-info is a genuinely ABSENT (null) verdict — the trap guard
    assert "if (v == null) return 'vdot-info';" in _JS

def test_legend_has_not_evaluated_entry():
    assert "not evaluated" in _JS and "vdot-na" in _JS

def test_css_defines_distinct_not_evaluated_dot_and_status_column():
    assert ".vdot-na{" in _CSS and ".vdot-col{" in _CSS
