from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, ChartType, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    CardItem,
    CardSection,
    ChartSection,
    FindingsSection,
    MetricItem,
    MetricSection,
    TableColumn,
    TableSection,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.subjects import (
    list_family_versions,
    resolve_active_version,
    subject_family,
)


def _canonical_store() -> ArtifactStore:
    """Construct an ArtifactStore for the active project on demand.

    Replaces the module-level singleton from before ADR 0002 phase 2.
    Each call resolves the current request's active project (falling back
    to the Default project outside a request context).
    """
    from cvhealthcheck.web.active_project import make_active_project_store
    return make_active_project_store()
from cvhealthcheck.quickhc import canonical_view as _canonical_view
from cvhealthcheck.quickhc.description_service import resolve_tile_description
from cvhealthcheck.quickhc.registry import (
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
    JSON_IMPORT_SOURCE_ID,
    REPORTSPLUS_DATASET_SOURCE_ID,
    REST_COMMAND_CENTER_API_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    SOURCE_DESCRIPTIONS,
    SOURCE_ENDPOINTS,
    SOURCE_LABELS,
    get_tiles,
    list_tiles,
)
from cvhealthcheck.quickhc.source_provenance_dispatch import get_provenance_builder

logger = logging.getLogger(__name__)

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

    # Commcell header comes from the SCOPED environment artifact (Fix 2 (b)) —
    # the same store the environment tile renders. Honest-empty when the
    # active project hasn't collected environment yet. (Previously read the
    # global commserv.json via the legacy loader: cross-customer.)
    commcell_info = _build_commcell_header(
        _load_from_canonical_store("environment")
    )

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

        # The scoped canonical store is the ONLY data source for a subject's
        # workspace view. The former fallthrough to the six legacy loaders read
        # GLOBAL unscoped files (commserv.json, LS/SA catalog artifacts, metrics
        # JSONs, backup_job_summary_latest.json), so any project with an empty
        # store rendered another customer's last collection — the Fix-2
        # isolation leak (2026-06-12 audit). An empty store now renders the
        # subject's honest not-collected state. This retires the ADR-0001
        # source-building fork's read path for workspace tiles.
        artifact = _load_from_canonical_store(subject_id)
        built = _build_generic_subject(tile, artifact)

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
    staging = _build_staging_shells(db)

    return {
        "commcell": commcell_info,
        "cats": cats,
        "staging": staging,
    }


# ── Staging zone: pending subject_proposal shells (ADR 0009 Phase 1) ──────────
#
# A pending proposal is rendered as an EMPTY structural shell: section titles +
# types, table header rows, metric labels with placeholder values, etc. — no
# collected data. The shell is built SERVER-SIDE here (the JS stays a pure
# renderer): synthesize an empty-bodied CanonicalArtifact from the proposal and
# run it through artifact_to_view, reusing its canonical→view-token mapping so
# section types resolve exactly as a collected subject's would.

_PROPOSAL_SOURCE_TYPE: dict[str, SourceType] = {
    "rest_command_center_api": SourceType.rest_commserve,
    "rest":  SourceType.rest,
    "json":  SourceType.json_import,
    "html":  SourceType.html_import,
    "csv":   SourceType.csv_import,
}


def _build_staging_shells(db: sqlite3.Connection | None) -> list[dict[str, Any]]:
    """Pending subject proposals as empty-bodied shell views for the Staging zone.

    Filtered to artifact_type=='subject_proposal' AND status=='pending', so
    orphaned approved proposals and all artifact_type=='artifact' rows are
    excluded by construction. No db → no staging (the list_tiles path)."""
    if db is None:
        return []
    from cvhealthcheck.db.staging import list_staged_artifacts

    shells: list[dict[str, Any]] = []
    for row in list_staged_artifacts(db, status="pending"):
        if row.get("artifact_type") != "subject_proposal":
            continue
        try:
            proposal = json.loads(row["artifact_json"])
        except (TypeError, KeyError, json.JSONDecodeError):
            continue
        shell = build_proposal_shell(proposal, stage_id=row["stage_id"])
        if shell is not None:
            shells.append(shell)
    return shells


def build_proposal_shell(
    proposal: dict[str, Any], *, stage_id: str
) -> dict[str, Any] | None:
    """Turn a subject proposal's artifact_json into an empty-bodied subject view.

    Reuses artifact_to_view's canonical→view-token mapping by synthesizing a
    CanonicalArtifact with structurally-correct but data-empty sections."""
    subject_id = proposal.get("subject_id")
    if not subject_id:
        return None
    title = proposal.get("title") or subject_id
    extraction = proposal.get("extraction_instructions") or {}
    sections = []
    for sdef in proposal.get("sections") or []:
        sec = _shell_section(sdef, extraction)
        if sec is not None:
            sections.append(sec)

    artifact = CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=datetime.now(timezone.utc),
        source=ArtifactSource(type=_proposal_source_type(extraction)),
        subject=ArtifactSubject(id=subject_id, title=title),
        summary=ArtifactSummary(status=ArtifactStatus.unknown),
        sections=sections,
    )
    view = _canonical_view.artifact_to_view(artifact)
    # Staging-zone markers (consumed by the JS renderStagingZone()).
    view["description"] = proposal.get("description") or ""
    view["subtitle"] = "Pending proposal — not yet collected"
    view["status"] = "pending"
    view["is_proposal"] = True
    view["stage_id"] = stage_id
    view["created_by"] = "ai"
    return view


def _proposal_source_type(extraction: dict[str, Any]) -> SourceType:
    for key in ("rest_command_center_api", "rest", "json", "html", "csv"):
        if key in extraction:
            return _PROPOSAL_SOURCE_TYPE[key]
    return SourceType.rest


def _shell_section(sdef: dict[str, Any], extraction: dict[str, Any]):
    """One empty-bodied canonical Section from a proposal's section definition.

    Defensive: a malformed section degrades to a titled empty table rather than
    breaking the whole shell."""
    section_id = sdef.get("section_id")
    if not section_id:
        return None
    title = sdef.get("title") or section_id
    stype = sdef.get("section_type") or "table"
    spec = _proposal_section_spec(extraction, section_id)
    try:
        if stype == "metric":
            items = [MetricItem(id=mid, label=label, value=None)
                     for mid, label in _shell_metric_items(spec)]
            return MetricSection(type="metric", id=section_id, title=title,
                                 items=items, render_mode="metric")
        if stype == "card":
            items = [CardItem(label=label, value=None) for label in _shell_card_labels(spec)]
            vm = (spec.get("card") or {}).get("view_mode") if isinstance(spec.get("card"), dict) else None
            return CardSection(type="card", id=section_id, title=title, items=items,
                               view_mode=vm if vm in ("tiles", "table") else None)
        if stype == "findings":
            return FindingsSection(type="findings", id=section_id, title=title, items=[])
        if stype == "chart":
            return ChartSection(type="chart", id=section_id, title=title,
                                chart_type=_shell_chart_type(spec), labels=[], series=[])
        # "table" and any unknown type → a titled table shell.
        cols = [TableColumn(id=cid, label=label) for cid, label in _shell_columns(spec)]
        return TableSection(type="table", id=section_id, title=title, columns=cols,
                            items=[], empty_message="No data collected")
    except Exception:
        return TableSection(type="table", id=section_id, title=title, columns=[],
                            items=[], empty_message="No data collected")


def _proposal_section_spec(extraction: dict[str, Any], section_id: str) -> dict[str, Any]:
    """The per-section extraction spec, preferring the live REST source types."""
    ordered = list(("rest_command_center_api", "rest", "json", "html", "csv")) + list(extraction.keys())
    for key in ordered:
        src_info = extraction.get(key)
        if isinstance(src_info, dict):
            secs = src_info.get("sections")
            if isinstance(secs, dict) and isinstance(secs.get(section_id), dict):
                return secs[section_id]
    return {}


def _shell_columns(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Column (id, label) pairs from a table spec, tolerant of shape:
    table.columns (ADR 0009 D2), columns (row_source form), or column_map (HTML)."""
    cols_src = None
    table_block = spec.get("table")
    if isinstance(table_block, dict) and isinstance(table_block.get("columns"), list):
        cols_src = table_block["columns"]
    elif isinstance(spec.get("columns"), list):
        cols_src = spec["columns"]
    elif isinstance(spec.get("column_map"), list):
        cols_src = spec["column_map"]
    out: list[tuple[str, str]] = []
    for c in cols_src or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("canonical") or c.get("field") or c.get("label")
        label = c.get("label") or c.get("canonical") or c.get("id") or c.get("field") or cid
        if cid:
            out.append((str(cid), str(label)))
    return out


def _shell_metric_items(spec: dict[str, Any]) -> list[tuple[str, str]]:
    src = spec.get("metrics") if isinstance(spec.get("metrics"), list) else spec.get("items")
    out: list[tuple[str, str]] = []
    for m in src or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or m.get("label")
        label = m.get("label") or m.get("id")
        if mid:
            out.append((str(mid), str(label)))
    return out


def _shell_card_labels(spec: dict[str, Any]) -> list[str]:
    card = spec.get("card") if isinstance(spec.get("card"), dict) else {}
    out: list[str] = []
    for it in card.get("items") or []:
        if isinstance(it, dict) and it.get("label"):
            out.append(str(it["label"]))
    return out


def _shell_chart_type(spec: dict[str, Any]) -> ChartType:
    chart = spec.get("chart") if isinstance(spec.get("chart"), dict) else {}
    raw = chart.get("chart_type")
    try:
        return ChartType(raw) if raw else ChartType.line
    except ValueError:
        return ChartType.line


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
        is_rp_dataset = src_id == REPORTSPLUS_DATASET_SOURCE_ID
        is_json = src_id == JSON_IMPORT_SOURCE_ID
        collect_url = src.get("collect_url")
        is_import = is_html or is_csv
        if is_import and extractable:
            accept = ".html,.htm" if is_html else ".csv"
            actions = [
                _upload_action(import_url=import_url_base, import_field="file", accept=accept)
            ]
            status = "a"
        elif (is_rest or is_command_center or is_rp_dataset or is_json) and collect_url:
            # REST / Command Center API / RP-dataset collect from the lab; JSON
            # (internal/test subjects) collects from a shipped fixture via the
            # collect-fixture route. The live-REST paths are auth-gated
            # (customer-bound CommCell session); requiresSession lets the frontend
            # open the connect modal in-place for that case. JSON fixture
            # collection needs no session and submits straight through.
            actions = [{
                "kind": "collect",
                "label": "Collect",
                "collectUrl": collect_url,
                "requiresSession": is_rest or is_command_center or is_rp_dataset,
            }]
            status = "a"
        else:
            actions = []
            status = "ni"
        # Command Center source cosmetics (ADR 0007 ph3 slice B — match what the
        # retired live builder showed, kept generic/data-driven):
        #   desc:   the canonical SOURCE_DESCRIPTIONS text (was empty in the
        #           generic path; the tile rows carry no description).
        #   status: "validated" once an artifact has been collected through it,
        #           else "available" — derived from whether a stored artifact
        #           exists, not hardcoded.
        description = src.get("description", "")
        if is_command_center:
            description = SOURCE_DESCRIPTIONS.get(src_id, description)
            if artifact_payload is not None:
                status = "v"
        result.append(_source_item(
            src_id,
            src.get("label", src_id),
            description,
            status=status,
            meta=_command_center_source_meta(artifact_payload) if is_command_center else [],
            actions=actions,
        ))
    return result


def _command_center_source_meta(artifact_payload: dict[str, Any] | None) -> list[dict[str, str]]:
    """Source-panel descriptor for the single-object Command Center API source,
    built in the GENERIC path so it survives the live builder's retirement.

    - Endpoint: a source-TYPE constant (SOURCE_ENDPOINTS) — GET /commandcenter/api/CommServ.
    - Host: the CommCell host from the collected identity card (Hostname, falling
      back to CommCell Name). It is NOT in the artifact's source block (that carries
      the customer name), so it is read from the card the collection produced; absent
      → the Host row is simply omitted. (Populating source.endpoint/host at collect
      time would be the cleaner long-term home, but that touches the stored artifact.)"""
    meta: list[dict[str, str]] = []
    endpoint = SOURCE_ENDPOINTS.get(REST_COMMAND_CENTER_API_SOURCE_ID)
    if endpoint:
        meta.append({"k": "Endpoint", "v": endpoint})
    host = _command_center_host(artifact_payload)
    if host:
        meta.append({"k": "Host", "v": host})
    return meta


def _command_center_host(artifact_payload: dict[str, Any] | None) -> str | None:
    """Best-effort CommCell host from the collected identity card (Hostname, then
    CommCell Name). Returns None when unavailable — no host row is shown."""
    if not artifact_payload:
        return None
    for sec in artifact_payload.get("sections", []) or []:
        if sec.get("type") != "card":
            continue
        items = {it.get("label"): it.get("value") for it in sec.get("items", []) or []}
        host = items.get("Hostname") or items.get("CommCell Name")
        if host:
            return str(host)
    return None


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
    # Saved description overrides (the workspace Save button) only exist for
    # system tiles; they used to surface via the legacy builders (retired by
    # Fix 2), so the generic path resolves them now. AI subjects -> KeyError
    # -> keep the catalog description.
    try:
        description = resolve_tile_description(subject_id) or description
    except KeyError:
        pass
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
            # Default-select the first source so its collect/import affordance is
            # visible on the empty (not-yet-collected) state — the JS panel only
            # renders for the active source. (Pre-slice-B, environment's live
            # builder set this to the command-center source; the generic path now
            # does it for every subject's empty state.)
            "activeSource": sources[0]["id"] if sources else None,
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
    # Command Center artifacts (environment) get a "<host> · <version>" subtitle
    # derived from the identity card — matching the retired live builder, instead
    # of the generic "Data available". Generic by source type, not env-special.
    if (artifact_payload or {}).get("source", {}).get("type") == "rest_commserve":
        cc_subtitle = _command_center_subtitle(artifact_payload)
        if cc_subtitle:
            view["subtitle"] = cc_subtitle
    return view


def _command_center_subtitle(artifact_payload: dict[str, Any] | None) -> str | None:
    """"<host> · <version>" for a Command Center artifact, from the identity card
    (Hostname/CommCell Name + Version). Matches the retired live builder's subtitle.
    Returns None when neither field is present (caller keeps the generic subtitle)."""
    host = _command_center_host(artifact_payload)
    version = None
    for sec in (artifact_payload or {}).get("sections", []) or []:
        if sec.get("type") != "card":
            continue
        items = {it.get("label"): it.get("value") for it in sec.get("items", []) or []}
        version = items.get("Version")
        if version:
            break
    if host and version:
        return f"{host} · {version}"
    return host or (str(version) if version else None)


# ── HEADER ──

def _build_commcell_header(artifact: CanonicalArtifact | None) -> dict:
    """Header summary (subtitle name/version) from the SCOPED environment
    artifact's identity card (Fix 2 (b)). Reads the card items by their
    catalog-declared labels (Hostname / CommCell Name / CommCell GUID /
    Version / Timezone); honest-empty when the active project has no
    environment artifact. Replaces the global commserv.json read."""
    if artifact is None:
        return {"exists": False, "name": "", "version": "", "id": "", "timezone": ""}
    items: dict[str, Any] = {}
    for sec in artifact.model_dump(mode="json").get("sections", []) or []:
        if sec.get("type") != "card":
            continue
        for item in sec.get("items", []) or []:
            label = item.get("label")
            if label and item.get("value") not in (None, ""):
                items.setdefault(label, item.get("value"))
    if not items:
        return {"exists": False, "name": "", "version": "", "id": "", "timezone": ""}
    return {
        "exists": True,
        "name": str(items.get("Hostname") or items.get("CommCell Name") or ""),
        "version": str(items.get("Version") or ""),
        "id": str(items.get("CommCell GUID") or items.get("CommCell ID") or ""),
        "timezone": str(items.get("Timezone") or ""),
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


