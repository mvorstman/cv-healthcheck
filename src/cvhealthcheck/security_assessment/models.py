from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .normalize import CANONICAL_FINDING_KEYS, DEFAULT_STATUS_KEYS


def _require_text(value: str | None, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    return text


def _optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _ensure_isoish_timestamp(value: str | None, field_name: str) -> str:
    text = _require_text(value, field_name)
    if "T" not in text and ":" not in text:
        raise ValueError(f"{field_name} must be a timestamp string.")
    return text


@dataclass(frozen=True)
class CustomerContext:
    customer_id: str
    customer_name: str = "Unknown Customer"

    def __post_init__(self) -> None:
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "customer_name", _require_text(self.customer_name, "customer_name"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
        }


@dataclass(frozen=True)
class CommCellContext:
    commcell_id: str
    customer_id: str
    commcell_name: str = "Unknown CommCell"

    def __post_init__(self) -> None:
        object.__setattr__(self, "commcell_id", _require_text(self.commcell_id, "commcell_id"))
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "commcell_name", _require_text(self.commcell_name, "commcell_name"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "commcell_id": self.commcell_id,
            "commcell_name": self.commcell_name,
            "customer_id": self.customer_id,
        }


@dataclass(frozen=True)
class EngagementContext:
    engagement_id: str
    customer_id: str
    commcell_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "engagement_id", _require_text(self.engagement_id, "engagement_id"))
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "commcell_id", _require_text(self.commcell_id, "commcell_id"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "engagement_id": self.engagement_id,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
        }


@dataclass(frozen=True)
class ReportStream:
    report_stream_id: str
    customer_id: str
    commcell_id: str
    cadence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_stream_id", _require_text(self.report_stream_id, "report_stream_id"))
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "commcell_id", _require_text(self.commcell_id, "commcell_id"))
        object.__setattr__(self, "cadence", _require_text(self.cadence, "cadence"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_stream_id": self.report_stream_id,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
            "cadence": self.cadence,
        }


@dataclass(frozen=True)
class ReportRun:
    report_run_id: str
    report_stream_id: str
    executed_at: str
    run_sequence: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_run_id", _require_text(self.report_run_id, "report_run_id"))
        object.__setattr__(self, "report_stream_id", _require_text(self.report_stream_id, "report_stream_id"))
        object.__setattr__(self, "executed_at", _ensure_isoish_timestamp(self.executed_at, "executed_at"))
        if self.run_sequence is not None and self.run_sequence < 0:
            raise ValueError("run_sequence must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_run_id": self.report_run_id,
            "report_stream_id": self.report_stream_id,
            "executed_at": self.executed_at,
            "run_sequence": self.run_sequence,
        }


@dataclass(frozen=True)
class ImportRun:
    import_run_id: str
    customer_id: str
    commcell_id: str
    imported_at: str
    engagement_id: str | None = None
    report_stream_id: str | None = None
    report_run_id: str | None = None
    executed_at: str | None = None
    run_sequence: int | None = None
    imported_by: str | None = None
    import_method: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "import_run_id", _require_text(self.import_run_id, "import_run_id"))
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "commcell_id", _require_text(self.commcell_id, "commcell_id"))
        object.__setattr__(self, "imported_at", _ensure_isoish_timestamp(self.imported_at, "imported_at"))
        object.__setattr__(self, "engagement_id", _optional_text(self.engagement_id))
        object.__setattr__(self, "report_stream_id", _optional_text(self.report_stream_id))
        object.__setattr__(self, "report_run_id", _optional_text(self.report_run_id))
        object.__setattr__(self, "executed_at", _optional_text(self.executed_at))
        object.__setattr__(self, "imported_by", _optional_text(self.imported_by))
        object.__setattr__(self, "import_method", _optional_text(self.import_method))
        if self.run_sequence is not None and self.run_sequence < 0:
            raise ValueError("run_sequence must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_run_id": self.import_run_id,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
            "engagement_id": self.engagement_id,
            "report_stream_id": self.report_stream_id,
            "report_run_id": self.report_run_id,
            "imported_at": self.imported_at,
            "executed_at": self.executed_at,
            "run_sequence": self.run_sequence,
            "imported_by": self.imported_by,
            "import_method": self.import_method,
        }


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    import_run_id: str
    artifact_type: str
    source_type: str
    file_path: str
    customer_id: str
    commcell_id: str
    imported_at: str
    source_file: str | None = None
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _require_text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "import_run_id", _require_text(self.import_run_id, "import_run_id"))
        object.__setattr__(self, "artifact_type", _require_text(self.artifact_type, "artifact_type"))
        object.__setattr__(self, "source_type", _require_text(self.source_type, "source_type"))
        object.__setattr__(self, "file_path", _require_text(self.file_path, "file_path"))
        object.__setattr__(self, "customer_id", _require_text(self.customer_id, "customer_id"))
        object.__setattr__(self, "commcell_id", _require_text(self.commcell_id, "commcell_id"))
        object.__setattr__(self, "imported_at", _ensure_isoish_timestamp(self.imported_at, "imported_at"))
        object.__setattr__(self, "source_file", _optional_text(self.source_file))
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
            "artifact_id": self.artifact_id,
            "import_run_id": self.import_run_id,
            "artifact_type": self.artifact_type,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "file_path": self.file_path,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
            "engagement_id": self.engagement_id,
            "report_stream_id": self.report_stream_id,
            "report_run_id": self.report_run_id,
            "imported_at": self.imported_at,
            "executed_at": self.executed_at,
            "run_sequence": self.run_sequence,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "retention_policy": self.retention_policy,
            "imported_by": self.imported_by,
            "import_method": self.import_method,
            "source_metadata": dict(self.source_metadata),
        }


@dataclass(frozen=True)
class CanonicalFinding:
    section: str
    parameter: str
    status: str
    remarks: str
    action: str
    source_type: str
    source_file: str | None
    imported_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "section", _require_text(self.section, "section"))
        object.__setattr__(self, "parameter", _require_text(self.parameter, "parameter"))
        object.__setattr__(self, "status", _require_text(self.status, "status"))
        object.__setattr__(self, "remarks", str(self.remarks or ""))
        object.__setattr__(self, "action", str(self.action or ""))
        object.__setattr__(self, "source_type", _require_text(self.source_type, "source_type"))
        object.__setattr__(self, "source_file", _optional_text(self.source_file))
        object.__setattr__(self, "imported_at", _ensure_isoish_timestamp(self.imported_at, "imported_at"))
        if self.status not in DEFAULT_STATUS_KEYS:
            raise ValueError(f"status must be one of {DEFAULT_STATUS_KEYS}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "parameter": self.parameter,
            "status": self.status,
            "remarks": self.remarks,
            "action": self.action,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "imported_at": self.imported_at,
        }


@dataclass(frozen=True)
class SecurityAssessmentArtifact:
    artifact_type: str
    source_type: str
    imported_at: str
    finding_count: int
    status_counts: dict[str, int]
    sections: list[str]
    findings: list[CanonicalFinding]
    source: dict[str, Any]
    source_file: str | None = None
    generated_on: str | None = None
    artifact_id: str | None = None
    import_run_id: str | None = None
    file_path: str | None = None
    customer_id: str | None = None
    commcell_id: str | None = None
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
    rest_summary: dict[str, Any] = field(default_factory=dict)
    widgets: list[Any] = field(default_factory=list)
    datasets: list[Any] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_type", _require_text(self.artifact_type, "artifact_type"))
        object.__setattr__(self, "source_type", _require_text(self.source_type, "source_type"))
        object.__setattr__(self, "imported_at", _ensure_isoish_timestamp(self.imported_at, "imported_at"))
        object.__setattr__(self, "source_file", _optional_text(self.source_file))
        object.__setattr__(self, "generated_on", _optional_text(self.generated_on))
        object.__setattr__(self, "artifact_id", _optional_text(self.artifact_id))
        object.__setattr__(self, "import_run_id", _optional_text(self.import_run_id))
        object.__setattr__(self, "file_path", _optional_text(self.file_path))
        object.__setattr__(self, "customer_id", _optional_text(self.customer_id))
        object.__setattr__(self, "commcell_id", _optional_text(self.commcell_id))
        object.__setattr__(self, "engagement_id", _optional_text(self.engagement_id))
        object.__setattr__(self, "report_stream_id", _optional_text(self.report_stream_id))
        object.__setattr__(self, "report_run_id", _optional_text(self.report_run_id))
        object.__setattr__(self, "executed_at", _optional_text(self.executed_at))
        object.__setattr__(self, "created_at", _optional_text(self.created_at) or self.imported_at)
        object.__setattr__(self, "last_accessed_at", _optional_text(self.last_accessed_at))
        object.__setattr__(self, "retention_policy", _optional_text(self.retention_policy))
        object.__setattr__(self, "imported_by", _optional_text(self.imported_by))
        object.__setattr__(self, "import_method", _optional_text(self.import_method))
        if self.finding_count != len(self.findings):
            raise ValueError("finding_count must match findings length.")
        counts = {status: int(self.status_counts.get(status, 0) or 0) for status in DEFAULT_STATUS_KEYS}
        if sum(counts.values()) != self.finding_count:
            raise ValueError("status_counts must match findings length.")
        object.__setattr__(self, "status_counts", counts)
        if self.run_sequence is not None and self.run_sequence < 0:
            raise ValueError("run_sequence must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "import_run_id": self.import_run_id,
            "customer_id": self.customer_id,
            "commcell_id": self.commcell_id,
            "engagement_id": self.engagement_id,
            "report_stream_id": self.report_stream_id,
            "report_run_id": self.report_run_id,
            "executed_at": self.executed_at,
            "run_sequence": self.run_sequence,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "file_path": self.file_path,
            "is_active": self.is_active,
            "imported_at": self.imported_at,
            "generated_on": self.generated_on,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "retention_policy": self.retention_policy,
            "imported_by": self.imported_by,
            "import_method": self.import_method,
            "source_metadata": dict(self.source_metadata),
            "finding_count": self.finding_count,
            "status_counts": dict(self.status_counts),
            "sections": list(self.sections),
            "findings": [finding.to_dict() for finding in self.findings],
            "source": dict(self.source),
            "artifacts": dict(self.artifacts),
            "rest_summary": dict(self.rest_summary),
            "widgets": list(self.widgets),
            "datasets": list(self.datasets),
            "artifact_paths": dict(self.artifact_paths),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SecurityAssessmentArtifact":
        findings_payload = payload.get("findings") or []
        findings = [
            finding
            if isinstance(finding, CanonicalFinding)
            else CanonicalFinding(
                section=str(finding.get("section") or ""),
                parameter=str(finding.get("parameter") or ""),
                status=str(finding.get("status") or ""),
                remarks=str(finding.get("remarks") or ""),
                action=str(finding.get("action") or ""),
                source_type=str(finding.get("source_type") or ""),
                source_file=finding.get("source_file"),
                imported_at=str(finding.get("imported_at") or ""),
            )
            for finding in findings_payload
            if isinstance(finding, dict)
        ]
        return cls(
            artifact_type=str(payload.get("artifact_type") or ""),
            source_type=str(payload.get("source_type") or ""),
            source_file=payload.get("source_file"),
            file_path=payload.get("file_path"),
            is_active=bool(payload.get("is_active", True)),
            imported_at=str(payload.get("imported_at") or ""),
            generated_on=payload.get("generated_on"),
            artifact_id=payload.get("artifact_id"),
            import_run_id=payload.get("import_run_id"),
            customer_id=payload.get("customer_id"),
            commcell_id=payload.get("commcell_id"),
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
            finding_count=int(payload.get("finding_count") or len(findings)),
            status_counts=dict(payload.get("status_counts") or {}),
            sections=list(payload.get("sections") or []),
            findings=findings,
            source=dict(payload.get("source") or {}),
            artifacts=dict(payload.get("artifacts") or {}),
            rest_summary=dict(payload.get("rest_summary") or {}),
            widgets=list(payload.get("widgets") or []),
            datasets=list(payload.get("datasets") or []),
            artifact_paths=dict(payload.get("artifact_paths") or {}),
        )


CANONICAL_FINDING_KEYS_TUPLE = CANONICAL_FINDING_KEYS
