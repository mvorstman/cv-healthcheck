from __future__ import annotations

from datetime import datetime, timezone

import cvhealthcheck.license_summary.service as _ls_service
from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    SummaryMetric,
    TableSection,
)
from cvhealthcheck.web.app import create_app


def _make_canonical() -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="license_summary",
        generated_at=datetime(2026, 5, 24, 10, 0, 0, tzinfo=timezone.utc),
        source=ArtifactSource(
            type=SourceType.csv_import,
        ),
        subject=ArtifactSubject(id="license_summary", title="License Summary"),
        summary=ArtifactSummary(
            status=ArtifactStatus.good,
            metrics=[
                SummaryMetric(id="other_license_count", label="Other Licenses", value=2),
                SummaryMetric(id="agent_feature_count", label="Agent / Feature Licenses", value=1),
            ],
        ),
        sections=[
            TableSection(
                type="table",
                id="other_licenses",
                title="Other Licenses",
                items=[
                    {"license": "Cloud Storage", "available_total": 100, "used": 40},
                ],
            )
        ],
    )


def _raise_file_not_found(self) -> None:
    raise FileNotFoundError("data/catalog/artifacts/license_summary/latest.json")


def test_canonical_endpoint_returns_404_when_no_artifact(monkeypatch) -> None:
    monkeypatch.setattr(_ls_service.LicenseSummaryService, "get_canonical", _raise_file_not_found)

    client = create_app().test_client()
    response = client.get("/api/license-summary/canonical")

    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert "canonical" in data["error"].lower() or "exist" in data["error"].lower()


def test_canonical_endpoint_returns_200_with_valid_structure(monkeypatch) -> None:
    canonical = _make_canonical()
    monkeypatch.setattr(
        _ls_service.LicenseSummaryService,
        "get_canonical",
        lambda self: canonical,
    )

    client = create_app().test_client()
    response = client.get("/api/license-summary/canonical")

    assert response.status_code == 200
    data = response.get_json()
    assert data["artifact_type"] == "license_summary"
    assert "summary" in data
    assert "sections" in data
    assert data["summary"]["status"] == "good"
    assert len(data["sections"]) == 1
    assert data["sections"][0]["type"] == "table"
    assert data["sections"][0]["id"] == "other_licenses"
