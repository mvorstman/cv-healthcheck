"""Evidence-context + verification-result foundation (pre-Fix-4).

PART 1: project_id completes the creation-context stamp on staged artifacts;
approval reads a stamped row's own (customer, project) as authority (coherence
check on the approver's context), with legacy NULL rows keeping D5 behaviour.

PART 2: ArtifactSource gains the verification-result home (status/sources/
notes/verified_at) — nothing populates it yet (Fix 4 does); this only creates
the home and proves it round-trips.

This slice is an inert enabler: NO declared-vs-wire check, NO approval
authority flip, NO D5 weakening.
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _mk_artifact(subject_id: str = "storage_policies"):
    res = ExtractionResult(subject_id=subject_id, source_type="csv")
    res.sections["rows"] = [{"col": "v"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    return result_to_artifact(res, subject_id=subject_id, subject_title=subject_id)


# ── PART 1 (commit 1): project_id stamped on new artifact rows ────────────────

def _seed_ai_subject(db: sqlite3.Connection, subject_id: str) -> None:
    from cvhealthcheck.db.subjects import create_subject_from_proposal
    create_subject_from_proposal(db, {
        "subject_id": subject_id, "version": 1, "title": subject_id,
        "description": "", "category": "operations",
        "sections": [{"section_id": "s", "title": "S", "section_type": "table",
                      "default_selected": True, "sort_order": 0}],
        "extraction_instructions": {"html": {"extractable": True, "sections": {"s": {}}}},
    })


def test_web_stage_import_stamps_customer_and_project(monkeypatch, migrated_db_path):
    from cvhealthcheck.extractors.dispatcher import DispatchResult
    from cvhealthcheck.extractors.recognition import RecognitionResult
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    def open_db():
        return _conn(migrated_db_path)
    monkeypatch.setattr(route_module, "get_db", open_db)

    db = open_db()
    _seed_ai_subject(db, "_ev_stage")
    db.execute(
        "INSERT INTO customers (customer_id, customer_name, created_at, updated_at)"
        " VALUES ('ev_cust', 'Ev', '2026-01-01', '2026-01-01')"
    )
    db.execute(
        "INSERT INTO projects (project_id, customer_id, project_number)"
        " VALUES ('ev_proj', 'ev_cust', 'P-1')"
    )
    db.commit()
    db.close()

    rec = RecognitionResult(subject_id="_ev_stage", version=1, source_type="html",
                            extractable=True, non_extractable_reason=None, title="t")
    monkeypatch.setattr(
        route_module, "extract_file",
        lambda *a, **k: DispatchResult(
            recognized=True, subject_id="_ev_stage", version=1, source_type="html",
            extractable=True, non_extractable_reason=None,
            artifact=_mk_artifact("_ev_stage"), recognition_result=rec,
        ),
    )
    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "ev_cust", "project_id": "ev_proj"}
    resp = client.post(
        "/quick-hc/_ev_stage/import?stage=1",
        data={"file": (io.BytesIO(b"<html></html>"), "x.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert resp.status_code == 200, resp.get_json()

    db = open_db()
    row = db.execute(
        "SELECT customer_id, project_id, artifact_type FROM staged_artifacts"
        " ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    db.close()
    assert row["artifact_type"] != "subject_proposal"
    assert row["customer_id"] == "ev_cust"
    assert row["project_id"] == "ev_proj"


def test_subject_proposal_stays_catalog_global_null(monkeypatch, migrated_db_path):
    """A subject_proposal carries no customer/project — catalog-global by design."""
    import cvhealthcheck.mcp.server as mcp
    monkeypatch.setattr(mcp, "get_db", lambda: _conn(migrated_db_path))
    result = mcp.propose_new_subject(
        subject_id="_ev_prop", version=1, title="P", description="",
        category="operations",
        sections=[{"section_id": "s", "title": "S", "section_type": "table",
                   "default_selected": True, "sort_order": 0}],
        extraction_instructions={"html": {"extractable": True, "sections": {"s": {}}}},
        ai_notes="",
    )
    db = _conn(migrated_db_path)
    row = db.execute(
        "SELECT artifact_type, customer_id, project_id FROM staged_artifacts"
        " WHERE stage_id = ?", (result["stage_id"],),
    ).fetchone()
    db.close()
    assert row["artifact_type"] == "subject_proposal"
    assert row["customer_id"] is None
    assert row["project_id"] is None
