from __future__ import annotations

from .models import SectionDefinition, TileDefinition


ENVIRONMENT_SELECTION_ID = "environment"
SECURITY_ASSESSMENT_SELECTION_ID = "security_assessment"
LICENSE_SUMMARY_SELECTION_ID = "license_summary"
CLIENT_GROWTH_SELECTION_ID = "client_growth"
CAPACITY_LICENSE_SELECTION_ID = "capacity_license"
BACKUP_JOB_SUMMARY_SELECTION_ID = "backup_job_summary"

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
BACKUP_JOB_SUMMARY_SUMMARY_SECTION_ID = "backup_job_summary.summary"
BACKUP_JOB_SUMMARY_STATUS_BREAKDOWN_SECTION_ID = "backup_job_summary.status_breakdown"
BACKUP_JOB_SUMMARY_RECENT_FAILURES_SECTION_ID = "backup_job_summary.recent_failures"
BACKUP_JOB_SUMMARY_RECENT_JOBS_SECTION_ID = "backup_job_summary.recent_jobs"

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
        detail_endpoint="main.quick_hc_security_assessment",
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
                id=SECURITY_ASSESSMENT_ALL_FINDINGS_SECTION_ID,
                label="Info / Good findings",
                preview_renderer="security_all_findings_preview",
                report_renderer="security_all_findings_report",
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
        detail_endpoint="main.quick_hc_license_summary",
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
