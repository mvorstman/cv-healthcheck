from __future__ import annotations

from pathlib import Path

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.quickhc.report_service import QuickHcReportService
from cvhealthcheck.security_assessment.artifact import build_security_assessment_artifact
from cvhealthcheck.security_assessment.service import persist_security_assessment_artifact
from cvhealthcheck.web.app import create_app


LICENSE_CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
CommCell ID,commcell-01
Customer ID,customer-01
License Expiry,Dec 31, 2026

Capacity Licenses
License,Available Total (TB),Permanent Purchased (TB),Term Purchased (TB),Used (TB),Used %,Summary
Backup and Recovery,100,100,0,0.00,0%,0%

Other Licenses - current usage details
License,Available Total,Used
Cloud Storage,100,40

Agent and Feature Licenses - current usage details
License,Permanent Total,Permanent Used,Term Total,Term Used,Client,Agent,Install Date
Virtual Server,50,12,10,3,Client A,Agent A,2026-05-01
"""


def _patch_security_assessment_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.security_assessment.service as security_assessment_service_module
    import cvhealthcheck.security_assessment.artifact as security_assessment_artifact_module

    monkeypatch.setattr(
        security_assessment_service_module,
        "SECURITY_ASSESSMENT_REGISTRY_PATH",
        tmp_path / "security_registry.sqlite3",
    )
    monkeypatch.setattr(
        security_assessment_service_module,
        "SECURITY_ASSESSMENT_CATALOG_DIR",
        tmp_path / "security_catalog",
    )
    monkeypatch.setattr(
        security_assessment_artifact_module,
        "SECURITY_ASSESSMENT_CATALOG_DIR",
        tmp_path / "security_catalog",
    )


def _patch_license_summary_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "license_registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "license_catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "license_catalog",
    )


def test_quick_hc_report_route_loads_without_artifacts() -> None:
    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Quick HealthCheck Report" in body
    assert body.count("Not collected yet") >= 2


def test_quick_hc_report_includes_security_assessment_summary(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            },
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            },
        ],
        source_type="html",
        source_file="/tmp/security-assessment.html",
        generated_on="May 17, 2026 07:00:14 PM",
    )
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    report = QuickHcReportService().build_report()

    assert report["security_assessment"]["available"] is True
    assert report["security_assessment"]["total_checks"] == 2
    assert report["security_assessment"]["critical"] == 1
    assert report["security_assessment"]["info"] == 1
    assert (
        report["security_assessment"]["loaded_from_path"]
        == persisted["file_path"]
    )


def test_quick_hc_report_includes_license_summary_summary(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    report = QuickHcReportService().build_report()

    assert report["license_summary"]["available"] is True
    assert report["license_summary"]["license_expiry"] == "Dec 31"
    assert report["license_summary"]["workload_summary_section_count"] == 1
    assert report["license_summary"]["other_license_row_count"] == 1
    assert report["license_summary"]["agent_feature_license_row_count"] == 1
    assert report["environment"]["commcell_name"] == "CommServe A"


def test_quick_hc_report_route_renders_both_summaries_when_artifacts_exist(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body
    assert "License Summary" in body
    assert "View Security Assessment" in body
    assert "View License Summary" in body
    assert "Cloud Storage" not in body


def test_quick_hc_report_route_uses_service(monkeypatch) -> None:
    called: dict[str, bool] = {"used": False}

    def fake_build_report(self):
        called["used"] = True
        return {
            "title": "Quick HealthCheck Report",
            "generated_at": "2026-05-18T20:00:00Z",
            "environment": {
                "customer_id": None,
                "commcell_id": None,
                "commcell_name": None,
                "generated_at": "2026-05-18T20:00:00Z",
            },
            "security_assessment": {
                "available": False,
                "message": "Not collected yet",
                "detail_url": "/quick-hc/security-assessment",
            },
            "license_summary": {
                "available": False,
                "message": "Not collected yet",
                "detail_url": "/quick-hc/license-summary",
            },
            "evidence": [],
        }

    monkeypatch.setattr(QuickHcReportService, "build_report", fake_build_report)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    assert called["used"] is True


def test_quick_hc_report_builder_loads_without_artifacts(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    app = create_app()

    response = app.test_client().get("/quick-hc/report/builder")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Quick HealthCheck Report Builder" in body
    assert "No current Quick HC artifacts are available yet." in body


def test_quick_hc_report_builder_shows_checkboxes_when_artifacts_exist(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/report/builder")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'value="environment"' in body
    assert 'value="security_assessment_summary"' in body
    assert 'value="security_assessment_findings"' in body
    assert 'value="license_summary_metadata"' in body
    assert 'value="license_summary_workload"' in body
    assert 'value="license_summary_details"' in body
    assert 'value="row.license_summary.other_licenses.0"' not in body


def test_quick_hc_report_builder_post_selected_sections_renders_only_selected_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            },
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            },
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report/builder/render",
        data={
            "selection_ids": [
                "environment",
                "security_assessment_findings",
                "license_summary_details",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Customer ID" in body
    assert "MFA enabled" in body
    assert "Audit retention" in body
    assert "Cloud Storage" in body
    assert "Virtual Server" in body
    assert "Workload Summary Sections" not in body


def test_quick_hc_report_builder_excludes_unchecked_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report/builder/render",
        data={"selection_ids": ["license_summary_metadata"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "License Summary" in body
    assert "Workload Summary Sections" in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body
