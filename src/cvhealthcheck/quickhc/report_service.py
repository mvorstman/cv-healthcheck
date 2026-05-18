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

ENVIRONMENT_SELECTION_ID = "environment"
SECURITY_ASSESSMENT_SUMMARY_SELECTION_ID = "security_assessment_summary"
SECURITY_ASSESSMENT_FINDINGS_SELECTION_ID = "security_assessment_findings"
LICENSE_SUMMARY_METADATA_SELECTION_ID = "license_summary_metadata"
LICENSE_SUMMARY_WORKLOAD_SELECTION_ID = "license_summary_workload"
LICENSE_SUMMARY_DETAILS_SELECTION_ID = "license_summary_details"
REPORT_SELECTION_IDS = {
    ENVIRONMENT_SELECTION_ID,
    SECURITY_ASSESSMENT_SUMMARY_SELECTION_ID,
    SECURITY_ASSESSMENT_FINDINGS_SELECTION_ID,
    LICENSE_SUMMARY_METADATA_SELECTION_ID,
    LICENSE_SUMMARY_WORKLOAD_SELECTION_ID,
    LICENSE_SUMMARY_DETAILS_SELECTION_ID,
}


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

    def build_report(
        self,
        selection_ids: set[str] | None = None,
        *,
        default_to_all: bool = True,
    ) -> dict[str, Any]:
        report = self._build_full_report()
        return self._filter_report(
            report,
            selection_ids=selection_ids or set(),
            default_to_all=default_to_all,
        )

    def build_builder(self) -> dict[str, Any]:
        report = self._build_full_report()
        default_selection_ids = self._default_builder_selection_ids(report)
        groups = self._build_builder_groups(report, default_selection_ids)
        return {
            "title": "Quick HealthCheck Report Builder",
            "generated_at": report["generated_at"],
            "groups": groups,
            "has_artifacts": any(
                (
                    report["security_assessment"]["available"],
                    report["license_summary"]["available"],
                )
            ),
        }

    def _build_full_report(self) -> dict[str, Any]:
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
                "summary_section_id": SECURITY_ASSESSMENT_SUMMARY_SELECTION_ID,
                "findings_section_id": SECURITY_ASSESSMENT_FINDINGS_SELECTION_ID,
                "sections": [],
            }

        summary = summarize_security_assessment_artifact(artifact, SECTION_ORDER)
        counters = dict(summary.get("counters") or {})
        sections = []
        for section in summary.get("sections", []):
            section_name = str(section.get("name") or "")
            rows = []
            for row in section.get("checks") or []:
                rows.append(
                    {
                        "section": row.get("section"),
                        "parameter": row.get("parameter"),
                        "status": row.get("status"),
                        "remarks": row.get("remarks"),
                        "action": row.get("action"),
                    }
                )
            sections.append(
                {
                    "name": section_name,
                    "rows": rows,
                }
            )
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
            "summary_section_id": SECURITY_ASSESSMENT_SUMMARY_SELECTION_ID,
            "findings_section_id": SECURITY_ASSESSMENT_FINDINGS_SELECTION_ID,
            "source_metadata": dict(
                artifact.get("source_metadata") or artifact.get("source") or {}
            ),
            "sections": sections,
            "evidence": ReportEvidence(
                artifact_type="security_assessment",
                source_type=artifact.get("source_type"),
                imported_at=artifact.get("imported_at"),
                generated_on=artifact.get("generated_on"),
                loaded_from_path=artifact.get("loaded_from_path")
                or artifact.get("file_path"),
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
                "summary_section_id": LICENSE_SUMMARY_METADATA_SELECTION_ID,
                "workload_sections": [],
                "other_license_rows": [],
                "agent_feature_rows": [],
                "workload_section_id": LICENSE_SUMMARY_WORKLOAD_SELECTION_ID,
                "details_section_id": LICENSE_SUMMARY_DETAILS_SELECTION_ID,
            }

        workload_sections = []
        for section in artifact.get("workload_summary_sections") or []:
            section_name = str(section.get("section_name") or "")
            rows = []
            for row in section.get("rows") or []:
                rows.append(
                    {
                        "license": row.get("license"),
                        "entitlement_value": row.get("entitlement_value"),
                        "used": row.get("used"),
                        "usage_percent": row.get("usage_percent"),
                        "status": row.get("status"),
                    }
                )
            workload_sections.append(
                {
                    "section_name": section_name,
                    "rows": rows,
                }
            )

        other_license_rows = [
            {
                "license": item.get("license"),
                "available_total": item.get("available_total"),
                "used": item.get("used"),
                "unit": item.get("unit"),
                "raw_available_total": item.get("raw_available_total"),
                "raw_used": item.get("raw_used"),
            }
            for item in artifact.get("other_licenses") or []
        ]
        agent_feature_rows = [
            {
                "license": item.get("license"),
                "permanent_total": item.get("permanent_total"),
                "permanent_used": item.get("permanent_used"),
                "term_total": item.get("term_total"),
                "term_used": item.get("term_used"),
                "client": item.get("client"),
                "agent": item.get("agent"),
                "install_date": item.get("install_date"),
            }
            for item in artifact.get("agent_feature_licenses") or []
        ]

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
            "summary_section_id": LICENSE_SUMMARY_METADATA_SELECTION_ID,
            "workload_summary_section_count": len(workload_sections),
            "other_license_row_count": len(other_license_rows),
            "agent_feature_license_row_count": len(agent_feature_rows),
            "source_metadata": dict(
                artifact.get("source_metadata") or artifact.get("source") or {}
            ),
            "workload_sections": workload_sections,
            "workload_section_id": LICENSE_SUMMARY_WORKLOAD_SELECTION_ID,
            "details_section_id": LICENSE_SUMMARY_DETAILS_SELECTION_ID,
            "other_license_rows": other_license_rows,
            "agent_feature_rows": agent_feature_rows,
            "evidence": ReportEvidence(
                artifact_type="license_summary",
                source_type=artifact.get("source_type"),
                imported_at=artifact.get("imported_at"),
                generated_on=artifact.get("generated_on"),
                loaded_from_path=artifact.get("loaded_from_path")
                or artifact.get("file_path"),
            ).to_dict(),
        }

    def _build_environment(
        self,
        security_artifact: dict[str, Any] | None,
        license_artifact: dict[str, Any] | None,
    ) -> dict[str, Any]:
        rows = [
            {
                "label": "Customer ID",
                "value": _first_value(license_artifact, security_artifact, key="customer_id"),
            },
            {
                "label": "CommCell ID",
                "value": _first_value(license_artifact, security_artifact, key="commcell_id"),
            },
            {
                "label": "CommCell Name",
                "value": _first_value(
                    license_artifact,
                    security_artifact,
                    key="commcell_name",
                ),
            },
            {
                "label": "Generated At",
                "value": _now_iso(),
            },
        ]
        return {
            "section_id": ENVIRONMENT_SELECTION_ID,
            "customer_id": rows[0]["value"],
            "commcell_id": rows[1]["value"],
            "commcell_name": rows[2]["value"],
            "generated_at": rows[3]["value"],
            "rows": rows,
        }

    def _filter_report(
        self,
        report: dict[str, Any],
        *,
        selection_ids: set[str],
        default_to_all: bool,
    ) -> dict[str, Any]:
        effective_selection_ids = (
            self._default_report_selection_ids(report)
            if default_to_all and not selection_ids
            else selection_ids
        )

        filtered_environment_rows = self._filter_rows_section(
            report["environment"]["section_id"],
            report["environment"]["rows"],
            effective_selection_ids,
        )
        filtered_environment = {
            **report["environment"],
            **filtered_environment_rows,
        }
        filtered_security = self._filter_security_assessment(
            report["security_assessment"],
            effective_selection_ids,
        )
        filtered_license = self._filter_license_summary(
            report["license_summary"],
            effective_selection_ids,
        )

        evidence = []
        if filtered_security.get("has_content") and filtered_security.get("evidence"):
            evidence.append(filtered_security["evidence"])
        if filtered_license.get("has_content") and filtered_license.get("evidence"):
            evidence.append(filtered_license["evidence"])

        return {
            "title": report["title"],
            "generated_at": report["generated_at"],
            "environment": filtered_environment,
            "security_assessment": filtered_security,
            "license_summary": filtered_license,
            "evidence": evidence,
        }

    def _filter_security_assessment(
        self,
        section: dict[str, Any],
        selection_ids: set[str],
    ) -> dict[str, Any]:
        if not section.get("available"):
            return {
                **section,
                "show_summary": False,
                "visible_sections": [],
                "has_content": False,
            }

        visible_sections = []
        if section["findings_section_id"] in selection_ids:
            visible_sections = [
                {
                    "name": item["name"],
                    "rows": item["rows"],
                }
                for item in section.get("sections", [])
            ]
        show_summary = section["summary_section_id"] in selection_ids
        has_content = show_summary or bool(visible_sections)
        return {
            **section,
            "show_summary": show_summary,
            "visible_sections": visible_sections,
            "has_content": has_content,
        }

    def _filter_license_summary(
        self,
        section: dict[str, Any],
        selection_ids: set[str],
    ) -> dict[str, Any]:
        if not section.get("available"):
            return {
                **section,
                "show_summary": False,
                "visible_workload_sections": [],
                "visible_other_license_rows": [],
                "visible_agent_feature_rows": [],
                "has_content": False,
            }

        visible_workload_sections = []
        if section["workload_section_id"] in selection_ids:
            visible_workload_sections = list(section.get("workload_sections", []))

        show_details = section["details_section_id"] in selection_ids
        show_summary = section["summary_section_id"] in selection_ids
        has_content = any(
            (
                show_summary,
                bool(visible_workload_sections),
                show_details,
            )
        )
        return {
            **section,
            "show_summary": show_summary,
            "visible_workload_sections": visible_workload_sections,
            "visible_other_license_rows": (
                list(section.get("other_license_rows", [])) if show_details else []
            ),
            "visible_agent_feature_rows": (
                list(section.get("agent_feature_rows", [])) if show_details else []
            ),
            "has_content": has_content,
        }

    def _filter_rows_section(
        self,
        section_id: str,
        rows: list[dict[str, Any]],
        selection_ids: set[str],
    ) -> dict[str, Any]:
        if section_id in selection_ids:
            return {"visible": True, "rows": rows}
        return {"visible": False, "rows": []}

    def _default_report_selection_ids(self, report: dict[str, Any]) -> set[str]:
        selection_ids: set[str] = {report["environment"]["section_id"]}

        security = report["security_assessment"]
        if security.get("available"):
            selection_ids.add(security["summary_section_id"])

        license_summary = report["license_summary"]
        if license_summary.get("available"):
            selection_ids.add(license_summary["summary_section_id"])
        return selection_ids

    def _default_builder_selection_ids(self, report: dict[str, Any]) -> set[str]:
        selection_ids: set[str] = {report["environment"]["section_id"]}

        security = report["security_assessment"]
        if security.get("available"):
            selection_ids.add(security["summary_section_id"])
            selection_ids.add(security["findings_section_id"])

        license_summary = report["license_summary"]
        if license_summary.get("available"):
            selection_ids.add(license_summary["summary_section_id"])
            selection_ids.add(license_summary["workload_section_id"])
            selection_ids.add(license_summary["details_section_id"])
        return selection_ids

    def _build_builder_groups(
        self,
        report: dict[str, Any],
        default_selection_ids: set[str],
    ) -> list[dict[str, Any]]:
        groups = [
            {
                "title": "Environment Metadata",
                "items": [
                    self._builder_item(
                        report["environment"]["section_id"],
                        "Environment",
                        default_selection_ids,
                    )
                ],
            }
        ]

        security = report["security_assessment"]
        security_items = []
        if security.get("available"):
            security_items.append(
                self._builder_item(
                    security["summary_section_id"],
                    "Security Assessment Summary",
                    default_selection_ids,
                )
            )
            security_items.append(
                self._builder_item(
                    security["findings_section_id"],
                    "Security Assessment Findings",
                    default_selection_ids,
                )
            )
        groups.append({"title": "Security Assessment", "items": security_items})

        license_summary = report["license_summary"]
        license_items = []
        if license_summary.get("available"):
            license_items.append(
                self._builder_item(
                    license_summary["summary_section_id"],
                    "License Summary Metadata",
                    default_selection_ids,
                )
            )
            license_items.append(
                self._builder_item(
                    license_summary["workload_section_id"],
                    "License Summary Workload",
                    default_selection_ids,
                )
            )
            license_items.append(
                self._builder_item(
                    license_summary["details_section_id"],
                    "License Summary Details",
                    default_selection_ids,
                )
            )
        groups.append({"title": "License Summary", "items": license_items})
        return groups

    def _builder_item(
        self,
        item_id: str,
        label: str,
        default_selection_ids: set[str],
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "label": label,
            "checked": item_id in default_selection_ids,
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
