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

SOURCE_ORDER = ("rest_reports_plus", "csv", "html")


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
    primary: bool = False

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
    return _serialize_items(
        [
            _method_item(
                "rest_reports_plus",
                label="REST / Reports Plus",
                status="validated",
                description="Live Reports Plus dataset-backed collection path for Backup Job Summary.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=BACKUP_JOB_SUMMARY_DATASET_GUID,
                report_name=BACKUP_JOB_SUMMARY_REPORT_NAME,
                generated_at=artifact.get("generated_at") if artifact_exists else None,
                row_count=artifact.get("total_jobs") if artifact_exists else None,
                artifact_path=(
                    f"data/catalog/quickhc/{BACKUP_JOB_SUMMARY_ARTIFACT_NAME}"
                    if artifact_exists
                    else None
                ),
                primary=True,
            ),
            _method_item(
                "csv",
                label="CSV",
                status="not_implemented",
                description="No CSV import pipeline exists for Backup Job Summary yet.",
            ),
            _method_item(
                "html",
                label="HTML",
                status="not_implemented",
                description="No HTML import pipeline exists for Backup Job Summary yet.",
            ),
        ]
    )


def build_license_summary_provenance(
    artifact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    artifact_exists = isinstance(artifact, dict)
    source_type = str((artifact or {}).get("source_type") or "").lower()
    primary_method = _normalized_primary_method(source_type, default="rest_reports_plus")
    generated_on = (artifact or {}).get("generated_on")
    source_metadata = dict((artifact or {}).get("source_metadata") or (artifact or {}).get("source") or {})
    dataset_guid = _first_dataset_guid(source_metadata)
    report_name = (
        source_metadata.get("report_name")
        or source_metadata.get("dataset_name")
        or "License Summary"
    )
    row_count = _license_row_count(artifact)
    artifact_path = (
        (artifact or {}).get("file_path") or "data/catalog/license_summary/latest.json"
        if artifact_exists
        else None
    )
    return _serialize_items(
        [
            _method_item(
                "rest_reports_plus",
                label="REST / Reports Plus",
                status="validated",
                description="Live Reports Plus collection path for License Summary.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=dataset_guid if primary_method == "rest_reports_plus" else None,
                report_name=report_name if primary_method == "rest_reports_plus" else None,
                generated_at=generated_on if primary_method == "rest_reports_plus" else None,
                row_count=row_count if primary_method == "rest_reports_plus" else None,
                artifact_path=artifact_path if primary_method == "rest_reports_plus" else None,
                primary=primary_method == "rest_reports_plus",
            ),
            _method_item(
                "csv",
                label="CSV",
                status="validated",
                description="Offline CSV import path for License Summary.",
                generated_at=generated_on if primary_method == "csv" else None,
                row_count=row_count if primary_method == "csv" else None,
                artifact_path=artifact_path if primary_method == "csv" else None,
                primary=primary_method == "csv",
            ),
            _method_item(
                "html",
                label="HTML",
                status="validated",
                description="Offline HTML import path for License Summary.",
                generated_at=generated_on if primary_method == "html" else None,
                row_count=row_count if primary_method == "html" else None,
                artifact_path=artifact_path if primary_method == "html" else None,
                primary=primary_method == "html",
            ),
        ]
    )


def build_security_assessment_provenance(
    assessment: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    source = dict((assessment or {}).get("source") or {})
    source_type = str((assessment or {}).get("source_type") or "").lower()
    primary_method = _normalized_primary_method(source_type, default="rest_reports_plus")
    generated_at = (assessment or {}).get("collected_at")
    row_count = _security_row_count(assessment)
    artifact_path = (assessment or {}).get("path") if (assessment or {}).get("exists") else None
    return _serialize_items(
        [
            _method_item(
                "rest_reports_plus",
                label="REST / Reports Plus",
                status="validated",
                description="Reports Plus-backed Security Assessment collection path.",
                endpoint="/commandcenter/api/cr/reportsplusengine/reports/336",
                dataset_guid=_first_dataset_guid(source) if primary_method == "rest_reports_plus" else None,
                report_name=(source.get("report_name") or "Security Assessment")
                if primary_method == "rest_reports_plus"
                else None,
                generated_at=generated_at if primary_method == "rest_reports_plus" else None,
                row_count=row_count if primary_method == "rest_reports_plus" else None,
                artifact_path=artifact_path if primary_method == "rest_reports_plus" else None,
                primary=primary_method == "rest_reports_plus",
            ),
            _method_item(
                "csv",
                label="CSV",
                status="validated",
                description="Offline CSV import path for Security Assessment.",
                generated_at=generated_at if primary_method == "csv" else None,
                row_count=row_count if primary_method == "csv" else None,
                artifact_path=artifact_path if primary_method == "csv" else None,
                primary=primary_method == "csv",
            ),
            _method_item(
                "html",
                label="HTML",
                status="validated",
                description="Offline HTML import path for Security Assessment.",
                generated_at=generated_at if primary_method == "html" else None,
                row_count=row_count if primary_method == "html" else None,
                artifact_path=artifact_path if primary_method == "html" else None,
                primary=primary_method == "html",
            ),
        ]
    )


def build_commcell_provenance(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    source = dict((result or {}).get("source") or {})
    live_success = (result or {}).get("http_status") == 200
    rest_status = "validated" if live_success else ("available" if result else "not_available")
    artifact_path = "data/catalog/rest/commserv.json" if source.get("method") == "cache" else None
    return _serialize_items(
        [
            _method_item(
                "rest_reports_plus",
                label="REST / Reports Plus",
                status=rest_status,
                description="Direct CommCell identity collection path via REST.",
                endpoint=source.get("endpoint"),
                generated_at=(result or {}).get("collected_at"),
                artifact_path=artifact_path,
                notes=source.get("auth"),
                primary=True,
            ),
            _method_item(
                "csv",
                label="CSV",
                status="not_applicable",
                description="No CSV import path exists for CommCell identity.",
            ),
            _method_item(
                "html",
                label="HTML",
                status="not_applicable",
                description="No HTML import path exists for CommCell identity.",
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
            _method_item(
                "rest_reports_plus",
                label="REST / Reports Plus",
                status="validated",
                description="Metrics / Reports Plus-backed operational collection path.",
                endpoint="/commandcenter/api/cr/reportsplusengine/datasets/<dataset_guid>/data",
                dataset_guid=source.get("dataset_guid"),
                report_name=source.get("dataset_name") or report_name,
                generated_at=(metric or {}).get("collected_at"),
                row_count=(metric or {}).get("record_count"),
                artifact_path=f"data/catalog/metrics/{artifact_name}.json" if exists else None,
                primary=True,
            ),
            _method_item(
                "csv",
                label="CSV",
                status="not_applicable",
                description="No CSV import path exists for this subject.",
            ),
            _method_item(
                "html",
                label="HTML",
                status="not_applicable",
                description="No HTML import path exists for this subject.",
            ),
        ]
    )


def _serialize_items(items: list[SourceProvenanceItem]) -> list[dict[str, Any]]:
    by_type = {item.source_type: item for item in items}
    ordered = [by_type[source_type] for source_type in SOURCE_ORDER if source_type in by_type]
    return [item.to_dict() for item in ordered]


def _method_item(
    source_type: str,
    *,
    label: str,
    status: str,
    description: str,
    endpoint: str | None = None,
    artifact_path: str | None = None,
    dataset_guid: str | None = None,
    report_name: str | None = None,
    generated_at: str | None = None,
    row_count: int | None = None,
    notes: str | None = None,
    primary: bool = False,
) -> SourceProvenanceItem:
    return SourceProvenanceItem(
        source_type=source_type,
        label=label,
        status=status,
        description=description,
        endpoint=endpoint,
        artifact_path=artifact_path,
        dataset_guid=dataset_guid,
        report_name=report_name,
        generated_at=generated_at,
        row_count=row_count,
        notes=notes,
        primary=primary,
    )


def _normalized_primary_method(source_type: str, *, default: str) -> str:
    normalized = source_type.strip().lower()
    if normalized == "csv":
        return "csv"
    if normalized == "html":
        return "html"
    return default


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
