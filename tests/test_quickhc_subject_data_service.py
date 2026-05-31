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
    SummaryMetric,
    TableColumn,
    TableSection,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.quickhc.subject_data_service import (
    _build_license_summary_subject,
    _build_security_assessment_subject,
)

_NOW = datetime(2026, 5, 24, 9, 0, 0, tzinfo=timezone.utc)


def _sa_canonical() -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="security_assessment",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="security_assessment", title="Security Assessment"),
        summary=ArtifactSummary(
            status=ArtifactStatus.critical,
            metrics=[
                SummaryMetric(id="critical", label="Critical", value=5),
                SummaryMetric(id="warning",  label="Warning",  value=2),
                SummaryMetric(id="info",     label="Info",     value=1),
                SummaryMetric(id="good",     label="Good",     value=10),
            ],
        ),
        sections=[
            FindingsSection(
                type="findings",
                id="access_security",
                title="Access Security",
                items=[
                    Finding(id="f1", severity=FindingSeverity.critical, status=FindingStatus.open, title="MFA disabled", category="Access", description="Not enabled"),
                ],
            ),
        ],
    )


def _ls_canonical() -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="license_summary",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="license_summary", title="License Summary"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=[
            TableSection(
                type="table",
                id="vm_workload",
                title="VM Workload",
                columns=[
                    TableColumn(id="license",           label="License"),
                    TableColumn(id="entitlement_value", label="Entitlement"),
                    TableColumn(id="used",              label="Used"),
                    TableColumn(id="usage_percent",     label="Usage %"),
                ],
                items=[{"license": "VM", "entitlement_value": 100, "used": 60, "usage_percent": "60%"}],
            ),
            TableSection(
                type="table",
                id="other_licenses",
                title="Other Licenses",
                columns=[
                    TableColumn(id="license", label="License"),
                    TableColumn(id="used",    label="Used"),
                ],
                items=[{"license": "Cloud Storage", "used": 40}],
            ),
        ],
    )


# ── security_assessment ──

def test_sa_uses_canonical_when_artifact_exists(monkeypatch):
    monkeypatch.setattr(ArtifactStore, "load_latest_artifact", lambda self, t: _sa_canonical())
    view = _build_security_assessment_subject(None)

    assert view["id"] == "security_assessment"
    assert view["state"] == "issues"
    counters_sec = next(s for s in view["sections"] if s["type"] == "counters")
    assert counters_sec["counters"]["Critical"] == 5
    assert counters_sec["counters"]["Warning"]  == 2
    assert counters_sec["counters"]["Good"]     == 10


def test_sa_falls_back_to_legacy_when_no_canonical(monkeypatch):
    monkeypatch.setattr(
        ArtifactStore,
        "load_latest_artifact",
        lambda self, t: (_ for _ in ()).throw(FileNotFoundError("no artifact")),
    )
    view = _build_security_assessment_subject(None)

    assert view["id"] == "security_assessment"
    assert view["state"] == "nodata"
    assert view["sections"] == []


# ── license_summary ──

def test_ls_uses_canonical_when_artifact_exists(monkeypatch):
    monkeypatch.setattr(ArtifactStore, "load_latest_artifact", lambda self, t: _ls_canonical())
    view = _build_license_summary_subject(None)

    assert view["id"] == "license_summary"
    assert view["state"] == "ok"
    workload_sec = next(s for s in view["sections"] if s["type"] == "workload")
    assert len(workload_sec["workload"]) == 1
    assert workload_sec["workload"][0]["name"] == "VM Workload"


def test_ls_falls_back_to_legacy_when_no_canonical(monkeypatch):
    monkeypatch.setattr(
        ArtifactStore,
        "load_latest_artifact",
        lambda self, t: (_ for _ in ()).throw(FileNotFoundError("no artifact")),
    )
    view = _build_license_summary_subject(None)

    assert view["id"] == "license_summary"
    assert view["state"] == "nodata"
    assert view["sections"] == []
