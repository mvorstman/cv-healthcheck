from __future__ import annotations

import logging
from typing import Any

from cvhealthcheck.reportsplus.checklist import normalize_check, normalize_status
from cvhealthcheck.security_assessment.artifact import (
    SECURITY_ASSESSMENT_CATALOG_DIR,
    build_security_assessment_artifact,
    summarize_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.service import (
    SecurityAssessmentService,
    load_active_security_assessment_artifact,
    persist_security_assessment_artifact,
)

from .catalog import collected_at, read_json, write_json
from .client import ReportsPlusClient
from .extract_report import REPORTSPLUS_CATALOG_DIR, extract_report

SECURITY_ASSESSMENT_REPORT_ID = "336"
NORMALIZED_ARTIFACT = "latest.json"
SECTION_ORDER = [
    "Access Security",
    "Auditing",
    "Platform Security",
    "Company and Owners Security",
    "Capabilities",
    "Hardening",
]
logger = logging.getLogger(__name__)


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
    artifact_paths = persist_security_assessment_artifact(normalized).get("artifact_paths", {})
    normalized = load_active_security_assessment_artifact()
    normalized["artifact"] = artifact_paths["latest"]
    normalized["artifact_paths"] = artifact_paths
    write_json(
        "report_336_security_assessment_rest_snapshot.json",
        normalized,
        catalog_dir=REPORTSPLUS_CATALOG_DIR,
    )
    return {
        "extraction": extraction,
        "normalized": normalized,
        "artifact": artifact_paths["latest"],
    }


def load_security_assessment_artifact() -> dict[str, Any]:
    path = SECURITY_ASSESSMENT_CATALOG_DIR / NORMALIZED_ARTIFACT
    payload = SecurityAssessmentService(
        catalog_dir=SECURITY_ASSESSMENT_CATALOG_DIR
    ).get_current()
    logger.info(
        "Loaded Security Assessment artifact path=%s imported_at=%s source_type=%s finding_count=%s first_finding=%s",
        payload.get("file_path") or path,
        payload.get("imported_at"),
        payload.get("source_type"),
        payload.get("finding_count"),
        _finding_preview(payload.get("findings", [])),
    )
    return payload


def security_assessment_status() -> dict[str, Any]:
    try:
        payload = load_security_assessment_artifact()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": str(SECURITY_ASSESSMENT_CATALOG_DIR / NORMALIZED_ARTIFACT),
        }
    return {
        "exists": True,
        "path": str(payload.get("file_path") or (SECURITY_ASSESSMENT_CATALOG_DIR / NORMALIZED_ARTIFACT)),
        "collected_at": payload.get("imported_at"),
        "source_type": payload.get("source_type"),
        "report_id": payload.get("source", {}).get("report_id"),
        "report_name": payload.get("source", {}).get("report_name"),
        "finding_count": payload.get("finding_count", 0),
    }


def security_assessment_quick_hc() -> dict[str, Any]:
    try:
        payload = load_security_assessment_artifact()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": str(SECURITY_ASSESSMENT_CATALOG_DIR / NORMALIZED_ARTIFACT),
            "summary": None,
        }
    summary = summarize_security_assessment_artifact(payload, SECTION_ORDER)
    return {
        "exists": True,
        "path": str(payload.get("file_path") or (SECURITY_ASSESSMENT_CATALOG_DIR / NORMALIZED_ARTIFACT)),
        "collected_at": payload.get("imported_at"),
        "source": payload.get("source", {}),
        "source_type": payload.get("source_type"),
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

    findings: list[dict[str, Any]] = []
    for dataset in normalized_datasets:
        fallback_section = str(dataset.get("dataset_name") or "").strip()
        for row in dataset.get("sample_rows") or []:
            check = normalize_check(row, fallback_section=fallback_section)
            if not check:
                continue
            findings.append(
                {
                    "section": check.get("section") or fallback_section or "Other",
                    "parameter": check.get("parameter"),
                    "status": normalize_status(check.get("status")),
                    "remarks": check.get("remarks"),
                    "action": _stringify_action(check.get("action")),
                }
            )

    source = {
            "report_id": SECURITY_ASSESSMENT_REPORT_ID,
            "report_name": summary.get("report_name") or "Security Assessment",
            "source_endpoint": extraction.get("report", {}).get("url"),
            "http_status": summary.get("report_http_status"),
            "ok": summary.get("report_ok"),
    }
    artifact = build_security_assessment_artifact(
        findings,
        source_type="rest",
        source=source,
        imported_at=collected_at(),
        extra={
            "artifacts": extraction.get("artifacts", {}),
            "rest_summary": {
            "widget_count": summary.get("widget_count", 0),
            "dataset_count": summary.get("dataset_count", 0),
            "execution_count": summary.get("execution_count", 0),
            "executions_ok": summary.get("executions_ok", 0),
            },
            "widgets": extraction.get("widgets", []),
            "datasets": normalized_datasets,
        },
    )
    artifact["source"]["report_http_status"] = summary.get("report_http_status")
    artifact["source"]["report_ok"] = summary.get("report_ok")
    return artifact


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


def _stringify_action(value: Any) -> str:
    if isinstance(value, dict):
        label = str(value.get("label") or "").strip()
        href = str(value.get("href") or "").strip()
        if label and href:
            return f"{label} ({href})"
        return label or href
    if value is None:
        return ""
    return str(value).strip()


def _finding_preview(findings: Any) -> str:
    if not isinstance(findings, list) or not findings:
        return "none"
    first = findings[0]
    if not isinstance(first, dict):
        return str(first)[:160]
    section = str(first.get("section") or "").strip()
    parameter = str(first.get("parameter") or "").strip()
    status = str(first.get("status") or "").strip()
    return f"{section} | {parameter} | {status}"[:160]
