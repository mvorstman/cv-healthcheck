from __future__ import annotations

import logging
from pathlib import Path

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.auth.commvault_auth import SESSION_TOKEN_KEY
from cvhealthcheck.config import Settings, load_settings
from cvhealthcheck.license_summary.artifact import build_license_summary_artifact
from cvhealthcheck.license_summary.models import LicenseSummaryArtifact
from cvhealthcheck.security_assessment.artifact import build_security_assessment_artifact
from cvhealthcheck.security_assessment.models import SecurityAssessmentArtifact
from cvhealthcheck.web.app import create_app


def test_route_split_keeps_expected_endpoints_registered() -> None:
    app = create_app()

    rules = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}

    assert rules["/quick-hc"] == "main.quick_hc"
    assert rules["/quick-hc/license-summary"] == "main.quick_hc_license_summary"
    assert rules["/quick-hc/backup-job-summary"] == "main.quick_hc_backup_job_summary"
    assert rules["/security-assessment"] == "main.reportsplus_security_assessment"
    assert rules["/development"] == "main.development"
    assert rules["/reportsplus/reports"] == "main.reportsplus_reports"


def test_quick_hc_and_report_pages_still_render() -> None:
    app = create_app()
    client = app.test_client()

    assert client.get("/quick-hc").status_code == 200
    assert client.get("/quick-hc/license-summary").status_code == 200
    assert client.get("/quick-hc/backup-job-summary").status_code == 200
    assert client.get("/security-assessment").status_code == 200


def test_operational_metrics_and_reportsplus_routes_require_login() -> None:
    app = create_app()
    client = app.test_client()

    for path in (
        "/metrics/client-count",
        "/metrics/client-growth",
        "/metrics/capacity-license",
        "/reportsplus/health-candidates",
        "/reportsplus/execution-validation",
    ):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_operational_metrics_and_reportsplus_routes_render_after_login() -> None:
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"

    for path in (
        "/metrics/client-count",
        "/metrics/client-growth",
        "/metrics/capacity-license",
        "/reportsplus/health-candidates",
        "/reportsplus/execution-validation",
    ):
        response = client.get(path)
        assert response.status_code == 200


def test_security_assessment_artifact_includes_version_fields() -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="html",
        source_file="/tmp/security-assessment.html",
    )

    assert artifact["schema_version"] == 1
    assert artifact["artifact_version"] == "1.0"
    assert artifact["collector_version"] == "1.0"


def test_license_summary_artifact_includes_version_fields() -> None:
    artifact = build_license_summary_artifact(
        source_type="csv",
        source_file="/tmp/license-summary.csv",
        other_licenses=[{"license": "Cloud Storage", "available_total": 100, "used": 40}],
        agent_feature_licenses=[
            {
                "license": "Virtual Server",
                "permanent_total": 50,
                "permanent_used": 12,
                "term_total": 10,
                "term_used": 3,
            }
        ],
        workload_summary_sections=[],
    )

    assert artifact["schema_version"] == 1
    assert artifact["artifact_version"] == "1.0"
    assert artifact["collector_version"] == "1.0"


def test_existing_artifact_payloads_load_without_version_fields() -> None:
    security = SecurityAssessmentArtifact.from_dict(
        {
            "artifact_type": "security_assessment",
            "source_type": "html",
            "imported_at": "2026-05-18T19:00:00Z",
            "finding_count": 1,
            "status_counts": {"Critical": 1, "Warning": 0, "Info": 0, "Good": 0},
            "sections": ["Access Security"],
            "findings": [
                {
                    "section": "Access Security",
                    "parameter": "MFA enabled",
                    "status": "Critical",
                    "remarks": "Missing",
                    "action": "Enable MFA",
                    "source_type": "html",
                    "source_file": "/tmp/security-assessment.html",
                    "imported_at": "2026-05-18T19:00:00Z",
                }
            ],
            "source": {"type": "html"},
        }
    )
    license_summary = LicenseSummaryArtifact.from_dict(
        {
            "artifact_type": "license_summary",
            "source_type": "csv",
            "imported_at": "2026-05-18T19:00:00Z",
            "other_licenses": [
                {"license": "Cloud Storage", "available_total": 100, "used": 40}
            ],
            "agent_feature_licenses": [],
            "workload_summary_sections": [],
            "source": {"type": "csv"},
        }
    )

    assert security.schema_version == 1
    assert license_summary.schema_version == 1


def test_load_settings_defaults_to_ssl_verification_enabled(monkeypatch) -> None:
    monkeypatch.delenv("CV_VERIFY_SSL", raising=False)

    settings = load_settings()

    assert settings.verify_ssl is True


def test_api_client_warns_when_ssl_verification_disabled(caplog) -> None:
    caplog.set_level(logging.WARNING)

    CommvaultApiClient(
        settings=Settings(
            base_url="https://commvault.example",
            token_path=Path(".token"),
            verify_ssl=False,
        )
    )

    assert "SSL certificate verification is disabled" in caplog.text
