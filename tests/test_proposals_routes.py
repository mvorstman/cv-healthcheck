"""ADR 0009 Phase 1 — consolidated /quick-hc Staging zone.

Covers the two NEW proposal endpoints (/quick-hc/proposals/<id>/approve|reject)
and the server-side shell-builder. The old /quick-hc/staging route is untouched
(its coverage stays in test_staging_routes.py). The shared approval path
(execute_approval / reject_staged_artifact) is reused, not modified.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.quickhc.subject_data_service import (
    _build_staging_shells,
    build_proposal_shell,
)
from cvhealthcheck.web.app import create_app


def _proposal(subject_id: str = "phase1_demo") -> dict[str, Any]:
    section_id = f"{subject_id}.rows"
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": "Phase 1 Demo",
        "description": "Shell demo (throwaway).",
        "category": "operations",
        "sections": [
            {"section_id": section_id, "title": "Rows", "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {
            "rest_command_center_api": {
                "extractable": True,
                "endpoint": "/commandcenter/api/v4/servergroup",
                "sections": {
                    section_id: {
                        "output_as": "table",
                        "table": {"root_key": "items",
                                  "columns": [{"id": "name", "label": "Name"},
                                              {"id": "count", "label": "Count"}]},
                    },
                },
            },
        },
    }


def _insert_proposal(db_path: Path, stage_id: str, *, status: str = "pending",
                     subject_id: str = "phase1_demo") -> str:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        INSERT INTO staged_artifacts
            (stage_id, subject_id, artifact_type, subject_version,
             source_type, status, artifact_json, ai_notes, created_at)
        VALUES (?, ?, 'subject_proposal', 1, 'ai', ?, ?, 'test',
                strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        """,
        (stage_id, subject_id, status, json.dumps(_proposal(subject_id))),
    )
    conn.commit()
    conn.close()
    return stage_id


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    def open_db() -> sqlite3.Connection:
        return _conn(migrated_db_path)

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c


# ── the new endpoints ─────────────────────────────────────────────────────────

def test_approve_proposal_promotes_into_catalog_and_redirects(client, migrated_db_path: Path):
    stage_id = _insert_proposal(migrated_db_path, "stage-approve-1")
    resp = client.post(f"/quick-hc/proposals/{stage_id}/approve")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/quick-hc")

    conn = _conn(migrated_db_path)
    try:
        subj = conn.execute(
            "SELECT status FROM subjects WHERE subject_id = 'phase1_demo'"
        ).fetchone()
        staged = conn.execute(
            "SELECT status FROM staged_artifacts WHERE stage_id = ?", (stage_id,)
        ).fetchone()
    finally:
        conn.close()
    assert subj is not None and subj["status"] == "active"   # promoted
    assert staged["status"] == "approved"                     # flipped


def test_reject_proposal_marks_rejected_and_redirects(client, migrated_db_path: Path):
    stage_id = _insert_proposal(migrated_db_path, "stage-reject-1")
    resp = client.post(f"/quick-hc/proposals/{stage_id}/reject")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/quick-hc")

    conn = _conn(migrated_db_path)
    try:
        staged = conn.execute(
            "SELECT status FROM staged_artifacts WHERE stage_id = ?", (stage_id,)
        ).fetchone()
        subj = conn.execute(
            "SELECT 1 FROM subjects WHERE subject_id = 'phase1_demo'"
        ).fetchone()
    finally:
        conn.close()
    assert staged["status"] == "rejected"
    assert subj is None                                       # reject never promotes


def test_approve_already_approved_proposal_flashes_not_pending(client, migrated_db_path: Path):
    stage_id = _insert_proposal(migrated_db_path, "stage-dbl-1")
    client.post(f"/quick-hc/proposals/{stage_id}/approve")
    resp = client.post(f"/quick-hc/proposals/{stage_id}/approve", follow_redirects=True)
    assert resp.status_code == 200
    assert "artifact is not pending" in resp.get_data(as_text=True)


def test_quick_hc_page_lists_pending_proposal_in_staging(client, migrated_db_path: Path):
    _insert_proposal(migrated_db_path, "stage-list-1")
    body = client.get("/quick-hc").get_data(as_text=True)
    # initial_data (incl. the staging shell) is serialized into the page.
    assert "stage-list-1" in body
    assert "Phase 1 Demo" in body
    assert "is_proposal" in body


# ── shell-builder (pure) ───────────────────────────────────────────────────────

def test_build_proposal_shell_table_shell_has_columns_and_no_rows():
    shell = build_proposal_shell(_proposal(), stage_id="s1")
    assert shell["is_proposal"] is True
    assert shell["status"] == "pending"
    assert shell["stage_id"] == "s1"
    assert shell["state"] == "nodata"
    sec = next(s for s in shell["sections"] if s["type"] == "table")
    assert sec["columns"] == ["Name", "Count"]   # header survives with no rows
    assert sec["rows"] == []
    assert sec["empty_message"] == "No data collected"


def test_build_proposal_shell_degrades_gracefully_on_garbage_section():
    proposal = _proposal()
    proposal["sections"] = [{"section_id": "x", "title": "X", "section_type": "table"}]
    proposal["extraction_instructions"] = {"rest": {"sections": {"x": "not-a-dict"}}}
    shell = build_proposal_shell(proposal, stage_id="s2")
    sec = next(s for s in shell["sections"] if s["id"].endswith("x"))
    assert sec["type"] == "table"
    assert sec["rows"] == []


def test_build_proposal_shell_returns_none_without_subject_id():
    assert build_proposal_shell({"title": "no id"}, stage_id="s3") is None


# ── staging filter (pending subject_proposal only) ─────────────────────────────

def test_build_staging_shells_includes_only_pending_proposals(migrated_db_path: Path):
    _insert_proposal(migrated_db_path, "stg-pending", status="pending", subject_id="phase1_demo")
    _insert_proposal(migrated_db_path, "stg-approved", status="approved", subject_id="other_demo")
    # a pending ARTIFACT-type row must be excluded by the filter.
    conn = _conn(migrated_db_path)
    conn.execute(
        "INSERT INTO staged_artifacts (stage_id, subject_id, artifact_type, status,"
        " artifact_json, created_at) VALUES (?, ?, 'artifact', 'pending', '{}',"
        " strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
        ("stg-artifact", "security_assessment"),
    )
    conn.commit()
    try:
        shells = _build_staging_shells(conn)
    finally:
        conn.close()
    stage_ids = {s["stage_id"] for s in shells}
    assert stage_ids == {"stg-pending"}
