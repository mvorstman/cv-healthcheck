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


# ── D: the environment Collect button (on the source, not the card) ──

def test_environment_emits_collect_action_on_command_center_source(migrated_db_path: Path):
    from cvhealthcheck.quickhc.subject_data_service import _build_environment_subject, _load_legacy_commcell
    from cvhealthcheck.quickhc.registry import REST_COMMAND_CENTER_API_SOURCE_ID
    conn = _conn(migrated_db_path)
    try:
        subj = _build_environment_subject(_load_legacy_commcell(), conn)
    finally:
        conn.close()
    cc_source = next(s for s in subj["sources"] if s["id"] == REST_COMMAND_CENTER_API_SOURCE_ID)
    collect = next((a for a in cc_source.get("actions", []) if a.get("kind") == "collect"), None)
    assert collect is not None
    assert collect["collectUrl"] == "/quick-hc/environment/collect"
    assert collect["requiresSession"] is True
    # the live-served CARD section is unchanged (still a card, still has its items)
    card = subj["sections"][0]
    assert card["type"] == "card" and card["items"]


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
