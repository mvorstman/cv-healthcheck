"""ADR 0007 Phase 2 — the single-object Command Center API extractor + pluggable
/collect dispatch + the environment Collect button.

Offline / fixture-based: a saved CommServ payload is injected, so no network is
needed. Proves: collect -> extract -> result_to_artifact -> a stored canonical
artifact whose card resolves nested fields and whose source.type is the CommServe
type (not `rest`).
"""
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact, CardSection
from cvhealthcheck.extractors.command_center import (
    COMMAND_CENTER_SOURCE_TYPE,
    CommandCenterExtractor,
)
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

# A saved GET CommServ payload (the shape get_commcell_identity returns), nested.
_PAYLOAD = {
    "http_status": 200,
    "ok": True,
    "error": None,
    "raw": {
        "commcell": {"commCellName": "cs01", "commCellId": 13183,
                     "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"},
        "csTimeZone": {"TimeZoneID": 269, "TimeZoneName": "America/Danmarkshavn"},
        "csVersionInfo": "11 SP40.47",
        "osType": "Unix",
        "currentSPVersion": 40,
        "installedSPVersion": 40,
        "hostName": "cs01",
    },
}


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── B: the single-object extractor produces a stored-shape card artifact ──

def test_command_center_extractor_builds_card_with_nested_reads(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        extractor = CommandCenterExtractor(conn, identity_provider=lambda: _PAYLOAD)
        result = extractor.extract("environment", 1)
    finally:
        conn.close()
    assert not result.errors
    assert result.source_type == COMMAND_CENTER_SOURCE_TYPE
    assert result.section_output_types["environment.metadata"] == "card"

    artifact = result_to_artifact(result, "environment", "CommCell Details")
    CanonicalArtifact.model_validate(artifact.model_dump())  # reload validates

    # source.type is the CommServe type, NOT rest
    assert artifact.source.type == SourceType.rest_commserve
    assert artifact.source.type != SourceType.rest
    # collected_at is stamped (live collection), not just imported_at
    assert artifact.source.collected_at is not None

    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    by = {i.label: i for i in card.items}
    # ADR 0007 ph3: FULL 9-field parity spec (migration 0028), read from the
    # real nested GET CommServ shape (no synthesis).
    assert set(by) == {
        "CommCell Name", "CommCell ID", "CommCell GUID", "Version", "OS Type",
        "Current SP Version", "Installed SP Version", "Timezone", "Hostname",
    }
    assert by["CommCell Name"].value == "cs01"                     # commcell.commCellName (nested)
    assert by["CommCell ID"].value == "337f"                       # hex(13183) — ADR 0007 D3
    assert by["CommCell GUID"].value == "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"
    assert by["Version"].value == "11 SP40.47"                     # csVersionInfo (flat)
    assert by["OS Type"].value == "Unix"                           # osType
    # SP versions are numeric at the model layer (the view layer stringifies).
    assert by["Current SP Version"].value == 40                    # currentSPVersion
    assert by["Installed SP Version"].value == 40                  # installedSPVersion
    assert by["Timezone"].value == "America/Danmarkshavn"          # csTimeZone.TimeZoneName (nested)
    assert by["Hostname"].value == "cs01"                          # hostName
    # ID and GUID are distinct (ID is hex of the int, NOT the GUID — the old bug)
    assert by["CommCell ID"].value != by["CommCell GUID"].value


def test_command_center_extractor_reports_api_failure(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        bad = {"http_status": 401, "ok": False, "error": "Access denied", "raw": None}
        result = CommandCenterExtractor(conn, identity_provider=lambda: bad).extract("environment", 1)
    finally:
        conn.close()
    assert result.errors and "CommServ" in result.errors[0]


# ── C: pluggable /collect dispatch discriminator ──

def test_collect_dispatch_discriminator(migrated_db_path: Path):
    from cvhealthcheck.web.routes.quick_hc import _has_command_center_source
    conn = _conn(migrated_db_path)
    try:
        # environment has a rest_command_center_api source (migration 0026)
        assert _has_command_center_source(conn, "environment", 1) is True
        # a Reports-Plus subject does not -> falls back to RESTExtractor path
        assert _has_command_center_source(conn, "client_growth", 1) is False
    finally:
        conn.close()


# ── D: the environment Collect button via the GENERIC path (ADR 0007 ph3 slice B) ──

def test_environment_emits_collect_action_on_command_center_source(migrated_db_path: Path):
    """Post-retirement: environment is served by the generic path. On a fresh DB
    (no stored artifact) it renders the not-collected empty state with the
    command-center source DEFAULT-SELECTED and its Collect action present — so a
    first collect is reachable without the retired live builder."""
    from cvhealthcheck.quickhc.registry import get_tiles, REST_COMMAND_CENTER_API_SOURCE_ID
    from cvhealthcheck.quickhc.subject_data_service import _build_generic_subject
    conn = _conn(migrated_db_path)
    try:
        tile = next(t for t in get_tiles(conn) if t["id"] == "environment")
    finally:
        conn.close()
    subj = _build_generic_subject(tile, None)          # no artifact -> empty state
    assert subj["state"] == "nodata"
    assert subj["activeSource"] == REST_COMMAND_CENTER_API_SOURCE_ID   # so the panel shows
    cc_source = next(s for s in subj["sources"] if s["id"] == REST_COMMAND_CENTER_API_SOURCE_ID)
    collect = next((a for a in cc_source.get("actions", []) if a.get("kind") == "collect"), None)
    assert collect is not None
    assert collect["collectUrl"] == "/quick-hc/environment/collect"
    assert collect["requiresSession"] is True


def test_legacy_builder_fork_is_fully_retired():
    """ADR 0007 ph3 slice B retired environment's bespoke builder; Fix 2
    (2026-06-12) retired the entire legacy fork — no loaders, no builders,
    no global-file reads. The module must not regrow them."""
    from cvhealthcheck.quickhc import subject_data_service as sds
    for symbol in (
        "_legacy_builders", "_legacy_loaders", "_build_environment_subject",
        "_build_security_assessment_subject", "_build_license_summary_subject",
        "_build_client_growth_subject", "_build_capacity_license_subject",
        "_build_backup_job_summary_subject",
    ):
        assert not hasattr(sds, symbol), symbol


def test_environment_generic_render_applies_command_center_cosmetics(migrated_db_path: Path):
    """Visual no-op proof: the generic render of a command-center artifact carries
    the cosmetics the retired live builder showed — CC source status 'v'
    (Validated), a non-empty source description, and a '<host> · <version>'
    subtitle — instead of the bare generic defaults."""
    from cvhealthcheck.quickhc.registry import get_tiles, REST_COMMAND_CENTER_API_SOURCE_ID
    from cvhealthcheck.quickhc.subject_data_service import _build_generic_subject
    conn = _conn(migrated_db_path)
    try:
        tile = next(t for t in get_tiles(conn) if t["id"] == "environment")
        result = CommandCenterExtractor(conn, identity_provider=lambda: _PAYLOAD).extract("environment", 1)
    finally:
        conn.close()
    artifact = result_to_artifact(result, "environment", "CommCell Details")
    subj = _build_generic_subject(tile, artifact)
    assert subj["activeSource"] == REST_COMMAND_CENTER_API_SOURCE_ID
    assert subj["subtitle"] == "cs01 · 11 SP40.47"      # <host> · <version> from the card
    cc = next(s for s in subj["sources"] if s["id"] == REST_COMMAND_CENTER_API_SOURCE_ID)
    assert cc["status"] == "v"                           # Validated — an artifact exists
    assert cc["desc"]                                    # non-empty source description


def test_command_center_source_carries_full_parity_binding(migrated_db_path: Path):
    """ADR 0007 ph3 (migration 0028): the binding holds the FULL 9-field parity
    spec — schema-ordered, CommCell ID authored with type:hex, plus the 3
    retargeted per-field rules (dot-path target_fields)."""
    conn = _conn(migrated_db_path)
    try:
        extractor = CommandCenterExtractor(conn, identity_provider=lambda: _PAYLOAD)
        instrs = extractor._load_section_instructions("environment", 1)
    finally:
        conn.close()
    assert len(instrs) == 1
    card = instrs[0]["extraction_instructions"]["card"]
    assert card["columns"] == 4 and card["view_mode"] == "table"
    items = card["items"]
    assert [(i["label"], i["field"]) for i in items] == [
        ("CommCell Name", "commcell.commCellName"),
        ("CommCell ID", "commcell.commCellId"),
        ("CommCell GUID", "commcell.csGUID"),
        ("Version", "csVersionInfo"),
        ("OS Type", "osType"),
        ("Current SP Version", "currentSPVersion"),
        ("Installed SP Version", "installedSPVersion"),
        ("Timezone", "csTimeZone.TimeZoneName"),
        ("Hostname", "hostName"),
    ]
    # CommCell ID is the only hex-coerced field (ADR 0007 D3).
    assert next(i for i in items if i["label"] == "CommCell ID")["type"] == "hex"
    assert all(i.get("type") is None for i in items if i["label"] != "CommCell ID")
    # the 3 rules, retargeted from the row-7 flat keys to row-22 dot-paths
    rules = {r["target_field"]: r for r in card["evaluative"]["rules"]}
    assert rules["csVersionInfo"]["rule_id"] == "environment_version_presence"
    assert rules["csVersionInfo"]["kind"] == "presence"
    assert rules["csTimeZone.TimeZoneName"]["rule_id"] == "environment_timezone_enum"
    assert rules["csTimeZone.TimeZoneName"]["kind"] == "enum"
    assert rules["commcell.commCellName"]["rule_id"] == "environment_name_format"
    assert rules["commcell.commCellName"]["kind"] == "format"


def test_command_center_parity_rules_fire_with_correct_severities(migrated_db_path: Path):
    """ADR 0007 ph3 PARITY GATE: on the stored artifact the 3 retargeted rules
    evaluate good/good/good (matching the live card) and the section rolls up
    good. Version present -> good; Timezone enum (no allowed-set) -> safe good;
    CommCell Name format (no pattern) -> safe good. The 6 bare fields carry no
    severity (informational; the render-time info dot is the JS fallback)."""
    conn = _conn(migrated_db_path)
    try:
        extractor = CommandCenterExtractor(conn, identity_provider=lambda: _PAYLOAD)
        result = extractor.extract("environment", 1)
    finally:
        conn.close()
    artifact = result_to_artifact(result, "environment", "CommCell Details")
    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    by = {i.label: i for i in card.items}
    assert by["Version"].severity == "good"
    assert by["Timezone"].severity == "good"
    assert by["CommCell Name"].severity == "good"
    for bare in ["CommCell ID", "CommCell GUID", "OS Type",
                 "Current SP Version", "Installed SP Version", "Hostname"]:
        assert by[bare].severity is None
    assert card.severity == "good"


# ── E: auth-gate flash (ADR 0007 ph3 follow-on, BUG 3) ──

def test_collect_auth_gate_flashes_instead_of_silent_redirect(monkeypatch):
    """An auth-failed collect (no customer-bound session) now FLASHES an error
    before redirecting to /login — so it no longer looks identical to a stale
    success (the prior silent redirect cost multiple diagnosis cycles)."""
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as qh

    # Active customer has a CommCell URL (so the hostname guard passes), but no
    # session token is set -> is_authenticated_for(...) is False -> the auth gate.
    monkeypatch.setattr(qh, "get_active_customer", lambda *a, **k: {
        "customer_id": "default", "customer_name": "Default",
        "commcell_hostname": "https://192.0.2.1:4433", "commcell_id": "X",
    })

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "default", "project_id": "default"}
    resp = client.post("/quick-hc/environment/collect")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
    assert any("Collection failed" in msg and "sign in" in msg for _cat, msg in flashes), flashes


# ── F: generic source-panel metadata + Last-collected relocation (ph3 follow-on) ──

def test_command_center_source_meta_carries_endpoint_and_host_from_artifact():
    """The GENERIC source panel surfaces the command-center descriptor (Endpoint
    constant + Host from the collected identity card) — no live builder needed."""
    from cvhealthcheck.quickhc.subject_data_service import _command_center_source_meta
    payload = {"sections": [{"type": "card", "items": [
        {"label": "CommCell Name", "value": "CS01"},
        {"label": "Hostname", "value": "cs01"},
    ]}]}
    kv = {m["k"]: m["v"] for m in _command_center_source_meta(payload)}
    assert kv["Endpoint"] == "GET /commandcenter/api/CommServ"
    assert kv["Host"] == "cs01"          # Hostname item preferred over CommCell Name


def test_command_center_source_meta_endpoint_only_when_no_host_artifact():
    """No artifact (no card) -> Endpoint row still shows, Host row omitted (not a
    placeholder). The "No source metadata" placeholder only shows when meta is
    genuinely empty — the endpoint constant means CC is never empty."""
    from cvhealthcheck.quickhc.subject_data_service import _command_center_source_meta
    meta = _command_center_source_meta(None)
    kv = {m["k"]: m["v"] for m in meta}
    assert kv == {"Endpoint": "GET /commandcenter/api/CommServ"}
    assert meta, "command-center meta must never be empty (endpoint is a constant)"


def test_command_center_host_falls_back_to_commcell_name():
    from cvhealthcheck.quickhc.subject_data_service import _command_center_host
    payload = {"sections": [{"type": "card", "items": [{"label": "CommCell Name", "value": "CS01"}]}]}
    assert _command_center_host(payload) == "CS01"


def test_last_collected_relocated_into_source_card_keeps_localtime():
    """Layout guard: "Last collected" now renders INSIDE the source card
    (src-last-collected, in the srcPanel block) and is still routed through fmtUtc
    -> window.fmtLocalTime (local time preserved). The Template dropdown stays in
    provBlock below the card."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1]
          / "src/cvhealthcheck/web/static/quick_hc.js").read_text()
    assert "src-last-collected" in js                  # relocated marker inside srcPanel
    assert "fmtUtc(s.last_collected)" in js            # still localtime-rendered
    # the Template dropdown is still authored (untouched) in the provenance block
    assert "version-dropdown" in js
