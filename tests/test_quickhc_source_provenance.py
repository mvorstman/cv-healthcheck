from __future__ import annotations

from cvhealthcheck.quickhc.source_provenance import (
    build_backup_job_summary_provenance,
    build_license_summary_provenance,
)
from cvhealthcheck.reportsplus.backup_job_summary import write_backup_job_summary_artifact
from cvhealthcheck.web.app import create_app
from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.service import persist_license_summary_artifact


CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A

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
    "recent_failures": [],
    "recent_jobs": [],
}


def _patch_backup_job_summary_paths(tmp_path, monkeypatch):
    import cvhealthcheck.reportsplus.backup_job_summary as backup_job_summary_module

    catalog_dir = tmp_path / "quickhc_catalog"
    monkeypatch.setattr(
        backup_job_summary_module,
        "QUICKHC_CATALOG_DIR",
        catalog_dir,
    )
    catalog_dir.mkdir(parents=True, exist_ok=True)
    return catalog_dir


def test_backup_job_summary_provenance_statuses_with_artifact() -> None:
    items = build_backup_job_summary_provenance(BACKUP_JOB_SUMMARY_ARTIFACT)
    by_type = {item["source_type"]: item for item in items}

    assert by_type["reports_plus"]["status"] == "validated"
    assert by_type["reports_plus"]["dataset_guid"] == "2638c3d3-adc7-4b61-bb24-2ba509229bf5"
    assert by_type["artifact"]["status"] == "available"
    assert by_type["artifact"]["active"] is True
    assert by_type["csv"]["status"] == "not_implemented"
    assert by_type["csv"]["active"] is False
    assert by_type["rest_api"]["status"] == "not_applicable"


def test_backup_job_summary_provenance_statuses_without_artifact_are_muted() -> None:
    items = build_backup_job_summary_provenance(None)
    by_type = {item["source_type"]: item for item in items}

    assert by_type["artifact"]["status"] == "not_available"
    assert by_type["artifact"]["active"] is False
    assert by_type["artifact"]["badge_class"] == "badge-warning"
    assert by_type["html"]["status"] == "not_implemented"
    assert by_type["manual"]["status"] == "not_applicable"


def test_license_summary_provenance_marks_import_and_reportsplus_paths_validated() -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    items = build_license_summary_provenance(artifact)
    by_type = {item["source_type"]: item for item in items}

    assert by_type["reports_plus"]["status"] == "validated"
    assert by_type["csv"]["status"] == "validated"
    assert by_type["html"]["status"] == "validated"
    assert by_type["artifact"]["status"] == "available"
    assert by_type["csv"]["notes"] == "Active source"


def test_backup_job_summary_detail_route_renders_source_provenance(
    tmp_path, monkeypatch
) -> None:
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/backup-job-summary")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Source Provenance" in body
    assert "Reports Plus dataset/report" in body
    assert "Normalized artifact" in body
    assert "CSV import" in body
    assert "HTML import" in body
    assert "Primary source:" in body
    assert body.count('class="source-provenance-item"') == 1
    assert "Other acquisition paths" in body
    assert "source-provenance-inline-meta" in body
    assert "Not implemented" in body
    assert "Not applicable" in body
    assert "source-provenance-secondary" in body
    assert "source-provenance-inactive-item" in body


def test_license_summary_detail_route_renders_shared_source_provenance(
    tmp_path, monkeypatch
) -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/license-summary")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Source Provenance" in body
    assert "Reports Plus dataset/report" in body
    assert "CSV import" in body
    assert "HTML import" in body
    assert "Normalized artifact" in body
    assert "Primary source: CSV import" in body
    assert body.count('class="source-provenance-item"') == 1
    assert "Other acquisition paths" in body
