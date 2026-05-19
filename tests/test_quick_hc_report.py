from __future__ import annotations

import json
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


def _patch_metrics_paths(tmp_path, monkeypatch) -> Path:
    import cvhealthcheck.metrics.common as metrics_common_module

    metrics_dir = tmp_path / "metrics_catalog"
    monkeypatch.setattr(
        metrics_common_module,
        "METRICS_CATALOG_DIR",
        metrics_dir,
    )
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


def _write_metric_artifact(metrics_dir: Path, name: str, payload: dict) -> None:
    (metrics_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


CLIENT_GROWTH_ARTIFACT = {
    "collected_at": "2026-05-18T21:00:00Z",
    "source": {
        "report_id": "318",
        "dataset_id": "2281",
        "dataset_guid": "8ac30a77-3de2-4968-86c1-ade4b02c85a4",
        "dataset_name": "Client Growth Summary",
        "widget_name": "Summary",
    },
    "http_status": 200,
    "ok": True,
    "record_count": 2,
    "history_range": {"start": "2026-04", "end": "2026-05", "points": 2},
    "records": [
        {"month": "2026-04", "total_clients": 120, "added": 4, "removed": 1, "data_source": "CommServe A"},
        {"month": "2026-05", "total_clients": 125, "added": 7, "removed": 2, "data_source": "CommServe A"},
    ],
}

CAPACITY_LICENSE_ARTIFACT = {
    "collected_at": "2026-05-18T21:05:00Z",
    "source": {
        "report_id": "318",
        "dataset_id": "2266",
        "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
        "dataset_name": "Capacity License Usage",
        "widget_name": "Capacity License Usage",
    },
    "http_status": 200,
    "ok": True,
    "record_count": 2,
    "history_range": {"start": "2026-05", "end": "2026-05", "points": 1},
    "records": [
        {"month": "2026-05", "entity_name": "CommServe A", "used_capacity": 18.5, "purchased_capacity": 40.0, "data_source": "CommServe A"},
        {"month": "2026-05", "entity_name": "CommServe B", "used_capacity": 11.0, "purchased_capacity": 20.0, "data_source": "CommServe B"},
    ],
}


def test_quick_hc_report_route_loads_without_artifacts() -> None:
    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Quick HealthCheck Report" in body
    assert body.count("Not collected yet") >= 2
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body


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
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body


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
                "requested": False,
                "has_content": False,
                "message": "Not collected yet",
                "detail_url": "/quick-hc/license-summary",
            },
            "client_growth": {
                "available": False,
                "requested": False,
                "has_content": False,
                "record_count": 0,
                "message": "Not collected yet",
                "detail_url": "/metrics/client-growth",
            },
            "capacity_license": {
                "available": False,
                "requested": False,
                "has_content": False,
                "record_count": 0,
                "message": "Not collected yet",
                "detail_url": "/metrics/capacity-license",
            },
            "evidence": [],
        }

    monkeypatch.setattr(QuickHcReportService, "build_report", fake_build_report)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    assert called["used"] is True


def test_quick_hc_overview_shows_report_selection_checkboxes(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    app = create_app()

    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Customer Report" in body
    assert 'value="environment"' in body
    assert 'value="environment.metadata"' in body
    assert 'value="security_assessment"' in body
    assert 'value="security_assessment.summary"' in body
    assert 'value="security_assessment.highlights"' in body
    assert 'value="security_assessment.all_findings"' in body
    assert 'value="license_summary"' in body
    assert 'value="license_summary.metadata"' in body
    assert 'value="license_summary.workload_sections"' in body
    assert 'value="license_summary.other_licenses"' in body
    assert 'value="license_summary.agent_feature_licenses"' in body
    assert 'value="client_growth"' in body
    assert 'value="client_growth.summary"' in body
    assert 'value="client_growth.chart"' in body
    assert 'value="client_growth.monthly_table"' in body
    assert 'value="capacity_license"' in body
    assert 'value="capacity_license.summary"' in body
    assert 'value="capacity_license.table"' in body
    assert "CommCell Details" in body
    assert "Client Growth" in body
    assert "Capacity License" in body
    assert "Generate/View Customer Report" in body


def test_quick_hc_report_post_license_summary_only_excludes_security_assessment(
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
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["license_summary"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" not in body
    assert "Cloud Storage" in body
    assert "Virtual Server" in body
    assert "MFA enabled" not in body


def test_quick_hc_report_post_security_assessment_only_excludes_license_summary(
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

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["security_assessment"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "MFA enabled" in body
    assert "License Summary" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body


def test_quick_hc_report_post_license_summary_workload_only_excludes_detail_tables(
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
        "/quick-hc/report",
        data={
            "selection_ids": [
                "license_summary",
                "license_summary.workload_sections",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "License Summary" in body
    assert "Capacity Licenses" in body
    assert "Other Licenses" not in body
    assert "Agent and Feature Licenses" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body


def test_quick_hc_report_post_security_assessment_summary_only_excludes_findings(
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

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "security_assessment",
                "security_assessment.summary",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body
    assert "Total checks" in body
    assert "Critical / Warning findings" not in body
    assert "All findings" not in body
    assert "MFA enabled" not in body
    assert "Audit retention" not in body


def test_quick_hc_report_post_client_growth_only_excludes_other_optional_subjects(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["client_growth"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Client Growth History" in body
    assert "Latest Total Clients" in body
    assert "Net Growth Over Period" in body
    assert "Monthly Summary" in body
    assert "125" in body
    assert "2026-04 to 2026-05" in body
    assert 'id="client-growth-history-chart"' in body
    assert '"labels": ["2026-04", "2026-05"]' in body
    assert '"label": "Total clients"' in body
    assert "dataset_guid" not in body
    assert "Source report" not in body
    assert "Source dataset" not in body
    assert "Source widget" not in body
    assert "HTTP status" not in body
    assert "Normalized fields" not in body
    assert "Sample rows" not in body
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body
    assert "Security Assessment" not in body
    assert "License Summary" not in body
    assert "Capacity License" not in body


def test_quick_hc_report_post_client_growth_chart_only_excludes_monthly_table(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "client_growth",
                "client_growth.chart",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Client Growth History" in body
    assert 'id="client-growth-history-chart"' in body
    assert "Monthly Summary" not in body
    assert "Latest Total Clients" not in body
    assert "<th>Month</th>" not in body


def test_quick_hc_report_post_capacity_license_only_excludes_other_optional_subjects(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["capacity_license"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Capacity License" in body
    assert "CommServe A" in body
    assert "CommServe B" in body
    assert "Security Assessment" not in body
    assert "License Summary" not in body
    assert "Client Growth" not in body


def test_quick_hc_report_selected_missing_metric_subject_renders_gracefully(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["client_growth"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Not collected yet" in body
    assert "Latest Total Clients" not in body


def test_quick_hc_report_post_unchecked_subject_omits_child_sections(
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

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["security_assessment.summary"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" not in body
    assert "Total checks" not in body


def test_quick_hc_report_get_still_uses_default_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)

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
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Environment" in body
    assert "Security Assessment" in body
    assert "Total checks" in body
    assert "Critical / Warning findings" not in body
    assert "License Summary" in body
    assert "Workload Summary Sections" in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body
    assert "Client Growth" in body
    assert "Monthly Summary" in body
    assert "Capacity License" in body
    assert "Latest Capacity Summary" in body


def test_quick_hc_report_builder_route_removed() -> None:
    app = create_app()

    response = app.test_client().get("/quick-hc/report/builder")

    assert response.status_code == 404
