from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cvhealthcheck.reportsplus.catalog import CATALOG_DIR, collected_at, write_json

from .models import LicenseSummaryArtifact
from .validate import (
    filter_valid_agent_feature_licenses,
    filter_valid_other_licenses,
)

LICENSE_SUMMARY_CATALOG_DIR = CATALOG_DIR / "license_summary"
logger = logging.getLogger(__name__)


def build_license_summary_artifact(
    *,
    source_type: str,
    other_licenses: list[dict[str, Any]],
    agent_feature_licenses: list[dict[str, Any]],
    source_file: str | None = None,
    imported_at: str | None = None,
    generated_on: str | None = None,
    source: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = LicenseSummaryArtifact(
        artifact_type="license_summary",
        source_type=source_type,
        source_file=source_file,
        imported_at=imported_at or collected_at(),
        generated_on=generated_on,
        customer_id=metadata.get("customer_id") if metadata else None,
        commcell_id=metadata.get("commcell_id") if metadata else None,
        commcell_name=metadata.get("commcell_name") if metadata else None,
        commcell_version=metadata.get("commcell_version") if metadata else None,
        timezone=metadata.get("timezone") if metadata else None,
        last_collection_time=metadata.get("last_collection_time") if metadata else None,
        license_expiry=metadata.get("license_expiry") if metadata else None,
        last_generation_time=metadata.get("last_generation_time") if metadata else None,
        last_application_time=metadata.get("last_application_time") if metadata else None,
        other_licenses=filter_valid_other_licenses(other_licenses),
        agent_feature_licenses=filter_valid_agent_feature_licenses(agent_feature_licenses),
        source=dict(source or {}),
        source_metadata=dict((extra or {}).get("source_metadata") or {}),
        artifacts=dict((extra or {}).get("artifacts") or {}),
        datasets=list((extra or {}).get("datasets") or []),
    )
    payload = artifact.to_dict()
    if extra:
        for key, value in extra.items():
            if key not in {"source_metadata", "artifacts", "datasets"}:
                payload[key] = value
    return payload


def write_license_summary_artifact(
    artifact: dict[str, Any],
    *,
    catalog_dir: Path | None = None,
    artifact_filename: str | None = None,
) -> dict[str, str]:
    target_dir = catalog_dir or LICENSE_SUMMARY_CATALOG_DIR
    source_type = str(artifact.get("source_type") or "unknown").lower()
    artifact_model = LicenseSummaryArtifact.from_dict(artifact)

    artifact_id = str(artifact_model.artifact_id or "unregistered")
    artifact_name = artifact_filename or f"artifact_{artifact_id}.json"
    artifact_path = write_json(artifact_name, artifact_model.to_dict(), target_dir)
    latest_source_path = write_json(
        f"latest_{source_type}.json",
        artifact_model.to_dict(),
        target_dir,
    )
    latest_path = write_json("latest.json", artifact_model.to_dict(), target_dir)
    logger.info(
        "Wrote License Summary artifact artifact=%s latest=%s latest_source=%s imported_at=%s source_type=%s other_count=%s agent_count=%s",
        artifact_path,
        latest_path,
        latest_source_path,
        artifact_model.imported_at,
        artifact_model.source_type,
        len(artifact_model.other_licenses),
        len(artifact_model.agent_feature_licenses),
    )
    return {
        "artifact": str(artifact_path),
        "latest_source": str(latest_source_path),
        "latest": str(latest_path),
    }
