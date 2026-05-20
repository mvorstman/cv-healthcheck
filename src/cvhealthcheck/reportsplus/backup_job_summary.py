from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cvhealthcheck.api_client import ApiResult
from cvhealthcheck.reportsplus.catalog import CATALOG_DIR, collected_at, read_json, write_json
from cvhealthcheck.reportsplus.client import DATASETS_PATH, ReportsPlusClient

BACKUP_JOB_SUMMARY_REPORT_NAME = "Backup Job Summary"
BACKUP_JOB_SUMMARY_DATASET_GUID = "2638c3d3-adc7-4b61-bb24-2ba509229bf5"
BACKUP_JOB_SUMMARY_RELATED_DATASET_GUID = "ce01fc88-d2bd-46cc-ba41-1d967c7fa4a2"
QUICKHC_CATALOG_DIR = CATALOG_DIR / "quickhc"
BACKUP_JOB_SUMMARY_ARTIFACT_NAME = "backup_job_summary_latest.json"

BACKUP_JOB_SUMMARY_SOURCE = {
    "report_name": BACKUP_JOB_SUMMARY_REPORT_NAME,
    "dataset_guid": BACKUP_JOB_SUMMARY_DATASET_GUID,
    "related_dataset_guid": BACKUP_JOB_SUMMARY_RELATED_DATASET_GUID,
    "endpoint_path": f"{DATASETS_PATH}/{BACKUP_JOB_SUMMARY_DATASET_GUID}/data",
}


def collect_backup_job_summary(
    client: ReportsPlusClient | None = None,
    *,
    limit: int | None = 100,
    write_artifact: bool = True,
) -> dict[str, Any]:
    reports_client = client or ReportsPlusClient()
    result = reports_client.get_dataset_data(
        BACKUP_JOB_SUMMARY_DATASET_GUID,
        limit=limit,
    )
    artifact = normalize_backup_job_summary(result)
    artifact_path = None
    if write_artifact and result.ok:
        artifact_path = write_backup_job_summary_artifact(artifact)
        artifact["artifact_path"] = str(artifact_path)
    return {
        "result": result,
        "normalized": artifact,
        "artifact": str(artifact_path) if artifact_path else None,
    }


def normalize_backup_job_summary(result: ApiResult) -> dict[str, Any]:
    rows = rows_from_payload(result.data)
    jobs = [normalize_backup_job_row(row) for row in rows]
    jobs = [job for job in jobs if _job_has_content(job)]
    jobs = _sort_jobs(jobs)

    status_breakdown: dict[str, int] = {}
    completed_jobs = 0
    failed_jobs = 0
    completed_with_errors_or_warnings = 0
    running_jobs = 0
    killed_jobs = 0
    other_jobs = 0
    protected_clients = {
        client_name
        for client_name in (job.get("client") for job in jobs)
        if isinstance(client_name, str) and client_name.strip()
    }

    for job in jobs:
        bucket = classify_job_status(job.get("status"))
        status_breakdown[bucket] = status_breakdown.get(bucket, 0) + 1
        if bucket == "Completed":
            completed_jobs += 1
        elif bucket == "Failed":
            failed_jobs += 1
        elif bucket == "Completed with errors/warnings":
            completed_with_errors_or_warnings += 1
        elif bucket == "Running":
            running_jobs += 1
        elif bucket == "Killed":
            killed_jobs += 1
        else:
            other_jobs += 1

    recent_failures = [
        job
        for job in jobs
        if classify_job_status(job.get("status")) == "Failed"
    ][:10]

    return {
        "generated_at": collected_at(),
        "source_report_name": BACKUP_JOB_SUMMARY_REPORT_NAME,
        "source_dataset_guid": BACKUP_JOB_SUMMARY_DATASET_GUID,
        "source_related_dataset_guid": BACKUP_JOB_SUMMARY_RELATED_DATASET_GUID,
        "source_endpoint_path": BACKUP_JOB_SUMMARY_SOURCE["endpoint_path"],
        "http_status": result.status_code,
        "ok": result.ok,
        "total_jobs": len(jobs),
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "completed_with_errors_or_warnings": completed_with_errors_or_warnings,
        "running_jobs": running_jobs,
        "killed_jobs": killed_jobs,
        "other_jobs": other_jobs,
        "protected_clients_seen": len(protected_clients),
        "status_breakdown": status_breakdown,
        "recent_failures": recent_failures,
        "recent_jobs": jobs[:10],
    }


def normalize_backup_job_row(row: dict[str, Any]) -> dict[str, Any]:
    status = clean_string(
        _first_value(
            row,
            "Job Status",
            "Status",
            "jobStatus",
            "status",
        )
    )
    return {
        "job_id": clean_string(_first_value(row, "Job Id", "Job ID", "jobId", "job_id")),
        "client": clean_string(_first_value(row, "Client", "Client Name", "clientName")),
        "company": clean_string(_first_value(row, "Company", "Company Name", "companyName")),
        "workload": clean_string(_first_value(row, "Workload", "Workload Type", "workload")),
        "agent": clean_string(_first_value(row, "Agent", "Subclient", "Agent Type", "agent")),
        "backup_type": clean_string(_first_value(row, "Backup Type", "Job Type", "backupType")),
        "start_time": clean_string(_first_value(row, "Start Time", "Start", "startTime")),
        "end_time": clean_string(_first_value(row, "End Time", "End", "endTime")),
        "duration": clean_string(_first_value(row, "Duration", "Elapsed Time", "duration")),
        "status": status,
        "failure_reason": clean_string(
            _first_value(
                row,
                "Failure Reason",
                "FailureReason",
                "Reason for Failure",
                "Reason",
                "failureReason",
            )
        ),
        "storage_policy": clean_string(
            _first_value(row, "Storage Policy", "storagePolicy", "Copy")
        ),
        "media_agent": clean_string(
            _first_value(row, "MediaAgent", "Media Agent", "mediaAgent")
        ),
        "size": clean_string(_first_value(row, "Size", "Data Size", "Application Size")),
        "throughput": clean_string(_first_value(row, "Throughput", "Transfer Rate")),
        "schedule_policy": clean_string(
            _first_value(row, "Schedule Policy", "schedulePolicy")
        ),
        "schedule_name": clean_string(
            _first_value(row, "Schedule Name", "scheduleName")
        ),
    }


def classify_job_status(value: Any) -> str:
    text = (clean_string(value) or "").strip().lower()
    if not text:
        return "Other"
    if "fail" in text:
        return "Failed"
    if "warn" in text or "error" in text:
        if "complete" in text or "success" in text:
            return "Completed with errors/warnings"
    if "run" in text or "progress" in text:
        return "Running"
    if "kill" in text or "terminate" in text:
        return "Killed"
    if "complete" in text or "success" in text:
        return "Completed"
    return "Other"


def write_backup_job_summary_artifact(
    payload: dict[str, Any],
    *,
    catalog_dir: Path | None = None,
) -> Path:
    return write_json(
        BACKUP_JOB_SUMMARY_ARTIFACT_NAME,
        payload,
        catalog_dir=catalog_dir or QUICKHC_CATALOG_DIR,
    )


def load_backup_job_summary_artifact(
    *,
    catalog_dir: Path | None = None,
) -> dict[str, Any]:
    return read_json(
        BACKUP_JOB_SUMMARY_ARTIFACT_NAME,
        catalog_dir=catalog_dir or QUICKHC_CATALOG_DIR,
    )


def rows_from_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("records", "rows", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        for value in data.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
    return []


def clean_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    lowered = {
        str(key).strip().lower(): value
        for key, value in row.items()
    }
    for key in keys:
        value = lowered.get(key.strip().lower())
        if value not in (None, ""):
            return value
    return None


def _job_has_content(job: dict[str, Any]) -> bool:
    return any(value not in (None, "") for value in job.values())


def _sort_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        jobs,
        key=lambda job: (
            _parse_timestamp(job.get("start_time")),
            _parse_timestamp(job.get("end_time")),
            clean_string(job.get("job_id")) or "",
        ),
        reverse=True,
    )


def _parse_timestamp(value: Any) -> datetime:
    text = clean_string(value)
    if not text:
        return datetime.min.replace(tzinfo=UTC)
    normalized = text.replace("Z", "+00:00")
    for parser in (
        lambda item: datetime.fromisoformat(item),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
        lambda item: datetime.strptime(item, "%m/%d/%Y %I:%M:%S %p"),
        lambda item: datetime.strptime(item, "%m/%d/%Y %H:%M:%S"),
        lambda item: datetime.strptime(item, "%b %d, %Y %I:%M:%S %p"),
    ):
        try:
            parsed = parser(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=UTC)
