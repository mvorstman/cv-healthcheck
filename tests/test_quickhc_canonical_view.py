from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingsSection,
    MetricSection,
    SummaryMetric,
    TableColumn,
    TableSection,
)
from cvhealthcheck.quickhc.canonical_view import (
    artifact_to_view,
    license_summary_to_view,
    security_assessment_to_view,
)

_NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)


def _sa_artifact(
    status: ArtifactStatus = ArtifactStatus.good,
    sections: list | None = None,
) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="security_assessment",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="security_assessment", title="Security Assessment"),
        summary=ArtifactSummary(
            status=status,
            metrics=[
                SummaryMetric(id="critical", label="Critical", value=2),
                SummaryMetric(id="warning",  label="Warning",  value=3),
                SummaryMetric(id="info",     label="Info",     value=1),
                SummaryMetric(id="good",     label="Good",     value=4),
            ],
        ),
        sections=sections if sections is not None else [
            FindingsSection(
                type="findings",
                id="access_security",
                title="Access Security",
                items=[
                    Finding(id="f1", severity=FindingSeverity.critical, status=FindingStatus.open,   title="MFA disabled",  category="Access", description="MFA not enabled"),
                    Finding(id="f2", severity=FindingSeverity.warning,  status=FindingStatus.open,   title="Weak password", category="Access", description="Password policy weak"),
                    Finding(id="f3", severity=FindingSeverity.good,     status=FindingStatus.open,   title="Audit logging", category="Access", description="Enabled"),
                ],
            ),
        ],
    )


def _ls_artifact(sections: list | None = None) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="license_summary",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="license_summary", title="License Summary"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=sections if sections is not None else [],
    )


# ── security_assessment_to_view ──

def test_sa_state_mapping_good():
    view = security_assessment_to_view(_sa_artifact(ArtifactStatus.good))
    assert view["state"] == "ok"


def test_sa_state_mapping_critical():
    view = security_assessment_to_view(_sa_artifact(ArtifactStatus.critical))
    assert view["state"] == "issues"


def test_sa_state_mapping_warning():
    view = security_assessment_to_view(_sa_artifact(ArtifactStatus.warning))
    assert view["state"] == "issues"


def test_sa_state_mapping_unknown():
    view = security_assessment_to_view(_sa_artifact(ArtifactStatus.unknown))
    assert view["state"] == "nodata"


def test_sa_counters_section():
    view = security_assessment_to_view(_sa_artifact())
    counters_sec = next(s for s in view["sections"] if s["type"] == "counters")
    assert counters_sec["counters"]["Critical"] == 2
    assert counters_sec["counters"]["Warning"]  == 3
    assert counters_sec["counters"]["Info"]     == 1
    assert counters_sec["counters"]["Good"]     == 4


def test_sa_highlights_only_critical_and_warning():
    many_findings = [
        Finding(id=f"c{i}", severity=FindingSeverity.critical, status=FindingStatus.open, title=f"C{i}", category="Sec", description="d")
        for i in range(8)
    ] + [
        Finding(id=f"w{i}", severity=FindingSeverity.warning,  status=FindingStatus.open, title=f"W{i}", category="Sec", description="d")
        for i in range(6)
    ] + [
        Finding(id="g0", severity=FindingSeverity.good, status=FindingStatus.open, title="G0", category="Sec", description="d"),
        Finding(id="i0", severity=FindingSeverity.info, status=FindingStatus.open, title="I0", category="Sec", description="d"),
    ]
    artifact = _sa_artifact(sections=[
        FindingsSection(type="findings", id="test_sec", title="Test", items=many_findings),
    ])
    view = security_assessment_to_view(artifact)
    highlights_sec = next(s for s in view["sections"] if s["type"] == "findings_grid")
    # capped at 12
    assert len(highlights_sec["findings"]) == 12
    # only crit and warn severities
    sevs = {f["sev"] for f in highlights_sec["findings"]}
    assert sevs <= {"crit", "warn"}


def test_sa_findings_list_section_id_dot_notation():
    artifact = _sa_artifact(sections=[
        FindingsSection(type="findings", id="access_security", title="Access Security", items=[
            Finding(id="t1", severity=FindingSeverity.good, status=FindingStatus.open, title="T", category="C", description="d"),
        ]),
    ])
    view = security_assessment_to_view(artifact)
    fl_sections = [s for s in view["sections"] if s["type"] == "findings_list"]
    assert len(fl_sections) == 1
    assert fl_sections[0]["id"] == "security_assessment.access_security"


def test_sa_section_id_no_double_prefix_when_already_qualified():
    # The HTML extractor stores fully-qualified section IDs. Both view builders
    # must accept them without re-prefixing — otherwise IDs leak into the JS
    # state and the localStorage key as "security_assessment.security_assessment.access_security",
    # silently breaking per-section include/exclude persistence.
    artifact = _sa_artifact(sections=[
        FindingsSection(
            type="findings",
            id="security_assessment.access_security",
            title="Access Security",
            items=[
                Finding(id="t1", severity=FindingSeverity.good, status=FindingStatus.open,
                        title="T", category="C", description="d"),
            ],
        ),
    ])

    generic_view = artifact_to_view(artifact)
    generic_ids = [s["id"] for s in generic_view["sections"]]
    assert generic_ids == ["security_assessment.access_security"]

    sa_view = security_assessment_to_view(artifact)
    sa_detail_ids = [s["id"] for s in sa_view["sections"] if s["type"] == "findings_list"]
    assert sa_detail_ids == ["security_assessment.access_security"]


def test_sa_empty_sections_state_nodata():
    artifact = _sa_artifact(sections=[])
    view = security_assessment_to_view(artifact)
    assert view["state"] == "nodata"


# ── license_summary_to_view ──

def test_ls_table_sections_shape():
    artifact = _ls_artifact(sections=[
        TableSection(
            type="table",
            id="other_licenses",
            title="Other Licenses",
            columns=[
                TableColumn(id="license", label="License"),
                TableColumn(id="used",    label="Used"),
            ],
            items=[
                {"license": "Cloud Storage", "used": 40},
                {"license": "File System",   "used": 10},
            ],
        ),
    ])
    view = license_summary_to_view(artifact)
    table_sec = next(s for s in view["sections"] if s["type"] == "table")
    assert table_sec["columns"] == ["License", "Used"]
    assert table_sec["rows"] == [["Cloud Storage", "40"], ["File System", "10"]]


def test_ls_workload_sections_collapsed():
    artifact = _ls_artifact(sections=[
        TableSection(
            type="table",
            id="vm_workload",
            title="VM Workload",
            columns=[
                TableColumn(id="license",          label="License"),
                TableColumn(id="entitlement_value", label="Entitlement"),
                TableColumn(id="used",             label="Used"),
                TableColumn(id="usage_percent",    label="Usage %"),
            ],
            items=[{"license": "VM", "entitlement_value": 100, "used": 50, "usage_percent": "50%"}],
        ),
        TableSection(
            type="table",
            id="file_workload",
            title="File Workload",
            columns=[
                TableColumn(id="license",          label="License"),
                TableColumn(id="entitlement_value", label="Entitlement"),
                TableColumn(id="used",             label="Used"),
                TableColumn(id="usage_percent",    label="Usage %"),
            ],
            items=[{"license": "FS", "entitlement_value": 200, "used": 80, "usage_percent": "40%"}],
        ),
    ])
    view = license_summary_to_view(artifact)
    workload_sec = next(s for s in view["sections"] if s["type"] == "workload")
    assert len(workload_sec["workload"]) == 2
    names = [w["name"] for w in workload_sec["workload"]]
    assert "VM Workload" in names
    assert "File Workload" in names


def test_ls_usage_percent_parsed_to_int():
    artifact = _ls_artifact(sections=[
        TableSection(
            type="table",
            id="vm_workload",
            title="VM Workload",
            columns=[
                TableColumn(id="license",          label="License"),
                TableColumn(id="entitlement_value", label="Entitlement"),
                TableColumn(id="used",             label="Used"),
                TableColumn(id="usage_percent",    label="Usage %"),
            ],
            items=[{"license": "VM", "entitlement_value": 100, "used": 73, "usage_percent": "73.6%"}],
        ),
    ])
    view = license_summary_to_view(artifact)
    workload_sec = next(s for s in view["sections"] if s["type"] == "workload")
    pct = workload_sec["workload"][0]["rows"][0]["pct"]
    assert pct == 73
    assert isinstance(pct, int)


def test_ls_empty_sections_state_nodata():
    artifact = _ls_artifact(sections=[])
    view = license_summary_to_view(artifact)
    assert view["state"] == "nodata"
