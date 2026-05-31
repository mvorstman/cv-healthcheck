from __future__ import annotations

from cvhealthcheck.api_client import ApiResult
from cvhealthcheck.reportsplus.backup_job_summary import (
    BACKUP_JOB_SUMMARY_ARTIFACT_NAME,
    BACKUP_JOB_SUMMARY_DATASET_GUID,
    BACKUP_JOB_SUMMARY_RELATED_DATASET_GUID,
    BACKUP_JOB_SUMMARY_REPORT_NAME,
    classify_job_status,
    collect_backup_job_summary,
    load_backup_job_summary_artifact,
    normalize_backup_job_summary,
    normalize_backup_job_row,
)


def test_normalize_backup_job_row_preserves_customer_facing_fields() -> None:
    row = {
        "Job ID": "12345",
        "Client Name": "client-a",
        "Company": "Tenant A",
        "Workload Type": "File System",
        "Agent Type": "File System",
        "Backup Type": "Incremental",
        "Start Time": "2026-05-20 08:00:00",
        "End Time": "2026-05-20 08:10:00",
        "Duration": "00:10:00",
        "Job Status": "Completed",
        "Failure Reason": "",
        "Storage Policy": "Gold",
        "Media Agent": "ma-1",
        "Data Size": "100 GB",
        "Throughput": "1.5 GB/min",
        "Schedule Policy": "Daily",
        "Schedule Name": "Nightly",
    }

    normalized = normalize_backup_job_row(row)

    assert normalized["job_id"] == "12345"
    assert normalized["client"] == "client-a"
    assert normalized["company"] == "Tenant A"
    assert normalized["workload"] == "File System"
    assert normalized["agent"] == "File System"
    assert normalized["backup_type"] == "Incremental"
    assert normalized["status"] == "Completed"
    assert normalized["storage_policy"] == "Gold"
    assert normalized["media_agent"] == "ma-1"
    assert normalized["size"] == "100 GB"
    assert normalized["throughput"] == "1.5 GB/min"
    assert normalized["schedule_policy"] == "Daily"
    assert normalized["schedule_name"] == "Nightly"


def test_normalize_backup_job_summary_aggregates_statuses_and_recent_failures() -> None:
    result = ApiResult(
        ok=True,
        status_code=200,
        url=f"/commandcenter/api/cr/reportsplusengine/datasets/{BACKUP_JOB_SUMMARY_DATASET_GUID}/data",
        data={
            "records": [
                {
                    "Job ID": "1001",
                    "Client Name": "client-a",
                    "Start Time": "2026-05-20 09:00:00",
                    "End Time": "2026-05-20 09:30:00",
                    "Job Status": "Completed",
                },
                {
                    "Job ID": "1002",
                    "Client Name": "client-b",
                    "Start Time": "2026-05-20 10:00:00",
                    "End Time": "2026-05-20 10:10:00",
                    "Job Status": "Failed",
                    "Failure Reason": "Media issue",
                },
                {
                    "Job ID": "1003",
                    "Client Name": "client-c",
                    "Start Time": "2026-05-20 11:00:00",
                    "Job Status": "Running",
                },
                {
                    "Job ID": "1004",
                    "Client Name": "client-a",
                    "Start Time": "2026-05-20 08:00:00",
                    "End Time": "2026-05-20 08:45:00",
                    "Job Status": "Completed with warnings",
                },
                {
                    "Job ID": "1005",
                    "Client Name": "client-d",
                    "Start Time": "2026-05-20 07:00:00",
                    "End Time": "2026-05-20 07:15:00",
                    "Job Status": "Killed",
                },
                {
                    "Job ID": "1006",
                    "Client Name": "client-e",
                    "Start Time": "2026-05-20 06:00:00",
                    "End Time": "2026-05-20 06:15:00",
                    "Job Status": "Queued",
                },
            ]
        },
        text="",
    )

    artifact = normalize_backup_job_summary(result)

    assert artifact["source_report_name"] == BACKUP_JOB_SUMMARY_REPORT_NAME
    assert artifact["source_dataset_guid"] == BACKUP_JOB_SUMMARY_DATASET_GUID
    assert artifact["source_related_dataset_guid"] == BACKUP_JOB_SUMMARY_RELATED_DATASET_GUID
    assert artifact["total_jobs"] == 6
    assert artifact["completed_jobs"] == 1
    assert artifact["failed_jobs"] == 1
    assert artifact["completed_with_errors_or_warnings"] == 1
    assert artifact["running_jobs"] == 1
    assert artifact["killed_jobs"] == 1
    assert artifact["other_jobs"] == 1
    assert artifact["protected_clients_seen"] == 5
    assert artifact["status_breakdown"] == {
        "Completed": 1,
        "Failed": 1,
        "Running": 1,
        "Completed with errors/warnings": 1,
        "Killed": 1,
        "Other": 1,
    }
    assert artifact["recent_jobs"][0]["job_id"] == "1003"
    assert artifact["recent_failures"] == [
        {
            "job_id": "1002",
            "client": "client-b",
            "company": None,
            "workload": None,
            "agent": None,
            "backup_type": None,
            "start_time": "2026-05-20 10:00:00",
            "end_time": "2026-05-20 10:10:00",
            "duration": None,
            "status": "Failed",
            "failure_reason": "Media issue",
            "storage_policy": None,
            "media_agent": None,
            "size": None,
            "throughput": None,
            "schedule_policy": None,
            "schedule_name": None,
        }
    ]


def test_collect_backup_job_summary_persists_latest_artifact(tmp_path) -> None:
    class FakeReportsPlusClient:
        def get_dataset_data(self, dataset_guid: str, limit: int | None = None):
            assert dataset_guid == BACKUP_JOB_SUMMARY_DATASET_GUID
            assert limit == 25
            return ApiResult(
                ok=True,
                status_code=200,
                url=f"/commandcenter/api/cr/reportsplusengine/datasets/{dataset_guid}/data",
                data={
                    "records": [
                        {
                            "Job ID": "2001",
                            "Client Name": "client-z",
                            "Start Time": "2026-05-20 09:00:00",
                            "Job Status": "Completed",
                        }
                    ]
                },
                text="",
            )

    import cvhealthcheck.reportsplus.backup_job_summary as module

    original_dir = module.QUICKHC_CATALOG_DIR
    try:
        module.QUICKHC_CATALOG_DIR = tmp_path
        collected = collect_backup_job_summary(
            FakeReportsPlusClient(),
            limit=25,
            write_artifact=True,
        )
        persisted = load_backup_job_summary_artifact(catalog_dir=tmp_path)
    finally:
        module.QUICKHC_CATALOG_DIR = original_dir

    assert collected["artifact"] == str(tmp_path / BACKUP_JOB_SUMMARY_ARTIFACT_NAME)
    assert persisted["total_jobs"] == 1
    assert persisted["recent_jobs"][0]["job_id"] == "2001"


def test_classify_job_status_covers_expected_buckets() -> None:
    assert classify_job_status("Completed") == "Completed"
    assert classify_job_status("Failed") == "Failed"
    assert classify_job_status("Completed with warnings") == "Completed with errors/warnings"
    assert classify_job_status("Running") == "Running"
    assert classify_job_status("Killed") == "Killed"
    assert classify_job_status("Queued") == "Other"
