from __future__ import annotations

import logging
from typing import Any

from cvhealthcheck.security_assessment.artifact import (
    SECURITY_ASSESSMENT_CATALOG_DIR,
    summarize_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.service import SecurityAssessmentService

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
        "generated_on": payload.get("generated_on"),
        "source": payload.get("source", {}),
        "source_type": payload.get("source_type"),
        "summary": summary,
    }


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
