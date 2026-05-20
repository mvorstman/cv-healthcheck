from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cvhealthcheck.license_summary.service import LicenseSummaryService
from cvhealthcheck.metrics import (
    get_capacity_license_usage,
    get_client_growth_summary,
)
from cvhealthcheck.quickhc.commcell import normalize_commserv
from cvhealthcheck.quickhc.models import TileDefinition
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID, QUICK_HC_TILES
from cvhealthcheck.quickhc.report_service import (
    REPORT_OVERVIEW_DEFAULT_SELECTION_IDS,
    REPORT_SUBSECTION_OPTIONS,
)
from cvhealthcheck.reportsplus.catalog import catalog_status, read_json
from cvhealthcheck.reportsplus.security_assessment import security_assessment_quick_hc


OverviewPreviewBuilder = Callable[[TileDefinition], dict[str, Any]]


OVERVIEW_PREVIEW_BUILDERS: dict[str, OverviewPreviewBuilder] = {}
OVERVIEW_CONTEXT_KEYS: dict[str, str] = {
    "environment": "commcell_preview",
    "security_assessment": "security_assessment",
    "license_summary": "license_summary",
    "client_growth": "client_growth",
    "capacity_license": "capacity_license",
}


def build_quick_hc_overview_context() -> dict[str, Any]:
    tile_previews = build_quick_hc_tile_previews()
    return {
        "commcell_status": catalog_status(
            "commserv.json",
            catalog_dir=Path("data/catalog/rest"),
        ),
        "quick_hc_tile_previews": tile_previews,
        "quick_hc_tiles": QUICK_HC_TILE_BY_ID,
        "selected_report_sections": REPORT_OVERVIEW_DEFAULT_SELECTION_IDS,
        "report_subsection_options": REPORT_SUBSECTION_OPTIONS,
        **{
            context_key: tile_previews[tile_id]
            for tile_id, context_key in OVERVIEW_CONTEXT_KEYS.items()
        },
    }


def build_quick_hc_tile_previews(
    tiles: tuple[TileDefinition, ...] = QUICK_HC_TILES,
) -> dict[str, dict[str, Any]]:
    return {
        tile.id: build_quick_hc_tile_preview(tile)
        for tile in tiles
    }


def build_quick_hc_tile_preview(tile: TileDefinition) -> dict[str, Any]:
    builder = OVERVIEW_PREVIEW_BUILDERS.get(tile.preview_renderer)
    if builder is None:
        raise KeyError(f"No Quick HC overview preview builder registered for {tile.id}")
    return builder(tile)


def commcell_quick_hc_preview(tile: TileDefinition | None = None) -> dict[str, Any]:
    try:
        payload = read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))
    except FileNotFoundError:
        return {
            "exists": False,
            "summary": "Not collected yet",
        }

    identity_payload = payload.get("identity") if isinstance(payload, dict) else {}
    identity = (
        identity_payload
        if hasattr(identity_payload, "get")
        else normalize_commserv(payload if isinstance(payload, dict) else {}).to_dict()
    )
    return {
        "exists": True,
        "commcell_name": identity.get("hostName"),
        "commcell_id": identity.get("csGUID"),
        "version": identity.get("csVersionInfo"),
        "release_id": identity.get("releaseId"),
        "timezone": identity.get("timeZone"),
        "status": "Available",
        "summary": (
            f"{identity.get('hostName') or 'CommCell'}"
            if identity.get("hostName")
            else "CommCell details available"
        ),
    }


def security_assessment_quick_hc_preview(
    tile: TileDefinition | None = None,
) -> dict[str, Any]:
    return security_assessment_quick_hc()


def license_summary_quick_hc_preview(
    tile: TileDefinition | None = None,
) -> dict[str, Any]:
    try:
        payload = LicenseSummaryService().get_current()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": "data/catalog/license_summary/latest.json",
        }

    workload_sections = list(payload.get("workload_summary_sections") or [])
    other_licenses = list(payload.get("other_licenses") or [])
    agent_feature_licenses = list(payload.get("agent_feature_licenses") or [])
    workload_section_previews = []
    for section in workload_sections:
        rows = list(section.get("rows") or [])
        preview_names = [
            str(row.get("license") or "")
            for row in rows
            if str(row.get("license") or "").strip()
        ]
        workload_section_previews.append(
            {
                "section_name": str(section.get("section_name") or ""),
                "row_count": len(rows),
                "license_names": preview_names[:3],
            }
        )

    other_license_preview_rows = [
        {
            "license": item.get("license"),
            "available_total": item.get("available_total")
            if item.get("available_total") is not None
            else item.get("raw_available_total"),
            "used": item.get("used")
            if item.get("used") is not None
            else item.get("raw_used"),
        }
        for item in other_licenses[:5]
    ]
    agent_feature_preview_rows = [
        {
            "license": item.get("license"),
            "client": item.get("client"),
            "agent": item.get("agent"),
            "usage": " / ".join(
                [
                    str(value)
                    for value in (item.get("permanent_used"), item.get("term_used"))
                    if value not in (None, "")
                ]
            ),
        }
        for item in agent_feature_licenses[:5]
    ]
    return {
        "exists": True,
        "path": str(
            payload.get("file_path") or "data/catalog/license_summary/latest.json"
        ),
        "source_type": payload.get("source_type"),
        "imported_at": payload.get("imported_at"),
        "generated_on": payload.get("generated_on"),
        "customer_id": payload.get("customer_id"),
        "commcell_id": payload.get("commcell_id"),
        "commcell_name": payload.get("commcell_name"),
        "license_expiry": payload.get("license_expiry"),
        "workload_section_count": len(workload_sections),
        "workload_section_names": [
            str(section.get("section_name") or "")
            for section in workload_sections
            if str(section.get("section_name") or "").strip()
        ],
        "workload_section_previews": workload_section_previews[:4],
        "other_count": len(other_licenses),
        "other_license_names": [
            str(item.get("license") or "")
            for item in other_licenses
            if str(item.get("license") or "").strip()
        ],
        "other_license_preview_rows": other_license_preview_rows,
        "other_license_more_count": max(
            len(other_licenses) - len(other_license_preview_rows),
            0,
        ),
        "agent_feature_count": len(agent_feature_licenses),
        "agent_feature_examples": [
            str(item.get("license") or "")
            for item in agent_feature_licenses
            if str(item.get("license") or "").strip()
        ],
        "agent_feature_preview_rows": agent_feature_preview_rows,
        "agent_feature_more_count": max(
            len(agent_feature_licenses) - len(agent_feature_preview_rows),
            0,
        ),
    }


def client_growth_quick_hc_preview(
    tile: TileDefinition | None = None,
) -> dict[str, Any]:
    try:
        summary = get_client_growth_summary(live=False)
    except FileNotFoundError:
        return {
            "exists": False,
            "source_label": "Reports Plus / Metrics",
            "summary": "Not collected yet",
        }

    records = list(summary.get("records") or [])
    latest = records[-1] if records else {}
    return {
        "exists": True,
        "source_label": "Reports Plus / Metrics",
        "record_count": int(summary.get("record_count") or 0),
        "history_range": summary.get("history_range"),
        "latest_month": latest.get("month"),
        "latest_total_clients": latest.get("total_clients"),
        "latest_added": latest.get("added"),
        "latest_removed": latest.get("removed"),
        "summary": (
            f"{latest.get('month')}: {latest.get('total_clients') or 0} total clients, "
            f"{latest.get('added') or 0} added, {latest.get('removed') or 0} removed"
            if latest
            else "No summary rows are available."
        ),
    }


def capacity_license_quick_hc_preview(
    tile: TileDefinition | None = None,
) -> dict[str, Any]:
    try:
        metric = get_capacity_license_usage(live=False)
    except FileNotFoundError:
        return {
            "exists": False,
            "source_label": "Reports Plus / Metrics",
            "summary": "Not collected yet",
        }

    records = list(metric.get("records") or [])
    history_range = metric.get("history_range")
    latest_month = history_range.get("end") if history_range else None
    latest_records = [row for row in records if row.get("month") == latest_month]
    total_used = sum(float(row.get("used_capacity") or 0) for row in latest_records)
    total_purchased = sum(
        float(row.get("purchased_capacity") or 0) for row in latest_records
    )
    return {
        "exists": True,
        "source_label": "Reports Plus / Metrics",
        "record_count": int(metric.get("record_count") or 0),
        "history_range": history_range,
        "latest_month": latest_month,
        "entity_count": len(latest_records),
        "total_used": total_used,
        "total_purchased": total_purchased,
        "summary": (
            f"{latest_month}: {len(latest_records)} entities, {total_used:.2f} used of {total_purchased:.2f}"
            if latest_month and latest_records
            else "No capacity rows are available."
        ),
    }


OVERVIEW_PREVIEW_BUILDERS.update(
    {
        "commcell_preview": commcell_quick_hc_preview,
        "security_assessment_preview": security_assessment_quick_hc_preview,
        "license_summary_preview": license_summary_quick_hc_preview,
        "client_growth_preview": client_growth_quick_hc_preview,
        "capacity_license_preview": capacity_license_quick_hc_preview,
    }
)
