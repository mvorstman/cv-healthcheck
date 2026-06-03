"""ADR 0010 Phase 2b — the rule authoring surface (list/save/bind/delete +
validation) and the MCP tool wiring. Self-contained: rules/bindings authored
into a temp migrated DB; data/app.db is never read.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.rules import (
    bind_rule, delete_rule, list_rules, load_rules_registry,
    load_subject_row_rules, save_rule, validate_row_match_rule,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal

ROW_RULE = {
    "rule_id": "r_empty", "kind": "row_match",
    "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
    "emit": "per_row", "severity": "warning",
    "title": "Empty: {row.name}", "message": "{row.name} empty",
}


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture()
def db(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        yield conn
    finally:
        conn.close()


def _seed_subject(conn: sqlite3.Connection) -> None:
    """A subject with a TABLE section (sg.rows, cols id/name/server_count) and a
    METRIC section (sg.meta) — for the bind-target validation tests."""
    create_subject_from_proposal(conn, {
        "subject_id": "sg", "version": 1, "title": "SG", "description": "d",
        "category": "operations",
        "sections": [
            {"section_id": "sg.rows", "title": "Rows", "section_type": "table", "sort_order": 0},
            {"section_id": "sg.meta", "title": "Meta", "section_type": "metric", "sort_order": 1},
        ],
        "extraction_instructions": {"rest_command_center_api": {
            "extractable": True, "endpoint": "/commandcenter/api/v4/servergroup",
            "sections": {
                "sg.rows": {"output_as": "table", "table": {"root_key": "items", "columns": [
                    {"id": "id", "field": "id"}, {"id": "name", "field": "name"},
                    {"id": "server_count", "field": "server_count"}]}},
                "sg.meta": {"output_as": "metric", "metrics": [{"id": "total", "label": "Total"}]},
            }}},
    })


# ── save_rule + versioning ────────────────────────────────────────────────────

def test_save_rule_upserts_and_bumps_version_on_change(db):
    v1 = save_rule(db, ROW_RULE)
    assert v1["version"] == 1
    assert save_rule(db, ROW_RULE)["version"] == 1            # unchanged body → no bump
    v2 = save_rule(db, {**ROW_RULE, "severity": "critical"})
    assert v2["version"] == 2                                 # changed → bump
    assert load_rules_registry(db)["r_empty"]["severity"] == "critical"


# ── list_rules filters ────────────────────────────────────────────────────────

def test_list_rules_subject_and_enabled_filters(db):
    _seed_subject(db)
    save_rule(db, ROW_RULE)
    save_rule(db, {**ROW_RULE, "rule_id": "r_off", "enabled": False})
    # (the migrated DB seeds e.g. capacity_utilisation — assert on our rules, not exact)
    assert {"r_empty", "r_off"} <= {r["rule_id"] for r in list_rules(db)}
    enabled_ids = {r["rule_id"] for r in list_rules(db, enabled=True)}
    assert "r_empty" in enabled_ids and "r_off" not in enabled_ids
    assert {r["rule_id"] for r in list_rules(db, enabled=False)} == {"r_off"}  # seeds default-enabled
    bind_rule(db, "r_empty", "sg", "sg.rows")
    assert [r["rule_id"] for r in list_rules(db, subject_id="sg")] == ["r_empty"]


# ── binding (idempotent) + unbound save ───────────────────────────────────────

def test_save_with_bind_writes_ref_idempotent(db):
    _seed_subject(db)
    save_rule(db, ROW_RULE)
    assert bind_rule(db, "r_empty", "sg", "sg.rows") == 1
    assert bind_rule(db, "r_empty", "sg", "sg.rows") == 0     # idempotent, no dup
    assert load_subject_row_rules(db, "sg")["sg.rows"][0]["rule_id"] == "r_empty"

def test_save_without_bind_writes_no_binding(db):
    _seed_subject(db)
    save_rule(db, ROW_RULE)
    assert load_subject_row_rules(db, "sg") == {}


# ── disabled rules don't fire ─────────────────────────────────────────────────

def test_disabled_rule_not_loaded_for_evaluation(db):
    _seed_subject(db)
    save_rule(db, {**ROW_RULE, "enabled": False})
    bind_rule(db, "r_empty", "sg", "sg.rows")
    assert load_subject_row_rules(db, "sg") == {}             # disabled → excluded


# ── delete strips the binding ─────────────────────────────────────────────────

def test_delete_rule_removes_and_strips_binding(db):
    _seed_subject(db)
    save_rule(db, ROW_RULE)
    bind_rule(db, "r_empty", "sg", "sg.rows")
    res = delete_rule(db, "r_empty")
    assert res == {"deleted": "r_empty", "existed": True, "bindings_stripped": 1}
    assert "r_empty" not in load_rules_registry(db)
    # binding stripped → load no longer hits "unknown ref fails loudly"
    assert load_subject_row_rules(db, "sg") == {}


# ── validation rejections (a–f + scope) ───────────────────────────────────────

def test_validation_rejections(db):
    _seed_subject(db)
    bind = {"subject_id": "sg", "section_id": "sg.rows"}
    # (a) section not on subject
    with pytest.raises(ValueError, match="not present on subject"):
        validate_row_match_rule(db, ROW_RULE, bind={"subject_id": "sg", "section_id": "sg.nope"})
    # (b) bound to a non-table section
    with pytest.raises(ValueError, match="must bind to a table section"):
        validate_row_match_rule(db, ROW_RULE, bind={"subject_id": "sg", "section_id": "sg.meta"})
    # (c) target column not in the section
    bad_col = {**ROW_RULE, "conditions": [{"target": "ghost_col", "operator": "eq", "value": 0}]}
    with pytest.raises(ValueError, match="columns not in section"):
        validate_row_match_rule(db, bad_col, bind=bind)
    # (c) a {ref} to a missing column also rejected
    bad_ref = {**ROW_RULE, "conditions": [{"target": "server_count", "operator": "gt",
                                           "value": {"ref": "ghost_col"}}]}
    with pytest.raises(ValueError, match="columns not in section"):
        validate_row_match_rule(db, bad_ref, bind=bind)
    # (d) emit=count without operator/value
    with pytest.raises(ValueError, match="count_operator"):
        validate_row_match_rule(db, {**ROW_RULE, "emit": "count"})
    # (e) unknown operator
    with pytest.raises(ValueError, match="unknown operator"):
        validate_row_match_rule(db, {**ROW_RULE, "conditions": [
            {"target": "server_count", "operator": "wat", "value": 0}]})
    # (f) between without value2
    with pytest.raises(ValueError, match="requires value2"):
        validate_row_match_rule(db, {**ROW_RULE, "conditions": [
            {"target": "server_count", "operator": "between", "value": 1}]})
    # scope != row
    with pytest.raises(ValueError, match="only 'row'"):
        validate_row_match_rule(db, {**ROW_RULE, "scope": "summary"})

def test_validation_accepts_valid_count_rule(db):
    _seed_subject(db)
    validate_row_match_rule(
        db, {**ROW_RULE, "emit": "count", "count_operator": "gte", "count_value": 1},
        bind={"subject_id": "sg", "section_id": "sg.rows"})  # no raise


# ── MCP tool wiring ───────────────────────────────────────────────────────────

@pytest.fixture()
def server(monkeypatch, migrated_db_path: Path):
    import cvhealthcheck.mcp.server as srv
    monkeypatch.setattr(srv, "get_db", lambda: _conn(migrated_db_path))
    return srv

def test_save_rule_tool_validates_saves_and_binds(server, migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _seed_subject(conn)
    finally:
        conn.close()
    out = server.save_rule(ROW_RULE, bind={"subject_id": "sg", "section_id": "sg.rows"})
    assert out["rule"]["rule_id"] == "r_empty" and out["bound_sections"] == 1
    # a malformed rule is rejected by the tool (validation runs before persist)
    with pytest.raises(ValueError, match="unknown operator"):
        server.save_rule({**ROW_RULE, "rule_id": "bad",
                          "conditions": [{"target": "x", "operator": "wat", "value": 1}]})
    conn = _conn(migrated_db_path)
    try:
        assert "bad" not in load_rules_registry(conn)         # not persisted
    finally:
        conn.close()

def test_evaluate_subject_tool_no_artifact_is_empty(server):
    res = server.evaluate_subject("nonexistent_subject_xyz")
    assert res["has_artifact"] is False and res["count"] == 0


def test_save_rule_tool_persists_canonical_kind_and_scope(server, migrated_db_path: Path):
    """A rule authored WITHOUT an explicit kind/scope is stored with the canonical
    `kind:"row_match"` / `scope:"row"`, so the evaluator's kind check always
    matches (the divergence that left save_rule-authored rules un-evaluated)."""
    conn = _conn(migrated_db_path)
    try:
        _seed_subject(conn)
    finally:
        conn.close()
    rule = {"rule_id": "nokind",
            "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
            "emit": "per_row", "severity": "warning", "title": "t", "message": "m"}
    assert "kind" not in rule and "scope" not in rule
    server.save_rule(rule, bind={"subject_id": "sg", "section_id": "sg.rows"})
    conn = _conn(migrated_db_path)
    try:
        stored = load_rules_registry(conn)["nokind"]
    finally:
        conn.close()
    assert stored["kind"] == "row_match" and stored["scope"] == "row"
