from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cvhealthcheck.reportsplus.catalog import CATALOG_DIR, collected_at, write_json

SECURITY_ASSESSMENT_CATALOG_DIR = CATALOG_DIR / "security_assessment"
DEFAULT_STATUS_KEYS = ("Critical", "Warning", "Info", "Good")
CANONICAL_FINDING_KEYS = (
    "section",
    "parameter",
    "status",
    "remarks",
    "action",
    "source_type",
    "source_file",
    "imported_at",
)
BLOCKED_TEXT_MARKERS = (
    "parameter status remarks action",
    "detailed checks",
    "1 to 3 of 3 entries",
)
MAX_PARAMETER_LENGTH = 300
MAX_STATUS_LENGTH = 40
MAX_FIELD_LENGTH = 4000
MAX_COMBINED_LENGTH = 6000
logger = logging.getLogger(__name__)


def build_security_assessment_artifact(
    findings: list[dict[str, Any]],
    *,
    source_type: str,
    source_file: str | None = None,
    generated_on: str | None = None,
    imported_at: str | None = None,
    source: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    imported_value = imported_at or collected_at()
    normalized_findings: list[dict[str, Any]] = []
    status_counts = {status: 0 for status in DEFAULT_STATUS_KEYS}
    sections: list[str] = []
    seen_sections: set[str] = set()

    for finding in findings:
        normalized = _normalize_finding(
            finding,
            source_type=source_type,
            source_file=source_file,
            imported_at=imported_value,
        )
        if not _is_valid_finding(normalized):
            continue
        section = normalized["section"]
        if section not in seen_sections:
            seen_sections.add(section)
            sections.append(section)
        status = normalized["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        normalized_findings.append(normalized)

    artifact = {
        "artifact_type": "security_assessment",
        "source_type": source_type,
        "source_file": source_file,
        "imported_at": imported_value,
        "generated_on": generated_on,
        "finding_count": len(normalized_findings),
        "status_counts": status_counts,
        "sections": sections,
        "findings": normalized_findings,
        "source": {
            "type": source_type,
            "raw_file_path": source_file,
            **(source or {}),
        },
    }
    if extra:
        artifact.update(extra)
    return artifact


def write_security_assessment_artifact(
    artifact: dict[str, Any],
    *,
    catalog_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR
    source_type = str(artifact.get("source_type") or "unknown").lower()
    latest_source_path = write_json(
        f"latest_{source_type}.json",
        artifact,
        target_dir,
    )
    latest_path = write_json("latest.json", artifact, target_dir)
    logger.info(
        "Wrote Security Assessment artifacts latest=%s latest_source=%s imported_at=%s source_type=%s finding_count=%s first_finding=%s",
        latest_path,
        latest_source_path,
        artifact.get("imported_at"),
        artifact.get("source_type"),
        artifact.get("finding_count"),
        _finding_preview(artifact.get("findings", [])),
    )
    return {
        "latest_source": str(latest_source_path),
        "latest": str(latest_path),
    }


def summarize_security_assessment_artifact(
    artifact: dict[str, Any],
    section_order: list[str] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in artifact.get("findings", []):
        if not isinstance(finding, dict):
            continue
        section = str(finding.get("section") or "Other").strip() or "Other"
        grouped.setdefault(section, []).append(finding)

    ordered_sections: list[str] = []
    seen: set[str] = set()
    for section in section_order or []:
        if section in grouped and section not in seen:
            ordered_sections.append(section)
            seen.add(section)
    for section in artifact.get("sections", []):
        if section in grouped and section not in seen:
            ordered_sections.append(section)
            seen.add(section)
    for section in grouped:
        if section not in seen:
            ordered_sections.append(section)

    findings = [item for section in ordered_sections for item in grouped.get(section, [])]
    counts = dict(artifact.get("status_counts") or {})
    for status in DEFAULT_STATUS_KEYS:
        counts.setdefault(status, 0)

    return {
        "counters": {
            "Critical": counts.get("Critical", 0),
            "Warning": counts.get("Warning", 0),
            "Info": counts.get("Info", 0),
            "Good": counts.get("Good", 0),
            "Total checks": len(findings),
        },
        "highlights": [
            finding
            for finding in findings
            if finding.get("status") in ("Critical", "Warning")
        ],
        "sections": [
            {"name": section, "checks": grouped.get(section, [])}
            for section in ordered_sections
            if grouped.get(section)
        ],
    }


def _normalize_finding(
    finding: dict[str, Any],
    *,
    source_type: str,
    source_file: str | None,
    imported_at: str,
) -> dict[str, Any]:
    canonical = {
        "section": _clean_text(finding.get("section")) or "Other",
        "parameter": _clean_text(finding.get("parameter")),
        "status": _clean_text(finding.get("status")) or "Info",
        "remarks": _clean_text(finding.get("remarks")),
        "action": _clean_text(finding.get("action")),
        "source_type": source_type,
        "source_file": source_file,
        "imported_at": imported_at,
    }
    return {key: canonical[key] for key in CANONICAL_FINDING_KEYS}


def _is_valid_finding(finding: dict[str, Any]) -> bool:
    parameter = str(finding.get("parameter") or "")
    status = str(finding.get("status") or "")
    remarks = str(finding.get("remarks") or "")
    action = str(finding.get("action") or "")

    if not parameter:
        return False
    if status not in DEFAULT_STATUS_KEYS:
        return False
    if len(parameter) > MAX_PARAMETER_LENGTH or len(status) > MAX_STATUS_LENGTH:
        return False
    if len(remarks) > MAX_FIELD_LENGTH or len(action) > MAX_FIELD_LENGTH:
        return False

    combined = "\n".join(
        [
            str(finding.get("section") or ""),
            parameter,
            status,
            remarks,
            action,
        ]
    ).strip()
    lowered = combined.lower()
    if len(combined) > MAX_COMBINED_LENGTH:
        return False
    if lowered == "parameter\nstatus\nremarks\naction":
        return False
    if any(marker in lowered for marker in BLOCKED_TEXT_MARKERS):
        return False
    return True


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
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
