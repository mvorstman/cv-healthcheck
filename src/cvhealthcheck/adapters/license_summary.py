from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    MetricItem,
    MetricSection,
    SummaryMetric,
    TableColumn,
    TableSection,
)

SUBJECT_ID = "license_summary"
SUBJECT_TITLE = "License Summary"

# Legacy source_type strings → canonical SourceType enum members.
_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "csv":  SourceType.csv_import,
    "html": SourceType.html_import,
    "rest": SourceType.rest,
}


def adapt(artifact: dict[str, Any]) -> CanonicalArtifact:
    source_type_str = str(artifact.get("source_type") or "rest").lower()
    source_type = _SOURCE_TYPE_MAP.get(source_type_str, SourceType.rest)

    imported_at = _parse_dt(artifact.get("imported_at")) or datetime.now(timezone.utc)
    collected_at = _parse_dt(artifact.get("last_collection_time")) or imported_at

    source = ArtifactSource(
        type=source_type,
        collected_at=collected_at,
        imported_at=imported_at,
    )

    return CanonicalArtifact(
        artifact_type=SUBJECT_ID,
        generated_at=imported_at,
        source=source,
        subject=ArtifactSubject(id=SUBJECT_ID, title=SUBJECT_TITLE),
        summary=_build_summary(artifact),
        sections=_build_sections(artifact),
    )


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------

def _build_sections(artifact: dict[str, Any]) -> list:
    sections: list = []

    info = _commcell_info_section(artifact)
    if info.items:
        sections.append(info)

    other = _other_licenses_section(artifact)
    if other.items:
        sections.append(other)

    agent = _agent_feature_section(artifact)
    if agent.items:
        sections.append(agent)

    sections.extend(_workload_sections(artifact))
    return sections


def _commcell_info_section(artifact: dict[str, Any]) -> MetricSection:
    items: list[MetricItem] = []
    _add_metric(items, "commcell_name",    "CommCell Name",          artifact.get("commcell_name"))
    _add_metric(items, "commcell_version", "CommCell Version",       artifact.get("commcell_version"))
    _add_metric(items, "license_expiry",   "License Expiry",         artifact.get("license_expiry"))
    _add_metric(items, "last_collection",  "Last Collection Time",   artifact.get("last_collection_time"))
    return MetricSection(type="metric", id="commcell_info", title="CommCell Info", items=items)


def _add_metric(items: list[MetricItem], id: str, label: str, value: Any) -> None:
    if value is not None and str(value).strip():
        items.append(MetricItem(id=id, label=label, value=str(value)))


def _other_licenses_section(artifact: dict[str, Any]) -> TableSection:
    columns = [
        TableColumn(id="license",         label="License"),
        TableColumn(id="available_total", label="Available Total"),
        TableColumn(id="used",            label="Used"),
        TableColumn(id="unit",            label="Unit"),
    ]
    items = [
        {
            "license":         str(row.get("license") or ""),
            "available_total": row.get("available_total"),
            "used":            row.get("used"),
            "unit":            row.get("unit"),
        }
        for row in (artifact.get("other_licenses") or [])
        if isinstance(row, dict) and row.get("license")
    ]
    return TableSection(
        type="table", id="other_licenses", title="Other Licenses",
        columns=columns, items=items,
    )


def _agent_feature_section(artifact: dict[str, Any]) -> TableSection:
    columns = [
        TableColumn(id="license",         label="License"),
        TableColumn(id="permanent_total", label="Permanent Total"),
        TableColumn(id="permanent_used",  label="Permanent Used"),
        TableColumn(id="term_total",      label="Term Total"),
        TableColumn(id="term_used",       label="Term Used"),
    ]
    seen: set[str] = set()
    items = []
    for row in (artifact.get("agent_feature_licenses") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("license") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({
            "license":         name,
            "permanent_total": row.get("permanent_total"),
            "permanent_used":  row.get("permanent_used"),
            "term_total":      row.get("term_total"),
            "term_used":       row.get("term_used"),
        })
    return TableSection(
        type="table", id="agent_feature_licenses", title="Agent / Feature Licenses",
        columns=columns, items=items,
    )


def _workload_sections(artifact: dict[str, Any]) -> list[TableSection]:
    columns = [
        TableColumn(id="license",           label="License"),
        TableColumn(id="entitlement_value", label="Entitlement"),
        TableColumn(id="used",              label="Used"),
        TableColumn(id="usage_percent",     label="Used %"),
        TableColumn(id="status",            label="Status"),
    ]
    result: list[TableSection] = []
    for ws in (artifact.get("workload_summary_sections") or []):
        if not isinstance(ws, dict):
            continue
        section_name = str(ws.get("section_name") or "").strip()
        if not section_name:
            continue
        section_id = _to_snake(section_name) or f"workload_{len(result)}"
        items = [
            {
                "license":           str(row.get("license") or ""),
                "entitlement_value": row.get("entitlement_value"),
                "used":              row.get("used"),
                "usage_percent":     row.get("usage_percent"),
                "status":            row.get("status"),
            }
            for row in (ws.get("rows") or [])
            if isinstance(row, dict) and row.get("license")
        ]
        if items:
            result.append(TableSection(
                type="table", id=section_id, title=section_name,
                columns=columns, items=items,
            ))
    return result


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def _build_summary(artifact: dict[str, Any]) -> ArtifactSummary:
    other = list(artifact.get("other_licenses") or [])
    agent_names = {
        str(row.get("license"))
        for row in (artifact.get("agent_feature_licenses") or [])
        if isinstance(row, dict) and row.get("license")
    }
    other_count = len(other)
    agent_count = len(agent_names)
    status = ArtifactStatus.good if (other or agent_names) else ArtifactStatus.unknown
    return ArtifactSummary(
        status=status,
        metrics=[
            SummaryMetric(id="other_license_count",  label="Other Licenses",          value=other_count),
            SummaryMetric(id="agent_feature_count",  label="Agent / Feature Licenses", value=agent_count),
        ],
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _to_snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


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
