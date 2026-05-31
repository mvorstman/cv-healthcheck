"""ADR 0004 phase 8 step 2 — rules registry + reference-by-id.

Registry (DP1, `rules` table) + resolution-by-ref through the step-1 single
locus, with DP2 (registry-or-inline + no-silent-double-fire guard) and DP3
(flat global rule_id, PK-enforced collision). No layering — a ref-resolved rule
and an inline rule both evaluate as the single template_default layer, identical.
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from cvhealthcheck.db.migrations import run_migrations
from cvhealthcheck.db.rules import load_rules_registry
from cvhealthcheck.evaluative import engine
from cvhealthcheck.extractors.metric_section import build_metric_section


_INLINE_RULE = {
    "rule_id": "capacity_utilisation", "target": "utilisation_pct", "kind": "threshold",
    "comparison": ">=", "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
    "default_severity": "good", "mute_on_sentinel": True,
}
_REGISTRY = {
    "capacity_utilisation": {
        "rule_id": "capacity_utilisation", "kind": "threshold", "comparison": ">=",
        "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
        "default_severity": "good", "mute_on_sentinel": True,
    }
}
_REF_RULE = {"ref": "capacity_utilisation", "target": "utilisation_pct"}

_SPEC_INLINE = {
    "items": [{"id": "utilisation_pct", "label": "Utilisation", "unit": "%",
               "source": "field", "field": "util"}],
    "evaluative": {"rules": [_INLINE_RULE]},
}
_SPEC_REF = {
    "items": [{"id": "utilisation_pct", "label": "Utilisation", "unit": "%",
               "source": "field", "field": "util"}],
    "evaluative": {"rules": [_REF_RULE]},
}
_ROWS = [{"util": 95.0}]   # fires the critical band


# ── resolve_rule ──

def test_resolve_inline_passthrough():
    assert engine.resolve_rule(_INLINE_RULE, _REGISTRY) is _INLINE_RULE


def test_resolve_ref_merges_definition_and_binding():
    resolved = engine.resolve_rule(_REF_RULE, _REGISTRY)
    # registry body + the section's binding (target); byte-equal to the inline dict
    assert resolved == _INLINE_RULE


def test_resolve_ref_plus_inline_body_raises():
    bad = {"ref": "capacity_utilisation", "target": "x", "bands": [{"at": 1, "severity": "good"}]}
    with pytest.raises(ValueError, match="ambiguous"):
        engine.resolve_rule(bad, _REGISTRY)


def test_resolve_unknown_ref_raises():
    with pytest.raises(ValueError, match="not found in the rules registry"):
        engine.resolve_rule({"ref": "nope", "target": "x"}, _REGISTRY)


# ── build_metric_section: ref == inline (parity) ──

def test_ref_resolved_metric_equals_inline():
    inline = build_metric_section("s.m", "Cap", _SPEC_INLINE, _ROWS)
    ref = build_metric_section("s.m", "Cap", _SPEC_REF, _ROWS, _REGISTRY)
    assert inline.model_dump() == ref.model_dump()
    item = {i.id: i for i in ref.items}["utilisation_pct"]
    assert item.severity.value == "critical"
    assert item.verdict_chain[0].rule_id == "capacity_utilisation"
    assert item.verdict_chain[0].layer == "template_default"


# ── DP2 guard: inline + ref on the same target ──

def test_inline_and_ref_same_target_raises():
    spec = {
        "items": [{"id": "utilisation_pct", "label": "U", "unit": "%", "source": "field", "field": "util"}],
        "evaluative": {"rules": [_INLINE_RULE, _REF_RULE]},  # both target utilisation_pct
    }
    with pytest.raises(ValueError, match="both an inline rule and a registry ref"):
        build_metric_section("s.m", "Cap", spec, _ROWS, _REGISTRY)


# ── registry load + DP3 collision (PK) ──

def _migrated_db() -> Path:
    p = Path(tempfile.mkdtemp()) / "t.db"
    run_migrations(db_path=p)
    return p


def test_load_rules_registry_has_seeded_rule():
    p = _migrated_db()
    conn = sqlite3.connect(str(p)); conn.row_factory = sqlite3.Row
    try:
        reg = load_rules_registry(conn)
    finally:
        conn.close()
    assert "capacity_utilisation" in reg
    assert reg["capacity_utilisation"]["bands"][0] == {"at": 90, "severity": "critical"}


def test_duplicate_rule_id_rejected_by_pk():
    p = _migrated_db()
    conn = sqlite3.connect(str(p))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rules (rule_id, definition_json) VALUES ('capacity_utilisation', '{}')"
            )
    finally:
        conn.close()


def test_load_rules_registry_missing_table_returns_empty():
    # A DB without the rules table (pre-0018) → empty registry, not a crash.
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    try:
        assert load_rules_registry(conn) == {}
    finally:
        conn.close()
