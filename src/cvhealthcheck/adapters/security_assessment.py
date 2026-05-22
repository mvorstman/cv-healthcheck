from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.artifacts.enums import (
    ArtifactStatus,
    FindingSeverity,
    FindingStatus,
    SourceType,
)
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingReference,
    FindingsSection,
    SummaryMetric,
)
from cvhealthcheck.reportsplus.checklist import normalize_check, normalize_status

REPORT_ID = 336
SUBJECT_ID = "security_assessment"
SUBJECT_TITLE = "Security Assessment"

_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "Critical": FindingSeverity.critical,
    "Warning":  FindingSeverity.warning,
    "Good":     FindingSeverity.good,
    "Info":     FindingSeverity.info,
}


def adapt_reportsplus_rest(extraction: dict[str, Any]) -> CanonicalArtifact:
    summary = extraction.get("summary") or {}
    generated_at = _parse_dt(summary.get("collected_at")) or datetime.now(timezone.utc)

    source = ArtifactSource(
        type=SourceType.reportsplus_rest,
        report_id=REPORT_ID,
        report_name=str(summary.get("report_name") or SUBJECT_TITLE),
        endpoint=_report_endpoint(extraction),
        collected_at=generated_at,
    )

    sections, severity_counts = _build_sections(extraction)

    artifact_summary = ArtifactSummary(
        status=_overall_status(severity_counts),
        metrics=[
            SummaryMetric(id="critical", label="Critical", value=severity_counts["critical"]),
            SummaryMetric(id="warning",  label="Warning",  value=severity_counts["warning"]),
            SummaryMetric(id="good",     label="Good",     value=severity_counts["good"]),
            SummaryMetric(id="info",     label="Info",     value=severity_counts["info"]),
        ],
    )

    return CanonicalArtifact(
        artifact_type=SUBJECT_ID,
        generated_at=generated_at,
        source=source,
        subject=ArtifactSubject(id=SUBJECT_ID, title=SUBJECT_TITLE),
        summary=artifact_summary,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _build_sections(
    extraction: dict[str, Any],
) -> tuple[list[FindingsSection], dict[str, int]]:
    executions_by_guid: dict[str, dict[str, Any]] = {
        e["dataset_guid"]: e
        for e in (extraction.get("executions") or [])
        if isinstance(e, dict) and e.get("dataset_guid")
    }

    severity_counts: dict[str, int] = {"critical": 0, "warning": 0, "good": 0, "info": 0}
    sections: list[FindingsSection] = []

    for dataset in (extraction.get("datasets") or []):
        if not isinstance(dataset, dict):
            continue
        dataset_name = str(dataset.get("dataset_name") or "").strip()
        execution = executions_by_guid.get(str(dataset.get("dataset_guid") or ""), {})
        raw_rows: list[dict[str, Any]] = execution.get("sample_rows") or []

        findings: list[Finding] = []
        for idx, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                continue
            normalized_row = _normalize_row_keys(raw_row)
            check = normalize_check(normalized_row, fallback_section=dataset_name)
            if not check:
                continue
            finding = _build_finding(check, normalized_row, idx)
            findings.append(finding)
            severity_counts[finding.severity.value] = (
                severity_counts.get(finding.severity.value, 0) + 1
            )

        if findings:
            section_id = _to_snake(dataset_name) or f"section_{len(sections)}"
            sections.append(FindingsSection(
                type="findings",
                id=section_id,
                title=dataset_name or section_id,
                items=findings,
            ))

    return sections, severity_counts


def _build_finding(
    check: dict[str, Any],
    normalized_row: dict[str, Any],
    idx: int,
) -> Finding:
    section = str(check.get("section") or "Other")
    severity_label = normalize_status(check.get("status"))
    severity = _SEVERITY_MAP.get(severity_label, FindingSeverity.info)

    finding_id = (
        str(normalized_row.get("attrname") or "").strip()
        or f"{_to_snake(section)}_{idx}"
    )

    action = check.get("action")
    recommendation: str | None = None
    references: list[FindingReference] = []
    if isinstance(action, dict):
        label = str(action.get("label") or "").strip()
        href = str(action.get("href") or "").strip()
        recommendation = label or None
        if href:
            references = [FindingReference(label=label or href, href=href)]
    elif action:
        recommendation = str(action).strip() or None

    return Finding(
        id=finding_id,
        severity=severity,
        status=FindingStatus.open,
        category=section,
        title=str(check.get("parameter") or "").strip(),
        description=str(check.get("remarks") or "").strip() or None,
        recommendation=recommendation,
        references=references,
    )


def _normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {_snake(k): v for k, v in row.items()}


def _snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "field"


def _to_snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _overall_status(counts: dict[str, int]) -> ArtifactStatus:
    if counts.get("critical", 0) > 0:
        return ArtifactStatus.critical
    if counts.get("warning", 0) > 0:
        return ArtifactStatus.warning
    if counts.get("good", 0) > 0 or counts.get("info", 0) > 0:
        return ArtifactStatus.good
    return ArtifactStatus.unknown


def _report_endpoint(extraction: dict[str, Any]) -> str | None:
    report = extraction.get("report")
    if isinstance(report, dict):
        return report.get("url") or None
    return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
