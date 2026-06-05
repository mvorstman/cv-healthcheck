"""ADR 0010 Phase 2 — catalog binding + the evaluate_subject dry-run.

Proves: a kind="row_match" registry rule bound to a table section resolves
(load_subject_row_rules), fires over the latest artifact without persisting
(evaluate_subject), and fires on a real collection through the extractor wiring.
No MCP yet (that's Phase 2b).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource, ArtifactSubject, ArtifactSummary, CanonicalArtifact,
    FindingsSection, TableColumn, TableSection,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.rules import load_subject_row_rules
from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.evaluative.subject_eval import evaluate_subject
from cvhealthcheck.extractors.command_center import CommandCenterExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

EMPTY_RULE = {
    "rule_id": "sg_empty", "kind": "row_match",
    "conditions": [{"target": "server_count", "operator": "eq", "value": 0}],
    "emit": "per_row", "severity": "warning",
    "title": "Empty server group: {row.name}", "message": "{row.name} has no servers.",
}


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_rule(conn: sqlite3.Connection, definition: dict) -> None:
    conn.execute(
        "INSERT INTO rules (rule_id, definition_json, created_by) VALUES (?, ?, 'ai')",
        (definition["rule_id"], json.dumps(definition)),
    )
    conn.commit()


def _proposal(subject_id="_rr_test", section_id="_rr_test.rows", row_rules=("sg_empty",)):
    return {
        "subject_id": subject_id, "version": 1, "title": "RR Test",
        "description": "row-rule binding test", "category": "operations",
        "sections": [{"section_id": section_id, "title": "Rows",
                      "section_type": "table", "sort_order": 0}],
        "extraction_instructions": {"rest_command_center_api": {
            "extractable": True, "endpoint": "/commandcenter/api/v4/servergroup",
            "sections": {section_id: {
                "output_as": "table",
                "table": {"root_key": "items", "columns": [
                    {"id": "id", "field": "id"}, {"id": "name", "field": "name"},
                    {"id": "server_count", "field": "server_count"}]},
                "evaluative": {"row_rules": [{"ref": ref} for ref in row_rules]},
            }},
        }},
    }


def _artifact(rows):
    return CanonicalArtifact(
        artifact_type="_rr_test", generated_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="_rr_test", title="RR Test"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[TableSection(
            type="table", id="_rr_test.rows", title="Rows",
            columns=[TableColumn(id="id", label="ID"), TableColumn(id="name", label="Name"),
                     TableColumn(id="server_count", label="SC")],
            items=rows)],
    )


# ── load_subject_row_rules ────────────────────────────────────────────────────

def test_load_subject_row_rules_resolves_binding(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _insert_rule(conn, EMPTY_RULE)
        create_subject_from_proposal(conn, _proposal())
        rr = load_subject_row_rules(conn, "_rr_test", 1)
        assert list(rr) == ["_rr_test.rows"]
        assert rr["_rr_test.rows"][0]["rule_id"] == "sg_empty"
        assert rr["_rr_test.rows"][0]["kind"] == "row_match"
    finally:
        conn.close()

def test_load_subject_row_rules_unknown_ref_raises(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        # bind a ref that is NOT in the registry → loud fail (authoring error)
        create_subject_from_proposal(conn, _proposal(row_rules=("does_not_exist",)))
        with pytest.raises(ValueError, match="not found in the rules registry"):
            load_subject_row_rules(conn, "_rr_test", 1)
    finally:
        conn.close()

def test_load_subject_row_rules_empty_when_no_binding(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        assert load_subject_row_rules(conn, "environment", 1) == {}
    finally:
        conn.close()


# ── evaluate_subject (dry-run) ────────────────────────────────────────────────

def test_evaluate_subject_fires_over_latest_artifact(migrated_db_path: Path, tmp_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _insert_rule(conn, EMPTY_RULE)
        create_subject_from_proposal(conn, _proposal())
        store = ArtifactStore("default", "default", base_dir=tmp_path / "art")
        # two empty rows share the name "dup" → must stay distinct by id (row_ref)
        store.save_artifact(_artifact([
            {"id": 1, "name": "ok", "server_count": 3},
            {"id": 2, "name": "dup", "server_count": 0},
            {"id": 3, "name": "dup", "server_count": 0},
        ]))
        res = evaluate_subject(conn, "_rr_test", store=store)
        assert res["has_artifact"] and res["rules_evaluated"] == 1 and res["count"] == 2
        assert {f["row_ref"] for f in res["findings"]} == {"2", "3"}   # ids, not "dup"
        assert {f["title"] for f in res["findings"]} == {"Empty server group: dup"}
        assert all(f["section_id"] == "_rr_test.rows" for f in res["findings"])
    finally:
        conn.close()

def test_evaluate_subject_no_artifact_is_empty_not_error(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _insert_rule(conn, EMPTY_RULE)
        create_subject_from_proposal(conn, _proposal())
        res = evaluate_subject(conn, "_rr_test",
                               store=ArtifactStore("default", "default", base_dir=Path("/nonexistent")))
        assert res["has_artifact"] is False and res["count"] == 0
    finally:
        conn.close()

def test_evaluate_subject_persists_nothing(migrated_db_path: Path, tmp_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _insert_rule(conn, EMPTY_RULE)
        create_subject_from_proposal(conn, _proposal())
        store = ArtifactStore("default", "default", base_dir=tmp_path / "art")
        store.save_artifact(_artifact([{"id": 2, "name": "x", "server_count": 0}]))
        latest = tmp_path / "art" / "default" / "default" / "working" / "_rr_test" / "latest.json"
        before = latest.read_bytes()
        evaluate_subject(conn, "_rr_test", store=store)
        assert latest.read_bytes() == before   # the stored artifact is untouched
    finally:
        conn.close()


# ── extractor wiring (rules fire on a real collection) ────────────────────────

def test_command_center_extractor_populates_and_fires_row_rules(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _insert_rule(conn, EMPTY_RULE)
        create_subject_from_proposal(conn, _proposal())
        payload = {"http_status": 200, "ok": True, "error": None,
                   "raw": {"items": [{"id": 1, "name": "a", "server_count": 0},
                                     {"id": 2, "name": "b", "server_count": 4}]}}
        ext = CommandCenterExtractor(conn, identity_provider=lambda: payload)
        result = ext.extract("_rr_test", 1)
    finally:
        conn.close()
    # the binding was resolved onto the result at collection
    assert result.section_row_rules.get("_rr_test.rows", [])[0]["rule_id"] == "sg_empty"
    # and the canonicalization pass baked a compliance finding into the artifact
    artifact = result_to_artifact(result, "_rr_test", "RR Test")
    comp = next(s for s in artifact.sections
                if isinstance(s, FindingsSection) and s.id == "_rr_test.compliance")
    assert [f.title for f in comp.items] == ["Empty server group: a"]
    assert comp.items[0].severity.value == "warning"


# ── regression: save_rule bind-write → evaluate_subject read MUST round-trip ──

def test_save_rule_bound_round_trip_fires_without_explicit_kind(migrated_db_path: Path, tmp_path: Path):
    """The bug Phase-2b shipped: a rule authored via save_rule WITHOUT an explicit
    `kind`, bound to a section that exists under MULTIPLE source types (so the bind
    fans → bound_sections>1), persisted + listed fine but was silently dropped by
    the evaluator's `kind == "row_match"` filter. This guards bind-write → eval-read
    end to end against exactly that shape (mirrors server_groups / rommelgroep)."""
    from cvhealthcheck.db.rules import bind_rule, save_rule, validate_row_match_rule

    conn = _conn(migrated_db_path)
    try:
        # a table section present under TWO source types (rest_command_center_api + json)
        create_subject_from_proposal(conn, {
            "subject_id": "_rt", "version": 1, "title": "RT", "description": "d",
            "category": "operations",
            "sections": [{"section_id": "_rt.rows", "title": "Rows",
                          "section_type": "table", "sort_order": 0}],
            "extraction_instructions": {
                "rest_command_center_api": {
                    "extractable": True, "endpoint": "/commandcenter/api/v4/servergroup",
                    "sections": {"_rt.rows": {"output_as": "table", "table": {"root_key": "items",
                        "columns": [{"id": "id", "field": "id"}, {"id": "name", "field": "name"},
                                    {"id": "association", "field": "association"}]}}}},
                "json": {"extractable": True, "sections": {"_rt.rows": {"output_as": "table",
                    "table": {"root_key": "items",
                              "columns": [{"id": "id"}, {"id": "name"}, {"id": "association"}]}}}},
            }})
        store = ArtifactStore("default", "default", base_dir=tmp_path / "art")
        store.save_artifact(CanonicalArtifact(
            artifact_type="_rt", generated_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
            source=ArtifactSource(type=SourceType.rest_commserve),
            subject=ArtifactSubject(id="_rt", title="RT"),
            summary=ArtifactSummary(status=ArtifactStatus.good),
            sections=[TableSection(type="table", id="_rt.rows", title="Rows",
                columns=[TableColumn(id="id", label="ID"), TableColumn(id="name", label="Name"),
                         TableColumn(id="association", label="Assoc")],
                items=[{"id": 19, "name": "rommelgroep", "association": "MANUAL"},
                       {"id": 41, "name": "rommelgroep", "association": "MANUAL"},
                       {"id": 7, "name": "GRP_x", "association": "MANUAL"},
                       {"id": 3, "name": "auto", "association": "AUTOMATIC"}])]))

        # authored WITHOUT a "kind" key — the exact trigger
        rule = {"rule_id": "naming",
                "conditions": [{"target": "association", "operator": "eq", "value": "MANUAL"},
                               {"target": "name", "operator": "not_contains", "value": "GRP_"}],
                "emit": "per_row", "severity": "warning",
                "title": "Naming: {row.name}", "message": "{row.name}"}
        assert "kind" not in rule
        validate_row_match_rule(conn, rule, bind={"subject_id": "_rt", "section_id": "_rt.rows"})
        save_rule(conn, rule)
        assert bind_rule(conn, "naming", "_rt", "_rt.rows") == 2   # fanned across both source variants

        res = evaluate_subject(conn, "_rt", store=store)
        fired = {f["row_ref"] for f in res["findings"] if f["rule_id"] == "naming"}
        assert fired == {"19", "41"}   # MANUAL non-GRP rows; GRP_x + AUTOMATIC excluded
    finally:
        conn.close()
