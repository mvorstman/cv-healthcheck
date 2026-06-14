"""ADR-0015 D4a — rule ownership/classification axis (INERT).

Classifies rule definitions as `policy` (universal) vs `customer_assertion`
(customer/person-specific). Classification ONLY — no firing/binding/override
behavior change. Self-contained.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.rules import (
    RULE_CLASSES,
    bind_rule,
    delete_rule,
    list_rules,
    load_rules_registry,
    save_rule,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src/cvhealthcheck/db/migrations/0036_rule_ownership_axis.sql"
)
_STEP0_CUSTOMER_ASSERTIONS = (
    "clients_company1_warning",
    "clients_company2_critical",
    "michiel_account_enabled",
    "sg_naming_convention",
    "sg_rommelgroep_company_1",
    "users_michiel_enabled_critical",
)


def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_RULE = {
    "rule_id": "t_rule", "kind": "row_match", "scope": "row", "emit": "per_row",
    "severity": "warning", "title": "t", "message": "m",
    "conditions": [{"target": "x", "operator": "eq", "value": "1"}],
}


def _class_of(db, rule_id: str):
    row = db.execute("SELECT rule_class FROM rules WHERE rule_id = ?", (rule_id,)).fetchone()
    return row[0] if row else None


# ── vocabulary + schema ───────────────────────────────────────────────────────

def test_rule_classes_vocabulary():
    assert set(RULE_CLASSES) == {"policy", "customer_assertion"}


def test_new_rule_defaults_policy(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        save_rule(db, _RULE)  # no rule_class
        assert _class_of(db, "t_rule") == "policy"
    finally:
        db.close()


def test_seeded_capacity_utilisation_is_policy(migrated_db_path):
    # the only migration-seeded rule (0018), present in a fresh DB → policy
    db = _conn(migrated_db_path)
    try:
        assert _class_of(db, "capacity_utilisation") == "policy"
    finally:
        db.close()


def test_check_constraint_rejects_invalid_class(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO rules (rule_id, definition_json, rule_class) "
                "VALUES ('bad', '{}', 'not_a_class')"
            )
    finally:
        db.close()


# ── save_rule: explicit, default, preserve, validate ─────────────────────────

def test_save_rule_explicit_customer_assertion(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        save_rule(db, _RULE, rule_class="customer_assertion")
        assert _class_of(db, "t_rule") == "customer_assertion"
    finally:
        db.close()


def test_save_rule_preserves_class_on_resave(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        save_rule(db, _RULE, rule_class="customer_assertion")
        save_rule(db, {**_RULE, "severity": "critical"})  # re-save, no rule_class
        assert _class_of(db, "t_rule") == "customer_assertion"  # preserved, not reset
    finally:
        db.close()


def test_save_rule_rejects_invalid_class(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(ValueError):
            save_rule(db, _RULE, rule_class="bogus")
    finally:
        db.close()


# ── list_rules exposes the class; the body does NOT (inert / firing-safe) ─────

def test_list_rules_exposes_rule_class(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        save_rule(db, _RULE, rule_class="customer_assertion")
        items = {r["rule_id"]: r for r in list_rules(db)}
        assert items["t_rule"]["rule_class"] == "customer_assertion"
        assert items["capacity_utilisation"]["rule_class"] == "policy"
    finally:
        db.close()


def test_rule_class_not_in_definition_body(migrated_db_path):
    # rule_class is a COLUMN, never in definition_json → the evaluator never sees
    # it and firing is unaffected (the inert property).
    db = _conn(migrated_db_path)
    try:
        save_rule(db, _RULE, rule_class="customer_assertion")
        body = load_rules_registry(db)["t_rule"]
        assert "rule_class" not in body
    finally:
        db.close()


# ── back-compat: bind / delete unaffected ────────────────────────────────────

def test_save_rule_bind_and_delete_back_compat(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, {
            "subject_id": "d4a_subj", "version": 1, "title": "S", "description": "d",
            "category": "operations",
            "sections": [{"section_id": "sec", "title": "S", "section_type": "table",
                          "sort_order": 0}],
            "extraction_instructions": {"csv": {"extractable": True, "sections": {
                "sec": {"format": "single_table",
                        "column_map": [{"source": "X", "canonical": "x", "type": "string"}],
                        "output_as": "table"}}}},
        })
        save_rule(db, _RULE, rule_class="customer_assertion")
        assert bind_rule(db, "t_rule", "d4a_subj", "sec") == 1   # binding still works
        result = delete_rule(db, "t_rule")                        # delete still works
        assert result["existed"] is True
    finally:
        db.close()


# ── backfill matches Step 0 (static guard on the committed migration) ─────────

def test_migration_backfills_exactly_step0_customer_assertions():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "rule_class" in sql and "customer_assertion" in sql
    for rid in _STEP0_CUSTOMER_ASSERTIONS:
        assert rid in sql, f"backfill missing customer_assertion rule: {rid}"
