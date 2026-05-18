from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import secrets
from typing import Any, BinaryIO
from uuid import uuid4

from werkzeug.utils import secure_filename

from cvhealthcheck.reportsplus.catalog import collected_at
from cvhealthcheck.reportsplus.client import ReportsPlusClient
from cvhealthcheck.security_assessment.registry import SecurityAssessmentArtifactRegistry

from .artifact import LICENSE_SUMMARY_CATALOG_DIR, write_license_summary_artifact
from .collect_rest import collect_license_summary_rest, import_license_summary_xlsx_recording
from .import_csv import import_license_summary_csv
from .import_html import import_license_summary_html
from .models import (
    ArtifactRecord,
    CommCellContext,
    CustomerContext,
    EngagementContext,
    ImportRun,
    LicenseSummaryArtifact,
    ReportRun,
    ReportStream,
)

LICENSE_SUMMARY_IMPORTS_DIR = Path("data/imports/license_summary")
LICENSE_SUMMARY_REGISTRY_PATH = LICENSE_SUMMARY_IMPORTS_DIR / "artifact_registry.sqlite3"
ALLOWED_EXTENSIONS = {
    ".csv": "csv",
    ".htm": "html",
    ".html": "html",
    ".xlsx": "rest",
}
DEFAULT_CUSTOMER_CONTEXT = CustomerContext(
    customer_id="unknown_customer",
    customer_name="Unknown Customer",
)
DEFAULT_COMMCELL_CONTEXT = CommCellContext(
    commcell_id="unknown_commcell",
    commcell_name="Unknown CommCell",
    customer_id=DEFAULT_CUSTOMER_CONTEXT.customer_id,
)
logger = logging.getLogger(__name__)


class LicenseSummaryImportError(ValueError):
    pass


class LicenseSummaryService:
    def __init__(
        self,
        *,
        catalog_dir: Path | None = None,
        registry_path: Path | None = None,
    ) -> None:
        self.catalog_dir = catalog_dir or LICENSE_SUMMARY_CATALOG_DIR
        self.registry_path = registry_path or LICENSE_SUMMARY_REGISTRY_PATH
        self.registry = SecurityAssessmentArtifactRegistry(self.registry_path)

    def get_current(
        self,
        *,
        customer_context: CustomerContext | None = None,
        commcell_context: CommCellContext | None = None,
        engagement_context: EngagementContext | None = None,
        report_stream: ReportStream | None = None,
        source_type: str | None = None,
        ) -> dict[str, Any]:
        return load_active_license_summary_artifact(
            catalog_dir=self.catalog_dir,
            registry_path=self.registry_path,
            customer_context=customer_context,
            commcell_context=commcell_context,
            engagement_context=engagement_context,
            report_stream=report_stream,
            source_type=source_type,
        )

    def collect_from_rest(
        self,
        *,
        client: ReportsPlusClient | None = None,
        customer_context: CustomerContext | None = None,
        commcell_context: CommCellContext | None = None,
        engagement_context: EngagementContext | None = None,
        report_stream: ReportStream | None = None,
        report_run: ReportRun | None = None,
        imported_by: str | None = None,
    ) -> dict[str, Any]:
        collected = collect_license_summary_rest(
            client=client,
            write_artifact=False,
        )
        normalized = collected["normalized"]
        if normalized.get("source", {}).get("http_status") == 401:
            return {
                "extraction": collected["extraction"],
                "normalized": normalized,
                "artifact": normalized.get("artifact_paths", {}).get("latest"),
            }
        if not normalized.get("other_licenses") and not normalized.get("agent_feature_licenses"):
            raise LicenseSummaryImportError(
                "REST collection produced no License Summary rows."
            )
        persisted = persist_license_summary_artifact(
            normalized,
            catalog_dir=self.catalog_dir,
            registry_path=self.registry_path,
            customer_context=customer_context,
            commcell_context=commcell_context,
            engagement_context=engagement_context,
            report_stream=report_stream,
            report_run=report_run,
            imported_by=imported_by,
            import_method="rest",
        )
        return {
            "extraction": collected["extraction"],
            "normalized": persisted,
            "artifact": persisted.get("artifact_paths", {}).get("latest"),
        }


def import_license_summary_upload(
    stream: BinaryIO,
    *,
    original_filename: str,
    imports_dir: Path | None = None,
    catalog_dir: Path | None = None,
    registry_path: Path | None = None,
    customer_context: CustomerContext | None = None,
    commcell_context: CommCellContext | None = None,
    engagement_context: EngagementContext | None = None,
    report_stream: ReportStream | None = None,
    report_run: ReportRun | None = None,
    imported_by: str | None = None,
) -> dict[str, Any]:
    safe_name = secure_filename(original_filename or "")
    if not safe_name:
        raise LicenseSummaryImportError("No file selected.")

    extension = Path(safe_name).suffix.lower()
    source_type = ALLOWED_EXTENSIONS.get(extension)
    if source_type is None:
        raise LicenseSummaryImportError(
            "Unsupported file type. Upload a License Summary CSV, HTML, or XLSX API viewer recording."
        )

    saved_path = _save_upload(
        stream,
        safe_name,
        imports_dir=imports_dir or LICENSE_SUMMARY_IMPORTS_DIR,
    )
    if source_type == "html":
        artifact = import_license_summary_html(saved_path, write_artifact=False)
    elif source_type == "csv":
        artifact = import_license_summary_csv(saved_path, write_artifact=False)
    else:
        artifact = import_license_summary_xlsx_recording(saved_path, write_artifact=False)

    if not artifact.get("other_licenses") and not artifact.get("agent_feature_licenses"):
        raise LicenseSummaryImportError(f"{source_type.upper()} import produced no license rows.")

    return persist_license_summary_artifact(
        artifact,
        catalog_dir=catalog_dir,
        registry_path=registry_path,
        customer_context=customer_context,
        commcell_context=commcell_context,
        engagement_context=engagement_context,
        report_stream=report_stream,
        report_run=report_run,
        imported_by=imported_by,
    )


def persist_license_summary_artifact(
    artifact: dict[str, Any],
    *,
    catalog_dir: Path | None = None,
    registry_path: Path | None = None,
    customer_context: CustomerContext | None = None,
    commcell_context: CommCellContext | None = None,
    engagement_context: EngagementContext | None = None,
    report_stream: ReportStream | None = None,
    report_run: ReportRun | None = None,
    imported_by: str | None = None,
    import_method: str | None = None,
    retention_policy: str | None = None,
) -> dict[str, Any]:
    customer = customer_context or DEFAULT_CUSTOMER_CONTEXT
    commcell = commcell_context or CommCellContext(
        commcell_id=(commcell_context.commcell_id if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_id),
        commcell_name=(commcell_context.commcell_name if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_name),
        customer_id=customer.customer_id,
    )
    imported_at = str(artifact.get("imported_at") or collected_at())
    created_at = str(artifact.get("created_at") or imported_at)
    import_run_id = str(artifact.get("import_run_id") or f"imprun_{uuid4().hex}")
    artifact_id = str(artifact.get("artifact_id") or f"artifact_{uuid4().hex}")
    resolved_import_method = (
        import_method
        or str(artifact.get("import_method") or "").strip()
        or ("upload" if str(artifact.get("source_type") or "").lower() in {"html", "csv", "rest"} else "rest")
    )
    artifact_payload = dict(artifact)
    artifact_payload.update(
        {
            "artifact_id": artifact_id,
            "import_run_id": import_run_id,
            "customer_id": customer.customer_id,
            "commcell_id": commcell.commcell_id,
            "commcell_name": artifact.get("commcell_name") or commcell.commcell_name,
            "engagement_id": engagement_context.engagement_id if engagement_context else None,
            "report_stream_id": report_stream.report_stream_id if report_stream else artifact.get("report_stream_id"),
            "report_run_id": report_run.report_run_id if report_run else artifact.get("report_run_id"),
            "executed_at": report_run.executed_at if report_run else artifact.get("executed_at"),
            "run_sequence": report_run.run_sequence if report_run else artifact.get("run_sequence"),
            "is_active": True,
            "imported_at": imported_at,
            "created_at": created_at,
            "retention_policy": retention_policy or artifact.get("retention_policy") or "keep",
            "imported_by": imported_by or artifact.get("imported_by"),
            "import_method": resolved_import_method,
            "source_metadata": dict(artifact.get("source_metadata") or artifact.get("source") or {}),
        }
    )
    artifact_model = LicenseSummaryArtifact.from_dict(artifact_payload)
    artifact_filename = f"{artifact_id}.json"
    artifact_paths = write_license_summary_artifact(
        artifact_model.to_dict(),
        catalog_dir=catalog_dir or LICENSE_SUMMARY_CATALOG_DIR,
        artifact_filename=artifact_filename,
    )

    registry = SecurityAssessmentArtifactRegistry(
        registry_path or LICENSE_SUMMARY_REGISTRY_PATH
    )
    import_run = ImportRun(
        import_run_id=import_run_id,
        customer_id=customer.customer_id,
        commcell_id=commcell.commcell_id,
        engagement_id=engagement_context.engagement_id if engagement_context else None,
        report_stream_id=report_stream.report_stream_id if report_stream else artifact.get("report_stream_id"),
        report_run_id=report_run.report_run_id if report_run else artifact.get("report_run_id"),
        imported_at=imported_at,
        executed_at=report_run.executed_at if report_run else artifact.get("executed_at"),
        run_sequence=report_run.run_sequence if report_run else artifact.get("run_sequence"),
        imported_by=imported_by or artifact.get("imported_by"),
        import_method=resolved_import_method,
    )
    record = ArtifactRecord(
        artifact_id=artifact_id,
        import_run_id=import_run_id,
        artifact_type=artifact_model.artifact_type,
        source_type=artifact_model.source_type,
        source_file=artifact_model.source_file,
        file_path=artifact_paths["artifact"],
        customer_id=customer.customer_id,
        commcell_id=commcell.commcell_id,
        engagement_id=engagement_context.engagement_id if engagement_context else None,
        report_stream_id=report_stream.report_stream_id if report_stream else artifact.get("report_stream_id"),
        report_run_id=report_run.report_run_id if report_run else artifact.get("report_run_id"),
        imported_at=imported_at,
        executed_at=report_run.executed_at if report_run else artifact.get("executed_at"),
        run_sequence=report_run.run_sequence if report_run else artifact.get("run_sequence"),
        is_active=True,
        created_at=created_at,
        last_accessed_at=artifact.get("last_accessed_at"),
        retention_policy=retention_policy or artifact.get("retention_policy") or "keep",
        imported_by=imported_by or artifact.get("imported_by"),
        import_method=resolved_import_method,
        source_metadata=dict(artifact_payload.get("source_metadata") or {}),
    )
    registry.register_artifact(import_run, record)

    persisted_payload = artifact_model.to_dict()
    persisted_payload["file_path"] = artifact_paths["artifact"]
    persisted_payload["artifact_paths"] = artifact_paths
    write_license_summary_artifact(
        persisted_payload,
        catalog_dir=catalog_dir or LICENSE_SUMMARY_CATALOG_DIR,
        artifact_filename=artifact_filename,
    )
    return persisted_payload


def load_active_license_summary_artifact(
    *,
    catalog_dir: Path | None = None,
    registry_path: Path | None = None,
    customer_context: CustomerContext | None = None,
    commcell_context: CommCellContext | None = None,
    engagement_context: EngagementContext | None = None,
    report_stream: ReportStream | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    customer = customer_context or DEFAULT_CUSTOMER_CONTEXT
    commcell = commcell_context or CommCellContext(
        commcell_id=(commcell_context.commcell_id if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_id),
        commcell_name=(commcell_context.commcell_name if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_name),
        customer_id=customer.customer_id,
    )
    registry = SecurityAssessmentArtifactRegistry(
        registry_path or LICENSE_SUMMARY_REGISTRY_PATH
    )
    active_record = registry.get_active_artifact(
        "license_summary",
        customer_id=customer.customer_id,
        commcell_id=commcell.commcell_id,
        source_type=source_type,
        engagement_id=engagement_context.engagement_id if engagement_context else None,
        report_stream_id=report_stream.report_stream_id if report_stream else None,
    )
    if active_record is not None:
        path = Path(active_record.file_path)
        if path.exists():
            return _load_artifact_payload_from_record(
                active_record,
                registry=registry,
                catalog_dir=catalog_dir or LICENSE_SUMMARY_CATALOG_DIR,
            )
        recovered_record = registry.find_recoverable_artifact(
            "license_summary",
            customer_id=customer.customer_id,
            commcell_id=commcell.commcell_id,
            source_type=source_type,
            engagement_id=engagement_context.engagement_id if engagement_context else None,
            report_stream_id=report_stream.report_stream_id if report_stream else None,
        )
        if recovered_record is not None:
            registry.set_active_artifact(recovered_record.artifact_id)
            return _load_artifact_payload_from_record(
                recovered_record,
                registry=registry,
                catalog_dir=catalog_dir or LICENSE_SUMMARY_CATALOG_DIR,
            )

    latest_path = (catalog_dir or LICENSE_SUMMARY_CATALOG_DIR) / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(latest_path)
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    payload.setdefault("file_path", str(latest_path))
    payload["loaded_from_path"] = str(latest_path)
    return payload


def _load_artifact_payload_from_record(
    record: ArtifactRecord,
    *,
    registry: SecurityAssessmentArtifactRegistry,
    catalog_dir: Path,
) -> dict[str, Any]:
    path = Path(record.file_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    accessed_at = collected_at()
    registry.touch_artifact_access(record.artifact_id, accessed_at)
    payload.setdefault("file_path", str(path))
    payload["last_accessed_at"] = accessed_at
    payload["loaded_from_path"] = str(path)
    payload.setdefault(
        "artifact_paths",
        {
            "artifact": str(path),
            "latest": str(catalog_dir / "latest.json"),
            "latest_source": str(
                catalog_dir / f"latest_{payload.get('source_type', 'unknown')}.json"
            ),
        },
    )
    return payload


def _save_upload(
    stream: BinaryIO,
    original_filename: str,
    *,
    imports_dir: Path,
) -> Path:
    imports_dir.mkdir(parents=True, exist_ok=True)
    filename = _build_saved_filename(original_filename)
    path = imports_dir / filename
    path.write_bytes(stream.read())
    return path


def _build_saved_filename(original_filename: str) -> str:
    path = Path(original_filename)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    token = secrets.token_hex(4)
    return f"{path.stem}-{timestamp}-{token}{path.suffix.lower()}"
