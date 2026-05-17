from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
import secrets
from typing import BinaryIO, Any

from werkzeug.utils import secure_filename

from .import_csv import import_security_assessment_csv
from .import_html import import_security_assessment_html
from .normalize import write_security_assessment_artifact

SECURITY_ASSESSMENT_IMPORTS_DIR = Path("data/imports/security_assessment")
ALLOWED_EXTENSIONS = {
    ".csv": "csv",
    ".htm": "html",
    ".html": "html",
}
logger = logging.getLogger(__name__)


class SecurityAssessmentImportError(ValueError):
    pass


def import_security_assessment_upload(
    stream: BinaryIO,
    *,
    original_filename: str,
    imports_dir: Path | None = None,
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

    artifact["artifact_paths"] = write_security_assessment_artifact(artifact)
    logger.info(
        "Imported Security Assessment upload source_file=%s source_type=%s imported_at=%s finding_count=%s first_finding=%s",
        saved_path,
        artifact.get("source_type"),
        artifact.get("imported_at"),
        artifact.get("finding_count"),
        _finding_preview(artifact.get("findings", [])),
    )
    return artifact


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
