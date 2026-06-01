from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.db.subjects import (
    list_family_versions,
    resolve_active_version,
    subject_family,
)
from cvhealthcheck.license_summary.service import LicenseSummaryService


def _canonical_store() -> ArtifactStore:
    """Construct an ArtifactStore for the active project on demand.

    Replaces the module-level singleton from before ADR 0002 phase 2.
    Each call resolves the current request's active project (falling back
    to the Default project outside a request context).
    """
    from cvhealthcheck.web.active_project import make_active_project_store
    return make_active_project_store()
from cvhealthcheck.metrics import get_capacity_license_usage, get_client_growth_summary
from cvhealthcheck.quickhc import canonical_view as _canonical_view
from cvhealthcheck.quickhc.description_service import resolve_tile_description
from cvhealthcheck.reportsplus.backup_job_summary import load_backup_job_summary_artifact
from cvhealthcheck.reportsplus.catalog import read_json
from cvhealthcheck.reportsplus.security_assessment import security_assessment_quick_hc
from cvhealthcheck.quickhc.commcell import normalize_commserv
from cvhealthcheck.quickhc.registry import (
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
    JSON_IMPORT_SOURCE_ID,
    QUICK_HC_TILE_BY_ID,
    REST_COMMAND_CENTER_API_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    SECURITY_ASSESSMENT_DETAIL_SECTION_IDS_BY_NAME,
    SECURITY_ASSESSMENT_METADATA_SECTION_ID,
    SOURCE_DESCRIPTIONS,
    SOURCE_LABELS,
    STANDARD_SOURCES,
    get_tiles,
    list_tiles,
)
from cvhealthcheck.quickhc.source_provenance_dispatch import get_provenance_builder

# Unified upload route — every subject POSTs to /quick-hc/<id>/import.
# These constants feed the legacy builders' source-action wiring;
# _build_generic_sources synthesises the same URL inline for AI subjects.
_SA_IMPORT_URL = "/quick-hc/security_assessment/import"
_LS_IMPORT_URL = "/quick-hc/license_summary/import"

logger = logging.getLogger(__name__)

_MONTH_ABBR = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}

_CATEGORY_ICONS = {
    "identity": "🖥",
    "security": "🔒",
    "licensing": "📋",
    "performance": "📈",
    "operations": "🔧",
}


def build_subject_initial_data(
    db: sqlite3.Connection | None = None,
    customer_id: str | None = None,
) -> dict[str, Any]:
    """Build the full initial data structure for the Quick HC frontend.

    ``customer_id`` is used to resolve the active (pinned) template version
    per subject family for the source-tile version dropdown. When omitted,
    the dropdown shows the latest version as active.
    """
    if db is not None:
        all_tiles = get_tiles(db)
    else:
        all_tiles = [_tile_def_to_dict(t) for t in list_tiles()]

    try:
        from flask import url_for
        report_url = url_for("main.quick_hc_report")
    except Exception:
        report_url = "/quick-hc/report"

    legacy_loaders = _legacy_loaders()
    legacy_builders = _legacy_builders()

    # Commcell header comes from the environment legacy loader (reads commserv.json).
    commcell_loader = legacy_loaders.get("environment")
    commcell_raw = commcell_loader() if commcell_loader else None
    commcell_info = _build_commcell_header(commcell_raw)

    category_groups: dict[str, dict] = {}
    for tile in all_tiles:
        cat_id = tile["category"]
        subject_id = tile["id"]
        if cat_id not in category_groups:
            category_groups[cat_id] = {
                "id": cat_id,
                "name": tile["category_label"],
                "icon": _CATEGORY_ICONS.get(cat_id, ""),
                "open": True,
                "subjects": [],
            }

        # Canonical store wins for all subjects when an artifact exists.
        #
        # Source-building fork: see docs/adr/0001-source-building-fork.md.
        # The legacy_builder branch (six system subjects with custom
        # view shapes: counters, findings_grid, workload, chart_growth)
        # is intentional. It cannot be merged with _build_generic_subject
        # without first migrating the canonical schema. Do not remove
        # this fork without reading the ADR.
        artifact = _load_from_canonical_store(subject_id)
        if artifact is not None:
            built = _build_generic_subject(tile, artifact)
        else:
            legacy_loader = legacy_loaders.get(subject_id)
            legacy_builder = legacy_builders.get(subject_id)
            if legacy_builder is not None:
                loaded = legacy_loader() if legacy_loader else None
                # environment reads its per-field card rules from the catalog
                # binding (data, migration 0023), so it needs the db connection;
                # the other legacy builders take only their loaded blob.
                if subject_id == "environment":
                    built = legacy_builder(loaded, db)
                else:
                    built = legacy_builder(loaded)
            elif db is not None:
                built = _build_generic_subject(tile, None)
            else:
                continue

        built["created_by"] = tile.get("created_by", "system")
        # ADR 0004 source-tile cleanup: version dropdown + last-collected.
        built["version_info"] = _version_info(db, customer_id, subject_id)
        built["last_collected"] = _last_collected(artifact)
        # ADR 0004 phase 2: internal/test subjects (subject_id prefix "_") are
        # hidden in the sidebar by default; the settings-page toggle reveals
        # them. Class-level flag so future test subjects inherit the behavior.
        built["is_test"] = subject_id.startswith("_")
        category_groups[cat_id]["subjects"].append(built)

    cats = list(category_groups.values())

    return {
        "commcell": commcell_info,
        "cats": cats,
        "report_url": report_url,
    }


def _tile_def_to_dict(tile: Any) -> dict[str, Any]:
    """Convert a TileDefinition to the dict format used by get_tiles(db)."""
    return {
        "id": tile.id,
        "title": tile.title,
        "subtitle": tile.subtitle,
        "description": tile.subtitle,
        "category": tile.category,
        "category_label": tile.category_label,
        "source_type": tile.source_type,
        "artifact_type": tile.artifact_type,
        "preview_renderer": tile.preview_renderer,
        "report_renderer": tile.report_renderer,
        "detail_endpoint": tile.detail_endpoint,
        "sections": [
            {
                "id": s.id,
                "label": s.label,
                "default_selected": s.default_selected,
                "preview_renderer": s.preview_renderer,
                "report_renderer": s.report_renderer,
            }
            for s in tile.sections
        ],
        "sources": [
            {"id": s.id, "label": s.label, "description": s.description}
            for s in tile.sources
        ],
    }


def _load_from_canonical_store(subject_id: str) -> CanonicalArtifact | None:
    try:
        return _canonical_store().load_latest_artifact(subject_id)
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading canonical artifact for %s", subject_id)
        return None


# Subjects with a registered provenance builder also have their REST
# collection at a hyphenated route (dedicated service, not the generic
# /quick-hc/<subject_id>/collect). See source_provenance_dispatch.py.
_DISPATCH_REST_COLLECT_URLS: dict[str, str] = {
    # security_assessment migrated to the generic catalog-driven extractor
    # in ADR 0003 phase 4 — the dispatch provenance builder still produces
    # source-status badges, but the Collect button uses the generic URL
    # constructed by /quick-hc/<subject_id>/collect.
    "security_assessment": "/quick-hc/security_assessment/collect",
    "license_summary": "/quick-hc/license-summary/collect",
}

# Provenance status strings → tile-source short codes consumed by
# quick_hc.js. See quick_hc.js:329 for the front-end mapping.
_PROVENANCE_STATUS_TO_TILE_STATUS: dict[str, str] = {
    "validated": "v",
    "available": "a",
    "not_available": "n",
    "not_implemented": "ni",
    "not_tested": "n",
    "not_applicable": "ni",
}

_PROVENANCE_TYPE_TO_SOURCE_ID: dict[str, str] = {
    "rest_reports_plus": REST_REPORTS_PLUS_SOURCE_ID,
    "csv": CSV_IMPORT_SOURCE_ID,
    "html": HTML_IMPORT_SOURCE_ID,
}


def _provenance_to_tile_sources(
    subject_id: str,
    provenance_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    import_url_base = f"/quick-hc/{subject_id}/import"
    rest_collect_url = _DISPATCH_REST_COLLECT_URLS.get(subject_id)
    # The server-side _handle_system_upload reads request.files[handler.form_field].
    # Ship the matching field name to the JS so it submits under the name the
    # handler will look up. Without this, subjects with an upload handler
    # (security_assessment, license_summary) silently fail with "No file
    # selected." once their canonical artifact exists and the provenance
    # path replaces the nodata builder. The nodata builders declare their
    # own (correct) field name; this branch is the one that had been
    # hardcoded to the AI-subject default.
    from cvhealthcheck.web.routes.upload_dispatch import get_handler
    handler = get_handler(subject_id)
    import_field = handler.form_field if handler is not None else "file"
    result = []
    for item in provenance_items:
        src_id = _PROVENANCE_TYPE_TO_SOURCE_ID.get(item.get("source_type", ""))
        if src_id is None:
            continue
        status = _PROVENANCE_STATUS_TO_TILE_STATUS.get(item.get("status", ""), "ni")
        is_html = src_id == HTML_IMPORT_SOURCE_ID
        is_csv = src_id == CSV_IMPORT_SOURCE_ID
        is_rest = src_id == REST_REPORTS_PLUS_SOURCE_ID
        if is_html or is_csv:
            accept = ".html,.htm" if is_html else ".csv"
            actions: list[dict[str, str]] = [
                _upload_action(import_url=import_url_base, import_field=import_field, accept=accept)
            ]
        elif is_rest and rest_collect_url:
            # REST collection is auth-gated against the active customer's
            # CommCell; requiresSession lets the frontend open the connect
            # modal in-place instead of being bounced to the /login page.
            actions = [{
                "kind": "collect",
                "label": "Collect",
                "collectUrl": rest_collect_url,
                "requiresSession": True,
            }]
        else:
            actions = []
        result.append(_source_item(
            src_id,
            item.get("label", SOURCE_LABELS.get(src_id, src_id)),
            item.get("description", ""),
            status=status,
            actions=actions,
        ))
    return result


def _build_generic_sources(
    subject_id: str,
    tile_sources: list[dict[str, Any]],
    artifact_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    # Subjects whose REST collection is hardcoded in Python services
    # (not described in subject_section_sources rows) defer source
    # status decisions to a dedicated provenance builder. Two such
    # subjects today: security_assessment, license_summary.
    builder = get_provenance_builder(subject_id)
    if builder is not None:
        return _provenance_to_tile_sources(subject_id, builder(artifact_payload))

    # Unified upload route — every subject (system or AI) POSTs here.
    import_url_base = f"/quick-hc/{subject_id}/import"
    result = []
    for src in tile_sources:
        src_id = src["id"]
        extractable = src.get("extractable", True)
        is_html = src_id == HTML_IMPORT_SOURCE_ID
        is_csv = src_id == CSV_IMPORT_SOURCE_ID
        is_rest = src_id == REST_REPORTS_PLUS_SOURCE_ID
        is_command_center = src_id == REST_COMMAND_CENTER_API_SOURCE_ID
        is_json = src_id == JSON_IMPORT_SOURCE_ID
        collect_url = src.get("collect_url")
        is_import = is_html or is_csv
        if is_import and extractable:
            accept = ".html,.htm" if is_html else ".csv"
            actions = [
                _upload_action(import_url=import_url_base, import_field="file", accept=accept)
            ]
            status = "a"
        elif (is_rest or is_command_center or is_json) and collect_url:
            # REST / Command Center API collect from the lab; JSON (internal/test
            # subjects) collects from a shipped fixture via the collect-fixture
            # route. Both live-REST paths are auth-gated (customer-bound CommCell
            # session); requiresSession lets the frontend open the connect modal
            # in-place for that case. JSON fixture collection needs no session and
            # submits straight through.
            actions = [{
                "kind": "collect",
                "label": "Collect",
                "collectUrl": collect_url,
                "requiresSession": is_rest or is_command_center,
            }]
            status = "a"
        else:
            actions = []
            status = "ni"
        result.append(_source_item(
            src_id,
            src.get("label", src_id),
            src.get("description", ""),
            status=status,
            actions=actions,
        ))
    return result


def _version_info(
    db: sqlite3.Connection | None, customer_id: str | None, subject_id: str
) -> dict[str, Any]:
    """ADR 0004: the family, available versions, and active version for the
    source-tile version dropdown. Without a db handle (list_tiles path) the
    subject is its own only version."""
    family = subject_family(subject_id)
    if db is None:
        return {"family": family, "versions": [subject_id], "active": subject_id}
    versions = list_family_versions(db, family) or [subject_id]
    return {
        "family": family,
        "versions": versions,
        "active": resolve_active_version(db, customer_id, subject_id),
    }


def _last_collected(artifact: CanonicalArtifact | None) -> str | None:
    """ISO timestamp the artifact was collected (REST) or imported (file)."""
    if artifact is None:
        return None
    ts = artifact.source.collected_at or artifact.source.imported_at
    return ts.isoformat() if ts else None


def _build_generic_subject(tile: dict[str, Any], artifact: CanonicalArtifact | None) -> dict:
    subject_id = tile["id"]
    description = tile.get("description") or tile.get("subtitle") or ""
    artifact_payload = artifact.model_dump(mode="json") if artifact is not None else None
    sources = _build_generic_sources(subject_id, tile.get("sources", []), artifact_payload=artifact_payload)
    created_by = tile.get("created_by", "ai")
    status = tile.get("status", "active")
    if artifact is None:
        return {
            "id": subject_id,
            "name": tile["title"],
            "description": description,
            "state": "nodata",
            "included": True,
            "subtitle": "Not collected",
            "fullUrl": None,
            "activeSource": None,
            "sources": sources,
            "sections": [],
            "created_by": created_by,
            "status": status,
        }
    view = _canonical_view.artifact_to_view(artifact)
    view["name"] = tile["title"]
    view["description"] = description
    view["sources"] = sources
    view["created_by"] = created_by
    view["status"] = status
    return view


# ── LEGACY DATA LOADERS ──
# These are fallbacks used only when no canonical artifact exists in ArtifactStore.

def _load_legacy_commcell() -> dict | None:
    """Return the REAL GET CommServ response (the ``raw`` block) for the
    environment subject — nested shape: ``commcell.{commCellId,commCellName,csGUID}``,
    ``csTimeZone.{TimeZoneID,TimeZoneName}``, ``csVersionInfo``, ``currentSPVersion``,
    ``installedSPVersion``, ``hostName``, ``osType``, ``releaseId``, ``timeZone``.

    Previously returned the lossy flat ``identity`` block, which dropped
    commCellId / commCellName / csTimeZone / SP versions and carried the dirty
    ``timeZone`` ("0:0:<IANA>") composite. The card + header now read the real
    response directly. Falls back to ``identity`` / a normalized view only when no
    ``raw`` is present (older captures). environment-ONLY loader (legacy_loaders)."""
    try:
        payload = read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))
        if not isinstance(payload, dict):
            return None
        raw = payload.get("raw")
        if isinstance(raw, dict) and raw:
            return raw
        identity = payload.get("identity")
        if isinstance(identity, dict) and identity:
            return identity
        return normalize_commserv(payload).to_dict()
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading commcell data")
        return None


def _load_legacy_security_assessment() -> dict | None:
    try:
        return security_assessment_quick_hc()
    except Exception:
        logger.exception("Error loading security assessment")
        return None


def _load_legacy_license_summary() -> dict | None:
    try:
        return LicenseSummaryService().get_current()
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading license summary")
        return None


def _load_legacy_client_growth() -> dict | None:
    try:
        return get_client_growth_summary(live=False)
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading client growth")
        return None


def _load_legacy_capacity_license() -> dict | None:
    try:
        return get_capacity_license_usage(live=False)
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading capacity license")
        return None


def _load_legacy_backup_job_summary() -> dict | None:
    try:
        return load_backup_job_summary_artifact()
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading backup job summary")
        return None


def _legacy_loaders() -> dict[str, Any]:
    # Source-building fork: see docs/adr/0001-source-building-fork.md.
    # These loaders read legacy on-disk tile data for the six system
    # subjects whose view shapes (counters, findings_grid, workload,
    # chart_growth) the canonical schema cannot represent. The fork is
    # intentional and not technical debt.
    return {
        "environment": _load_legacy_commcell,
        "security_assessment": _load_legacy_security_assessment,
        "license_summary": _load_legacy_license_summary,
        "client_growth": _load_legacy_client_growth,
        "capacity_license": _load_legacy_capacity_license,
        "backup_job_summary": _load_legacy_backup_job_summary,
    }


# ── HEADER ──

def _build_commcell_header(cc: dict | None) -> dict:
    """Header summary (subtitle name/version). ``cc`` is now the REAL GET CommServ
    response (nested), so read commCellId/csGUID/TimeZoneName from their real
    locations rather than the old flat fields."""
    if not cc:
        return {"exists": False, "name": "", "version": "", "id": "", "timezone": ""}
    commcell = cc.get("commcell") if isinstance(cc.get("commcell"), dict) else {}
    cstz = cc.get("csTimeZone") if isinstance(cc.get("csTimeZone"), dict) else {}
    return {
        "exists": True,
        "name": cc.get("hostName") or "",
        "version": cc.get("csVersionInfo") or "",
        "id": commcell.get("csGUID") or cc.get("csGUID") or "",
        "timezone": cstz.get("TimeZoneName") or cc.get("timeZone") or "",
    }


def _legacy_builders() -> dict[str, Any]:
    # Source-building fork: see docs/adr/0001-source-building-fork.md.
    # These builders produce the six system subjects' custom view
    # shapes (counters, findings_grid, workload, chart_growth) that
    # the canonical schema cannot represent. They run when the
    # canonical store has no artifact for the subject. The fork is
    # intentional. Do not "clean it up" without reading the ADR.
    return {
        "environment": _build_environment_subject,
        "security_assessment": _build_security_assessment_subject,
        "license_summary": _build_license_summary_subject,
        "client_growth": _build_client_growth_subject,
        "capacity_license": _build_capacity_license_subject,
        "backup_job_summary": _build_backup_job_summary_subject,
    }


# ── SUBJECT BUILDERS ──

def _nodata_subject(subject_id: str, name: str, full_url: str | None = None) -> dict:
    return {
        "id": subject_id,
        "name": name,
        "description": resolve_tile_description(subject_id),
        "state": "nodata",
        "included": True,
        "subtitle": "Not collected",
        "fullUrl": full_url,
        "activeSource": None,
        "sources": [],
        "sections": [],
    }


def _source_item(
    source_id: str,
    name: str,
    desc: str,
    *,
    status: str = "n",
    meta: list[dict[str, str]] | None = None,
    actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": name,
        "desc": desc,
        "status": status,
        "meta": list(meta or []),
        "actions": list(actions or []),
    }


def _upload_action(
    *,
    import_url: str,
    import_field: str,
    accept: str = ".html,.htm,.csv,.json",
    label: str = "Import",
) -> dict[str, str]:
    return {
        "kind": "upload",
        "label": label,
        "importUrl": import_url,
        "importField": import_field,
        "accept": accept,
    }


def _build_tile_sources(
    tile_id: str,
    *,
    active_source_id: str,
    statuses: dict[str, str] | None = None,
    meta: dict[str, list[dict[str, str]]] | None = None,
    descriptions: dict[str, str] | None = None,
    actions: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    status_map = dict(statuses or {})
    meta_map = dict(meta or {})
    description_map = dict(descriptions or {})
    action_map = dict(actions or {})
    return [
        _source_item(
            src_id,
            SOURCE_LABELS.get(src_id, src_id),
            description_map.get(src_id, SOURCE_DESCRIPTIONS.get(src_id, "")),
            status=status_map.get(src_id, "ni"),
            meta=meta_map.get(src_id, []),
            actions=action_map.get(src_id, []),
        )
        for src_id in STANDARD_SOURCES
    ]


def _build_environment_subject(cc: dict | None, db: sqlite3.Connection | None = None) -> dict:
    full_url = _try_url("main.quick_hc_commcell")
    if not cc:
        subj = _nodata_subject("environment", "CommCell Details", full_url)
        subj["activeSource"] = REST_COMMAND_CENTER_API_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "environment",
            active_source_id=REST_COMMAND_CENTER_API_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "n",
                REST_REPORTS_PLUS_SOURCE_ID: "ni",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                REST_COMMAND_CENTER_API_SOURCE_ID: [
                    {"k": "Endpoint", "v": "GET /commandcenter/api/CommServ"},
                ],
            },
            descriptions={
                REST_COMMAND_CENTER_API_SOURCE_ID: "Live collection of CommCell identity details from Command Center.",
            },
        )
        return subj

    name = cc.get("hostName") or "CommCell"
    version = cc.get("csVersionInfo") or ""
    subtitle = f"{name} · {version}" if version else name

    return {
        "id": "environment",
        "name": "CommCell Details",
        "description": resolve_tile_description("environment"),
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": REST_COMMAND_CENTER_API_SOURCE_ID,
        "sources": _build_tile_sources(
            "environment",
            active_source_id=REST_COMMAND_CENTER_API_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "v",
                REST_REPORTS_PLUS_SOURCE_ID: "ni",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                # ADR 0004: CommCell server version is NOT shown on the data
                # source tile — it's a property of the deployment, not of this
                # collection. It stays in the environment subject's identity
                # card (built below), where it's the whole point.
                REST_COMMAND_CENTER_API_SOURCE_ID: [
                    {"k": "Endpoint", "v": "GET /commandcenter/api/CommServ"},
                    {"k": "Host", "v": name},
                ],
            },
            descriptions={
                REST_COMMAND_CENTER_API_SOURCE_ID: "Live collection of CommCell identity details from Command Center.",
            },
            # ADR 0007 ph2: surface a Collect button on environment's Command
            # Center source tile (the button lives on the SOURCE, not the card —
            # the live-served card section below is untouched). requiresSession
            # stays True: the collect is customer-bound-auth, same as Reports-Plus.
            actions={
                REST_COMMAND_CENTER_API_SOURCE_ID: [{
                    "kind": "collect",
                    "label": "Collect",
                    "collectUrl": "/quick-hc/environment/collect",
                    "requiresSession": True,
                }],
            },
        ),
        "sections": [_build_environment_identity_section(cc, name, version, db)],
    }


def _normalize_timezone(raw: Any) -> str | None:
    """Normalize a CommCell timezone to its IANA component for both display and
    evaluation. commserv.json carries a composite like ``"0:0:America/Danmarkshavn"``
    (``<offsetH>:<offsetM>:<IANA>``); reduce it to ``"America/Danmarkshavn"`` so
    BOTH the displayed CardItem value AND the value handed to the enum evaluator
    are the IANA name (the evaluator deliberately does not normalize). Values that
    don't match the composite shape (e.g. ``"UTC"``) pass through unchanged; an
    absent value → None (renders "—", reads as "not set")."""
    if raw is None:
        return None
    text = str(raw)
    if not text:
        return None
    m = re.match(r"^\d+:\d+:(.+)$", text)
    return m.group(1) if m else text


def _load_environment_card_block(db: sqlite3.Connection | None) -> dict[str, Any]:
    """Read environment's ``card`` config block from its catalog binding (DATA),
    not from a Python literal — the ``card`` object of ``extraction_instructions``
    on the ``subject_section_sources`` row for ``environment / environment.metadata``
    (migrations 0023 rules + 0024 view_mode). Carries ``evaluative.rules`` and the
    presentational ``view_mode`` hint. Returns ``{}`` when the binding is absent or
    no db is available (e.g. the no-db status API path) — the card then renders
    bare/tiles, which is safe; the main render path always has a db."""
    if db is None:
        return {}
    try:
        row = db.execute(
            "SELECT sss.extraction_instructions "
            "FROM subject_section_sources sss "
            "JOIN subject_sources src ON src.id = sss.source_id "
            "WHERE src.subject_id = 'environment' AND src.subject_version = 1 "
            "  AND sss.section_id = 'environment.metadata'",
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not row or not row["extraction_instructions"]:
        return {}
    try:
        instructions = json.loads(row["extraction_instructions"])
    except (json.JSONDecodeError, TypeError):
        return {}
    return instructions.get("card") or {}


def _load_environment_identity_rules(db: sqlite3.Connection | None) -> list[dict[str, Any]]:
    """The per-field rules from environment's catalog binding (``card.evaluative.rules``)."""
    return (_load_environment_card_block(db).get("evaluative") or {}).get("rules") or []


def _hex_commcell_id(commcell_id: Any) -> str | None:
    """Render commcell.commCellId (an integer, e.g. 2 or 13183) as lowercase hex
    with no '0x' prefix (2 → "2", 13183 → "337f"). The raw int is NOT shown — it
    stays in commserv.json. None / non-numeric → None (renders "—")."""
    if commcell_id is None:
        return None
    try:
        return format(int(commcell_id), "x")
    except (TypeError, ValueError):
        return None


def _build_environment_identity_section(
    cc: dict, name: str, version: str, db: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Build the CommCell-identity card for the bespoke environment subject.

    The identity card is built through the SAME shared path the generic cards use
    — ``build_card_section`` (the single ``engine.evaluate`` locus) +
    ``_card_section_view`` (the shared per-field card view) — and its per-field
    rules are DATA from the catalog binding (migration 0023), not a literal.

    The card VALUES are read DIRECTLY from the real GET /commandcenter/api/CommServ
    response (``cc`` is now the raw nested block: ``commcell.{commCellId,commCellName,
    csGUID}``, ``csTimeZone.TimeZoneName``, ``csVersionInfo``, SP versions, …). No
    synthesis: CommCell ID is the numeric commCellId rendered as hex; CommCell GUID
    and Timezone are read directly (csTimeZone.TimeZoneName — no "0:0:" composite).
    Fields the API doesn't return (e.g. releaseName) get no row. Rows for releaseId
    / TimeZoneID / top-level timeZone are intentionally omitted (they stay in
    commserv.json; there is no card-metadata slot).

    Field keys ``name`` / ``version`` / ``timezone`` are preserved so the 49053a9
    rule binding still attaches (Version presence, Timezone enum, Name format); the
    new fields carry no rule and render bare."""
    # One read of the catalog binding's card block — carries both the per-field
    # rules and the view_mode presentational hint (DATA, migrations 0023 + 0024).
    card_block = _load_environment_card_block(db)
    commcell = cc.get("commcell") if isinstance(cc.get("commcell"), dict) else {}
    cstz = cc.get("csTimeZone") if isinstance(cc.get("csTimeZone"), dict) else {}
    # *_or_None so absent values render "—" AND a presence rule reads "not set".
    identity_row = {
        "name": commcell.get("commCellName") or None,            # format rule
        "id": _hex_commcell_id(commcell.get("commCellId")),      # numeric → hex
        "guid": commcell.get("csGUID") or None,                  # direct, no synth
        "version": cc.get("csVersionInfo") or None,              # presence rule
        "os_type": cc.get("osType") or None,
        "current_sp": cc.get("currentSPVersion"),
        "installed_sp": cc.get("installedSPVersion"),
        # csTimeZone.TimeZoneName is already clean; _normalize_timezone kept as a
        # harmless pass-through guard (no-op on clean values, strips a stray
        # "0:0:" if a deployment ever puts the composite here). enum rule target.
        "timezone": _normalize_timezone(cstz.get("TimeZoneName")),
        "hostname": cc.get("hostName") or None,
    }
    identity_spec = {
        "columns": 4,
        # Schema order (reordering is a later cosmetic pass). Release Name omitted
        # — releaseName is absent from the real response.
        "items": [
            {"label": "CommCell Name", "field": "name"},
            {"label": "CommCell ID", "field": "id"},
            {"label": "CommCell GUID", "field": "guid"},
            {"label": "Version", "field": "version"},
            {"label": "OS Type", "field": "os_type"},
            {"label": "Current SP Version", "field": "current_sp"},
            {"label": "Installed SP Version", "field": "installed_sp"},
            {"label": "Timezone", "field": "timezone"},
            {"label": "Hostname", "field": "hostname"},
        ],
        # Rules + view_mode come from the catalog binding (DATA), not literals.
        "evaluative": {"rules": (card_block.get("evaluative") or {}).get("rules") or []},
    }
    card_section = build_card_section(
        "environment.metadata", "Environment metadata", identity_spec, [identity_row]
    )
    # view_mode is presentational DATA on the section (migration 0024 sets "table"
    # for environment); the renderer reads it. Default "tiles" keeps other cards
    # unchanged.
    view_mode = card_block.get("view_mode") or "tiles"
    section = _canonical_view._card_section_view(
        card_section, "environment.metadata", view_mode=view_mode
    )
    # Preserve the original section sub-label (the view builder defaults meta="").
    section["meta"] = "CommCell profile"
    return section


def _build_security_assessment_subject(sa: dict | None) -> dict:
    try:
        artifact = _canonical_store().load_latest_artifact("security_assessment")
        view = _canonical_view.security_assessment_to_view(artifact)
        view["fullUrl"] = _try_url("main.quick_hc")
        return view
    except Exception:
        pass
    full_url = _try_url("main.quick_hc")
    if not sa or not sa.get("exists"):
        subj = _nodata_subject("security_assessment", "Security Assessment", full_url)
        subj["activeSource"] = REST_REPORTS_PLUS_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "security_assessment",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "n",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "a",
                HTML_IMPORT_SOURCE_ID: "a",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Report ID", "v": "336"}],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Security Assessment.",
                CSV_IMPORT_SOURCE_ID: "Import a Security Assessment CSV export into the canonical artifact.",
                HTML_IMPORT_SOURCE_ID: "Import a Security Assessment HTML export into the canonical artifact.",
            },
            actions={
                CSV_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_SA_IMPORT_URL,
                        import_field="assessment_file",
                    )
                ],
                HTML_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_SA_IMPORT_URL,
                        import_field="assessment_file",
                    )
                ],
            },
        )
        return subj

    summary = sa.get("summary") or {}
    counters = summary.get("counters") or {}
    highlights = summary.get("highlights") or []
    sections = summary.get("sections") or []
    source_type = sa.get("source_type") or ""
    generated_on = str(sa.get("generated_on") or "")
    source = sa.get("source") or {}
    report_id = str(source.get("report_id") or "").strip()
    report_name = str(source.get("report_name") or "").strip()

    critical = int(counters.get("Critical") or 0)
    warning = int(counters.get("Warning") or 0)
    info_count = int(counters.get("Info") or 0)
    good_count = int(counters.get("Good") or 0)
    total = int(counters.get("Total checks") or 0)

    state = "issues" if (critical > 0 or warning > 0) else "ok"
    parts = []
    if critical: parts.append(f"{critical} critical")
    if warning: parts.append(f"{warning} warning")
    if info_count: parts.append(f"{info_count} info")
    if good_count: parts.append(f"{good_count} good")
    subtitle = " · ".join(parts) if parts else f"{total} checks"

    # Map findings
    highlight_findings = [
        {
            "sev": "crit" if f.get("status") == "Critical" else "warn",
            "title": str(f.get("parameter") or ""),
            "rem": _finding_rem(f),
        }
        for f in highlights[:12]
    ]
    highlight_rows = [
        [
            str(f.get("section") or ""),
            str(f.get("parameter") or ""),
            str(f.get("status") or ""),
            _finding_rem(f),
        ]
        for f in highlights[:12]
    ]

    info_good_findings = [
        {
            "sev": "info" if f.get("status") == "Info" else "good",
            "title": str(f.get("parameter") or ""),
            "rem": str(f.get("remarks") or ""),
        }
        for sec in sections
        for f in sec.get("checks") or []
        if f.get("status") in ("Info", "Good")
    ][:20]

    summary_rows = [
        {"k": "TOTAL CHECKS", "v": str(total)},
        {"k": "CRITICAL", "v": str(critical), "cls": "err" if critical > 0 else ""},
        {"k": "WARNING", "v": str(warning), "cls": "warn" if warning > 0 else ""},
        {"k": "INFO", "v": str(info_count)},
        {"k": "GOOD", "v": str(good_count), "cls": "ok" if good_count > 0 else ""},
    ]
    if collected_at := str(sa.get("collected_at") or ""):
        summary_rows.append({"k": "COLLECTED", "v": collected_at[:19]})

    detail_sections = []
    for sec in sections:
        section_name = str(sec.get("name") or "")
        section_id = SECURITY_ASSESSMENT_DETAIL_SECTION_IDS_BY_NAME.get(section_name)
        if not section_id:
            continue
        checks = list(sec.get("checks") or [])
        section_findings = [
            {
                "sev": _security_finding_sev(f.get("status")),
                "title": str(f.get("parameter") or ""),
                "rem": _finding_rem(f),
            }
            for f in checks
        ]
        detail_sections.append(
            {
                "id": section_id,
                "title": section_name,
                "meta": f"{len(checks)} finding{'s' if len(checks) != 1 else ''}",
                "included": True,
                "type": "findings_list",
                "findings": section_findings,
                "rows": [
                    [
                        str(f.get("parameter") or ""),
                        str(f.get("status") or ""),
                        str(f.get("remarks") or ""),
                        str(f.get("action") or ""),
                    ]
                    for f in checks
                ],
                "columns": ["Parameter", "Status", "Remarks", "Action"],
            }
        )

    # Source metadata
    is_rest = source_type in ("rest", "reportsplus")
    active_src = REST_REPORTS_PLUS_SOURCE_ID
    if source_type == "csv":
        active_src = CSV_IMPORT_SOURCE_ID
    elif source_type == "html":
        active_src = HTML_IMPORT_SOURCE_ID

    return {
        "id": "security_assessment",
        "name": "Security Assessment",
        "description": resolve_tile_description("security_assessment"),
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": active_src,
        "sources": _build_tile_sources(
            "security_assessment",
            active_source_id=active_src,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "v" if is_rest else "a",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "v" if source_type == "csv" else "a",
                HTML_IMPORT_SOURCE_ID: "v" if source_type == "html" else "a",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [
                    {"k": "Report ID", "v": "336"},
                    *([{"k": "Last Collected", "v": collected_at[:19]}] if is_rest and collected_at else []),
                    {"k": "Findings", "v": str(total)},
                ],
                CSV_IMPORT_SOURCE_ID: (
                    [{"k": "Last Imported", "v": collected_at[:19]}]
                    if source_type == "csv" and collected_at
                    else []
                ),
                HTML_IMPORT_SOURCE_ID: (
                    [{"k": "Last Imported", "v": collected_at[:19]}]
                    if source_type == "html" and collected_at
                    else []
                ),
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Security Assessment.",
                CSV_IMPORT_SOURCE_ID: "Import a Security Assessment CSV export into the canonical artifact.",
                HTML_IMPORT_SOURCE_ID: "Import a Security Assessment HTML export into the canonical artifact.",
            },
            actions={
                CSV_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_SA_IMPORT_URL,
                        import_field="assessment_file",
                    )
                ],
                HTML_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_SA_IMPORT_URL,
                        import_field="assessment_file",
                    )
                ],
            },
        ),
        "sections": [
            {
                "id": SECURITY_ASSESSMENT_METADATA_SECTION_ID,
                "title": "Source metadata",
                "meta": (report_name or "Security Assessment"),
                "included": True,
                "type": "meta",
                "rows": [
                    {"k": "SOURCE", "v": str(source_type or "unknown").upper()},
                    *([{"k": "IMPORTED", "v": collected_at[:19]}] if collected_at else []),
                    *([{"k": "GENERATED", "v": generated_on}] if generated_on else []),
                    *([{"k": "REPORT", "v": f"{report_name} ({report_id})"}] if report_name and report_id else []),
                    *([{"k": "REPORT", "v": report_name}] if report_name and not report_id else []),
                ],
            },
            {
                "id": "security_assessment.summary",
                "title": "Summary counters",
                "meta": f"{total} checks",
                "included": True,
                "type": "counters",
                "counters": {
                    "Critical": critical,
                    "Warning": warning,
                    "Info": info_count,
                    "Good": good_count,
                },
                "rows": summary_rows,
            },
            {
                "id": "security_assessment.highlights",
                "title": "Critical / Warning highlights",
                "meta": f"{len(highlight_findings)} finding{'s' if len(highlight_findings) != 1 else ''}",
                "included": True,
                "type": "findings_grid",
                "findings": highlight_findings,
                "columns": ["Section", "Parameter", "Status", "Remarks"],
                "rows": highlight_rows,
            },
            *detail_sections,
        ],
    }


def _build_license_summary_subject(ls: dict | None) -> dict:
    try:
        artifact = _canonical_store().load_latest_artifact("license_summary")
        view = _canonical_view.license_summary_to_view(artifact)
        view["fullUrl"] = _try_url("main.quick_hc")
        return view
    except Exception:
        pass
    full_url = _try_url("main.quick_hc")
    if not ls:
        subj = _nodata_subject("license_summary", "License Summary", full_url)
        subj["activeSource"] = REST_REPORTS_PLUS_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "license_summary",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "n",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "a",
                HTML_IMPORT_SOURCE_ID: "a",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Report ID", "v": "206"}],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for License Summary.",
                CSV_IMPORT_SOURCE_ID: "Import a License Summary CSV export into the canonical artifact.",
                HTML_IMPORT_SOURCE_ID: "Import a License Summary HTML export into the canonical artifact.",
            },
            actions={
                CSV_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_LS_IMPORT_URL,
                        import_field="license_summary_file",
                    )
                ],
                HTML_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_LS_IMPORT_URL,
                        import_field="license_summary_file",
                    )
                ],
            },
        )
        return subj

    source_type = str(ls.get("source_type") or "")
    imported_at = str(ls.get("imported_at") or "")
    generated_on = str(ls.get("generated_on") or "")
    license_expiry = str(ls.get("license_expiry") or "")

    workload_sections = list(ls.get("workload_summary_sections") or [])
    other_licenses = list(ls.get("other_licenses") or [])
    agent_feature_licenses = list(ls.get("agent_feature_licenses") or [])

    wl_count = len(workload_sections)
    other_count = len(other_licenses)
    agent_count = len(agent_feature_licenses)

    subtitle_parts = []
    if wl_count: subtitle_parts.append(f"{wl_count} workload section{'s' if wl_count != 1 else ''}")
    if other_count: subtitle_parts.append(f"{other_count} other licenses")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    is_rest = source_type in ("rest", "reportsplus")
    active_src = REST_REPORTS_PLUS_SOURCE_ID
    if source_type == "csv":
        active_src = CSV_IMPORT_SOURCE_ID
    elif source_type == "html":
        active_src = HTML_IMPORT_SOURCE_ID
    elif source_type == "json":
        active_src = JSON_IMPORT_SOURCE_ID

    # Metadata rows
    meta_rows = [
        {"k": "SOURCE", "v": source_type.upper() if source_type else "Unknown"},
    ]
    if imported_at:
        meta_rows.append({"k": "IMPORTED", "v": imported_at[:19]})
    if generated_on:
        meta_rows.append({"k": "GENERATED ON", "v": generated_on})
    if license_expiry:
        meta_rows.append({"k": "LICENSE EXPIRY", "v": license_expiry, "cls": _expiry_class(license_expiry)})

    # Workload data
    workload_data = []
    for section in workload_sections:
        rows = list(section.get("rows") or [])
        workload_data.append({
            "name": str(section.get("section_name") or ""),
            "rows": [
                {
                    "license": str(row.get("license") or ""),
                    "ent": str(row.get("entitlement_value") or ""),
                    "used": str(row.get("used") or ""),
                    "pct": _safe_int_percent(row.get("usage_percent")),
                }
                for row in rows
            ],
        })

    # Other licenses table
    other_table_rows = [
        [
            str(r.get("license") or ""),
            str(r.get("available_total") if r.get("available_total") is not None else r.get("raw_available_total") or ""),
            str(r.get("used") if r.get("used") is not None else r.get("raw_used") or ""),
        ]
        for r in other_licenses[:30]
    ]

    # Agent/feature licenses table
    agent_table_rows = [
        [
            str(r.get("license") or ""),
            str(r.get("client") or ""),
            str(r.get("agent") or ""),
            " / ".join(str(v) for v in [r.get("permanent_used"), r.get("term_used")] if v is not None and v != ""),
        ]
        for r in agent_feature_licenses[:30]
    ]

    return {
        "id": "license_summary",
        "name": "License Summary",
        "description": resolve_tile_description("license_summary"),
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": active_src,
        "sources": _build_tile_sources(
            "license_summary",
            active_source_id=active_src,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "v" if is_rest else "a",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "v" if source_type == "csv" else "a",
                HTML_IMPORT_SOURCE_ID: "v" if source_type == "html" else "a",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Report ID", "v": "206"}],
                **(
                    {REST_REPORTS_PLUS_SOURCE_ID: [
                        {"k": "Report ID", "v": "206"},
                        {"k": "Last Collected", "v": imported_at[:19] if imported_at else (generated_on or "Unknown")},
                    ]}
                    if is_rest else {}
                ),
                CSV_IMPORT_SOURCE_ID: (
                    [{"k": "Last Imported", "v": imported_at[:19]}]
                    if source_type == "csv" and imported_at
                    else []
                ),
                HTML_IMPORT_SOURCE_ID: (
                    [{"k": "Last Imported", "v": imported_at[:19]}]
                    if source_type == "html" and imported_at
                    else []
                ),
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for License Summary.",
                CSV_IMPORT_SOURCE_ID: "Import a License Summary CSV export into the canonical artifact.",
                HTML_IMPORT_SOURCE_ID: "Import a License Summary HTML export into the canonical artifact.",
            },
            actions={
                CSV_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_LS_IMPORT_URL,
                        import_field="license_summary_file",
                    )
                ],
                HTML_IMPORT_SOURCE_ID: [
                    _upload_action(
                        import_url=_LS_IMPORT_URL,
                        import_field="license_summary_file",
                    )
                ],
            },
        ),
        "sections": [
            {
                "id": "license_summary.metadata",
                "title": "Summary metadata",
                "meta": "Source and dates",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "license_summary.workload_sections",
                "title": "Workload Summary Sections",
                "meta": f"{wl_count} section{'s' if wl_count != 1 else ''}",
                "included": True,
                "type": "workload",
                "workload": workload_data,
            },
            {
                "id": "license_summary.other_licenses",
                "title": "Other Licenses table",
                "meta": f"{other_count} row{'s' if other_count != 1 else ''}",
                "included": True,
                "type": "table",
                "columns": ["License", "Available", "Used"],
                "rows": other_table_rows,
            },
            {
                "id": "license_summary.agent_feature_licenses",
                "title": "Agent / Feature Licenses table",
                "meta": f"{agent_count} row{'s' if agent_count != 1 else ''}",
                "included": True,
                "type": "table",
                "columns": ["License", "Client", "Agent", "Perm / Term Used"],
                "rows": agent_table_rows,
            },
        ],
    }


def _safe_int_percent(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _build_client_growth_subject(cg: dict | None) -> dict:
    full_url = None
    if not cg:
        subj = _nodata_subject("client_growth", "Client Growth", full_url)
        subj["activeSource"] = REST_REPORTS_PLUS_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "client_growth",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "n",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Report ID", "v": "318"}]},
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Client Growth metrics.",
            },
        )
        return subj

    records = list(cg.get("records") or [])
    history_range = cg.get("history_range") or {}
    latest = records[-1] if records else {}
    total_clients = int(latest.get("total_clients") or 0)
    added = int(latest.get("added") or 0)
    latest_month = latest.get("month") or ""

    # YoY calculation
    yoy_pct = None
    if len(records) >= 13:
        prev_year = records[-13]
        prev_total = int(prev_year.get("total_clients") or 0)
        if prev_total > 0:
            pct = round((total_clients - prev_total) / prev_total * 100)
            yoy_pct = f"{'+' if pct >= 0 else ''}{pct}%"

    subtitle_parts = []
    if total_clients: subtitle_parts.append(f"{total_clients} clients")
    if yoy_pct: subtitle_parts.append(f"{yoy_pct} YoY")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    # Chart data (last 12 months)
    recent = records[-12:]
    chart = {
        "months": [_short_month(r.get("month") or "") for r in recent],
        "totals": [int(r.get("total_clients") or 0) for r in recent],
        "added": [int(r.get("added") or 0) for r in recent],
        "latest_total": total_clients,
        "yoy_pct": yoy_pct,
    }

    # Summary meta rows
    period_start = records[0].get("month") if records else ""
    meta_rows = [
        {"k": "LATEST TOTAL", "v": f"{total_clients} clients"},
        {"k": "LATEST MONTH", "v": latest_month},
        {"k": "ADDED (LATEST)", "v": f"+{added}"},
        {"k": "RECORDS", "v": str(len(records))},
    ]
    if yoy_pct:
        meta_rows.append({"k": "YoY GROWTH", "v": yoy_pct, "cls": "ok" if not yoy_pct.startswith("-") else "warn"})

    # Monthly table
    monthly_rows = [
        [
            str(r.get("month") or ""),
            str(r.get("total_clients") or ""),
            f"+{r.get('added') or 0}",
            f"-{r.get('removed') or 0}",
        ]
        for r in reversed(records[-24:])
    ]

    return {
        "id": "client_growth",
        "name": "Client Growth",
        "description": resolve_tile_description("client_growth"),
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": REST_REPORTS_PLUS_SOURCE_ID,
        "sources": _build_tile_sources(
            "client_growth",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "v",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [
                    {"k": "Report ID", "v": "318"},
                    {"k": "Records", "v": str(len(records))},
                    {"k": "Latest Month", "v": latest_month or "Unknown"},
                ],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Client Growth metrics.",
            },
        ),
        "sections": [
            {
                "id": "client_growth.summary",
                "title": "Summary metrics",
                "meta": f"{total_clients} total clients" if total_clients else "Overview",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "client_growth.chart",
                "title": "Client Growth chart",
                "meta": "12-month trend",
                "included": True,
                "type": "chart_growth",
                "chart": chart,
            },
            {
                "id": "client_growth.monthly_table",
                "title": "Monthly summary table",
                "meta": f"{len(records)} rows",
                "included": True,
                "type": "table",
                "columns": ["Month", "Total Clients", "Added", "Removed"],
                "rows": monthly_rows,
            },
        ],
    }


def _build_capacity_license_subject(cl: dict | None) -> dict:
    full_url = None
    if not cl:
        subj = _nodata_subject("capacity_license", "Capacity Licenses", full_url)
        subj["activeSource"] = REST_REPORTS_PLUS_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "capacity_license",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "n",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Report ID", "v": "318"}]},
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Capacity License metrics.",
            },
        )
        return subj

    records = list(cl.get("records") or [])
    history_range = cl.get("history_range") or {}
    latest_month = history_range.get("end") or ""

    # Aggregate by month
    monthly: dict[str, dict[str, float]] = {}
    for r in records:
        m = str(r.get("month") or "")
        if not m:
            continue
        monthly.setdefault(m, {"used": 0.0, "purchased": 0.0})
        # treat negative sentinel values (-1) as 0
        monthly[m]["used"] += max(float(r.get("used_capacity") or 0), 0.0)
        monthly[m]["purchased"] += max(float(r.get("purchased_capacity") or 0), 0.0)

    sorted_months = sorted(monthly.keys())
    recent_months = sorted_months[-12:]

    # Latest period stats
    latest_used = monthly[latest_month]["used"] if latest_month in monthly else 0.0
    latest_purchased = monthly[latest_month]["purchased"] if latest_month in monthly else 0.0
    utilisation_pct = round(latest_used / latest_purchased * 100, 1) if latest_purchased > 0 else 0.0

    # Peak purchased (for chart scale)
    peak_purchased = max((monthly[m]["purchased"] for m in recent_months), default=1.0)

    subtitle_parts = []
    if latest_used: subtitle_parts.append(f"{latest_used:.1f} TB used")
    if utilisation_pct: subtitle_parts.append(f"{utilisation_pct:.0f}%")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    chart = {
        "months": [_short_month(m) for m in recent_months],
        "used": [round(monthly[m]["used"], 2) for m in recent_months],
        "purchased": round(peak_purchased, 2),
        "utilisation_pct": utilisation_pct,
    }

    meta_rows = [
        {"k": "USED CAPACITY", "v": f"{latest_used:.1f} TB"},
        {"k": "PURCHASED", "v": f"{latest_purchased:.1f} TB"},
        {"k": "UTILISATION", "v": f"{utilisation_pct:.0f}%"},
        {"k": "PERIOD", "v": latest_month},
    ]

    # Capacity entity table
    latest_records = [r for r in records if str(r.get("month") or "") == latest_month]
    entity_rows = [
        [
            str(r.get("entity_name") or ""),
            f"{float(r.get('used_capacity') or 0):.2f} TB",
            f"{float(r.get('purchased_capacity') or 0):.2f} TB",
            f"{round(float(r.get('used_capacity') or 0) / float(r.get('purchased_capacity') or 1) * 100):.0f}%",
        ]
        for r in latest_records[:30]
    ]

    return {
        "id": "capacity_license",
        "name": "Capacity Licenses",
        "description": resolve_tile_description("capacity_license"),
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": REST_REPORTS_PLUS_SOURCE_ID,
        "sources": _build_tile_sources(
            "capacity_license",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "v",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [
                    {"k": "Report ID", "v": "318"},
                    {"k": "Period", "v": latest_month or "Unknown"},
                ],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Capacity License metrics.",
            },
        ),
        "sections": [
            {
                "id": "capacity_license.summary",
                "title": "Summary",
                "meta": latest_month or "Latest period",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "capacity_license.table",
                "title": "Usage/details table",
                "meta": f"{len(latest_records)} entities",
                "included": True,
                "type": "table",
                "columns": ["Entity", "Used", "Purchased", "Utilisation"],
                "rows": entity_rows,
            },
        ],
    }


def _build_backup_job_summary_subject(bjs: dict | None) -> dict:
    full_url = _try_url("main.quick_hc_backup_job_summary")
    if not bjs:
        subj = _nodata_subject("backup_job_summary", "Backup Job Summary", full_url)
        subj["activeSource"] = REST_REPORTS_PLUS_SOURCE_ID
        subj["sources"] = _build_tile_sources(
            "backup_job_summary",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "n",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [{"k": "Dataset", "v": "2638c3d3-adc7-4b61-bb24-2ba509229bf5"}],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Backup Job Summary.",
            },
        )
        return subj

    total_jobs = int(bjs.get("total_jobs") or 0)
    failed_jobs = int(bjs.get("failed_jobs") or 0)
    completed_jobs = int(bjs.get("completed_jobs") or 0)
    running_jobs = int(bjs.get("running_jobs") or 0)
    recent_failures = list(bjs.get("recent_failures") or [])
    recent_jobs = list(bjs.get("recent_jobs") or [])
    status_breakdown = dict(bjs.get("status_breakdown") or {})

    state = "issues" if failed_jobs > 0 else "ok"
    subtitle_parts = [f"{total_jobs} jobs"]
    if failed_jobs: subtitle_parts.append(f"{failed_jobs} failed")
    subtitle = " · ".join(subtitle_parts)

    # Summary meta
    meta_rows = [
        {"k": "TOTAL JOBS", "v": str(total_jobs)},
        {"k": "COMPLETED", "v": str(completed_jobs)},
        {"k": "FAILED", "v": str(failed_jobs), "cls": "err" if failed_jobs > 0 else ""},
        {"k": "RUNNING", "v": str(running_jobs)},
    ]

    # Status breakdown as counters
    status_meta = [
        {"k": str(k), "v": str(v)}
        for k, v in sorted(status_breakdown.items(), key=lambda x: -x[1])
    ]

    # Recent failures as findings list
    failure_findings = [
        {
            "sev": "crit",
            "title": str(f.get("client") or f.get("job_id") or "Unknown Job"),
            "rem": str(f.get("failure_reason") or f.get("status") or ""),
        }
        for f in recent_failures[:10]
    ]

    # Recent jobs table
    job_rows = [
        [
            str(j.get("job_id") or ""),
            str(j.get("client") or ""),
            str(j.get("status") or ""),
            str(j.get("start_time") or ""),
            str(j.get("size") or ""),
        ]
        for j in recent_jobs[:15]
    ]

    return {
        "id": "backup_job_summary",
        "name": "Backup Job Summary",
        "description": resolve_tile_description("backup_job_summary"),
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": REST_REPORTS_PLUS_SOURCE_ID,
        "sources": _build_tile_sources(
            "backup_job_summary",
            active_source_id=REST_REPORTS_PLUS_SOURCE_ID,
            statuses={
                REST_COMMAND_CENTER_API_SOURCE_ID: "ni",
                REST_REPORTS_PLUS_SOURCE_ID: "v",
                JSON_IMPORT_SOURCE_ID: "ni",
                CSV_IMPORT_SOURCE_ID: "ni",
                HTML_IMPORT_SOURCE_ID: "ni",
            },
            meta={
                REST_REPORTS_PLUS_SOURCE_ID: [
                    {"k": "Dataset", "v": str(bjs.get("source_dataset_guid") or "2638c3d3-adc7-4b61-bb24-2ba509229bf5")},
                    {"k": "Last Generated", "v": str(bjs.get("generated_at") or "Unknown")},
                    {"k": "Total Jobs", "v": str(total_jobs)},
                ],
            },
            descriptions={
                REST_REPORTS_PLUS_SOURCE_ID: "Live Reports Plus collection path for Backup Job Summary.",
            },
        ),
        "sections": [
            {
                "id": "backup_job_summary.summary",
                "title": "Summary",
                "meta": f"{total_jobs} jobs",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "backup_job_summary.status_breakdown",
                "title": "Status breakdown",
                "meta": f"{len(status_breakdown)} statuses",
                "included": True,
                "type": "meta",
                "rows": status_meta,
            },
            {
                "id": "backup_job_summary.recent_failures",
                "title": "Recent failures",
                "meta": f"{len(recent_failures)} failures",
                "included": True,
                "type": "findings_list",
                "findings": failure_findings,
            },
            {
                "id": "backup_job_summary.recent_jobs",
                "title": "Recent jobs",
                "meta": f"{len(recent_jobs)} jobs",
                "included": True,
                "type": "table",
                "columns": ["Job ID", "Client", "Status", "Start Time", "Size"],
                "rows": job_rows,
            },
        ],
    }


# ── UTILITIES ──

def _try_url(endpoint: str) -> str | None:
    try:
        from flask import url_for
        return url_for(endpoint)
    except Exception:
        return None


def _short_month(month_str: str) -> str:
    """Convert '2026-04' to 'Apr'."""
    if not month_str or len(month_str) < 7:
        return month_str
    mm = month_str[5:7]
    return _MONTH_ABBR.get(mm, mm)


def _expiry_class(date_str: str) -> str:
    """Return CSS class for license expiry date: 'warn' if <90 days, 'err' if past."""
    try:
        expiry = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        delta = (expiry - date.today()).days
        if delta < 0:
            return "err"
        if delta < 90:
            return "warn"
    except Exception:
        pass
    return ""


def _finding_rem(f: dict) -> str:
    section = str(f.get("section") or "")
    remarks = str(f.get("remarks") or "")
    if section and remarks:
        return f"{section} · {remarks}"
    return remarks or section


def _security_finding_sev(status: object) -> str:
    value = str(status or "")
    if value == "Critical":
        return "crit"
    if value == "Warning":
        return "warn"
    if value == "Info":
        return "info"
    return "good"
