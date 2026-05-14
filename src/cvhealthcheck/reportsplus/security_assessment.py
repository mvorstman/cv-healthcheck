from __future__ import annotations

from typing import Any

from .catalog import collected_at, read_json, write_json
from .checklist import checklist_summary
from .client import ReportsPlusClient
from .extract_report import REPORTSPLUS_CATALOG_DIR, extract_report

SECURITY_ASSESSMENT_REPORT_ID = "336"
NORMALIZED_ARTIFACT = "report_336_security_assessment_normalized.json"
SECTION_ORDER = [
    "Access Security",
    "Auditing",
    "Platform Security",
    "Company and Owners Security",
    "Capabilities",
    "Hardening",
]


def extract_security_assessment(
    client: ReportsPlusClient | None = None,
    execute: bool = True,
    sample_limit: int = 50,
) -> dict[str, Any]:
    extraction = extract_report(
        SECURITY_ASSESSMENT_REPORT_ID,
        client=client,
        execute=execute,
        sample_limit=sample_limit,
    )
    normalized = normalize_security_assessment(extraction)
    artifact = write_json(
        NORMALIZED_ARTIFACT,
        normalized,
        catalog_dir=REPORTSPLUS_CATALOG_DIR,
    )
    normalized["artifact"] = str(artifact)
    return {
        "extraction": extraction,
        "normalized": normalized,
        "artifact": str(artifact),
    }


def load_security_assessment_artifact() -> dict[str, Any]:
    return read_json(NORMALIZED_ARTIFACT, catalog_dir=REPORTSPLUS_CATALOG_DIR)


def security_assessment_status() -> dict[str, Any]:
    try:
        payload = load_security_assessment_artifact()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": str(REPORTSPLUS_CATALOG_DIR / NORMALIZED_ARTIFACT),
        }
    return {
        "exists": True,
        "path": str(REPORTSPLUS_CATALOG_DIR / NORMALIZED_ARTIFACT),
        "collected_at": payload.get("collected_at"),
        "report_id": payload.get("source", {}).get("report_id"),
        "report_name": payload.get("source", {}).get("report_name"),
        "dataset_count": len(payload.get("datasets", [])),
        "executable_dataset_count": sum(
            1
            for dataset in payload.get("datasets", [])
            if dataset.get("execution_status") == "EXECUTABLE"
        ),
    }


def security_assessment_quick_hc() -> dict[str, Any]:
    try:
        payload = load_security_assessment_artifact()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": str(REPORTSPLUS_CATALOG_DIR / NORMALIZED_ARTIFACT),
            "summary": None,
        }
    summary = checklist_summary(payload.get("datasets", []), SECTION_ORDER)
    return {
        "exists": True,
        "path": str(REPORTSPLUS_CATALOG_DIR / NORMALIZED_ARTIFACT),
        "collected_at": payload.get("collected_at"),
        "source": payload.get("source", {}),
        "summary": summary,
    }


def normalize_security_assessment(extraction: dict[str, Any]) -> dict[str, Any]:
    summary = extraction.get("summary", {})
    datasets = extraction.get("datasets", [])
    executions = {
        execution.get("dataset_guid"): execution
        for execution in extraction.get("executions", [])
        if isinstance(execution, dict)
    }

    normalized_datasets = []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        execution = executions.get(dataset.get("dataset_guid"), {})
        sample_rows = execution.get("sample_rows") or []
        normalized_datasets.append(
            {
                "dataset_guid": dataset.get("dataset_guid"),
                "dataset_id": dataset.get("dataset_id"),
                "dataset_name": dataset.get("dataset_name"),
                "metadata_status": dataset.get("metadata_status"),
                "metadata_http_status": dataset.get("metadata_http_status"),
                "execution_status": execution.get("status", "NOT_EXECUTED"),
                "execution_http_status": execution.get("http_status"),
                "record_count": execution.get("record_count", 0),
                "required_parameters": dataset.get("required_parameters") or [],
                "default_parameters": dataset.get("default_parameters") or {},
                "available_fields": dataset.get("available_fields") or [],
                "selected_fields": dataset.get("selected_fields") or [],
                "used_by": dataset.get("used_by") or [],
                "raw_artifact": execution.get("raw_artifact"),
                "error": execution.get("error"),
                "sample_rows": [_normalize_row(row) for row in sample_rows],
            }
        )

    return {
        "collected_at": collected_at(),
        "source": {
            "report_id": SECURITY_ASSESSMENT_REPORT_ID,
            "report_name": summary.get("report_name") or "Security Assessment",
            "source_endpoint": extraction.get("report", {}).get("url"),
            "http_status": summary.get("report_http_status"),
            "ok": summary.get("report_ok"),
        },
        "artifacts": extraction.get("artifacts", {}),
        "summary": {
            "widget_count": summary.get("widget_count", 0),
            "dataset_count": summary.get("dataset_count", 0),
            "execution_count": summary.get("execution_count", 0),
            "executions_ok": summary.get("executions_ok", 0),
        },
        "widgets": extraction.get("widgets", []),
        "datasets": normalized_datasets,
    }


def _normalize_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized[_normalize_key(str(key))] = value
    return normalized


def _normalize_key(value: str) -> str:
    import re

    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    return normalized or "field"
