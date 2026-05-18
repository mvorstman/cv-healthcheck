from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from cvhealthcheck.license_summary.service import LicenseSummaryService
from cvhealthcheck.reportsplus.security_assessment import (
    SECTION_ORDER,
    summarize_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.service import SecurityAssessmentService


@dataclass(frozen=True)
class ReportEvidence:
    artifact_type: str
    source_type: str | None
    imported_at: str | None
    generated_on: str | None
    loaded_from_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QuickHcReportService:
    def __init__(
        self,
        *,
        security_assessment_service: SecurityAssessmentService | None = None,
        license_summary_service: LicenseSummaryService | None = None,
    ) -> None:
        self.security_assessment_service = (
            security_assessment_service or SecurityAssessmentService()
        )
        self.license_summary_service = license_summary_service or LicenseSummaryService()

    def build_report(self) -> dict[str, Any]:
        security_assessment = self._build_security_assessment_section()
        license_summary = self._build_license_summary_section()
        environment = self._build_environment(
            security_assessment.get("artifact"),
            license_summary.get("artifact"),
        )
        evidence = [
            item
            for item in (
                security_assessment.get("evidence"),
                license_summary.get("evidence"),
            )
            if item is not None
        ]
        return {
            "title": "Quick HealthCheck Report",
            "generated_at": _now_iso(),
            "environment": environment,
            "security_assessment": security_assessment,
            "license_summary": license_summary,
            "evidence": evidence,
        }

    def _build_security_assessment_section(self) -> dict[str, Any]:
        try:
            artifact = self.security_assessment_service.get_current()
        except FileNotFoundError:
            return {
                "available": False,
                "title": "Security Assessment",
                "message": "Not collected yet",
                "detail_url": "/quick-hc/security-assessment",
                "artifact": None,
                "evidence": None,
            }

        summary = summarize_security_assessment_artifact(artifact, SECTION_ORDER)
        counters = dict(summary.get("counters") or {})
        return {
            "available": True,
            "title": "Security Assessment",
            "detail_url": "/quick-hc/security-assessment",
            "artifact": artifact,
            "source_type": artifact.get("source_type"),
            "imported_at": artifact.get("imported_at"),
            "generated_on": artifact.get("generated_on"),
            "loaded_from_path": artifact.get("loaded_from_path"),
            "total_checks": counters.get("Total checks", 0),
            "critical": counters.get("Critical", 0),
            "warning": counters.get("Warning", 0),
            "info": counters.get("Info", 0),
            "good": counters.get("Good", 0),
            "source_metadata": dict(artifact.get("source_metadata") or artifact.get("source") or {}),
            "evidence": ReportEvidence(
                artifact_type="security_assessment",
                source_type=artifact.get("source_type"),
                imported_at=artifact.get("imported_at"),
                generated_on=artifact.get("generated_on"),
                loaded_from_path=artifact.get("loaded_from_path") or artifact.get("file_path"),
            ).to_dict(),
        }

    def _build_license_summary_section(self) -> dict[str, Any]:
        try:
            artifact = self.license_summary_service.get_current()
        except FileNotFoundError:
            return {
                "available": False,
                "title": "License Summary",
                "message": "Not collected yet",
                "detail_url": "/quick-hc/license-summary",
                "artifact": None,
                "evidence": None,
            }

        return {
            "available": True,
            "title": "License Summary",
            "detail_url": "/quick-hc/license-summary",
            "artifact": artifact,
            "source_type": artifact.get("source_type"),
            "imported_at": artifact.get("imported_at"),
            "generated_on": artifact.get("generated_on"),
            "loaded_from_path": artifact.get("loaded_from_path"),
            "license_expiry": artifact.get("license_expiry"),
            "workload_summary_section_count": len(
                artifact.get("workload_summary_sections") or []
            ),
            "other_license_row_count": len(artifact.get("other_licenses") or []),
            "agent_feature_license_row_count": len(
                artifact.get("agent_feature_licenses") or []
            ),
            "source_metadata": dict(artifact.get("source_metadata") or artifact.get("source") or {}),
            "evidence": ReportEvidence(
                artifact_type="license_summary",
                source_type=artifact.get("source_type"),
                imported_at=artifact.get("imported_at"),
                generated_on=artifact.get("generated_on"),
                loaded_from_path=artifact.get("loaded_from_path") or artifact.get("file_path"),
            ).to_dict(),
        }

    def _build_environment(
        self,
        security_artifact: dict[str, Any] | None,
        license_artifact: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "customer_id": _first_value(
                license_artifact,
                security_artifact,
                key="customer_id",
            ),
            "commcell_id": _first_value(
                license_artifact,
                security_artifact,
                key="commcell_id",
            ),
            "commcell_name": _first_value(
                license_artifact,
                security_artifact,
                key="commcell_name",
            ),
            "generated_at": _now_iso(),
        }


def _first_value(*payloads: dict[str, Any] | None, key: str) -> str | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
