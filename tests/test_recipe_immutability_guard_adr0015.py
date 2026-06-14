"""ADR-0015 D2a — recipe immutability guard.

A post-approval write to a section's ``extraction_instructions`` may change ONLY
``evaluative.row_rules``. Every recipe key (known or future) and every OTHER
``evaluative`` subkey is locked. The guard compares PARSED structures (key order /
formatting irrelevant). Self-contained; never reads data/app.db.

Multi-version behavior (bind writes EVERY matching row across versions, not just
the active one) is asserted explicitly so a future scoping change is loud — it is
a deliberate NON-GOAL of this slice, preserved exactly.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.rules import (
    RecipeImmutabilityError,
    assert_recipe_unchanged,
    bind_rule,
    delete_rule,
    load_subject_row_rules,
    save_rule,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal


def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_RECIPE = {
    "format": "single_table",
    "column_map": [
        {"source": "License", "canonical": "license", "type": "string"},
        {"source": "Used", "canonical": "used", "transforms": ["to_integer"]},
    ],
    "null_values": ["N/A", "-"],
    "output_as": "table",
}


# ── the pure guard ────────────────────────────────────────────────────────────

def test_guard_allows_adding_row_rules():
    old = dict(_RECIPE)
    new = {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}]}}
    assert_recipe_unchanged(old, new)  # no raise


def test_guard_allows_changing_and_emptying_row_rules():
    old = {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}]}}
    assert_recipe_unchanged(old, {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}, {"ref": "r2"}]}})
    assert_recipe_unchanged(old, {**_RECIPE, "evaluative": {"row_rules": []}})


def test_guard_rejects_recipe_key_delta():
    old = {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}]}}
    new = json.loads(json.dumps(old))
    new["column_map"][1]["transforms"] = ["to_float"]  # a RECIPE change
    with pytest.raises(RecipeImmutabilityError):
        assert_recipe_unchanged(old, new)


def test_guard_rejects_recipe_key_addition():
    # a brand-new recipe key nobody enumerated must be protected by default (allowlist)
    old = dict(_RECIPE)
    new = {**_RECIPE, "some_future_recipe_key": {"x": 1},
           "evaluative": {"row_rules": [{"ref": "r1"}]}}
    with pytest.raises(RecipeImmutabilityError):
        assert_recipe_unchanged(old, new)


def test_guard_rejects_other_evaluative_subkey_delta():
    # only row_rules may differ; another evaluative subkey changing is rejected
    old = {**_RECIPE, "evaluative": {"row_rules": [], "scope": ["a"]}}
    new = {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}], "scope": ["a", "b"]}}
    with pytest.raises(RecipeImmutabilityError):
        assert_recipe_unchanged(old, new)


def test_guard_compares_parsed_not_raw():
    # old as a RAW string with keys in a different order than the new dict; same
    # structure + a row_rules add → passes (parsed compare, not text compare)
    old_raw = json.dumps({
        "output_as": "table",
        "column_map": _RECIPE["column_map"],
        "null_values": ["N/A", "-"],
        "format": "single_table",
    })
    new = {**_RECIPE, "evaluative": {"row_rules": [{"ref": "r1"}]}}
    assert_recipe_unchanged(old_raw, new)  # no raise despite key reordering


def test_guard_treats_empty_evaluative_as_absent():
    # first bind: old has no 'evaluative'; new has an (effectively empty) one
    assert_recipe_unchanged(dict(_RECIPE), {**_RECIPE, "evaluative": {"row_rules": []}})


def test_guard_handles_none_old_instructions():
    # a section whose stored extraction_instructions is NULL → treated as {}
    assert_recipe_unchanged(None, {"evaluative": {"row_rules": [{"ref": "r1"}]}})


# ── end-to-end through bind_rule / delete_rule (the authoring loop) ────────────

def _proposal(version: int, instr: dict, *, section_type: str = "table") -> dict:
    return {
        "subject_id": "guard_subj", "version": version, "title": "G", "description": "d",
        "category": "operations",
        "sections": [{"section_id": "sec", "title": "S", "section_type": section_type, "sort_order": 0}],
        "extraction_instructions": {"csv": {"extractable": True, "sections": {"sec": instr}}},
    }


_RULE = {
    "rule_id": "g1", "kind": "row_match", "scope": "row", "emit": "per_row",
    "severity": "warning", "title": "t", "message": "m",
    "conditions": [{"target": "used", "operator": "gt", "value": 0}],
}


def _section_instr(db, version: int) -> dict:
    row = db.execute(
        "SELECT sss.extraction_instructions AS instr FROM subject_section_sources sss "
        "JOIN subject_sources src ON src.id = sss.source_id "
        "WHERE src.subject_id='guard_subj' AND sss.section_id='sec' AND src.subject_version=?",
        (version,),
    ).fetchone()
    return json.loads(row["instr"])


@pytest.fixture()
def db(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    create_subject_from_proposal(conn, _proposal(1, dict(_RECIPE)))
    try:
        yield conn
    finally:
        conn.close()


def test_bind_rule_writes_ref_and_preserves_recipe(db):
    save_rule(db, _RULE)
    assert bind_rule(db, "g1", "guard_subj", "sec") == 1
    assert load_subject_row_rules(db, "guard_subj", 1)["sec"][0]["rule_id"] == "g1"
    # the recipe portion is intact after the guarded write
    assert _section_instr(db, 1)["column_map"] == _RECIPE["column_map"]


def test_delete_rule_strips_ref_and_preserves_recipe(db):
    save_rule(db, _RULE)
    bind_rule(db, "g1", "guard_subj", "sec")
    result = delete_rule(db, "g1")
    assert result["bindings_stripped"] == 1
    assert load_subject_row_rules(db, "guard_subj", 1).get("sec", []) == []
    assert _section_instr(db, 1)["column_map"] == _RECIPE["column_map"]  # recipe intact


def test_idempotent_rebind_is_noop(db):
    save_rule(db, _RULE)
    assert bind_rule(db, "g1", "guard_subj", "sec") == 1
    assert bind_rule(db, "g1", "guard_subj", "sec") == 0  # already present, no second ref


# ── NON-GOAL preserved: multi-version write is unchanged (asserted explicitly) ──

def test_bind_rule_writes_every_version_unchanged(migrated_db_path: Path):
    """bind_rule filters by subject_id+section_id, NOT version — it writes EVERY
    matching row across versions (incl. superseded). This is a deliberate NON-GOAL
    of the guard slice; assert the current behavior so a future scoping change is
    LOUD. Each version's distinct recipe survives the per-row guard."""
    conn = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(conn, _proposal(1, dict(_RECIPE)))
        # v2 has a DIFFERENT recipe (distinct null_values) — proves per-row recipe survival
        create_subject_from_proposal(conn, _proposal(2, {**_RECIPE, "null_values": ["ONLY_V2"]}))
        conn.execute("UPDATE subjects SET status='superseded' WHERE subject_id='guard_subj' AND version=1")
        conn.execute("UPDATE subjects SET status='active' WHERE subject_id='guard_subj' AND version=2")
        conn.commit()

        save_rule(conn, _RULE)
        # BOTH versions' rows are written (the preserved multi-version behavior)
        assert bind_rule(conn, "g1", "guard_subj", "sec") == 2
        assert load_subject_row_rules(conn, "guard_subj", 1)["sec"][0]["rule_id"] == "g1"
        assert load_subject_row_rules(conn, "guard_subj", 2)["sec"][0]["rule_id"] == "g1"
        # each version's distinct recipe survived the guard untouched
        assert _section_instr(conn, 1)["null_values"] == ["N/A", "-"]
        assert _section_instr(conn, 2)["null_values"] == ["ONLY_V2"]
    finally:
        conn.close()
