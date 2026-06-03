"""ADR 0010 (slice 3) — authored rule `description` + Option-B criteria render.

The criteria card's per-check primary line is the rule's AUTHORED `description`
(falling back to the static text of its `title`, NEVER the raw rule id); the
condition line is a MECHANICAL render of the rule's conditions (one tested place,
not inference). The interim prose deriver is retired. Fixture-based; never reads
data/app.db.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource, ArtifactSubject, ArtifactSummary, CanonicalArtifact,
    TableColumn, TableSection,
)
from cvhealthcheck.evaluative.row_match import format_conditions
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc import canonical_view
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

NOW = datetime(2026, 6, 3, tzinfo=timezone.utc)


# ── the mechanical condition formatter ────────────────────────────────────────

def test_formatter_one_case_per_operator():
    def fmt(op, **kw):
        return format_conditions([{"target": "x", "operator": op, **kw}])
    assert fmt("eq", value=0) == "x = 0"
    assert fmt("ne", value=0) == "x ≠ 0"
    assert fmt("gt", value=0) == "x > 0"
    assert fmt("gte", value=0) == "x ≥ 0"
    assert fmt("lt", value=0) == "x < 0"
    assert fmt("lte", value=0) == "x ≤ 0"
    assert fmt("contains", value="GRP_") == 'x contains "GRP_"'
    assert fmt("not_contains", value="GRP_") == 'x not contains "GRP_"'
    assert fmt("between", value=1, value2=10) == "x between 1 and 10"   # value2 rendered
    assert fmt("exists") == "x is set"
    assert fmt("not_exists") == "x is not set"
    assert fmt("stale_days", value=365) == "x older than 365 days"      # n rendered

def test_formatter_quotes_strings_bares_numbers_and_refs():
    assert format_conditions([{"target": "name", "operator": "eq", "value": "rommelgroep"}]) \
        == 'name = "rommelgroep"'
    assert format_conditions([{"target": "server_count", "operator": "eq", "value": 0}]) \
        == "server_count = 0"
    # a field-to-field {ref} renders as the bare column name, not a quoted string
    assert format_conditions([{"target": "used", "operator": "gt", "value": {"ref": "available"}}]) \
        == "used > available"

def test_formatter_ands_multiple_conditions():
    assert format_conditions([
        {"target": "name", "operator": "eq", "value": "rommelgroep"},
        {"target": "company", "operator": "eq", "value": "Company_1"},
    ]) == 'name = "rommelgroep" and company = "Company_1"'

def test_formatter_empty_is_blank():
    assert format_conditions([]) == "" and format_conditions(None) == ""


# ── the bake carries description, title, condition_text ───────────────────────

_RULE = {
    "rule_id": "sg_empty_group", "kind": "row_match",
    "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
    "emit": "per_row", "severity": "warning",
    "title": "Empty server group: {row.name}", "message": "m",
    "description": "Every server group must contain at least one server.",
}


def test_bake_check_carries_description_title_condition_text():
    r = ExtractionResult(subject_id="sg", source_type="rest")
    r.sections["sg.rows"] = [{"id": 1, "name": "a", "server_count": 0}]
    r.section_output_types["sg.rows"] = "table"
    r.section_titles["sg.rows"] = "Rows"
    r.section_row_rules["sg.rows"] = [_RULE]
    art = result_to_artifact(r, "sg", "SG")
    check = art.metadata["evaluation"]["sg.rows"]["checks"][0]
    assert check == {
        "rule_id": "sg_empty_group", "severity": "warning",
        "description": "Every server group must contain at least one server.",
        "title": "Empty server group: {row.name}", "condition_text": "server_count = 0",
    }

def test_bake_check_description_absent_is_null():
    r = ExtractionResult(subject_id="sg", source_type="rest")
    r.sections["sg.rows"] = [{"id": 1, "name": "a", "server_count": 0}]
    r.section_output_types["sg.rows"] = "table"
    r.section_titles["sg.rows"] = "Rows"
    r.section_row_rules["sg.rows"] = [{k: v for k, v in _RULE.items() if k != "description"}]
    art = result_to_artifact(r, "sg", "SG")
    assert art.metadata["evaluation"]["sg.rows"]["checks"][0]["description"] is None


# ── the render contract (the reported-bug regression guard) ───────────────────

def _criteria_checks(checks):
    art = CanonicalArtifact(
        artifact_type="sg", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="sg", title="SG"),
        summary=ArtifactSummary(status=ArtifactStatus.warning),
        sections=[TableSection(type="table", id="sg.rows", title="Rows",
            columns=[TableColumn(id="id", label="ID")], items=[{"id": 1}])],
        metadata={"evaluation": {"sg.rows": {"scope": [], "checks": checks}}})
    crit = next(s for s in artifact_to_view(art)["sections"] if s["type"] == "criteria")
    return crit["checks"]

def test_primary_is_description_when_present():
    checks = _criteria_checks([{"rule_id": "sg_empty_group", "severity": "warning",
        "description": "Every server group must contain at least one server.",
        "title": "Empty: {row.name}", "condition_text": "server_count = 0"}])
    assert checks == [{"sev": "warn",
        "primary": "Every server group must contain at least one server.",
        "condition": "server_count = 0"}]

def test_primary_falls_back_to_static_title_when_no_description():
    checks = _criteria_checks([{"rule_id": "sg_naming_convention", "severity": "warning",
        "description": None, "title": "Group {row.name} breaks the GRP_ convention",
        "condition_text": 'name not contains "GRP_"'}])
    # the {row.name} placeholder is stripped to leave clean static text
    assert checks[0]["primary"] == "Group breaks the GRP_ convention"

def test_raw_rule_id_is_never_the_primary_line():
    # description absent AND title absent → a generic fallback, NEVER the rule id
    checks = _criteria_checks([{"rule_id": "sg_some_internal_id", "severity": "critical",
        "description": None, "title": None, "condition_text": "x = 1"}])
    assert checks[0]["primary"] == "Check"
    assert "sg_some_internal_id" not in checks[0]["primary"]


# ── the interim prose deriver is retired (assert the new path, not the mapping)─

def test_interim_prose_deriver_removed():
    assert not hasattr(canonical_view, "_RULE_SENTENCE")
    assert not hasattr(canonical_view, "_rule_sentence")
    # the static-title helper is the replacement path
    assert canonical_view._title_static("Empty: {row.name}") == "Empty"


# ── save_rule persists/returns/surfaces description; absent ⇒ null ────────────

def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON"); return conn

@pytest.fixture()
def server(monkeypatch, migrated_db_path: Path):
    import cvhealthcheck.mcp.server as srv
    monkeypatch.setattr(srv, "get_db", lambda: _conn(migrated_db_path))
    return srv

_AUTHORED = {
    "rule_id": "r_desc",
    "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
    "emit": "per_row", "severity": "warning", "title": "t", "message": "m",
    "description": "Every server group must contain at least one server.",
}

def test_save_rule_persists_returns_and_lists_description(server):
    out = server.save_rule(_AUTHORED)
    assert out["rule"]["description"] == "Every server group must contain at least one server."
    listed = {r["rule_id"]: r for r in server.list_rules()}
    assert listed["r_desc"]["description"] == "Every server group must contain at least one server."

def test_save_rule_absent_description_is_null(server):
    server.save_rule({k: v for k, v in _AUTHORED.items() if k != "description"} | {"rule_id": "r_nodesc"})
    listed = {r["rule_id"]: r for r in server.list_rules()}
    assert listed["r_nodesc"].get("description") is None       # absent ⇒ null, valid
