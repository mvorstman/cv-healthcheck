"""Context Integrity — READ-side enforcement (the D5 complement).

A no-context web read must not silently render the Default customer's scoped
artifacts; it returns an honest "no active context" state. Two-customer
cross-isolation already PASSED (2026-06-14 audit); this pins the no-context →
Default display hazard closed. Self-contained; the conftest isolates the artifact
store under tmp.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from flask import session

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.web.active_project import (
    NoExplicitContextError,
    get_active_customer,
    get_active_project,
    make_active_project_store,
    resolve_default_project,
)
from cvhealthcheck.web.app import create_app


def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _artifact(subject_id: str):
    res = ExtractionResult(subject_id=subject_id, source_type="csv")
    res.sections["rows"] = [{"col": "value"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    return result_to_artifact(res, subject_id=subject_id, subject_title=subject_id)


def _subjects_by_id(data: dict) -> dict[str, dict]:
    return {s["id"]: s for cat in data["cats"] for s in cat["subjects"]}


# ── resolver: no-fallback raises; explicit opt-in still falls back ────────────

def test_get_active_project_no_fallback_raises_outside_context(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(NoExplicitContextError):
            get_active_project(db, allow_default=False)
        # explicit opt-in (CLI/tests/MCP) still resolves the Default project
        assert get_active_project(db, allow_default=True) == resolve_default_project(db)
    finally:
        db.close()


def test_get_active_customer_no_fallback_raises_outside_context(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(NoExplicitContextError):
            get_active_customer(db, allow_default=False)
    finally:
        db.close()


def test_make_active_project_store_no_fallback_raises_outside_context(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(NoExplicitContextError):
            make_active_project_store(db, allow_default=False)
    finally:
        db.close()


# ── workspace: no-context does NOT surface Default; explicit selection does ───

def test_default_artifact_not_rendered_without_explicit_context(migrated_db_path):
    """The bounded no-context → Default hazard, now closed: a Default-customer
    artifact exists, but with no explicit selection the workspace renders the
    honest not-collected state, NOT Default's data."""
    db = _conn(migrated_db_path)
    try:
        cust, proj = resolve_default_project(db)
        ArtifactStore(cust, proj).save_artifact(_artifact("capacity_license"))
        # build_subject_initial_data runs OUTSIDE a request context here → no
        # explicit selection → must not fall back to Default.
        subjects = _subjects_by_id(build_subject_initial_data(db))
        assert subjects["capacity_license"]["state"] == "nodata"
    finally:
        db.close()


def test_explicit_selection_renders_only_that_customers_store(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        ArtifactStore("cust_b", "proj_b").save_artifact(_artifact("capacity_license"))
        app = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test"
        # cust_b explicitly selected → sees its own data
        with app.test_request_context():
            session["active_project"] = {"customer_id": "cust_b", "project_id": "proj_b"}
            subjects = _subjects_by_id(build_subject_initial_data(db))
            assert subjects["capacity_license"]["state"] != "nodata"
        # a DIFFERENT customer selected → does NOT see cust_b's data (no leak)
        with app.test_request_context():
            session["active_project"] = {"customer_id": "cust_a", "project_id": "proj_a"}
            subjects = _subjects_by_id(build_subject_initial_data(db))
            assert subjects["capacity_license"]["state"] == "nodata"
    finally:
        db.close()


# ── canonical API: no session → structured no-active-context 200 (not 404) ────

@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c


def test_canonical_api_no_session_returns_structured_no_context_200(client):
    for path in ("/api/license-summary/canonical", "/api/security-assessment/canonical"):
        resp = client.get(path)
        assert resp.status_code == 200, path  # "nothing selected" is a normal state
        body = resp.get_json()
        assert body.get("active_context") is False, path
        assert body.get("artifact") is None, path
