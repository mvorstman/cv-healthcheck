from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cvhealthcheck.security_assessment.models import (
    ArtifactRecord,
    CommCellContext,
    CustomerContext,
    EngagementContext,
    ImportRun,
    ReportRun,
    ReportStream,
)


def _require_text(value: str | None, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    return text


def _optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"invalid integer value: {value}") from exc


def _ensure_isoish_timestamp(value: str | None, field_name: str) -> str:
    text = _require_text(value, field_name)
    if "T" not in text and ":" not in text:
        raise ValueError(f"{field_name} must be a timestamp string.")
    return text


@dataclass(frozen=True)
class OtherLicense:
    license: str
    available_total: int | None
    used: int | None
    unit: str | None = None
    raw_available_total: str | None = None
    raw_used: str | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "license", _require_text(self.license, "license"))
        object.__setattr__(self, "available_total", _optional_int(self.available_total))
        object.__setattr__(self, "used", _optional_int(self.used))
        object.__setattr__(self, "unit", _optional_text(self.unit))
        object.__setattr__(self, "raw_available_total", _optional_text(self.raw_available_total))
        object.__setattr__(self, "raw_used", _optional_text(self.raw_used))

    def to_dict(self) -> dict[str, Any]:
        return {
            "license": self.license,
            "available_total": self.available_total,
            "used": self.used,
            "unit": self.unit,
            "raw_available_total": self.raw_available_total,
            "raw_used": self.raw_used,
            "raw_fields": dict(self.raw_fields),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OtherLicense":
        return cls(
            license=str(payload.get("license") or ""),
            available_total=payload.get("available_total"),
            used=payload.get("used"),
            unit=payload.get("unit"),
            raw_available_total=payload.get("raw_available_total"),
            raw_used=payload.get("raw_used"),
            raw_fields=dict(payload.get("raw_fields") or {}),
        )


@dataclass(frozen=True)
class AgentFeatureLicense:
    license: str
    permanent_total: int | None
    permanent_used: int | None
    term_total: int | None
    term_used: int | None
    client: str | None = None
    agent: str | None = None
    install_date: str | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "license", _require_text(self.license, "license"))
        object.__setattr__(self, "permanent_total", _optional_int(self.permanent_total))
        object.__setattr__(self, "permanent_used", _optional_int(self.permanent_used))
        object.__setattr__(self, "term_total", _optional_int(self.term_total))
        object.__setattr__(self, "term_used", _optional_int(self.term_used))
        object.__setattr__(self, "client", _optional_text(self.client))
        object.__setattr__(self, "agent", _optional_text(self.agent))
        object.__setattr__(self, "install_date", _optional_text(self.install_date))

    def to_dict(self) -> dict[str, Any]:
        return {
            "license": self.license,
            "permanent_total": self.permanent_total,
            "permanent_used": self.permanent_used,
            "term_total": self.term_total,
            "term_used": self.term_used,
            "client": self.client,
            "agent": self.agent,
            "install_date": self.install_date,
            "raw_fields": dict(self.raw_fields),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentFeatureLicense":
        return cls(
            license=str(payload.get("license") or ""),
            permanent_total=payload.get("permanent_total"),
            permanent_used=payload.get("permanent_used"),
            term_total=payload.get("term_total"),
            term_used=payload.get("term_used"),
            client=payload.get("client"),
            agent=payload.get("agent"),
            install_date=payload.get("install_date"),
            raw_fields=dict(payload.get("raw_fields") or {}),
        )


@dataclass(frozen=True)
class WorkloadSummaryRow:
    license: str
    entitlement_value: str | None
    used: str | None
    usage_percent: str | None = None
    status: str | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "license", _require_text(self.license, "license"))
        object.__setattr__(self, "entitlement_value", _optional_text(self.entitlement_value))
        object.__setattr__(self, "used", _optional_text(self.used))
        object.__setattr__(self, "usage_percent", _optional_text(self.usage_percent))
        object.__setattr__(self, "status", _optional_text(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "license": self.license,
            "entitlement_value": self.entitlement_value,
            "used": self.used,
            "usage_percent": self.usage_percent,
            "status": self.status,
            "raw_fields": dict(self.raw_fields),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkloadSummaryRow":
        return cls(
            license=str(payload.get("license") or ""),
            entitlement_value=payload.get("entitlement_value"),
            used=payload.get("used"),
            usage_percent=payload.get("usage_percent"),
            status=payload.get("status"),
            raw_fields=dict(payload.get("raw_fields") or {}),
        )


@dataclass(frozen=True)
class WorkloadSummarySection:
    section_name: str
    rows: list[WorkloadSummaryRow]

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_name", _require_text(self.section_name, "section_name"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_name": self.section_name,
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkloadSummarySection":
        return cls(
            section_name=str(payload.get("section_name") or ""),
            rows=[
                WorkloadSummaryRow.from_dict(item)
                for item in payload.get("rows") or []
                if isinstance(item, dict)
            ],
        )


@dataclass(frozen=True)
class LicenseSummaryArtifact:
    artifact_type: str
    source_type: str
    imported_at: str
    other_licenses: list[OtherLicense]
    agent_feature_licenses: list[AgentFeatureLicense]
    workload_summary_sections: list[WorkloadSummarySection]
    source: dict[str, Any]
    source_file: str | None = None
    generated_on: str | None = None
    customer_id: str | None = None
    commcell_id: str | None = None
    commcell_name: str | None = None
    commcell_version: str | None = None
    masked_registration_code: str | None = None
    timezone: str | None = None
    last_collection_time: str | None = None
    license_expiry: str | None = None
    last_generation_time: str | None = None
    last_application_time: str | None = None
    artifact_id: str | None = None
    import_run_id: str | None = None
    file_path: str | None = None
    engagement_id: str | None = None
    report_stream_id: str | None = None
    report_run_id: str | None = None
    executed_at: str | None = None
    run_sequence: int | None = None
    is_active: bool = True
    created_at: str | None = None
    last_accessed_at: str | None = None
    retention_policy: str | None = None
    imported_by: str | None = None
    import_method: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    datasets: list[Any] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_type", _require_text(self.artifact_type, "artifact_type"))
        object.__setattr__(self, "source_type", _require_text(self.source_type, "source_type"))
        object.__setattr__(self, "imported_at", _ensure_isoish_timestamp(self.imported_at, "imported_at"))
        object.__setattr__(self, "source_file", _optional_text(self.source_file))
        object.__setattr__(self, "generated_on", _optional_text(self.generated_on))
        object.__setattr__(self, "customer_id", _optional_text(self.customer_id))
        object.__setattr__(self, "commcell_id", _optional_text(self.commcell_id))
        object.__setattr__(self, "commcell_name", _optional_text(self.commcell_name))
        object.__setattr__(self, "commcell_version", _optional_text(self.commcell_version))
        object.__setattr__(self, "masked_registration_code", _optional_text(self.masked_registration_code))
        object.__setattr__(self, "timezone", _optional_text(self.timezone))
        object.__setattr__(self, "last_collection_time", _optional_text(self.last_collection_time))
        object.__setattr__(self, "license_expiry", _optional_text(self.license_expiry))
        object.__setattr__(self, "last_generation_time", _optional_text(self.last_generation_time))
        object.__setattr__(self, "last_application_time", _optional_text(self.last_application_time))
        object.__setattr__(self, "artifact_id", _optional_text(self.artifact_id))
        object.__setattr__(self, "import_run_id", _optional_text(self.import_run_id))
        object.__setattr__(self, "file_path", _optional_text(self.file_path))
        object.__setattr__(self, "engagement_id", _optional_text(self.engagement_id))
        object.__setattr__(self, "report_stream_id", _optional_text(self.report_stream_id))
        object.__setattr__(self, "report_run_id", _optional_text(self.report_run_id))
        object.__setattr__(self, "executed_at", _optional_text(self.executed_at))
        object.__setattr__(self, "created_at", _optional_text(self.created_at) or self.imported_at)
        object.__setattr__(self, "last_accessed_at", _optional_text(self.last_accessed_at))
        object.__setattr__(self, "retention_policy", _optional_text(self.retention_policy))
        object.__setattr__(self, "imported_by", _optional_text(self.imported_by))
        object.__setattr__(self, "import_method", _optional_text(self.import_method))
        if self.run_sequence is not None and self.run_sequence < 0:
            raise ValueError("run_sequence must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "import_run_id": self.import_run_id,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "file_path": self.file_path,
            "is_active": self.is_active,
            "imported_at": self.imported_at,
            "generated_on": self.generated_on,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
            "commcell_name": self.commcell_name,
            "commcell_version": self.commcell_version,
            "masked_registration_code": self.masked_registration_code,
            "timezone": self.timezone,
            "last_collection_time": self.last_collection_time,
            "license_expiry": self.license_expiry,
            "last_generation_time": self.last_generation_time,
            "last_application_time": self.last_application_time,
            "engagement_id": self.engagement_id,
            "report_stream_id": self.report_stream_id,
            "report_run_id": self.report_run_id,
            "executed_at": self.executed_at,
            "run_sequence": self.run_sequence,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "retention_policy": self.retention_policy,
            "imported_by": self.imported_by,
            "import_method": self.import_method,
            "source_metadata": dict(self.source_metadata),
            "other_licenses": [license_item.to_dict() for license_item in self.other_licenses],
            "agent_feature_licenses": [
                license_item.to_dict() for license_item in self.agent_feature_licenses
            ],
            "workload_summary_sections": [
                section.to_dict() for section in self.workload_summary_sections
            ],
            "source": dict(self.source),
            "artifacts": dict(self.artifacts),
            "datasets": list(self.datasets),
            "artifact_paths": dict(self.artifact_paths),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LicenseSummaryArtifact":
        return cls(
            artifact_type=str(payload.get("artifact_type") or ""),
            artifact_id=payload.get("artifact_id"),
            import_run_id=payload.get("import_run_id"),
            source_type=str(payload.get("source_type") or ""),
            source_file=payload.get("source_file"),
            file_path=payload.get("file_path"),
            is_active=bool(payload.get("is_active", True)),
            imported_at=str(payload.get("imported_at") or ""),
            generated_on=payload.get("generated_on"),
            customer_id=payload.get("customer_id"),
            commcell_id=payload.get("commcell_id"),
            commcell_name=payload.get("commcell_name"),
            commcell_version=payload.get("commcell_version"),
            masked_registration_code=payload.get("masked_registration_code"),
            timezone=payload.get("timezone"),
            last_collection_time=payload.get("last_collection_time"),
            license_expiry=payload.get("license_expiry"),
            last_generation_time=payload.get("last_generation_time"),
            last_application_time=payload.get("last_application_time"),
            engagement_id=payload.get("engagement_id"),
            report_stream_id=payload.get("report_stream_id"),
            report_run_id=payload.get("report_run_id"),
            executed_at=payload.get("executed_at"),
            run_sequence=payload.get("run_sequence"),
            created_at=payload.get("created_at"),
            last_accessed_at=payload.get("last_accessed_at"),
            retention_policy=payload.get("retention_policy"),
            imported_by=payload.get("imported_by"),
            import_method=payload.get("import_method"),
            source_metadata=dict(payload.get("source_metadata") or {}),
            other_licenses=[
                OtherLicense.from_dict(item)
                for item in payload.get("other_licenses") or []
                if isinstance(item, dict)
            ],
            agent_feature_licenses=[
                AgentFeatureLicense.from_dict(item)
                for item in payload.get("agent_feature_licenses") or []
                if isinstance(item, dict)
            ],
            workload_summary_sections=[
                WorkloadSummarySection.from_dict(item)
                for item in payload.get("workload_summary_sections") or []
                if isinstance(item, dict)
            ],
            source=dict(payload.get("source") or {}),
            artifacts=dict(payload.get("artifacts") or {}),
            datasets=list(payload.get("datasets") or []),
            artifact_paths=dict(payload.get("artifact_paths") or {}),
        )


__all__ = [
    "AgentFeatureLicense",
    "ArtifactRecord",
    "CommCellContext",
    "CustomerContext",
    "EngagementContext",
    "ImportRun",
    "LicenseSummaryArtifact",
    "OtherLicense",
    "ReportRun",
    "ReportStream",
    "WorkloadSummaryRow",
    "WorkloadSummarySection",
]
