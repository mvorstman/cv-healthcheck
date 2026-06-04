"""Transpose / property-table materialization: one object -> N rows of
{id, key, label, value}, one per declared field. Additive branch in
`_project_table_rows`; reuses the existing row-scope engine + columns render —
NO engine change. Fixture-based; never reads app.db.
"""
from __future__ import annotations

from cvhealthcheck.evaluative.row_match import evaluate_section_rows
from cvhealthcheck.extractors.command_center import _project_table_rows
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

# a single object (the commserve_software_cache shape), heterogeneous field types
OBJ = {"commserveSoftwareCache": {
    "cacheFreeSpace": 46284349440,
    "UaInfo": {"uaPackageCacheStatus": "OK", "inSyncWithCSLevelCache": False}}}
TRANSPOSE = [
    {"key": "free_space",       "label": "Free space",                  "field": "cacheFreeSpace"},
    {"key": "ua_package_cache", "label": "UA package cache",            "field": "UaInfo.uaPackageCacheStatus"},
    {"key": "in_sync",          "label": "In sync with CS-level cache",  "field": "UaInfo.inSyncWithCSLevelCache"},
]
SPEC = {"root_key": "commserveSoftwareCache", "transpose": TRANSPOSE,
        "columns": [{"id": "label", "label": "Setting"}, {"id": "value", "label": "Value"}]}


# ── CHANGE 1: object -> N rows ────────────────────────────────────────────────

def test_transpose_explodes_object_into_n_rows_typed():
    rows = _project_table_rows(OBJ, SPEC)
    assert [r["key"] for r in rows] == ["free_space", "ua_package_cache", "in_sync"]
    assert all(r["id"] == r["key"] for r in rows)            # id mirrors key (stable ref)
    assert rows[0] == {"id": "free_space", "key": "free_space",
                       "label": "Free space", "value": 46284349440}
    # value types preserved: int / str / bool (nested field paths resolve)
    assert isinstance(rows[0]["value"], int) and rows[0]["value"] == 46284349440
    assert rows[1]["value"] == "OK"
    assert rows[2]["value"] is False

def test_transpose_label_defaults_to_key_and_skips_incomplete_entries():
    spec = {"root_key": "x", "transpose": [{"key": "a", "field": "a"}, {"key": "b"}, {"field": "c"}]}
    rows = _project_table_rows({"x": {"a": 1}}, spec)
    assert rows == [{"id": "a", "key": "a", "label": "a", "value": 1}]   # label->key; b & c skipped

def test_transpose_over_raw_when_no_root_key():
    spec = {"transpose": [{"key": "a", "label": "A", "field": "a"}]}
    assert _project_table_rows({"a": 5}, spec) == [{"id": "a", "key": "a", "label": "A", "value": 5}]


# ── regression: dict-wrap (object -> 1 row) unchanged without a transpose key ──

def test_no_transpose_dict_wrap_unchanged():
    spec = {"root_key": "auditTrailInfo",
            "columns": [{"id": "retention_critical", "field": "retention_critical"}]}
    rows = _project_table_rows({"auditTrailInfo": {"retention_critical": 365}}, spec)
    assert rows == [{"retention_critical": 365}]             # still object -> 1 row


# ── CHANGE 2 + engine reuse, end to end through result_to_artifact ────────────

def _result(rules=None):
    r = ExtractionResult(subject_id="csc", source_type="rest")
    r.sections["cfg"] = _project_table_rows(OBJ, SPEC)
    r.section_output_types["cfg"] = "table"
    r.section_titles["cfg"] = "Cache Configuration"
    r.section_table_specs["cfg"] = SPEC
    if rules:
        r.section_row_rules["cfg"] = rules
    return r

def test_declared_columns_restrict_display_id_key_stay_on_items():
    tbl = next(s for s in result_to_artifact(_result(), "csc", "CSC").sections if s.type == "table")
    assert [c.id for c in tbl.columns] == ["label", "value"]         # id/key NOT displayed
    assert [c.label for c in tbl.columns] == ["Setting", "Value"]
    assert tbl.items[0]["id"] == "free_space" and tbl.items[0]["key"] == "free_space"  # still on the row

IN_SYNC_RULE = {
    "rule_id": "csc_in_sync_false", "kind": "row_match", "scope": "row", "emit": "per_row",
    "severity": "warning", "title": "Cache out of sync", "message": "m",
    "conditions": [{"target": "key", "operator": "eq", "value": "in_sync"},
                   {"target": "value", "operator": "eq", "value": False}],
}

def test_row_rule_on_key_value_gives_per_row_verdict_no_engine_change():
    rows = _project_table_rows(OBJ, SPEC)
    findings, per_row = evaluate_section_rows([IN_SYNC_RULE], rows)
    # row_ref == the stable id (= setting key); only the in_sync row flags
    assert {pr["row_ref"]: pr["verdict"] for pr in per_row} == \
        {"free_space": "good", "ua_package_cache": "good", "in_sync": "warning"}
    assert [f["row_ref"] for f in findings] == ["in_sync"]

def test_transpose_verdict_bakes_per_row_end_to_end():
    tbl = next(s for s in result_to_artifact(_result(rules=[IN_SYNC_RULE]), "csc", "CSC").sections
               if s.type == "table")
    assert {r["key"]: r["_verdict"] for r in tbl.items} == \
        {"free_space": "good", "ua_package_cache": "good", "in_sync": "warning"}
