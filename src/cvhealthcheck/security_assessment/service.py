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

from .artifact import SECURITY_ASSESSMENT_CATALOG_DIR, write_security_assessment_artifact
from .import_csv import import_security_assessment_csv
from .import_html import import_security_assessment_html
from .models import (
    ArtifactRecord,
    CommCellContext,
    CustomerContext,
    EngagementContext,
    ImportRun,
    ReportRun,
    ReportStream,
    SecurityAssessmentArtifact,
)
from .registry import SecurityAssessmentArtifactRegistry

SECURITY_ASSESSMENT_IMPORTS_DIR = Path("data/imports/security_assessment")
SECURITY_ASSESSMENT_REGISTRY_PATH = SECURITY_ASSESSMENT_IMPORTS_DIR / "artifact_registry.sqlite3"
ALLOWED_EXTENSIONS = {
    ".csv": "csv",
    ".htm": "html",
    ".html": "html",
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


class SecurityAssessmentImportError(ValueError):
    pass


def import_security_assessment_upload(
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
) -> dict[str, Any]:
    safe_name = secure_filename(original_filename or "")
    if not safe_name:
        raise SecurityAssessmentImportError("No file selected.")

    extension = Path(safe_name).suffix.lower()
    source_type = ALLOWED_EXTENSIONS.get(extension)
    if source_type is None:
        raise SecurityAssessmentImportError(
            "Unsupported file type. Upload a Commvault Security Assessment HTML or CSV export."
        )

    saved_path = _save_upload(
        stream,
        safe_name,
        imports_dir=imports_dir or SECURITY_ASSESSMENT_IMPORTS_DIR,
    )
    if source_type == "html":
        artifact = import_security_assessment_html(saved_path, write_artifact=False)
    else:
        artifact = import_security_assessment_csv(saved_path, write_artifact=False)

    if int(artifact.get("finding_count") or 0) <= 0:
        raise SecurityAssessmentImportError(
            f"{source_type.upper()} import produced no findings."
        )

    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=catalog_dir,
        registry_path=registry_path,
        customer_context=customer_context,
        commcell_context=commcell_context,
        engagement_context=engagement_context,
        report_stream=report_stream,
        report_run=report_run,
    )
    logger.info(
        "Imported Security Assessment upload source_file=%s source_type=%s imported_at=%s finding_count=%s first_finding=%s",
        saved_path,
        persisted.get("source_type"),
        persisted.get("imported_at"),
        persisted.get("finding_count"),
        _finding_preview(persisted.get("findings", [])),
    )
    return persisted


def persist_security_assessment_artifact(
    artifact: dict[str, Any],
    *,
    catalog_dir: Path | None = None,
    registry_path: Path | None = None,
    customer_context: CustomerContext | None = None,
    commcell_context: CommCellContext | None = None,
    engagement_context: EngagementContext | None = None,
    report_stream: ReportStream | None = None,
    report_run: ReportRun | None = None,
) -> dict[str, Any]:
    customer = customer_context or DEFAULT_CUSTOMER_CONTEXT
    commcell = commcell_context or CommCellContext(
        commcell_id=(commcell_context.commcell_id if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_id),
        commcell_name=(commcell_context.commcell_name if commcell_context else DEFAULT_COMMCELL_CONTEXT.commcell_name),
        customer_id=customer.customer_id,
    )
    imported_at = str(artifact.get("imported_at") or collected_at())
    import_run_id = str(artifact.get("import_run_id") or f"imprun_{uuid4().hex}")
    artifact_id = str(artifact.get("artifact_id") or f"artifact_{uuid4().hex}")
    artifact_payload = dict(artifact)
    artifact_payload.update(
        {
            "artifact_id": artifact_id,
            "import_run_id": import_run_id,
            "customer_id": customer.customer_id,
            "commcell_id": commcell.commcell_id,
            "engagement_id": engagement_context.engagement_id if engagement_context else None,
            "report_stream_id": report_stream.report_stream_id if report_stream else None,
            "report_run_id": report_run.report_run_id if report_run else None,
            "executed_at": report_run.executed_at if report_run else artifact.get("executed_at"),
            "run_sequence": report_run.run_sequence if report_run else artifact.get("run_sequence"),
            "is_active": True,
            "imported_at": imported_at,
        }
    )
    artifact_model = SecurityAssessmentArtifact.from_dict(artifact_payload)
    artifact_filename = f"{artifact_id}.json"
    artifact_paths = write_security_assessment_artifact(
        artifact_model.to_dict(),
        catalog_dir=catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR,
        artifact_filename=artifact_filename,
    )

    registry = SecurityAssessmentArtifactRegistry(
        registry_path or SECURITY_ASSESSMENT_REGISTRY_PATH
    )
    import_run = ImportRun(
        import_run_id=import_run_id,
        customer_id=customer.customer_id,
        commcell_id=commcell.commcell_id,
        engagement_id=engagement_context.engagement_id if engagement_context else None,
        report_stream_id=report_stream.report_stream_id if report_stream else None,
        report_run_id=report_run.report_run_id if report_run else None,
        imported_at=imported_at,
        executed_at=report_run.executed_at if report_run else artifact.get("executed_at"),
        run_sequence=report_run.run_sequence if report_run else artifact.get("run_sequence"),
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
        report_stream_id=report_stream.report_stream_id if report_stream else None,
        report_run_id=report_run.report_run_id if report_run else None,
        imported_at=imported_at,
        executed_at=report_run.executed_at if report_run else artifact.get("executed_at"),
        run_sequence=report_run.run_sequence if report_run else artifact.get("run_sequence"),
        is_active=True,
    )
    registry.register_artifact(import_run, record)

    persisted_payload = artifact_model.to_dict()
    persisted_payload["file_path"] = artifact_paths["artifact"]
    persisted_payload["artifact_paths"] = artifact_paths
    write_security_assessment_artifact(
        persisted_payload,
        catalog_dir=catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR,
        artifact_filename=artifact_filename,
    )
    return persisted_payload


def load_active_security_assessment_artifact(
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
        registry_path or SECURITY_ASSESSMENT_REGISTRY_PATH
    )
    active_record = registry.get_active_artifact(
        "security_assessment",
        customer_id=customer.customer_id,
        commcell_id=commcell.commcell_id,
        source_type=source_type,
        engagement_id=engagement_context.engagement_id if engagement_context else None,
        report_stream_id=report_stream.report_stream_id if report_stream else None,
    )
    if active_record is not None:
        path = Path(active_record.file_path)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.setdefault("file_path", str(path))
            payload.setdefault("loaded_from_path", str(path))
            payload.setdefault(
                "artifact_paths",
                {
                    "artifact": str(path),
                    "latest": str((catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR) / "latest.json"),
                    "latest_source": str(
                        (catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR)
                        / f"latest_{payload.get('source_type', 'unknown')}.json"
                    ),
                },
            )
            return payload
        recovered_record = registry.find_recoverable_artifact(
            "security_assessment",
            customer_id=customer.customer_id,
            commcell_id=commcell.commcell_id,
            source_type=source_type,
            engagement_id=engagement_context.engagement_id if engagement_context else None,
            report_stream_id=report_stream.report_stream_id if report_stream else None,
        )
        if recovered_record is not None:
            registry.set_active_artifact(recovered_record.artifact_id)
            recovered_path = Path(recovered_record.file_path)
            payload = json.loads(recovered_path.read_text(encoding="utf-8"))
            payload.setdefault("file_path", str(recovered_path))
            payload.setdefault("loaded_from_path", str(recovered_path))
            payload.setdefault(
                "artifact_paths",
                {
                    "artifact": str(recovered_path),
                    "latest": str((catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR) / "latest.json"),
                    "latest_source": str(
                        (catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR)
                        / f"latest_{payload.get('source_type', 'unknown')}.json"
                    ),
                },
            )
            return payload

    latest_path = (catalog_dir or SECURITY_ASSESSMENT_CATALOG_DIR) / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(latest_path)
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    payload.setdefault("file_path", str(latest_path))
    payload["loaded_from_path"] = str(latest_path)
    return payload


def export_security_assessment_registry(
    *,
    registry_path: Path | None = None,
    export_path: Path | None = None,
) -> dict[str, Any]:
    registry = SecurityAssessmentArtifactRegistry(
        registry_path or SECURITY_ASSESSMENT_REGISTRY_PATH
    )
    payload = registry.export_registry(artifact_type="security_assessment")
    if export_path is not None:
        registry.write_export_json(export_path, artifact_type="security_assessment")
        payload["export_path"] = str(export_path)
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
