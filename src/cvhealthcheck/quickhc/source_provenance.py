from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from cvhealthcheck.reportsplus.backup_job_summary import (
    BACKUP_JOB_SUMMARY_ARTIFACT_NAME,
    BACKUP_JOB_SUMMARY_DATASET_GUID,
    BACKUP_JOB_SUMMARY_REPORT_NAME,
)

STATUS_LABELS = {
    "available": "Available",
    "validated": "Validated",
    "not_available": "Not available",
    "not_implemented": "Not implemented",
    "not_tested": "Not tested",
    "not_applicable": "Not applicable",
}

STATUS_BADGE_CLASSES = {
    "available": "badge-available",
    "validated": "badge-good",
    "not_available": "badge-warning",
    "not_implemented": "badge-muted",
    "not_tested": "badge-info",
    "not_applicable": "badge-muted",
}

ACTIVE_STATUSES = {"available", "validated"}

SOURCE_ORDER = (
    "rest_api",
    "reports_plus",
    "csv",
    "html",
    "artifact",
    "manual",
)


@dataclass(frozen=True)
class SourceProvenanceItem:
    source_type: str
    label: str
    status: str
    description: str | None = None
    endpoint: str | None = None
    artifact_path: str | None = None
    dataset_guid: str | None = None
    report_name: str | None = None
    generated_at: str | None = None
    row_count: int | None = None
    notes: str | None = None

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status.replace("_", " ").title())

    @property
    def badge_class(self) -> str:
        return STATUS_BADGE_CLASSES.get(self.status, "badge-muted")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["active"] = self.active
        payload["status_label"] = self.status_label
        payload["badge_class"] = self.badge_class
        return payload


def build_backup_job_summary_provenance(
    artifact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    artifact_exists = isinstance(artifact, dict)
    artifact_path = (
        f"data/catalog/quickhc/{BACKUP_JOB_SUMMARY_ARTIFACT_NAME}"
        if artifact_exists
        else None
    )
    return _serialize_items(
        [
            SourceProvenanceItem(
                source_type="reports_plus",
                label="Reports Plus dataset/report",
                status="validated",
                description="Primary collector path for Backup Job Summary.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=BACKUP_JOB_SUMMARY_DATASET_GUID,
                report_name=BACKUP_JOB_SUMMARY_REPORT_NAME,
                generated_at=artifact.get("generated_at") if artifact_exists else None,
                row_count=artifact.get("total_jobs") if artifact_exists else None,
            ),
            SourceProvenanceItem(
                source_type="artifact",
                label="Normalized artifact",
                status="available" if artifact_exists else "not_available",
                description="Local normalized Quick HC artifact used by the detail page and report builder.",
                artifact_path=artifact_path,
                generated_at=artifact.get("generated_at") if artifact_exists else None,
                row_count=artifact.get("total_jobs") if artifact_exists else None,
            ),
            SourceProvenanceItem(
                source_type="rest_api",
                label="REST API",
                status="not_applicable",
                description="This tile currently relies on Reports Plus rather than a direct operational REST endpoint.",
            ),
            SourceProvenanceItem(
                source_type="csv",
                label="CSV import",
                status="not_implemented",
                description="No CSV import pipeline exists for Backup Job Summary yet.",
            ),
            SourceProvenanceItem(
                source_type="html",
                label="HTML import",
                status="not_implemented",
                description="No HTML import pipeline exists for Backup Job Summary yet.",
            ),
            SourceProvenanceItem(
                source_type="manual",
                label="Manual/static source",
                status="not_applicable",
                description="No manual/static backup job summary source is currently used.",
            ),
        ]
    )


def build_license_summary_provenance(
    artifact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    artifact_exists = isinstance(artifact, dict)
    source_type = str((artifact or {}).get("source_type") or "").lower()
    imported_at = (artifact or {}).get("imported_at")
    generated_on = (artifact or {}).get("generated_on")
    source_metadata = dict((artifact or {}).get("source_metadata") or (artifact or {}).get("source") or {})
    dataset_guid = _first_dataset_guid(source_metadata)
    report_name = (
        source_metadata.get("report_name")
        or source_metadata.get("dataset_name")
        or "License Summary"
    )
    return _serialize_items(
        [
            SourceProvenanceItem(
                source_type="reports_plus",
                label="Reports Plus dataset/report",
                status="validated",
                description="Live collection path for License Summary.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=dataset_guid,
                report_name=report_name,
                generated_at=generated_on,
                row_count=_license_row_count(artifact),
                notes="Active source" if source_type == "rest" else None,
            ),
            SourceProvenanceItem(
                source_type="csv",
                label="CSV import",
                status="validated",
                description="Offline CSV import path for License Summary.",
                generated_at=generated_on,
                row_count=_license_row_count(artifact),
                notes="Active source" if source_type == "csv" else None,
            ),
            SourceProvenanceItem(
                source_type="html",
                label="HTML import",
                status="validated",
                description="Offline HTML import path for License Summary.",
                generated_at=generated_on,
                row_count=_license_row_count(artifact),
                notes="Active source" if source_type == "html" else None,
            ),
            SourceProvenanceItem(
                source_type="artifact",
                label="Normalized artifact",
                status="available" if artifact_exists else "not_available",
                description="Registry-backed canonical License Summary artifact.",
                artifact_path=(artifact or {}).get("file_path") or "data/catalog/license_summary/latest.json",
                generated_at=imported_at,
                row_count=_license_row_count(artifact),
            ),
            SourceProvenanceItem(
                source_type="rest_api",
                label="REST API",
                status="not_applicable",
                description="License Summary is collected through Reports Plus rather than a dedicated operational REST endpoint.",
            ),
            SourceProvenanceItem(
                source_type="manual",
                label="Manual/static source",
                status="not_applicable",
                description="No manual/static license source is currently used.",
            ),
        ]
    )


def build_security_assessment_provenance(
    assessment: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    exists = bool((assessment or {}).get("exists"))
    source = dict((assessment or {}).get("source") or {})
    source_type = str((assessment or {}).get("source_type") or "").lower()
    return _serialize_items(
        [
            SourceProvenanceItem(
                source_type="reports_plus",
                label="Reports Plus dataset/report",
                status="validated",
                description="Primary source for the Security Assessment tile.",
                endpoint="/commandcenter/api/cr/reportsplusengine/reports/336",
                dataset_guid=_first_dataset_guid(source),
                report_name=source.get("report_name") or "Security Assessment",
                generated_at=(assessment or {}).get("collected_at"),
                row_count=_security_row_count(assessment),
                notes="Active source" if source_type == "rest" else None,
            ),
            SourceProvenanceItem(
                source_type="csv",
                label="CSV import",
                status="validated",
                description="Offline CSV import path for Security Assessment.",
                generated_at=(assessment or {}).get("collected_at"),
                row_count=_security_row_count(assessment),
                notes="Active source" if source_type == "csv" else None,
            ),
            SourceProvenanceItem(
                source_type="html",
                label="HTML import",
                status="validated",
                description="Offline HTML import path for Security Assessment.",
                generated_at=(assessment or {}).get("collected_at"),
                row_count=_security_row_count(assessment),
                notes="Active source" if source_type == "html" else None,
            ),
            SourceProvenanceItem(
                source_type="artifact",
                label="Normalized artifact",
                status="available" if exists else "not_available",
                description="Canonical Security Assessment artifact.",
                artifact_path=(assessment or {}).get("path") or "data/imports/security_assessment/latest.json",
                generated_at=(assessment or {}).get("collected_at"),
                row_count=_security_row_count(assessment),
            ),
            SourceProvenanceItem(
                source_type="rest_api",
                label="REST API",
                status="not_applicable",
                description="Security Assessment uses Reports Plus rather than a direct Command Center REST endpoint.",
            ),
            SourceProvenanceItem(
                source_type="manual",
                label="Manual/static source",
                status="not_applicable",
                description="No manual/static security assessment source is currently used.",
            ),
        ]
    )


def build_commcell_provenance(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    source = dict((result or {}).get("source") or {})
    status = "validated" if (result or {}).get("http_status") == 200 else "not_available"
    return _serialize_items(
        [
            SourceProvenanceItem(
                source_type="rest_api",
                label="REST API",
                status=status,
                description="Direct CommCell identity endpoint.",
                endpoint=source.get("endpoint"),
                generated_at=(result or {}).get("collected_at"),
                notes=source.get("auth"),
            ),
            SourceProvenanceItem(
                source_type="artifact",
                label="Normalized artifact",
                status="available" if source.get("method") == "cache" else "not_available",
                description="Cached CommCell identity payload used when live authentication is unavailable.",
                artifact_path="data/catalog/rest/commserv.json" if source.get("method") == "cache" else None,
                generated_at=(result or {}).get("collected_at"),
            ),
            SourceProvenanceItem(
                source_type="reports_plus",
                label="Reports Plus dataset/report",
                status="not_applicable",
                description="CommCell identity is not sourced from Reports Plus.",
            ),
            SourceProvenanceItem(
                source_type="csv",
                label="CSV import",
                status="not_applicable",
                description="No CSV import path exists for CommCell identity.",
            ),
            SourceProvenanceItem(
                source_type="html",
                label="HTML import",
                status="not_applicable",
                description="No HTML import path exists for CommCell identity.",
            ),
            SourceProvenanceItem(
                source_type="manual",
                label="Manual/static source",
                status="not_applicable",
                description="No manual/static source is currently used.",
            ),
        ]
    )


def build_metric_provenance(
    metric: dict[str, Any] | None,
    *,
    artifact_name: str,
    report_name: str,
) -> list[dict[str, Any]]:
    source = dict((metric or {}).get("source") or {})
    exists = isinstance(metric, dict) and bool(metric)
    return _serialize_items(
        [
            SourceProvenanceItem(
                source_type="reports_plus",
                label="Reports Plus dataset/report",
                status="validated",
                description="Metrics-based operational source used by this tile.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=source.get("dataset_guid"),
                report_name=source.get("dataset_name") or report_name,
                generated_at=(metric or {}).get("collected_at"),
                row_count=(metric or {}).get("record_count"),
            ),
            SourceProvenanceItem(
                source_type="artifact",
                label="Normalized artifact",
                status="available" if exists else "not_available",
                description="Local normalized metric artifact used by the Quick HC detail page.",
                artifact_path=f"data/catalog/metrics/{artifact_name}.json",
                generated_at=(metric or {}).get("collected_at"),
                row_count=(metric or {}).get("record_count"),
            ),
            SourceProvenanceItem(
                source_type="rest_api",
                label="REST API",
                status="not_applicable",
                description="This tile is currently backed by Metrics / Reports Plus, not a dedicated REST endpoint.",
            ),
            SourceProvenanceItem(
                source_type="csv",
                label="CSV import",
                status="not_applicable",
                description="No CSV import path exists for this tile.",
            ),
            SourceProvenanceItem(
                source_type="html",
                label="HTML import",
                status="not_applicable",
                description="No HTML import path exists for this tile.",
            ),
            SourceProvenanceItem(
                source_type="manual",
                label="Manual/static source",
                status="not_applicable",
                description="No manual/static source is currently used.",
            ),
        ]
    )


def _serialize_items(items: list[SourceProvenanceItem]) -> list[dict[str, Any]]:
    by_type = {item.source_type: item for item in items}
    ordered = [by_type[source_type] for source_type in SOURCE_ORDER if source_type in by_type]
    return [item.to_dict() for item in ordered]


def _first_dataset_guid(source: dict[str, Any]) -> str | None:
    for key in ("dataset_guid", "source_dataset_guid", "guid"):
        value = source.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _license_row_count(artifact: dict[str, Any] | None) -> int | None:
    if not isinstance(artifact, dict):
        return None
    return (
        len(artifact.get("other_licenses") or [])
        + len(artifact.get("agent_feature_licenses") or [])
        + sum(len(section.get("rows") or []) for section in artifact.get("workload_summary_sections") or [])
    )


def _security_row_count(assessment: dict[str, Any] | None) -> int | None:
    summary = (assessment or {}).get("summary") or {}
    counters = summary.get("counters") or {}
    total = counters.get("Total checks")
    return int(total) if isinstance(total, int) else None
