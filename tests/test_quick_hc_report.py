from __future__ import annotations

import json
from pathlib import Path

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.quickhc.report_service import QuickHcReportService
from cvhealthcheck.reportsplus.backup_job_summary import write_backup_job_summary_artifact
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


LICENSE_CSV_WITH_UNPURCHASED = """\
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
Archive,0,0

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


def _patch_backup_job_summary_paths(tmp_path, monkeypatch) -> Path:
    import cvhealthcheck.reportsplus.backup_job_summary as backup_job_summary_module

    catalog_dir = tmp_path / "quickhc_catalog"
    monkeypatch.setattr(
        backup_job_summary_module,
        "QUICKHC_CATALOG_DIR",
        catalog_dir,
    )
    catalog_dir.mkdir(parents=True, exist_ok=True)
    return catalog_dir


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

BACKUP_JOB_SUMMARY_ARTIFACT = {
    "generated_at": "2026-05-20T10:30:00Z",
    "source_report_name": "Backup Job Summary",
    "source_dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "source_related_dataset_guid": "ce01fc88-d2bd-46cc-ba41-1d967c7fa4a2",
    "total_jobs": 12,
    "completed_jobs": 8,
    "failed_jobs": 2,
    "completed_with_errors_or_warnings": 1,
    "running_jobs": 1,
    "killed_jobs": 0,
    "other_jobs": 0,
    "protected_clients_seen": 5,
    "status_breakdown": {
        "Completed": 8,
        "Failed": 2,
        "Completed with errors/warnings": 1,
        "Running": 1,
    },
    "recent_failures": [
        {
            "job_id": "9002",
            "client": "client-b",
            "company": "Tenant B",
            "workload": "File System",
            "agent": "FS",
            "backup_type": "Incremental",
            "start_time": "2026-05-20 08:00:00",
            "end_time": "2026-05-20 08:20:00",
            "duration": "00:20:00",
            "status": "Failed",
            "failure_reason": "Media issue",
            "storage_policy": "Gold",
            "media_agent": "ma-1",
            "size": "100 GB",
            "throughput": "80 MB/s",
            "schedule_policy": "Daily",
            "schedule_name": "Nightly",
        }
    ],
    "recent_jobs": [
        {
            "job_id": "9003",
            "client": "client-c",
            "company": "Tenant C",
            "workload": "VMware",
            "agent": "VSA",
            "backup_type": "Full",
            "start_time": "2026-05-20 09:00:00",
            "end_time": "2026-05-20 09:40:00",
            "duration": "00:40:00",
            "status": "Completed",
            "failure_reason": None,
            "storage_policy": "Silver",
            "media_agent": "ma-2",
            "size": "250 GB",
            "throughput": "120 MB/s",
            "schedule_policy": "Weekly",
            "schedule_name": "Weekend",
        }
    ],
}


def test_quick_hc_report_route_loads_without_artifacts() -> None:
    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Quick HealthCheck Report" in body
    assert "Environment" in body
    assert "Security Assessment" in body
    assert "License Summary" in body
    assert "Backup Job Summary" in body
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
    assert report["license_summary"]["other_license_rows"][0]["usage_percent_label"] == "40%"
    assert report["license_summary"]["other_license_rows"][0]["usage_has_bar"] is True
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
            "backup_job_summary": {
                "available": False,
                "requested": False,
                "has_content": False,
                "total_jobs": 0,
                "message": "No Backup Job Summary artifact available yet.",
                "detail_url": "/quick-hc",
            },
            "evidence": [],
        }

    monkeypatch.setattr(QuickHcReportService, "build_report", fake_build_report)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    assert called["used"] is True


def test_quick_hc_report_service_uses_registry_detail_urls_and_client_growth_has_no_stale_message(
    tmp_path, monkeypatch
) -> None:
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    with app.test_request_context():
        report = QuickHcReportService().build_report()

    assert report["security_assessment"]["detail_url"] == "/quick-hc/security-assessment"
    assert report["license_summary"]["detail_url"] == "/quick-hc/license-summary"
    assert report["client_growth"]["detail_url"] == "/metrics/client-growth"
    assert report["capacity_license"]["detail_url"] == "/metrics/capacity-license"
    assert report["backup_job_summary"]["detail_url"] == "/quick-hc/backup-job-summary"
    assert "message" not in report["client_growth"]


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
    assert "window.QUICK_HC_INITIAL_DATA" in body
    assert "/static/quick_hc.css" in body
    assert "/static/quick_hc.js" in body
    assert 'id="left-scroll"' in body
    assert 'id="right-body"' in body
    assert 'id="report-form"' in body
    assert '"id": "environment"' in body
    assert '"id": "security_assessment"' in body
    assert '"id": "license_summary"' in body
    assert '"id": "client_growth"' in body
    assert '"id": "capacity_license"' in body
    assert '"id": "backup_job_summary"' in body
    assert '"id": "security_assessment.highlights"' in body
    assert "CommCell Details" in body
    assert "Client Growth" in body
    assert "Capacity Licenses" in body
    assert "Backup Job Summary" in body
    assert "Generate Customer Report" in body
    assert "dataset_guid" not in body
    assert "HTTP status" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body
    assert "registry" not in body.lower()


def test_quick_hc_overview_license_summary_previews_real_fields(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '"id": "license_summary.metadata"' in body
    assert '"k": "SOURCE", "v": "CSV"' in body
    assert '"k": "IMPORTED"' in body
    assert '"k": "GENERATED ON"' in body
    assert '"k": "LICENSE EXPIRY"' in body
    assert '"title": "Other Licenses table"' in body
    assert '"title": "Agent / Feature Licenses table"' in body
    assert '"Cloud Storage"' in body
    assert '"Virtual Server"' in body
    assert '"pct": 0' in body
    assert "dataset_guid" not in body
    assert "HTTP status" not in body


def test_quick_hc_overview_handles_missing_backup_job_summary_artifact(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    _patch_backup_job_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert '"id": "backup_job_summary"' in body
    assert '"state": "nodata"' in body
    assert '"subtitle": "Not collected"' in body


def test_quick_hc_overview_renders_backup_job_summary_preview(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert '"meta": "12 jobs"' in body
    assert '{"k": "TOTAL JOBS", "v": "12"}' in body
    assert '{"cls": "err", "k": "FAILED", "v": "2"}' in body
    assert '"meta": "1 failures"' in body
    assert '"title": "Recent jobs"' in body
    assert "dataset_guid" not in body


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


def test_quick_hc_report_renders_selected_backup_job_summary_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "backup_job_summary",
                "backup_job_summary.summary",
                "backup_job_summary.recent_failures",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert "Source Report" in body
    assert "Backup Job Summary" in body
    assert "Recent Failures" in body
    assert "Media issue" in body
    assert "Status Breakdown" not in body
    assert "Recent Jobs" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body
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


def test_quick_hc_report_renders_license_summary_usage_visualization(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_WITH_UNPURCHASED,
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
                "license_summary.other_licenses",
                "license_summary.agent_feature_licenses",
                "license_summary.workload_sections",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<th>Summary</th>" in body
    assert 'class="usage-summary-bar"' in body
    assert 'class="usage-summary-bar-fill"' in body
    assert "40%" in body
    assert "License not purchased" in body
    agent_table_idx = body.index("<h4>Agent and Feature Licenses</h4>")
    agent_client_agent_idx = body.index("<th>Client / Agent</th>", agent_table_idx)
    agent_status_idx = body.index("<th>Status</th>", agent_table_idx)
    assert agent_table_idx < agent_client_agent_idx < agent_status_idx
    assert body.find('class="usage-summary-bar"', agent_table_idx, body.index("</table>", agent_table_idx)) == -1
    assert "dataset_guid" not in body
    assert "HTTP status" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body


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
