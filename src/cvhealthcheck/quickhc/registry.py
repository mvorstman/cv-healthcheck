from __future__ import annotations

from .models import SectionDefinition, SourceDefinition, TileDefinition


ENVIRONMENT_SELECTION_ID = "environment"
SECURITY_ASSESSMENT_SELECTION_ID = "security_assessment"
LICENSE_SUMMARY_SELECTION_ID = "license_summary"
CLIENT_GROWTH_SELECTION_ID = "client_growth"
CAPACITY_LICENSE_SELECTION_ID = "capacity_license"
BACKUP_JOB_SUMMARY_SELECTION_ID = "backup_job_summary"

REST_COMMAND_CENTER_API_SOURCE_ID = "rest_command_center_api"
REST_REPORTS_PLUS_SOURCE_ID = "rest_reports_plus"
JSON_IMPORT_SOURCE_ID = "json_import"
CSV_IMPORT_SOURCE_ID = "csv_import"
HTML_IMPORT_SOURCE_ID = "html_import"

UNIVERSAL_SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        id=REST_COMMAND_CENTER_API_SOURCE_ID,
        label="REST / Command Center API",
        description="Live collection through Command Center API endpoints.",
    ),
    SourceDefinition(
        id=REST_REPORTS_PLUS_SOURCE_ID,
        label="REST / Reports Plus",
        description="Live collection through Reports Plus report and dataset endpoints.",
    ),
    SourceDefinition(
        id=JSON_IMPORT_SOURCE_ID,
        label="JSON import",
        description="Offline JSON import into the canonical Quick HC artifact contract.",
    ),
    SourceDefinition(
        id=CSV_IMPORT_SOURCE_ID,
        label="CSV import",
        description="Offline CSV import into the canonical Quick HC artifact contract.",
    ),
    SourceDefinition(
        id=HTML_IMPORT_SOURCE_ID,
        label="HTML import",
        description="Offline HTML import into the canonical Quick HC artifact contract.",
    ),
)

ENVIRONMENT_METADATA_SECTION_ID = "environment.metadata"
SECURITY_ASSESSMENT_SUMMARY_SECTION_ID = "security_assessment.summary"
SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID = "security_assessment.highlights"
SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID = "security_assessment.all_findings"
SECURITY_ASSESSMENT_ACCESS_SECURITY_SECTION_ID = "security_assessment.access_security"
SECURITY_ASSESSMENT_AUDITING_SECTION_ID = "security_assessment.auditing"
SECURITY_ASSESSMENT_PLATFORM_SECURITY_SECTION_ID = "security_assessment.platform_security"
SECURITY_ASSESSMENT_COMPANY_OWNERS_SECURITY_SECTION_ID = (
    "security_assessment.company_and_owners_security"
)
SECURITY_ASSESSMENT_CAPABILITIES_SECTION_ID = "security_assessment.capabilities"
SECURITY_ASSESSMENT_HARDENING_SECTION_ID = "security_assessment.hardening"
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
BACKUP_JOB_SUMMARY_SUMMARY_SECTION_ID = "backup_job_summary.summary"
BACKUP_JOB_SUMMARY_STATUS_BREAKDOWN_SECTION_ID = "backup_job_summary.status_breakdown"
BACKUP_JOB_SUMMARY_RECENT_FAILURES_SECTION_ID = "backup_job_summary.recent_failures"
BACKUP_JOB_SUMMARY_RECENT_JOBS_SECTION_ID = "backup_job_summary.recent_jobs"

SECURITY_ASSESSMENT_DETAIL_SECTION_IDS_BY_NAME = {
    "Access Security": SECURITY_ASSESSMENT_ACCESS_SECURITY_SECTION_ID,
    "Auditing": SECURITY_ASSESSMENT_AUDITING_SECTION_ID,
    "Platform Security": SECURITY_ASSESSMENT_PLATFORM_SECURITY_SECTION_ID,
    "Company and Owners Security": SECURITY_ASSESSMENT_COMPANY_OWNERS_SECURITY_SECTION_ID,
    "Capabilities": SECURITY_ASSESSMENT_CAPABILITIES_SECTION_ID,
    "Hardening": SECURITY_ASSESSMENT_HARDENING_SECTION_ID,
}
SECURITY_ASSESSMENT_DETAIL_SECTION_ORDER = tuple(
    SECURITY_ASSESSMENT_DETAIL_SECTION_IDS_BY_NAME.keys()
)

QUICK_HC_TILES: tuple[TileDefinition, ...] = (
    TileDefinition(
        id=ENVIRONMENT_SELECTION_ID,
        title="CommCell Details",
        subtitle="Platform identity and environment context for the customer-facing summary.",
        source_type="rest",
        source_service="commcell_identity",
        artifact_type="commcell",
        preview_renderer="commcell_preview",
        report_renderer="environment_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.quick_hc_commcell",
        sections=(
            SectionDefinition(
                id=ENVIRONMENT_METADATA_SECTION_ID,
                label="Environment metadata",
                preview_renderer="commcell_metadata_preview",
                report_renderer="environment_metadata_report",
            ),
        ),
    ),
    TileDefinition(
        id=SECURITY_ASSESSMENT_SELECTION_ID,
        title="Security Assessment",
        subtitle="Posture summary with emphasis on the most important findings to address.",
        source_type="reportsplus",
        source_service="security_assessment_service",
        artifact_type="security_assessment",
        preview_renderer="security_assessment_preview",
        report_renderer="security_assessment_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.quick_hc",
        collect_capable=True,
        import_capable=True,
        sections=(
            SectionDefinition(
                id=SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
                label="Summary counters",
                preview_renderer="security_summary_preview",
                report_renderer="security_summary_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
                label="Critical / Warning findings",
                preview_renderer="security_highlights_preview",
                report_renderer="security_highlights_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_ACCESS_SECURITY_SECTION_ID,
                label="Access Security",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_AUDITING_SECTION_ID,
                label="Auditing",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_PLATFORM_SECURITY_SECTION_ID,
                label="Platform Security",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_COMPANY_OWNERS_SECURITY_SECTION_ID,
                label="Company and Owners Security",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_CAPABILITIES_SECTION_ID,
                label="Capabilities",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_HARDENING_SECTION_ID,
                label="Hardening",
                default_selected=False,
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
        ),
    ),
    TileDefinition(
        id=LICENSE_SUMMARY_SELECTION_ID,
        title="License Summary",
        subtitle="Consumption snapshot across workloads, other licenses, and agent or feature usage.",
        source_type="reportsplus",
        source_service="license_summary_service",
        artifact_type="license_summary",
        preview_renderer="license_summary_preview",
        report_renderer="license_summary_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.quick_hc",
        collect_capable=True,
        import_capable=True,
        sections=(
            SectionDefinition(
                id=LICENSE_SUMMARY_METADATA_SECTION_ID,
                label="Summary metadata",
                preview_renderer="license_metadata_preview",
                report_renderer="license_metadata_report",
            ),
            SectionDefinition(
                id=LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
                label="Workload Summary Sections",
                preview_renderer="license_workload_preview",
                report_renderer="license_workload_report",
            ),
            SectionDefinition(
                id=LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
                label="Other Licenses table",
                preview_renderer="license_other_preview",
                report_renderer="license_other_report",
            ),
            SectionDefinition(
                id=LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
                label="Agent / Feature Licenses table",
                preview_renderer="license_agent_feature_preview",
                report_renderer="license_agent_feature_report",
            ),
        ),
    ),
    TileDefinition(
        id=CLIENT_GROWTH_SELECTION_ID,
        title="Client Growth",
        subtitle="Trend snapshot showing recent protected client count and change over time.",
        source_type="metrics",
        source_service="client_growth_metrics",
        artifact_type="client_growth",
        preview_renderer="client_growth_preview",
        report_renderer="client_growth_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.metrics_client_growth",
        sections=(
            SectionDefinition(
                id=CLIENT_GROWTH_SUMMARY_SECTION_ID,
                label="Summary metrics",
                preview_renderer="client_growth_summary_preview",
                report_renderer="client_growth_summary_report",
            ),
            SectionDefinition(
                id=CLIENT_GROWTH_CHART_SECTION_ID,
                label="Client Growth chart",
                preview_renderer="client_growth_chart_preview",
                report_renderer="client_growth_chart_report",
            ),
            SectionDefinition(
                id=CLIENT_GROWTH_MONTHLY_TABLE_SECTION_ID,
                label="Monthly summary table",
                preview_renderer="client_growth_monthly_preview",
                report_renderer="client_growth_monthly_report",
            ),
        ),
    ),
    TileDefinition(
        id=CAPACITY_LICENSE_SELECTION_ID,
        title="Capacity Licenses",
        subtitle="Capacity utilization summary for the latest available reporting period.",
        source_type="metrics",
        source_service="capacity_license_metrics",
        artifact_type="capacity_license",
        preview_renderer="capacity_license_preview",
        report_renderer="capacity_license_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.metrics_capacity_license",
        sections=(
            SectionDefinition(
                id=CAPACITY_LICENSE_SUMMARY_SECTION_ID,
                label="Summary",
                preview_renderer="capacity_license_summary_preview",
                report_renderer="capacity_license_summary_report",
            ),
            SectionDefinition(
                id=CAPACITY_LICENSE_TABLE_SECTION_ID,
                label="Usage/details table",
                preview_renderer="capacity_license_table_preview",
                report_renderer="capacity_license_table_report",
            ),
        ),
    ),
    TileDefinition(
        id=BACKUP_JOB_SUMMARY_SELECTION_ID,
        title="Backup Job Summary",
        subtitle="Operational backup job visibility from the latest Reports Plus Backup Job Summary artifact.",
        source_type="reportsplus",
        source_service="backup_job_summary_collector",
        artifact_type="backup_job_summary",
        preview_renderer="backup_job_summary_preview",
        report_renderer="backup_job_summary_report",
        sources=UNIVERSAL_SOURCE_DEFINITIONS,
        detail_endpoint="main.quick_hc_backup_job_summary",
        sections=(
            SectionDefinition(
                id=BACKUP_JOB_SUMMARY_SUMMARY_SECTION_ID,
                label="Summary",
                preview_renderer="backup_job_summary_summary_preview",
                report_renderer="backup_job_summary_summary_report",
            ),
            SectionDefinition(
                id=BACKUP_JOB_SUMMARY_STATUS_BREAKDOWN_SECTION_ID,
                label="Status breakdown",
                preview_renderer="backup_job_summary_status_preview",
                report_renderer="backup_job_summary_status_report",
            ),
            SectionDefinition(
                id=BACKUP_JOB_SUMMARY_RECENT_FAILURES_SECTION_ID,
                label="Recent failures",
                preview_renderer="backup_job_summary_failures_preview",
                report_renderer="backup_job_summary_failures_report",
            ),
            SectionDefinition(
                id=BACKUP_JOB_SUMMARY_RECENT_JOBS_SECTION_ID,
                label="Recent jobs",
                preview_renderer="backup_job_summary_jobs_preview",
                report_renderer="backup_job_summary_jobs_report",
            ),
        ),
    ),
)

QUICK_HC_TILE_BY_ID: dict[str, TileDefinition] = {
    tile.id: tile for tile in QUICK_HC_TILES
}
QUICK_HC_SUBJECT_IDS = {tile.id for tile in QUICK_HC_TILES}
QUICK_HC_SECTION_IDS = {
    section.id for tile in QUICK_HC_TILES for section in tile.sections
}
QUICK_HC_SELECTION_IDS = QUICK_HC_SUBJECT_IDS | QUICK_HC_SECTION_IDS


def report_subsection_options() -> dict[str, tuple[dict[str, str], ...]]:
    return {
        tile.id: tuple({"id": section.id, "label": section.label} for section in tile.sections)
        for tile in QUICK_HC_TILES
    }


def report_overview_default_selection_ids() -> set[str]:
    return {
        tile.id
        for tile in QUICK_HC_TILES
    } | {
        section.id
        for tile in QUICK_HC_TILES
        for section in tile.sections
        if section.default_selected
    }
