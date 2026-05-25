from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingsSection,
    SummaryMetric,
    TableColumn,
    TableSection,
)
from cvhealthcheck.extractors.html import ExtractionResult


_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "critical": FindingSeverity.critical,
    "warning":  FindingSeverity.warning,
    "good":     FindingSeverity.good,
    "info":     FindingSeverity.info,
}

_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "html":  SourceType.html_import,
    "csv":   SourceType.csv_import,
    "json":  SourceType.json_import,
    "rest":  SourceType.rest,
}


def result_to_artifact(
    result: ExtractionResult,
    subject_id: str,
    subject_title: str,
    file_path: Path | None = None,
    commcell_id: str | None = None,
    commcell_name: str | None = None,
) -> CanonicalArtifact:
    now = datetime.now(timezone.utc)
    artifact_source_type = _SOURCE_TYPE_MAP.get(
        result.source_type, SourceType.html_import
    )
    source = ArtifactSource(
        type=artifact_source_type,
        imported_at=now,
        commcell_id=commcell_id,
        commcell_name=commcell_name,
    )
    subject = ArtifactSubject(id=subject_id, title=subject_title)

    sections = []
    severity_counts: dict[str, int] = {"critical": 0, "warning": 0, "good": 0, "info": 0}
    has_findings_section = False

    for section_id, rows in result.sections.items():
        output_as = result.section_output_types.get(section_id, "table")
        title = result.section_titles.get(section_id, section_id)

        if output_as == "findings":
            has_findings_section = True
            findings = []
            for row in rows:
                finding = _build_finding(section_id, row)
                findings.append(finding)
                sev = finding.severity.value
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            sections.append(FindingsSection(
                type="findings",
                id=section_id,
                title=title,
                items=findings,
            ))
        else:
            columns = _derive_columns(rows)
            sections.append(TableSection(
                type="table",
                id=section_id,
                title=title,
                columns=columns,
                items=rows,
            ))

    if not has_findings_section:
        has_table_data = any(
            isinstance(s, TableSection) and len(s.items) > 0 for s in sections
        )
        summary = ArtifactSummary(
            status=ArtifactStatus.good if has_table_data else ArtifactStatus.unknown
        )
    else:
        metrics = [
            SummaryMetric(id="critical_count", label="Critical", value=severity_counts["critical"]),
            SummaryMetric(id="warning_count",  label="Warning",  value=severity_counts["warning"]),
            SummaryMetric(id="good_count",     label="Good",     value=severity_counts["good"]),
            SummaryMetric(id="info_count",     label="Info",     value=severity_counts["info"]),
        ]
        summary = ArtifactSummary(
            status=_overall_status(severity_counts),
            metrics=metrics,
        )

    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=now,
        source=source,
        subject=subject,
        summary=summary,
        sections=sections,
    )


def _build_finding(section_id: str, row: dict[str, Any]) -> Finding:
    parameter = str(row.get("parameter") or "")
    finding_id = hashlib.sha256(
        f"{section_id}:{parameter}".encode()
    ).hexdigest()[:12]
    severity_str = str(row.get("severity") or "info")
    severity = _SEVERITY_MAP.get(severity_str, FindingSeverity.info)
    recommendation = row.get("action") or None
    if isinstance(recommendation, str) and not recommendation.strip():
        recommendation = None
    return Finding(
        id=finding_id,
        severity=severity,
        status=FindingStatus.open,
        category=section_id,
        title=parameter,
        description=row.get("remarks") or None,
        recommendation=recommendation,
    )


def _derive_columns(rows: list[dict[str, Any]]) -> list[TableColumn]:
    if not rows:
        return []
    return [TableColumn(id=key, label=key) for key in rows[0].keys()]


def _overall_status(counts: dict[str, int]) -> ArtifactStatus:
    if counts.get("critical", 0) > 0:
        return ArtifactStatus.critical
    if counts.get("warning", 0) > 0:
        return ArtifactStatus.warning
    return ArtifactStatus.good
