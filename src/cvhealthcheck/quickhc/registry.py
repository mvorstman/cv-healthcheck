from __future__ import annotations

import sqlite3
from typing import Any

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

STANDARD_SOURCES: list[str] = [
    REST_COMMAND_CENTER_API_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    JSON_IMPORT_SOURCE_ID,
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
]

SOURCE_LABELS: dict[str, str] = {
    REST_COMMAND_CENTER_API_SOURCE_ID: "REST / Command Center API",
    REST_REPORTS_PLUS_SOURCE_ID:       "REST / Reports Plus",
    JSON_IMPORT_SOURCE_ID:             "JSON import",
    CSV_IMPORT_SOURCE_ID:              "CSV import",
    HTML_IMPORT_SOURCE_ID:             "HTML import",
}

SOURCE_DESCRIPTIONS: dict[str, str] = {
    REST_COMMAND_CENTER_API_SOURCE_ID: "Live collection through Command Center API endpoints.",
    REST_REPORTS_PLUS_SOURCE_ID:       "Live collection through Reports Plus report and dataset endpoints.",
    JSON_IMPORT_SOURCE_ID:             "Offline JSON import into the canonical Quick HC artifact contract.",
    CSV_IMPORT_SOURCE_ID:              "Offline CSV import into the canonical Quick HC artifact contract.",
    HTML_IMPORT_SOURCE_ID:             "Offline HTML import into the canonical Quick HC artifact contract.",
}

# ADR 0007 ph3 follow-on: the REST endpoint a live source collects from, keyed by
# canonical source id. Source-TYPE metadata (a constant of the source, not of any
# one collection), surfaced on the generic source panel so it survives the live
# builder's retirement. Only sources with a fixed single endpoint appear here;
# absent → no endpoint row (Reports Plus varies by report, imports have none).
SOURCE_ENDPOINTS: dict[str, str] = {
    REST_COMMAND_CENTER_API_SOURCE_ID: "GET /commandcenter/api/CommServ",
}

# Private tuple kept for canonical_view.py backward compatibility (legacy subject builders).
_UNIVERSAL_SOURCES: tuple[SourceDefinition, ...] = tuple(
    SourceDefinition(id=sid, label=SOURCE_LABELS[sid], description=SOURCE_DESCRIPTIONS[sid])
    for sid in STANDARD_SOURCES
)

ENVIRONMENT_METADATA_SECTION_ID = "environment.metadata"
SECURITY_ASSESSMENT_METADATA_SECTION_ID = "security_assessment.metadata"
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

_SYSTEM_TILES: tuple[TileDefinition, ...] = (
    TileDefinition(
        id=ENVIRONMENT_SELECTION_ID,
        title="CommCell Details",
        subtitle="Platform identity and environment context for the customer-facing summary.",
        category="identity",
        category_label="Identity",
        source_type="rest",
        source_service="commcell_identity",
        artifact_type="commcell",
        preview_renderer="commcell_preview",
        report_renderer="environment_report",
        sources=_UNIVERSAL_SOURCES,
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
        category="security",
        category_label="Security",
        source_type="reportsplus",
        source_service="security_assessment_service",
        artifact_type="security_assessment",
        preview_renderer="security_assessment_preview",
        report_renderer="security_assessment_report",
        sources=_UNIVERSAL_SOURCES,
        detail_endpoint="main.quick_hc",
        collect_capable=True,
        import_capable=True,
        import_url="/quick-hc/security-assessment/import",
        # collect_url omitted — the dynamic /quick-hc/<subject_id>/collect
        # URL is built at runtime from the catalog's rest source row
        # (ADR 0003 phase 4 migrated SA to the catalog-driven extractor).
        sections=(
            SectionDefinition(
                id=SECURITY_ASSESSMENT_METADATA_SECTION_ID,
                label="Source metadata",
                preview_renderer="security_metadata_preview",
                report_renderer="security_metadata_report",
            ),
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
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_AUDITING_SECTION_ID,
                label="Auditing",
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_PLATFORM_SECURITY_SECTION_ID,
                label="Platform Security",
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_COMPANY_OWNERS_SECURITY_SECTION_ID,
                label="Company and Owners Security",
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_CAPABILITIES_SECTION_ID,
                label="Capabilities",
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
            SectionDefinition(
                id=SECURITY_ASSESSMENT_HARDENING_SECTION_ID,
                label="Hardening",
                preview_renderer="security_section_preview",
                report_renderer="security_detail_section_report",
            ),
        ),
    ),
    TileDefinition(
        id=LICENSE_SUMMARY_SELECTION_ID,
        title="License Summary",
        subtitle="Consumption snapshot across workloads, other licenses, and agent or feature usage.",
        category="licensing",
        category_label="Licensing",
        source_type="reportsplus",
        source_service="license_summary_service",
        artifact_type="license_summary",
        preview_renderer="license_summary_preview",
        report_renderer="license_summary_report",
        sources=_UNIVERSAL_SOURCES,
        detail_endpoint="main.quick_hc",
        collect_capable=True,
        import_capable=True,
        import_url="/quick-hc/license-summary/import",
        collect_url="/quick-hc/license-summary/collect",
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
        category="performance",
        category_label="Performance & Growth",
        source_type="metrics",
        source_service="client_growth_metrics",
        artifact_type="client_growth",
        preview_renderer="client_growth_preview",
        report_renderer="client_growth_report",
        sources=_UNIVERSAL_SOURCES,
        # ADR 0004 #25: client_growth now renders canonically in the workspace
        # (phase 6), so its report "detail" link opens the workspace like SA/LS —
        # not the retired dev metrics page (phase 6.5).
        detail_endpoint="main.quick_hc",
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
        category="performance",
        category_label="Performance & Growth",
        source_type="metrics",
        source_service="capacity_license_metrics",
        artifact_type="capacity_license",
        preview_renderer="capacity_license_preview",
        report_renderer="capacity_license_report",
        sources=_UNIVERSAL_SOURCES,
        # ADR 0004 #25: capacity_license now renders canonically in the workspace
        # (phase 5), so its report "detail" link opens the workspace like SA/LS —
        # not the retired dev metrics page (phase 6.5).
        detail_endpoint="main.quick_hc",
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
        category="operations",
        category_label="Operations",
        source_type="reportsplus",
        source_service="backup_job_summary_collector",
        artifact_type="backup_job_summary",
        preview_renderer="backup_job_summary_preview",
        report_renderer="backup_job_summary_report",
        sources=_UNIVERSAL_SOURCES,
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
    tile.id: tile for tile in _SYSTEM_TILES
}
QUICK_HC_SUBJECT_IDS = {tile.id for tile in _SYSTEM_TILES}
QUICK_HC_SECTION_IDS = {
    section.id for tile in _SYSTEM_TILES for section in tile.sections
}
QUICK_HC_SELECTION_IDS = QUICK_HC_SUBJECT_IDS | QUICK_HC_SECTION_IDS


def list_tiles() -> tuple[TileDefinition, ...]:
    return _SYSTEM_TILES


def get_tiles(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all active subjects as tile dicts (system tiles + db-registered subjects)."""
    from cvhealthcheck.db.subjects import get_all_active_subjects
    subjects = get_all_active_subjects(db)
    return [_subject_to_tile(subject) for subject in subjects]


_SOURCE_TYPE_TO_CANONICAL_ID: dict[str, str] = {
    "html": HTML_IMPORT_SOURCE_ID,
    "csv":  CSV_IMPORT_SOURCE_ID,
    "rest": REST_REPORTS_PLUS_SOURCE_ID,
    "json": JSON_IMPORT_SOURCE_ID,
    # ADR 0007 ph3 follow-on: the single-object Command Center API source. Without
    # this, a rest_command_center_api row (e.g. environment row 22) maps to
    # src_id=None and is dropped below — so its source tab + Collect button never
    # render in the generic path once a stored artifact wins precedence.
    "rest_command_center_api": REST_COMMAND_CENTER_API_SOURCE_ID,
}

_SOURCE_TYPE_TO_LABEL: dict[str, str] = {
    "html": "HTML import",
    "csv":  "CSV import",
    "rest": "REST / Reports Plus",
    "json": "JSON import",
    "rest_command_center_api": "REST / Command Center API",
}


def _build_db_source_entries(
    source_rows: list[dict[str, Any]],
    subject_id: str = "",
) -> list[dict[str, Any]]:
    if not source_rows:
        return [
            {"id": sid, "label": SOURCE_LABELS.get(sid, sid), "description": SOURCE_DESCRIPTIONS.get(sid, "")}
            for sid in STANDARD_SOURCES
        ]
    entries = []
    for src in source_rows:
        source_type = src.get("source_type", "")
        src_id = _SOURCE_TYPE_TO_CANONICAL_ID.get(source_type)
        if src_id is None:
            continue
        has_instructions = bool(src.get("has_section_instructions", 0))
        if source_type in ("rest", "rest_command_center_api") and has_instructions and subject_id:
            # Both live-REST collect paths post to the same /collect route; the
            # /collect dispatch (_has_command_center_source) picks the extractor.
            collect_url = f"/quick-hc/{subject_id}/collect"
        elif source_type == "json" and has_instructions and subject_id:
            # ADR 0004: internal fixture-backed subjects collect from a shipped
            # JSON file via the fixture route (no lab/auth).
            collect_url = f"/quick-hc/{subject_id}/collect-fixture"
        else:
            collect_url = None
        entries.append({
            "id": src_id,
            "label": _SOURCE_TYPE_TO_LABEL.get(source_type, source_type.upper()),
            "description": "",
            "source_type": source_type,
            "extractable": bool(src.get("extractable", 1)),
            "has_section_instructions": has_instructions,
            "collect_url": collect_url,
        })
    # ADR 0007 ph3 follow-on: when a subject has the single-object Command Center
    # API source, it SUPERSEDES the legacy plain-'rest' row for display. environment
    # carries both a stale 'rest' row (its old generic placeholder, whose live-card
    # rules only the now-bypassed bespoke builder reads) and the real
    # 'rest_command_center_api' row — both would otherwise post to the same /collect,
    # so a "REST / Reports Plus" tab for environment is a mislabeled duplicate.
    # Hide the plain-'rest' tab so the user sees one correct Command Center tab.
    # Generic (keyed on source_type, not subject id) and reversible; the 'rest' row
    # itself is untouched — only its tab is suppressed. environment is the only
    # command-center subject today, so nothing else is affected.
    if any(e["source_type"] == "rest_command_center_api" for e in entries):
        entries = [e for e in entries if e["source_type"] != "rest"]
    return entries or [
        {"id": sid, "label": SOURCE_LABELS.get(sid, sid), "description": SOURCE_DESCRIPTIONS.get(sid, "")}
        for sid in STANDARD_SOURCES
    ]


def _subject_to_tile(subject: dict[str, Any]) -> dict[str, Any]:
    """Convert a db subject row (with sections/sources lists) to a tile dict."""
    subject_id = subject["subject_id"]
    tile_def = QUICK_HC_TILE_BY_ID.get(subject_id)

    section_renderers: dict[str, tuple[str | None, str | None]] = {}
    if tile_def is not None:
        for sec in tile_def.sections:
            section_renderers[sec.id] = (sec.preview_renderer, sec.report_renderer)

    sections = []
    for sec in subject.get("sections", []):
        sec_id = sec["section_id"]
        preview_r, report_r = section_renderers.get(sec_id, (None, None))
        sections.append({
            "id": sec_id,
            "label": sec["title"],
            "default_selected": bool(sec["default_selected"]),
            "preview_renderer": preview_r,
            "report_renderer": report_r,
        })

    sources = _build_db_source_entries(subject.get("sources", []), subject_id)

    return {
        "id": subject_id,
        "title": tile_def.title if tile_def else subject["title"],
        "subtitle": tile_def.subtitle if tile_def else (subject.get("description") or ""),
        "description": tile_def.subtitle if tile_def else (subject.get("description") or ""),
        "category": subject["category"],
        "category_label": subject["category_label"],
        "source_type": tile_def.source_type if tile_def else (subject.get("preferred_source") or "rest"),
        "artifact_type": tile_def.artifact_type if tile_def else subject_id,
        "preview_renderer": tile_def.preview_renderer if tile_def else None,
        "report_renderer": tile_def.report_renderer if tile_def else None,
        "detail_endpoint": tile_def.detail_endpoint if tile_def else None,
        "sections": sections,
        "sources": sources,
        "created_by": subject.get("created_by", "system"),
        "status": subject.get("status", "active"),
    }


def report_subsection_options() -> dict[str, tuple[dict[str, str], ...]]:
    return {
        tile.id: tuple({"id": section.id, "label": section.label} for section in tile.sections)
        for tile in _SYSTEM_TILES
    }


def report_overview_default_selection_ids() -> set[str]:
    return {
        tile.id
        for tile in _SYSTEM_TILES
    } | {
        section.id
        for tile in _SYSTEM_TILES
        for section in tile.sections
        if section.default_selected
    }
