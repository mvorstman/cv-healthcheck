from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from cvhealthcheck.license_summary.service import LicenseSummaryService
from cvhealthcheck.metrics import (
    get_capacity_license_usage,
    get_client_growth_summary,
)
from cvhealthcheck.reportsplus.security_assessment import (
    SECTION_ORDER,
    summarize_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.service import SecurityAssessmentService

ENVIRONMENT_SELECTION_ID = "environment"
SECURITY_ASSESSMENT_SELECTION_ID = "security_assessment"
LICENSE_SUMMARY_SELECTION_ID = "license_summary"
CLIENT_GROWTH_SELECTION_ID = "client_growth"
CAPACITY_LICENSE_SELECTION_ID = "capacity_license"

ENVIRONMENT_METADATA_SECTION_ID = "environment.metadata"
SECURITY_ASSESSMENT_SUMMARY_SECTION_ID = "security_assessment.summary"
SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID = "security_assessment.highlights"
SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID = "security_assessment.all_findings"
LICENSE_SUMMARY_METADATA_SECTION_ID = "license_summary.metadata"
LICENSE_SUMMARY_WORKLOAD_SECTION_ID = "license_summary.workload_sections"
LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID = "license_summary.other_licenses"
LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID = (
    "license_summary.agent_feature_licenses"
)
CLIENT_GROWTH_SUMMARY_SECTION_ID = "client_growth.summary"
CLIENT_GROWTH_CHART_SECTION_ID = "client_growth.chart"
CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID = "client_growth.monthly_table"
CAPACITY_LICENSE_SUMMARY_SECTION_ID = "capacity_license.summary"
CAPACITY_LICENSE_TABLE_SECTION_ID = "capacity_license.table"

REPORT_SUBJECT_IDS = {
    ENVIRONMENT_SELECTION_ID,
    SECURITY_ASSESSMENT_SELECTION_ID,
    LICENSE_SUMMARY_SELECTION_ID,
    CLIENT_GROWTH_SELECTION_ID,
    CAPACITY_LICENSE_SELECTION_ID,
}

REPORT_SUBSECTION_OPTIONS: dict[str, tuple[dict[str, str], ...]] = {
    ENVIRONMENT_SELECTION_ID: (
        {
            "id": ENVIRONMENT_METADATA_SECTION_ID,
            "label": "Environment metadata",
        },
    ),
    SECURITY_ASSESSMENT_SELECTION_ID: (
        {
            "id": SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
            "label": "Summary counters",
        },
        {
            "id": SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
            "label": "Critical / Warning findings",
        },
        {
            "id": SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID,
            "label": "Info / Good findings",
        },
    ),
    LICENSE_SUMMARY_SELECTION_ID: (
        {
            "id": LICENSE_SUMMARY_METADATA_SECTION_ID,
            "label": "Summary metadata",
        },
        {
            "id": LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
            "label": "Workload Summary Sections",
        },
        {
            "id": LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
            "label": "Other Licenses table",
        },
        {
            "id": LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
            "label": "Agent / Feature Licenses table",
        },
    ),
    CLIENT_GROWTH_SELECTION_ID: (
        {
            "id": CLIENT_GROWTH_SUMMARY_SECTION_ID,
            "label": "Summary metrics",
        },
        {
            "id": CLIENT_GROWTH_CHART_SECTION_ID,
            "label": "Client Growth chart",
        },
        {
            "id": CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID,
            "label": "Monthly summary table",
        },
    ),
    CAPACITY_LICENSE_SELECTION_ID: (
        {
            "id": CAPACITY_LICENSE_SUMMARY_SECTION_ID,
            "label": "Summary",
        },
        {
            "id": CAPACITY_LICENSE_TABLE_SECTION_ID,
            "label": "Usage/details table",
        },
    ),
}

REPORT_SECTION_IDS = {
    option["id"]
    for options in REPORT_SUBSECTION_OPTIONS.values()
    for option in options
}
REPORT_SELECTION_IDS = REPORT_SUBJECT_IDS | REPORT_SECTION_IDS
REPORT_OVERVIEW_DEFAULT_SELECTION_IDS = REPORT_SELECTION_IDS
REPORT_DEFAULT_SUBJECT_SELECTION_IDS = REPORT_SUBJECT_IDS


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
        selected_ids = set(selection_ids or set())
        subject_selection_ids = (
            set(REPORT_DEFAULT_SUBJECT_SELECTION_IDS)
            if default_to_all and not selected_ids
            else selected_ids & REPORT_SUBJECT_IDS
        )
        expanded_selection_ids = (
            self._default_report_selection_ids(report)
            if default_to_all and not selected_ids
            else self._expand_subject_selection_ids(selected_ids)
        )
        return self._filter_report(
            report,
            subject_selection_ids=subject_selection_ids,
            selection_ids=expanded_selection_ids,
        )

    def _build_full_report(self) -> dict[str, Any]:
        security_assessment = self._build_security_assessment_section()
        license_summary = self._build_license_summary_section()
        client_growth = self._build_client_growth_section()
        capacity_license = self._build_capacity_license_section()
        environment = self._build_environment(
            security_assessment.get("artifact"),
            license_summary.get("artifact"),
        )
        evidence = [
            item
            for item in (
                security_assessment.get("evidence"),
                license_summary.get("evidence"),
                client_growth.get("evidence"),
                capacity_license.get("evidence"),
            )
            if item is not None
        ]
        return {
            "title": "Quick HealthCheck Report",
            "generated_at": _now_iso(),
            "environment": environment,
            "security_assessment": security_assessment,
            "license_summary": license_summary,
            "client_growth": client_growth,
            "capacity_license": capacity_license,
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
                "summary_section_id": SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
                "highlights_section_id": SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
                "all_findings_section_id": SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID,
                "sections": [],
                "highlight_rows": [],
            }

        summary = summarize_security_assessment_artifact(artifact, SECTION_ORDER)
        counters = dict(summary.get("counters") or {})
        sections = []
        highlight_rows = []
        for section in summary.get("sections", []):
            section_name = str(section.get("name") or "")
            rows = []
            for row in section.get("checks") or []:
                normalized_row = {
                    "section": row.get("section"),
                    "parameter": row.get("parameter"),
                    "status": row.get("status"),
                    "remarks": row.get("remarks"),
                    "action": row.get("action"),
                }
                rows.append(normalized_row)
                if normalized_row["status"] in {"Critical", "Warning"}:
                    highlight_rows.append(normalized_row)
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
            "summary_section_id": SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
            "highlights_section_id": SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
            "all_findings_section_id": SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID,
            "source_metadata": dict(
                artifact.get("source_metadata") or artifact.get("source") or {}
            ),
            "sections": sections,
            "highlight_rows": highlight_rows,
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
                "metadata_section_id": LICENSE_SUMMARY_METADATA_SECTION_ID,
                "workload_section_id": LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
                "other_licenses_section_id": LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
                "agent_feature_section_id": LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
                "workload_sections": [],
                "other_license_rows": [],
                "agent_feature_rows": [],
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
            "metadata_section_id": LICENSE_SUMMARY_METADATA_SECTION_ID,
            "workload_section_id": LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
            "other_licenses_section_id": LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
            "agent_feature_section_id": LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
            "workload_summary_section_count": len(workload_sections),
            "other_license_row_count": len(other_license_rows),
            "agent_feature_license_row_count": len(agent_feature_rows),
            "source_metadata": dict(
                artifact.get("source_metadata") or artifact.get("source") or {}
            ),
            "workload_sections": workload_sections,
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
            "metadata_section_id": ENVIRONMENT_METADATA_SECTION_ID,
            "customer_id": rows[0]["value"],
            "commcell_id": rows[1]["value"],
            "commcell_name": rows[2]["value"],
            "generated_at": rows[3]["value"],
            "rows": rows,
        }

    def _build_client_growth_section(self) -> dict[str, Any]:
        try:
            artifact = get_client_growth_summary(live=False)
        except FileNotFoundError:
            return {
                "available": False,
                "requested": False,
                "title": "Client Growth",
                "message": "Not collected yet",
                "detail_url": "/metrics/client-growth",
                "evidence": None,
                "record_count": 0,
                "history_range": None,
                "latest_record": None,
                "rows": [],
                "summary_section_id": CLIENT_GROWTH_SUMMARY_SECTION_ID,
                "chart_section_id": CLIENT_GROWTH_CHART_SECTION_ID,
                "monthly_table_section_id": CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID,
            }

        records = list(artifact.get("records") or [])
        period_start = records[0] if records else None
        latest_record = records[-1] if records else None
        latest_total_clients = (
            _coerce_int(latest_record.get("total_clients")) if latest_record else None
        )
        starting_total_clients = (
            _coerce_int(period_start.get("total_clients")) if period_start else None
        )
        net_growth = (
            latest_total_clients - starting_total_clients
            if latest_total_clients is not None and starting_total_clients is not None
            else None
        )
        chart = _client_growth_chart(records)
        return {
            "available": True,
            "requested": False,
            "title": "Client Growth",
            "description": "Client Growth summarizes how the protected client count has changed over the recorded period.",
            "message": "Not collected yet",
            "detail_url": "/metrics/client-growth",
            "imported_at": artifact.get("collected_at"),
            "record_count": int(artifact.get("record_count") or 0),
            "history_range": artifact.get("history_range"),
            "latest_record": latest_record,
            "latest_total_clients": latest_total_clients,
            "starting_total_clients": starting_total_clients,
            "net_growth": net_growth,
            "chart": chart,
            "rows": records,
            "summary_section_id": CLIENT_GROWTH_SUMMARY_SECTION_ID,
            "chart_section_id": CLIENT_GROWTH_CHART_SECTION_ID,
            "monthly_table_section_id": CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID,
            "evidence": ReportEvidence(
                artifact_type="client_growth",
                source_type="metric_artifact",
                imported_at=artifact.get("collected_at"),
                generated_on=None,
                loaded_from_path=None,
            ).to_dict(),
        }

    def _build_capacity_license_section(self) -> dict[str, Any]:
        try:
            artifact = get_capacity_license_usage(live=False)
        except FileNotFoundError:
            return {
                "available": False,
                "requested": False,
                "title": "Capacity License",
                "message": "Not collected yet",
                "detail_url": "/metrics/capacity-license",
                "evidence": None,
                "record_count": 0,
                "history_range": None,
                "latest_month": None,
                "latest_rows": [],
                "summary_section_id": CAPACITY_LICENSE_SUMMARY_SECTION_ID,
                "table_section_id": CAPACITY_LICENSE_TABLE_SECTION_ID,
            }

        records = list(artifact.get("records") or [])
        history_range = artifact.get("history_range")
        latest_month = history_range.get("end") if isinstance(history_range, dict) else None
        latest_rows = [row for row in records if row.get("month") == latest_month]
        return {
            "available": True,
            "requested": False,
            "title": "Capacity License",
            "message": "Not collected yet",
            "detail_url": "/metrics/capacity-license",
            "source_type": "metric_artifact",
            "imported_at": artifact.get("collected_at"),
            "generated_on": None,
            "record_count": int(artifact.get("record_count") or 0),
            "history_range": history_range,
            "latest_month": latest_month,
            "latest_rows": latest_rows,
            "summary_section_id": CAPACITY_LICENSE_SUMMARY_SECTION_ID,
            "table_section_id": CAPACITY_LICENSE_TABLE_SECTION_ID,
            "evidence": ReportEvidence(
                artifact_type="capacity_license",
                source_type="metric_artifact",
                imported_at=artifact.get("collected_at"),
                generated_on=None,
                loaded_from_path=None,
            ).to_dict(),
        }

    def _filter_report(
        self,
        report: dict[str, Any],
        *,
        subject_selection_ids: set[str],
        selection_ids: set[str],
    ) -> dict[str, Any]:
        filtered_environment = self._filter_environment(
            report["environment"],
            ENVIRONMENT_SELECTION_ID in subject_selection_ids,
            selection_ids,
        )
        filtered_security = self._filter_security_assessment(
            report["security_assessment"],
            SECURITY_ASSESSMENT_SELECTION_ID in subject_selection_ids,
            selection_ids,
        )
        filtered_license = self._filter_license_summary(
            report["license_summary"],
            LICENSE_SUMMARY_SELECTION_ID in subject_selection_ids,
            selection_ids,
        )
        filtered_client_growth = self._filter_client_growth(
            report["client_growth"],
            CLIENT_GROWTH_SELECTION_ID in subject_selection_ids,
            selection_ids,
        )
        filtered_capacity_license = self._filter_capacity_license(
            report["capacity_license"],
            CAPACITY_LICENSE_SELECTION_ID in subject_selection_ids,
            selection_ids,
        )

        evidence = []
        if filtered_security.get("has_content") and filtered_security.get("evidence"):
            evidence.append(filtered_security["evidence"])
        if filtered_license.get("has_content") and filtered_license.get("evidence"):
            evidence.append(filtered_license["evidence"])
        if filtered_client_growth.get("has_content") and filtered_client_growth.get("evidence"):
            evidence.append(filtered_client_growth["evidence"])
        if filtered_capacity_license.get("has_content") and filtered_capacity_license.get("evidence"):
            evidence.append(filtered_capacity_license["evidence"])

        return {
            "title": report["title"],
            "generated_at": report["generated_at"],
            "environment": filtered_environment,
            "security_assessment": filtered_security,
            "license_summary": filtered_license,
            "client_growth": filtered_client_growth,
            "capacity_license": filtered_capacity_license,
            "evidence": evidence,
        }

    def _filter_environment(
        self,
        section: dict[str, Any],
        requested: bool,
        selection_ids: set[str],
    ) -> dict[str, Any]:
        show_metadata = requested and section["metadata_section_id"] in selection_ids
        return {
            **section,
            "requested": requested,
            "show_metadata": show_metadata,
            "rows": list(section.get("rows", [])) if show_metadata else [],
            "has_content": show_metadata,
        }

    def _filter_security_assessment(
        self,
        section: dict[str, Any],
        requested: bool,
        selection_ids: set[str],
    ) -> dict[str, Any]:
        show_summary = requested and section["summary_section_id"] in selection_ids
        show_highlights = requested and section["highlights_section_id"] in selection_ids
        show_all_findings = (
            requested and section["all_findings_section_id"] in selection_ids
        )

        if not section.get("available"):
            return {
                **section,
                "requested": requested,
                "show_summary": show_summary,
                "show_highlights": show_highlights,
                "show_all_findings": show_all_findings,
                "highlight_rows": [],
                "visible_sections": [],
                "has_content": False,
            }

        return {
            **section,
            "requested": requested,
            "show_summary": show_summary,
            "show_highlights": show_highlights,
            "show_all_findings": show_all_findings,
            "highlight_rows": (
                list(section.get("highlight_rows", [])) if show_highlights else []
            ),
            "visible_sections": list(section.get("sections", [])) if show_all_findings else [],
            "has_content": requested
            and any((show_summary, show_highlights, show_all_findings)),
        }

    def _filter_license_summary(
        self,
        section: dict[str, Any],
        requested: bool,
        selection_ids: set[str],
    ) -> dict[str, Any]:
        show_summary = requested and section["metadata_section_id"] in selection_ids
        show_workload_sections = requested and section["workload_section_id"] in selection_ids
        show_other_licenses = (
            requested and section["other_licenses_section_id"] in selection_ids
        )
        show_agent_feature_licenses = (
            requested and section["agent_feature_section_id"] in selection_ids
        )

        if not section.get("available"):
            return {
                **section,
                "requested": requested,
                "show_summary": show_summary,
                "show_workload_sections": show_workload_sections,
                "show_other_licenses": show_other_licenses,
                "show_agent_feature_licenses": show_agent_feature_licenses,
                "visible_workload_sections": [],
                "visible_other_license_rows": [],
                "visible_agent_feature_rows": [],
                "has_content": False,
            }

        return {
            **section,
            "requested": requested,
            "show_summary": show_summary,
            "show_workload_sections": show_workload_sections,
            "show_other_licenses": show_other_licenses,
            "show_agent_feature_licenses": show_agent_feature_licenses,
            "visible_workload_sections": (
                list(section.get("workload_sections", []))
                if show_workload_sections
                else []
            ),
            "visible_other_license_rows": (
                list(section.get("other_license_rows", [])) if show_other_licenses else []
            ),
            "visible_agent_feature_rows": (
                list(section.get("agent_feature_rows", []))
                if show_agent_feature_licenses
                else []
            ),
            "has_content": requested
            and any(
                (
                    show_summary,
                    show_workload_sections,
                    show_other_licenses,
                    show_agent_feature_licenses,
                )
            ),
        }

    def _filter_client_growth(
        self,
        section: dict[str, Any],
        requested: bool,
        selection_ids: set[str],
    ) -> dict[str, Any]:
        show_summary = requested and section["summary_section_id"] in selection_ids
        show_chart = requested and section["chart_section_id"] in selection_ids
        show_monthly_table = (
            requested and section["monthly_table_section_id"] in selection_ids
        )
        has_content = requested and any((show_summary, show_chart, show_monthly_table))

        if not section.get("available"):
            return {
                **section,
                "requested": requested,
                "show_summary": show_summary,
                "show_chart": show_chart,
                "show_monthly_table": show_monthly_table,
                "chart": None,
                "rows": [],
                "has_content": False,
            }

        return {
            **section,
            "requested": requested,
            "show_summary": show_summary,
            "show_chart": show_chart,
            "show_monthly_table": show_monthly_table,
            "chart": section.get("chart") if show_chart else None,
            "rows": list(section.get("rows", [])) if show_monthly_table else [],
            "has_content": has_content,
        }

    def _filter_capacity_license(
        self,
        section: dict[str, Any],
        requested: bool,
        selection_ids: set[str],
    ) -> dict[str, Any]:
        show_summary = requested and section["summary_section_id"] in selection_ids
        show_table = requested and section["table_section_id"] in selection_ids
        has_content = requested and any((show_summary, show_table))

        if not section.get("available"):
            return {
                **section,
                "requested": requested,
                "show_summary": show_summary,
                "show_table": show_table,
                "latest_rows": [],
                "has_content": False,
            }

        return {
            **section,
            "requested": requested,
            "show_summary": show_summary,
            "show_table": show_table,
            "latest_rows": list(section.get("latest_rows", [])) if show_table else [],
            "has_content": has_content,
        }

    def _default_report_selection_ids(self, report: dict[str, Any]) -> set[str]:
        selection_ids: set[str] = {
            report["environment"]["metadata_section_id"],
            CLIENT_GROWTH_SUMMARY_SECTION_ID,
            CLIENT_GROWTH_CHART_SECTION_ID,
            CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID,
            CAPACITY_LICENSE_SUMMARY_SECTION_ID,
            CAPACITY_LICENSE_TABLE_SECTION_ID,
        }

        security = report["security_assessment"]
        if security.get("available"):
            selection_ids.add(security["summary_section_id"])

        license_summary = report["license_summary"]
        if license_summary.get("available"):
            selection_ids.add(license_summary["metadata_section_id"])

        return selection_ids

    def _expand_subject_selection_ids(self, selection_ids: set[str]) -> set[str]:
        expanded_selection_ids = set(selection_ids & REPORT_SECTION_IDS)
        for subject_id, options in REPORT_SUBSECTION_OPTIONS.items():
            if subject_id not in selection_ids:
                continue
            explicit_child_ids = {
                option["id"] for option in options if option["id"] in selection_ids
            }
            if explicit_child_ids:
                expanded_selection_ids.update(explicit_child_ids)
                continue
            expanded_selection_ids.update(option["id"] for option in options)
        return expanded_selection_ids


def _first_value(*payloads: dict[str, Any] | None, key: str) -> str | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _client_growth_chart(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None

    labels = [str(record.get("month") or "") for record in records]
    total_clients = [_coerce_int(record.get("total_clients")) or 0 for record in records]
    added = [_coerce_int(record.get("added")) or 0 for record in records]
    removed = [_coerce_int(record.get("removed")) or 0 for record in records]
    if not any(total_clients):
        return None

    return {
        "canvas_id": "client-growth-history-chart",
        "type": "bar",
        "title": "Client Growth History",
        "labels": labels,
        "datasets": [
            {
                "type": "line",
                "label": "Total clients",
                "data": total_clients,
                "borderColor": "rgb(36, 87, 166)",
                "backgroundColor": "rgba(36, 87, 166, 0.16)",
                "borderWidth": 3,
                "pointRadius": 4,
                "pointHoverRadius": 5,
                "pointBackgroundColor": "rgb(36, 87, 166)",
                "tension": 0.25,
                "fill": False,
                "yAxisID": "clients",
                "order": 1,
            },
            {
                "type": "bar",
                "label": "Added clients",
                "data": added,
                "backgroundColor": "rgba(22, 163, 74, 0.70)",
                "borderColor": "rgb(22, 163, 74)",
                "borderWidth": 1,
                "yAxisID": "changes",
                "order": 2,
            },
            {
                "type": "bar",
                "label": "Removed clients",
                "data": removed,
                "backgroundColor": "rgba(217, 119, 6, 0.68)",
                "borderColor": "rgb(217, 119, 6)",
                "borderWidth": 1,
                "yAxisID": "changes",
                "order": 3,
            },
        ],
        "x_label": "Month",
        "scales": {
            "clients": {
                "beginAtZero": False,
                "position": "left",
                "title": {"display": True, "text": "Total clients"},
                "grid": {"color": "rgba(148, 163, 184, 0.20)"},
            },
            "changes": {
                "beginAtZero": True,
                "position": "right",
                "title": {"display": True, "text": "Added / removed clients"},
                "grid": {"drawOnChartArea": False},
            },
            "x": {
                "grid": {"color": "rgba(148, 163, 184, 0.16)"},
            },
        },
    }


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
