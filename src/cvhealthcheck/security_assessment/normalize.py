from __future__ import annotations

from typing import Any

DEFAULT_STATUS_KEYS = ("Critical", "Warning", "Info", "Good")
CANONICAL_FINDING_KEYS = (
    "section",
    "parameter",
    "status",
    "remarks",
    "action",
    "source_type",
    "source_file",
    "imported_at",
)


def normalize_canonical_finding_input(
    finding: dict[str, Any],
    *,
    source_type: str,
    source_file: str | None,
    imported_at: str,
) -> dict[str, Any]:
    canonical = {
        "section": clean_text(finding.get("section")) or "Other",
        "parameter": clean_text(finding.get("parameter")),
        "status": clean_text(finding.get("status")) or "Info",
        "remarks": clean_text(finding.get("remarks")),
        "action": clean_text(finding.get("action")),
        "source_type": source_type,
        "source_file": source_file,
        "imported_at": imported_at,
    }
    return {key: canonical[key] for key in CANONICAL_FINDING_KEYS}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return str(value).strip()


def __getattr__(name: str):
    if name in {
        "SECURITY_ASSESSMENT_CATALOG_DIR",
        "build_security_assessment_artifact",
        "summarize_security_assessment_artifact",
        "write_security_assessment_artifact",
    }:
        from .artifact import (
            SECURITY_ASSESSMENT_CATALOG_DIR,
            build_security_assessment_artifact,
            summarize_security_assessment_artifact,
            write_security_assessment_artifact,
        )

        return {
            "SECURITY_ASSESSMENT_CATALOG_DIR": SECURITY_ASSESSMENT_CATALOG_DIR,
            "build_security_assessment_artifact": build_security_assessment_artifact,
            "summarize_security_assessment_artifact": summarize_security_assessment_artifact,
            "write_security_assessment_artifact": write_security_assessment_artifact,
        }[name]
    raise AttributeError(name)
