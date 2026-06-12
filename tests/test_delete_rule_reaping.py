"""Regression: delete_subject reaps rules its deletion orphaned.

The gap: delete_subject cascaded catalog rows, staging rows, and (via the MCP
wrapper) the stored artifact — but never the rules registry, so a rule whose
ONLY binding was the deleted subject's sections survived as inert residue
(12 such csc_*/ccprop_* rules found dangling on 2026-06-12).

Reap semantics (scoped, deliberately): only rules referenced by the deleted
subject's own bindings are candidates; a candidate is reaped iff it now has
zero bindings across ALL subjects AND zero rule_overrides rows. A rule
authored elsewhere but not yet bound is never touched.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from cvhealthcheck.db.rules import bind_rule, save_rule
from cvhealthcheck.db.subjects import create_subject_from_proposal, delete_subject


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _proposal(subject_id: str) -> dict:
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": subject_id,
        "description": "reaping fixture",
        "category": "operations",
        "sections": [
            {"section_id": "rows", "title": "Rows", "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {
            "html": {"extractable": True, "sections": {"rows": {"output_as": "table"}}},
        },
    }


def _rule(rule_id: str) -> dict:
    return {
        "rule_id": rule_id,
        "kind": "row_match",
        "scope": "row",
        "emit": "per_row",
        "severity": "warning",
        "conditions": [{"operator": "eq", "target": "key", "value": "x"}],
    }


def _registry_has(db: sqlite3.Connection, rule_id: str) -> bool:
    return db.execute(
        "SELECT 1 FROM rules WHERE rule_id = ?", (rule_id,)
    ).fetchone() is not None


def test_rule_bound_only_to_deleted_subject_is_reaped(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _proposal("_reap_a"))
        save_rule(db, _rule("_reap_a_rule"))
        assert bind_rule(db, "_reap_a_rule", "_reap_a", "rows") == 1

        result = delete_subject(db, "_reap_a")

        assert result["rules_reaped"] == ["_reap_a_rule"]
        assert not _registry_has(db, "_reap_a_rule")
    finally:
        db.close()


def test_rule_also_bound_to_surviving_subject_survives(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _proposal("_reap_b1"))
        create_subject_from_proposal(db, _proposal("_reap_b2"))
        save_rule(db, _rule("_reap_shared_rule"))
        assert bind_rule(db, "_reap_shared_rule", "_reap_b1", "rows") == 1
        assert bind_rule(db, "_reap_shared_rule", "_reap_b2", "rows") == 1

        result = delete_subject(db, "_reap_b1")

        assert result["rules_reaped"] == []
        assert _registry_has(db, "_reap_shared_rule")
        # ... and deleting the last binder DOES reap it (the scoped semantics
        # converge to full cleanup once no binder survives).
        result2 = delete_subject(db, "_reap_b2")
        assert result2["rules_reaped"] == ["_reap_shared_rule"]
        assert not _registry_has(db, "_reap_shared_rule")
    finally:
        db.close()


def test_orphaned_rule_with_override_is_not_reaped(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _proposal("_reap_c"))
        save_rule(db, _rule("_reap_overridden_rule"))
        assert bind_rule(db, "_reap_overridden_rule", "_reap_c", "rows") == 1
        # a customer-wide standing waiver on the rule (project_id NULL)
        db.execute(
            "INSERT INTO rule_overrides"
            " (customer_id, project_id, subject_id, subject_version, section_id,"
            "  rule_id, severity, reason)"
            " VALUES ('default', NULL, '_reap_c', 1, 'rows',"
            "         '_reap_overridden_rule', 'muted', 'audit waiver')",
        )
        db.commit()

        result = delete_subject(db, "_reap_c")

        assert result["rules_reaped"] == []
        assert _registry_has(db, "_reap_overridden_rule")
    finally:
        db.close()


def test_unbound_rule_elsewhere_is_never_touched(migrated_db_path: Path):
    """An authored-but-not-yet-bound rule is not a candidate — deleting an
    unrelated subject must not sweep it (the scoped-candidates guarantee)."""
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _proposal("_reap_d"))
        save_rule(db, _rule("_reap_unbound_rule"))   # authored, never bound

        result = delete_subject(db, "_reap_d")

        assert result["rules_reaped"] == []
        assert _registry_has(db, "_reap_unbound_rule")
    finally:
        db.close()
