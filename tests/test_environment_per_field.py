"""Phase-8 follow-on — per-field evaluation on the bespoke environment track.

CommCell Details / environment is built by the bespoke _build_environment_subject
(one of the six system subjects with custom view shapes, ADR 0001 source-building
fork), NOT the generic build_card_section path that _card_test uses. Its identity
card flows through the SAME shared path (build_card_section → engine.evaluate →
_card_section_view → the per-field card renderer).

Option A (this slice): the per-field rules are DATA — read from environment's
catalog binding (migration 0023) — not a Python literal. Values are still sourced
live from commserv.json (cc). Rules: Version (presence), Timezone (enum, no
allowed-set yet), CommCell Name (format, no pattern yet); CommCell ID informational.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.quickhc.subject_data_service import (
    _build_environment_subject,
    _load_environment_identity_rules,
    _normalize_timezone,
)

# The REAL GET /commandcenter/api/CommServ response shape (the .raw block) — the
# builder now reads card fields directly from this nested structure, not a flat
# identity dict. commCellId is the integer 2 (rendered hex "2").
_CC = {
    "commcell": {
        "commCellId": 2,
        "commCellName": "CS01",
        "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D",
    },
    "csTimeZone": {"TimeZoneID": 269, "TimeZoneName": "America/Danmarkshavn"},
    "csVersionInfo": "11 SP40.47",
    "currentSPVersion": 40,
    "installedSPVersion": 40,
    "hostName": "cs01",
    "osType": "Unix",
    "releaseId": 16,
    "timeZone": "0:0:America/Danmarkshavn",
}


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _identity_section(cc: dict, db: sqlite3.Connection | None = None) -> dict:
    return _build_environment_subject(cc, db)["sections"][0]


# ── the rules are DATA (from the binding), not a Python literal ──

def test_environment_rules_loaded_from_binding(migrated_db_path: Path):
    """With the catalog binding present (migration 0023), the card's per-field
    rules load from DATA: Version (presence) judges good; Timezone (enum, no
    allowed-set) and CommCell Name (format, no pattern) render SAFE good; CommCell
    ID is informational (bare). Section rolls up good."""
    conn = _conn(migrated_db_path)
    try:
        by = {i["label"]: i for i in _identity_section(_CC, conn)["items"]}
    finally:
        conn.close()
    assert by["Version"]["sev"] == "good" and by["Version"]["reason"] == "Version is set"
    assert by["Timezone"]["sev"] == "good"          # enum, no allowed-set -> safe
    assert "no allowed-set configured" in by["Timezone"]["reason"]
    assert by["CommCell Name"]["sev"] == "good"     # format, no pattern -> safe
    assert "no format pattern configured" in by["CommCell Name"]["reason"]
    assert by["CommCell ID"]["sev"] is None         # informational, no rule


def test_environment_section_rolls_up_good(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        sec = _identity_section(_CC, conn)
    finally:
        conn.close()
    assert sec["type"] == "card" and sec["columns"] == 4 and sec["meta"] == "CommCell profile"
    assert sec["sev"] == "good"


def test_environment_section_view_mode_is_table_from_binding(migrated_db_path: Path):
    """view_mode is DATA on the section (migration 0024), read from the binding —
    environment opts into the Field/Value table. The renderer reads sec.view_mode;
    nothing is hardcoded per subject."""
    conn = _conn(migrated_db_path)
    try:
        sec = _identity_section(_CC, conn)
    finally:
        conn.close()
    assert sec["view_mode"] == "table"


def test_environment_table_dots_verdict_vs_info_fallback(migrated_db_path: Path):
    """Every row gets a dot: ruled fields carry a real verdict severity (their
    dot colour), and no-verdict fields fall back to the "info" dot at RENDER time
    — NOT via authored rules. The data contract here is: ruled fields have sev;
    informational fields have sev=None (no info rule written onto them). The
    info-fallback itself lives in the JS renderer (effState: sev ?? state ?? info)."""
    conn = _conn(migrated_db_path)
    try:
        by = {i["label"]: i for i in _identity_section(_CC, conn)["items"]}
    finally:
        conn.close()
    # ruled fields -> a real verdict severity drives the dot
    assert by["CommCell Name"]["sev"] and by["Version"]["sev"] and by["Timezone"]["sev"]
    # informational fields carry NO sev -> their info dot comes from the render
    # fallback, not from an authored info rule (the 49053a9 binding is untouched).
    for bare in ["CommCell ID", "CommCell GUID", "OS Type",
                 "Current SP Version", "Installed SP Version", "Hostname"]:
        assert by[bare]["sev"] is None


def test_environment_view_mode_defaults_tiles_without_binding():
    """No db / no binding -> view_mode falls back to the default "tiles" (safe)."""
    sec = _identity_section(_CC, None)
    assert sec["view_mode"] == "tiles"


def test_environment_no_db_no_rules_is_bare_proves_literal_gone(migrated_db_path: Path):
    """The rule literal is GONE: with no db (so the binding can't be read), NO
    field is judged — every field is bare. If a Version literal still lived in the
    builder, Version would be `good` here. It isn't, so the rules are pure data."""
    by = {i["label"]: i for i in _identity_section(_CC, None)["items"]}
    assert all(by[f]["sev"] is None for f in
               ["CommCell Name", "CommCell ID", "Version", "Timezone"])


def test_environment_binding_carries_three_rules(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        rules = _load_environment_identity_rules(conn)
    finally:
        conn.close()
    by_field = {r["target_field"]: r for r in rules}
    assert by_field["version"]["kind"] == "presence"
    assert by_field["timezone"]["kind"] == "enum" and "allowed_values" not in by_field["timezone"]
    assert by_field["name"]["kind"] == "format" and "pattern" not in by_field["name"]


# ── timezone normalization ──

def test_timezone_normalized_to_iana_component():
    # composite "<offsetH>:<offsetM>:<IANA>" -> the IANA name only
    assert _normalize_timezone("0:0:America/Danmarkshavn") == "America/Danmarkshavn"
    assert _normalize_timezone("UTC") == "UTC"             # non-composite passes through
    assert _normalize_timezone("") is None
    assert _normalize_timezone(None) is None


def test_environment_timezone_value_is_normalized(migrated_db_path: Path):
    """The normalized IANA component is what both displays AND is evaluated."""
    conn = _conn(migrated_db_path)
    try:
        by = {i["label"]: i for i in _identity_section(_CC, conn)["items"]}
    finally:
        conn.close()
    assert by["Timezone"]["value"] == "America/Danmarkshavn"


# ── the full GET CommServ field set, read directly from the real response ──

def test_environment_card_shows_full_commserv_field_set_in_schema_order(migrated_db_path: Path):
    """The card surfaces the real GET CommServ fields in schema order, read
    directly (no synthesis). commCellId(int 2) → hex "2"; GUID + Timezone direct;
    Release Name omitted (absent from the API). Labels CSS-uppercased at render."""
    conn = _conn(migrated_db_path)
    try:
        sec = _identity_section(_CC, conn)
    finally:
        conn.close()
    assert [(i["label"], i["value"]) for i in sec["items"]] == [
        ("CommCell Name", "CS01"),                 # commcell.commCellName
        ("CommCell ID", "2"),                       # hex(commCellId=2) — NOT the GUID
        ("CommCell GUID", "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"),  # direct
        ("Version", "11 SP40.47"),                  # csVersionInfo
        ("OS Type", "Unix"),                        # osType
        ("Current SP Version", "40"),               # currentSPVersion
        ("Installed SP Version", "40"),             # installedSPVersion
        ("Timezone", "America/Danmarkshavn"),       # csTimeZone.TimeZoneName (clean)
        ("Hostname", "cs01"),                       # hostName
    ]
    assert "Release Name" not in {i["label"] for i in sec["items"]}


def test_environment_commcell_id_is_hex_not_synthesized(migrated_db_path: Path):
    """commCellId is read as an integer and rendered hex (the brief's 13183 ->
    "337f"); the GUID is read directly. ID and GUID are distinct values — the ID
    is NOT the GUID (the old bug) and neither is synthesized from Serial/RegCode."""
    cc = dict(_CC, commcell=dict(_CC["commcell"], commCellId=13183))
    conn = _conn(migrated_db_path)
    try:
        by = {i["label"]: i for i in _identity_section(cc, conn)["items"]}
    finally:
        conn.close()
    assert by["CommCell ID"]["value"] == "337f"     # hex(13183)
    assert by["CommCell GUID"]["value"] == "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"
    assert by["CommCell ID"]["value"] != by["CommCell GUID"]["value"]


def test_environment_version_missing_renders_dash_and_warns(migrated_db_path: Path):
    """Absent version renders '—' AND the presence rule reads not-set -> warning."""
    conn = _conn(migrated_db_path)
    try:
        by = {i["label"]: i for i in _identity_section(dict(_CC, csVersionInfo=""), conn)["items"]}
    finally:
        conn.close()
    assert by["Version"]["value"] == "—"
    assert by["Version"]["sev"] == "warn"


def test_environment_no_data_branch_unchanged():
    """The no-data branch (cc is None) is untouched — no identity card built."""
    subj = _build_environment_subject(None)
    assert subj["id"] == "environment"
    assert all(s.get("type") != "card" for s in subj.get("sections", []))


# ── Model-layer: the shared path's CardSection validates on reload ──

def test_environment_identity_card_validates_on_reload():
    """The identity card the bespoke builder produces (via build_card_section) is
    a real CardSection that round-trips through CanonicalArtifact validation."""
    spec = {
        "columns": 4,
        "items": [
            {"label": "CommCell Name", "field": "name"},
            {"label": "Version", "field": "version"},
        ],
        "evaluative": {"rules": [
            {"rule_id": "environment_version_presence", "target_field": "version",
             "kind": "presence", "severity_when_missing": "warning",
             "severity_when_present": "good"},
        ]},
    }
    sec = build_card_section("environment.metadata", "Environment metadata",
                             spec, [{"name": "cs01", "version": "11 SP40.47"}])
    art = CanonicalArtifact(
        artifact_type="environment", generated_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        source=ArtifactSource(type=SourceType.rest),
        subject=ArtifactSubject(id="environment", title="CommCell Details"),
        summary=ArtifactSummary(status=ArtifactStatus.good), sections=[sec],
    )
    CanonicalArtifact.model_validate(art.model_dump(mode="json"))  # no raise
