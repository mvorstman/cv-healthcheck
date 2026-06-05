"""ADR 0010 (engine slice) — section-level evaluation scope + per-row verdict.

Scope = a list of AND-ed conditions on the section's evaluative block. Rules run
only on in-scope rows; every row gets an explicit verdict
(not_evaluated / good / warning / critical). Verdict is baked at canonicalization
and previewed identically by evaluate_subject. Fixture-based; never reads app.db.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource, ArtifactSubject, ArtifactSummary, CanonicalArtifact,
    FindingsSection, TableColumn, TableSection,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.evaluative.row_match import evaluate_section_rows
from cvhealthcheck.evaluative.subject_eval import evaluate_subject
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

NOW = datetime(2026, 6, 3, tzinfo=timezone.utc)

ROWS = [
    {"id": 1, "name": "a", "association": "MANUAL",    "server_count": 0},  # in scope, empty → warning
    {"id": 2, "name": "b", "association": "MANUAL",    "server_count": 5},  # in scope, ok    → good
    {"id": 3, "name": "c", "association": "AUTOMATIC", "server_count": 0},  # out of scope    → not_evaluated
]
EMPTY = {"rule_id": "empty", "kind": "row_match",
         "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
         "emit": "per_row", "severity": "warning", "title": "Empty {row.name}", "message": "m"}
CRIT = {"rule_id": "crit", "kind": "row_match",
        "conditions": [{"target": "name", "operator": "eq", "value": "a"}],
        "emit": "per_row", "severity": "critical", "title": "Crit {row.name}", "message": "m"}
SCOPE_MANUAL = [{"target": "association", "operator": "eq", "value": "MANUAL"}]


def _rows():
    return [dict(r) for r in ROWS]   # fresh copies (the pass mutates row dicts)


# ── evaluate_section_rows (the engine) ────────────────────────────────────────

def test_scope_gates_rules_to_in_scope_rows():
    findings, _ = evaluate_section_rows([EMPTY], _rows(), scope=SCOPE_MANUAL, now=NOW)
    # id 3 is empty too, but AUTOMATIC → out of scope → NOT flagged
    assert {f["row_ref"] for f in findings} == {"1"}

def test_absent_scope_is_unchanged_all_rows_evaluated():
    findings, _ = evaluate_section_rows([EMPTY], _rows(), scope=None, now=NOW)
    assert {f["row_ref"] for f in findings} == {"1", "3"}    # both empty rows flagged

def test_per_row_verdicts_good_worst_not_evaluated():
    _, per_row = evaluate_section_rows([EMPTY], _rows(), scope=SCOPE_MANUAL, now=NOW)
    verdict = {pr["row_ref"]: pr["verdict"] for pr in per_row}
    in_scope = {pr["row_ref"]: pr["in_scope"] for pr in per_row}
    assert verdict == {"1": "warning", "2": "good", "3": "not_evaluated"}
    assert in_scope == {"1": True, "2": True, "3": False}

def test_verdict_is_worst_severity_among_a_rows_findings():
    _, per_row = evaluate_section_rows([EMPTY, CRIT], _rows(), scope=SCOPE_MANUAL, now=NOW)
    # row 1 fires both empty(warning) + crit(critical) → worst = critical
    assert {pr["row_ref"]: pr["verdict"] for pr in per_row}["1"] == "critical"

def test_multi_condition_scope_is_anded():
    scope = [{"target": "association", "operator": "eq", "value": "MANUAL"},
             {"target": "server_count", "operator": "gt", "value": 0}]
    findings, per_row = evaluate_section_rows([EMPTY], _rows(), scope=scope, now=NOW)
    assert findings == []   # only id 2 is in scope, and it is not empty
    assert {pr["row_ref"]: pr["verdict"] for pr in per_row} == \
        {"1": "not_evaluated", "2": "good", "3": "not_evaluated"}


# ── result_to_artifact bakes the verdict onto the rows ────────────────────────

def test_result_to_artifact_bakes_per_row_verdict():
    r = ExtractionResult(subject_id="sg", source_type="rest")
    r.sections["sg.rows"] = _rows()
    r.section_output_types["sg.rows"] = "table"
    r.section_titles["sg.rows"] = "Rows"
    r.section_row_rules["sg.rows"] = [EMPTY]
    r.section_scope["sg.rows"] = SCOPE_MANUAL
    art = result_to_artifact(r, "sg", "SG")

    table = next(s for s in art.sections if s.type == "table")
    assert {str(row["id"]): row["_verdict"] for row in table.items} == \
        {"1": "warning", "2": "good", "3": "not_evaluated"}
    # the out-of-scope empty group (id 3) produced NO finding
    comp = next(s for s in art.sections if isinstance(s, FindingsSection) and s.id == "sg.compliance")
    assert [f.category for f in comp.items] == ["sg.rows"] and len(comp.items) == 1


# ── evaluate_subject preview matches the baked verdicts ───────────────────────

def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON"); return conn

def _artifact():
    return CanonicalArtifact(
        artifact_type="sg", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="sg", title="SG"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[TableSection(type="table", id="sg.rows", title="Rows",
            columns=[TableColumn(id=c, label=c) for c in ("id", "name", "association", "server_count")],
            items=_rows())])

def test_evaluate_subject_row_verdicts_consistent_with_scope(migrated_db_path: Path, tmp_path: Path):
    conn = _conn(migrated_db_path)
    try:
        conn.execute("INSERT INTO rules (rule_id, definition_json, created_by) VALUES (?, ?, 'ai')",
                     ("empty", json.dumps(EMPTY)))
        conn.commit()
        create_subject_from_proposal(conn, {
            "subject_id": "sg", "version": 1, "title": "SG", "description": "d",
            "category": "operations",
            "sections": [{"section_id": "sg.rows", "title": "Rows", "section_type": "table", "sort_order": 0}],
            "extraction_instructions": {"rest_command_center_api": {
                "extractable": True, "endpoint": "/commandcenter/api/v4/servergroup",
                "sections": {"sg.rows": {
                    "output_as": "table",
                    "table": {"root_key": "items", "columns": [
                        {"id": "id", "field": "id"}, {"id": "name", "field": "name"},
                        {"id": "association", "field": "association"},
                        {"id": "server_count", "field": "server_count"}]},
                    "evaluative": {"scope": SCOPE_MANUAL, "row_rules": [{"ref": "empty"}]},
                }}}}})
        store = ArtifactStore("default", "default", base_dir=tmp_path / "art")
        store.save_artifact(_artifact())
        res = evaluate_subject(conn, "sg", store=store)
    finally:
        conn.close()
    assert {f["row_ref"] for f in res["findings"]} == {"1"}          # scope honoured end to end
    assert {pr["row_ref"]: pr["verdict"] for pr in res["row_verdicts"]} == \
        {"1": "warning", "2": "good", "3": "not_evaluated"}
