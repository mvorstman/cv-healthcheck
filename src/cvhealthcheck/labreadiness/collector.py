from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.reportsplus.client import ReportsPlusClient

from .models import Indicator

CATALOG_DIR = Path("data/catalog")


def collect_indicators() -> dict[str, Indicator]:
    indicators: dict[str, Indicator] = {}
    indicators["commserve_reachable"] = _api_ping_indicator()
    indicators["command_center_reachable"] = indicators["commserve_reachable"]
    indicators["reports_plus_reachable"] = _reports_plus_indicator()

    reports = _read_catalog("reports.json")
    datasets = _read_catalog("datasets.json")
    execution = _read_catalog("execution_validation.json")

    indicators["reports_inventory_count"] = _count_indicator("reports inventory", reports)
    indicators["datasets_inventory_count"] = _count_indicator("datasets inventory", datasets)

    validation_records = _records(execution)
    executable = [
        record for record in validation_records if record.get("status") == "EXECUTABLE"
    ]
    executable_with_records = [
        record for record in executable if (record.get("record_count") or 0) > 0
    ]
    indicators["executable_datasets_count"] = Indicator(
        "executable_datasets_count",
        len(executable),
        "ok" if executable else "missing",
        "Count from data/catalog/execution_validation.json.",
    )
    indicators["executable_datasets_returning_records"] = Indicator(
        "executable_datasets_returning_records",
        len(executable_with_records),
        "ok" if executable_with_records else "missing",
        "Executable datasets with record_count greater than zero.",
    )

    indicators.update(_core_configuration_indicators(datasets))
    indicators.update(_operational_activity_indicators(validation_records))
    return indicators


def _api_ping_indicator() -> Indicator:
    result = CommvaultApiClient().ping()
    return Indicator(
        "commserve_reachable",
        bool(result.ok),
        "ok" if result.ok else "missing",
        f"HTTP {result.status_code}" if result.status_code else (result.error or ""),
    )


def _reports_plus_indicator() -> Indicator:
    result = ReportsPlusClient().list_reports()
    return Indicator(
        "reports_plus_reachable",
        bool(result.ok),
        "ok" if result.ok else "missing",
        f"HTTP {result.status_code}" if result.status_code else (result.error or ""),
    )


def _read_catalog(name: str) -> dict[str, Any]:
    path = CATALOG_DIR / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records", [])
    return records if isinstance(records, list) else []


def _count_indicator(label: str, payload: dict[str, Any]) -> Indicator:
    count = payload.get("record_count")
    if not isinstance(count, int):
        count = len(_records(payload))
    return Indicator(
        f"{label.replace(' ', '_')}_count",
        count,
        "ok" if count > 0 else "missing",
        f"Count from data/catalog/{label.split()[0]}.json.",
    )


def _core_configuration_indicators(datasets_payload: dict[str, Any]) -> dict[str, Indicator]:
    records = _records(datasets_payload)
    text = " ".join(
        str(record.get("dataSet", {}).get("dataSetName", "")) + " "
        + str(record.get("description", ""))
        for record in records
        if isinstance(record, dict)
    ).lower()
    return {
        "mediaagents_count": Indicator("mediaagents_count", None, "unknown", "No mapped source yet."),
        "libraries_count": Indicator("libraries_count", None, "unknown", "No mapped source yet."),
        "storage_policies_or_plans_count": Indicator(
            "storage_policies_or_plans_count",
            None,
            "unknown",
            "No mapped source yet.",
        ),
        "clients_count": Indicator("clients_count", None, "unknown", "No mapped source yet."),
        "companies_or_tenants_count": Indicator(
            "companies_or_tenants_count",
            1 if "tenant" in text or "company" in text or "commcellgroups" in text else 0,
            "partial" if text else "unknown",
            "Inferred only from Reports Plus dataset catalog names; not a real object count.",
        ),
    }


def _operational_activity_indicators(
    validation_records: list[dict[str, Any]],
) -> dict[str, Indicator]:
    audit_records = _record_count_for(validation_records, "AuditTrailDataset")
    company_job_records = _record_count_for(validation_records, "GetCompanyJobStatus")
    return {
        "backup_jobs_present": Indicator(
            "backup_jobs_present",
            company_job_records > 0,
            "ok" if company_job_records > 0 else "missing",
            "Based on GetCompanyJobStatus validation record count.",
        ),
        "successful_backup_jobs_present": Indicator(
            "successful_backup_jobs_present",
            False,
            "missing",
            "No validated dataset currently proves successful backup jobs.",
        ),
        "failed_backup_jobs_present": Indicator(
            "failed_backup_jobs_present",
            company_job_records > 0,
            "partial" if company_job_records > 0 else "missing",
            "GetCompanyJobStatus exposes failed job fields, but current lab returned no rows.",
        ),
        "restore_jobs_present": Indicator(
            "restore_jobs_present",
            False,
            "missing",
            "No validated restore dataset returned operational records.",
        ),
        "alerts_or_events_present": Indicator(
            "alerts_or_events_present",
            False,
            "missing",
            "No validated alerts/events source yet.",
        ),
        "audit_records_present": Indicator(
            "audit_records_present",
            audit_records > 0,
            "ok" if audit_records > 0 else "missing",
            "Based on AuditTrailDataset validation record count.",
        ),
    }


def _record_count_for(records: list[dict[str, Any]], dataset_name: str) -> int:
    for record in records:
        if record.get("dataset_name") == dataset_name:
            value = record.get("record_count")
            return value if isinstance(value, int) else 0
    return 0
