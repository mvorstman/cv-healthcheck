"""ADR 0010 (layout slice 2) — the Evaluation band: criteria + findings cards,
moved out of Report Sections, plus the always-present scope caption. Data-layer
+ render-marker tests; derived phrasing is interim (next slice authors it).
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

_EVAL_META = {"server_groups": {
    "scope": [{"target": "association", "operator": "eq", "value": "MANUAL"}],
    "checks": [
        {"rule_id": "sg_empty_group", "severity": "warning",
         "description": "Every server group must contain at least one server.",
         "title": "Empty server group: {row.name}", "condition_text": "server_count = 0"},
        {"rule_id": "sg_naming_convention", "severity": "warning",   # description absent → title fallback
         "title": "Group {row.name} breaks the naming convention",
         "condition_text": 'name not contains "GRP_"'},
    ],
}}


def _view(metadata):
    art = CanonicalArtifact(
        artifact_type="server_groups", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="server_groups", title="Server Groups"),
        summary=ArtifactSummary(status=ArtifactStatus.warning),
        sections=[
            TableSection(type="table", id="server_groups", title="Server Groups",
                columns=[TableColumn(id="id", label="ID"), TableColumn(id="name", label="Name"),
                         TableColumn(id="association", label="Assoc")],
                items=[{"id": 19, "name": "rommelgroep", "association": "MANUAL", "_verdict": "warning"},
                       {"id": 7, "name": "GRP_x", "association": "MANUAL", "_verdict": "good"},
                       {"id": 3, "name": "auto", "association": "AUTOMATIC", "_verdict": "not_evaluated"}]),
            FindingsSection(type="findings", id="server_groups.compliance", title="Compliance",
                items=[Finding(id="a", severity=FindingSeverity.warning, status=FindingStatus.open,
                               category="server_groups", title="Empty: rommelgroep")]),
        ],
        metadata=metadata)
    return artifact_to_view(art)["sections"]


# ── the Evaluation band ───────────────────────────────────────────────────────

def test_evaluation_band_has_criteria_then_findings_after_report():
    secs = _view({"evaluation": _EVAL_META})
    report = [s for s in secs if s.get("band") == "report"]
    evaluation = [s for s in secs if s.get("band") == "evaluation"]
    assert [s["type"] for s in report] == ["table"]
    assert [s["type"] for s in evaluation] == ["criteria", "findings_list"]   # criteria first
    # report sections come before the evaluation sections in the flat list
    report_idx = [i for i, s in enumerate(secs) if s.get("band") == "report"]
    eval_idx = [i for i, s in enumerate(secs) if s.get("band") == "evaluation"]
    assert max(report_idx) < min(eval_idx)

def test_findings_moved_out_of_report_and_retitled():
    secs = _view({"evaluation": _EVAL_META})
    report = [s for s in secs if s.get("band") == "report"]
    assert not any(s["type"] == "findings_list" for s in report)   # gone from Report
    findings = next(s for s in secs if s["type"] == "findings_list")
    assert findings["band"] == "evaluation" and findings["title"] == "Findings"
    assert findings["sev"] == "warn"   # keeps its Warning pill

def test_criteria_card_scope_and_checks_no_pill():
    crit = next(s for s in _view({"evaluation": _EVAL_META}) if s["type"] == "criteria")
    assert crit["title"] == "Evaluation criteria"
    assert "sev" not in crit                                       # criteria has NO pill
    assert crit["scope_sentence"] == "Manual server groups. Automatic groups are excluded from assessment."
    assert crit["checks"] == [
        {"sev": "warn", "primary": "Every server group must contain at least one server.",
         "condition": "server_count = 0"},
        # description absent → the title's static text (placeholder stripped), never the id
        {"sev": "warn", "primary": "Group breaks the naming convention",
         "condition": 'name not contains "GRP_"'},
    ]

def test_each_evaluation_card_has_its_own_include_flag():
    evaluation = [s for s in _view({"evaluation": _EVAL_META}) if s.get("band") == "evaluation"]
    assert all(s["included"] is True for s in evaluation)          # independent, defaulted on
    assert len({s["id"] for s in evaluation}) == len(evaluation)   # distinct ids → distinct toggles

def test_scope_caption_on_table_legend():
    table = next(s for s in _view({"evaluation": _EVAL_META}) if s["type"] == "table")
    assert table["scope_caption"] == "manual server groups · automatic excluded"
    assert table["band"] == "report"                              # caption lives on the data table

def test_no_evaluation_metadata_means_no_band_and_no_caption():
    # a generic subject with NO evaluation block (the realistic "other subjects"
    # case): no Evaluation band, no criteria, no scope caption; and a NON-compliance
    # findings section is NOT rebanded (only <subject>.compliance moves).
    art = CanonicalArtifact(
        artifact_type="x", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="x", title="X"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[
            TableSection(type="table", id="x", title="X",
                columns=[TableColumn(id="id", label="ID")], items=[{"id": 1}]),
            FindingsSection(type="findings", id="x.other", title="Other",
                items=[Finding(id="a", severity=FindingSeverity.info, status=FindingStatus.open,
                               category="x", title="t")]),
        ],
        metadata={})
    secs = artifact_to_view(art)["sections"]
    assert not any(s.get("band") == "evaluation" for s in secs)
    assert not any(s["type"] == "criteria" for s in secs)
    assert next(s for s in secs if s["type"] == "table")["scope_caption"] is None
    other = next(s for s in secs if s["type"] == "findings_list")
    assert other["title"] == "Other" and other.get("band") == "report"   # not rebanded


# ── render markers ────────────────────────────────────────────────────────────

_JS = (Path(__file__).resolve().parents[1] / "src/cvhealthcheck/web/static/quick_hc.js").read_text()

def test_js_renders_evaluation_band_criteria_and_scope_caption():
    assert "sec.band === 'evaluation'" in _JS              # the band partition
    assert 'cfg-sec-title">Evaluation' in _JS              # the new band header
    assert "sec.type === 'criteria'" in _JS               # the criteria renderer
    assert "vdot-legend-scope" in _JS and "Scope: " in _JS  # the table scope caption
