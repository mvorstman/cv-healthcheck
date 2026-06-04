"""save_rule bind path scopes section lookups to the ACTIVE subject version, and
recognizes a transpose property table's implicit key/id targets. Regression for
the bug where binding to v4 commserve_software_cache.cache_configuration (table)
was rejected as 'card' because the unscoped lookup picked v1. Self-contained;
never reads data/app.db.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.rules import (
    _section_column_ids, bind_rule, load_subject_row_rules,
    save_rule, validate_row_match_rule,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal


def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON"); return conn


def _proposal(version: int, section_type: str, instr: dict) -> dict:
    return {
        "subject_id": "csc", "version": version, "title": "CSC", "description": "d",
        "category": "operations",
        "sections": [{"section_id": "cfg", "title": "Cfg", "section_type": section_type, "sort_order": 0}],
        "extraction_instructions": {"rest_command_center_api": {
            "extractable": True, "endpoint": "/commandcenter/api/commserv/x",
            "sections": {"cfg": instr}}},
    }

# v1: cfg is a CARD (declares top-level `columns` incl. free_space) — the stale shape.
_V1 = _proposal(1, "card", {"output_as": "card",
    "columns": [{"id": "free_space", "field": "cacheFreeSpace"}]})
# v4: cfg is a transpose TABLE (display columns label/value; rule targets key/value).
_V4 = _proposal(4, "table", {"output_as": "table", "table": {
    "root_key": "obj",
    "transpose": [{"key": "in_sync", "label": "In sync", "field": "f"}],
    "columns": [{"id": "label", "label": "Setting"}, {"id": "value", "label": "Value"}]}})


@pytest.fixture()
def db(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    create_subject_from_proposal(conn, _V1)
    create_subject_from_proposal(conn, _V4)
    # v1 superseded, v4 active (v1 inserted first → lower rowid → the row the old
    # unscoped `.fetchone()` returned)
    conn.execute("UPDATE subjects SET status='superseded' WHERE subject_id='csc' AND version<4")
    conn.execute("UPDATE subjects SET status='active' WHERE subject_id='csc' AND version=4")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


TRANSPOSE_RULE = {
    "rule_id": "csc_in_sync", "kind": "row_match", "scope": "row", "emit": "per_row",
    "severity": "warning", "title": "t", "message": "m",
    "conditions": [{"target": "key", "operator": "eq", "value": "in_sync"},
                   {"target": "value", "operator": "eq", "value": False}],
}
BIND = {"subject_id": "csc", "section_id": "cfg"}


# ── FIX 1: version-scoped section-type lookup ─────────────────────────────────

def test_bind_succeeds_on_active_version_when_section_type_changed(db):
    # the bug condition reproduced: the UNSCOPED query returns v1's 'card' first
    unscoped = db.execute(
        "SELECT section_type FROM subject_sections WHERE subject_id='csc' AND section_id='cfg'"
    ).fetchone()
    assert unscoped["section_type"] == "card"           # the stale (v1) row the OLD code picked
    # the fixed path resolves the ACTIVE v4 ('table') → no "must bind to a table section"
    validate_row_match_rule(db, TRANSPOSE_RULE, bind=BIND)   # does not raise

def test_section_column_ids_returns_active_version_only(db):
    # active v4: transpose display columns + implicit per-row targets; NOT v1's free_space
    assert _section_column_ids(db, "csc", "cfg", 4) == {"label", "value", "id", "key"}
    # the stale v1 (card) declared free_space — must NOT leak into the active-version set
    assert "free_space" not in _section_column_ids(db, "csc", "cfg", 4)
    # scoping is real: asking for v1 explicitly returns v1's columns
    assert _section_column_ids(db, "csc", "cfg", 1) == {"free_space"}

def test_no_active_version_raises_clear_error(db):
    db.execute("UPDATE subjects SET status='superseded' WHERE subject_id='csc'")
    db.commit()
    with pytest.raises(ValueError, match="no active version"):
        validate_row_match_rule(db, TRANSPOSE_RULE, bind=BIND)


# ── FIX 2: transpose key/id are valid targets; bogus still rejected ───────────

def test_rule_targeting_key_and_value_binds_end_to_end(db):
    validate_row_match_rule(db, TRANSPOSE_RULE, bind=BIND)   # key + value accepted, no raise
    save_rule(db, TRANSPOSE_RULE)                            # persist the rule
    assert bind_rule(db, "csc_in_sync", "csc", "cfg") >= 1   # ref written
    # the ACTIVE v4 binding carries the rule (collection reads v4)
    assert load_subject_row_rules(db, "csc", 4)["cfg"][0]["rule_id"] == "csc_in_sync"

def test_bogus_target_still_rejected(db):
    bad = {**TRANSPOSE_RULE, "rule_id": "bad",
           "conditions": [{"target": "nonexistent", "operator": "eq", "value": 1}]}
    with pytest.raises(ValueError, match="columns not in section"):
        validate_row_match_rule(db, bad, bind=BIND)


# ── regression: single-version table bind unchanged ───────────────────────────

def test_single_version_table_bind_unchanged(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(conn, _proposal(1, "table", {"output_as": "table", "table": {
            "root_key": "items", "columns": [{"id": "id", "field": "id"}, {"id": "n", "field": "n"}]}}))
        rule = {"rule_id": "r", "kind": "row_match", "scope": "row", "emit": "per_row",
                "severity": "warning", "title": "t", "message": "m",
                "conditions": [{"target": "n", "operator": "eq", "value": 0}]}
        validate_row_match_rule(conn, rule, bind=BIND)      # active = v1, no raise
        assert _section_column_ids(conn, "csc", "cfg", 1) == {"id", "n"}   # no transpose implicit keys
    finally:
        conn.close()
