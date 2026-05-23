from __future__ import annotations

from datetime import datetime, timezone

import cvhealthcheck.security_assessment.service as _sa_service
from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingsSection,
    SummaryMetric,
)
from cvhealthcheck.web.app import create_app


def _make_canonical() -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="security_assessment",
        generated_at=datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc),
        source=ArtifactSource(
            type=SourceType.reportsplus_rest,
            report_id=336,
            report_name="Security Assessment",
        ),
        subject=ArtifactSubject(id="security_assessment", title="Security Assessment"),
        summary=ArtifactSummary(
            status=ArtifactStatus.critical,
            metrics=[
                SummaryMetric(id="critical", label="Critical", value=1),
                SummaryMetric(id="warning",  label="Warning",  value=0),
                SummaryMetric(id="good",     label="Good",     value=0),
                SummaryMetric(id="info",     label="Info",     value=0),
            ],
        ),
        sections=[
            FindingsSection(
                type="findings",
                id="access_security",
                title="Access Security",
                items=[
                    Finding(
                        id="mfa_enabled",
                        severity=FindingSeverity.critical,
                        status=FindingStatus.open,
                        category="Access Security",
                        title="MFA enabled",
                        description="Missing for admin users",
                    )
                ],
            )
        ],
    )


def _raise_file_not_found(self) -> None:
    raise FileNotFoundError("data/catalog/artifacts/security_assessment/latest.json")


def test_canonical_endpoint_returns_404_when_no_artifact(monkeypatch) -> None:
    monkeypatch.setattr(_sa_service.SecurityAssessmentService, "get_canonical", _raise_file_not_found)

    client = create_app().test_client()
    response = client.get("/api/security-assessment/canonical")

    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert "canonical" in data["error"].lower() or "exist" in data["error"].lower()


def test_canonical_endpoint_returns_200_with_valid_structure(monkeypatch) -> None:
    canonical = _make_canonical()
    monkeypatch.setattr(
        _sa_service.SecurityAssessmentService,
        "get_canonical",
        lambda self: canonical,
    )

    client = create_app().test_client()
    response = client.get("/api/security-assessment/canonical")

    assert response.status_code == 200
    data = response.get_json()
    assert data["artifact_type"] == "security_assessment"
    assert "summary" in data
    assert "sections" in data
    assert data["summary"]["status"] == "critical"
    assert len(data["sections"]) == 1
    assert data["sections"][0]["type"] == "findings"
    assert data["sections"][0]["id"] == "access_security"
