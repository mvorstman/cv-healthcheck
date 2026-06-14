"""Fix 2 — the scoped canonical store is the ONLY workspace data source.

Regression for the "new project shows old data" isolation leak (2026-06-12
audit): with an empty scoped store, the six system subjects used to fall
through to legacy loaders reading GLOBAL unscoped files and render another
customer's last collection. Now: empty store -> honest not-collected state;
data renders only for the project whose store holds it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import session

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.web.active_project import resolve_default_project
from cvhealthcheck.web.app import create_app


def _initial_data_as(db, customer_id: str, project_id: str) -> dict:
    """build_subject_initial_data under an EXPLICIT active context. Context
    Integrity read-side (2026-06-14): the workspace no longer falls back to the
    Default project for reads, so rendering a project's scoped artifact requires
    that project to be explicitly selected — exactly what these tests assert."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_request_context():
        session["active_project"] = {"customer_id": customer_id, "project_id": project_id}
        return build_subject_initial_data(db, customer_id=customer_id)

LEGACY_SIX = [
    "environment",
    "security_assessment",
    "license_summary",
    "client_growth",
    "capacity_license",
    "backup_job_summary",
]


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _subjects_by_id(data: dict) -> dict[str, dict]:
    return {s["id"]: s for cat in data["cats"] for s in cat["subjects"]}


def _artifact(subject_id: str):
    res = ExtractionResult(subject_id=subject_id, source_type="csv")
    res.sections["rows"] = [{"col": "value"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    return result_to_artifact(res, subject_id=subject_id, subject_title=subject_id)


def test_empty_store_renders_all_legacy_subjects_not_collected(migrated_db_path):
    """The heart of Fix 2: no scoped artifact -> 'nodata', NEVER legacy global
    data (the global files may well exist on disk; they must not be read)."""
    db = _conn(migrated_db_path)
    try:
        subjects = _subjects_by_id(build_subject_initial_data(db))
        for sid in LEGACY_SIX:
            assert subjects[sid]["state"] == "nodata", sid
            assert subjects[sid]["sections"] == [], sid
            assert subjects[sid]["subtitle"] == "Not collected", sid
    finally:
        db.close()


def test_artifact_in_another_projects_store_does_not_leak(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        # data exists, but for a DIFFERENT (customer, project) store
        ArtifactStore("other_customer", "other_project").save_artifact(
            _artifact("capacity_license")
        )
        subjects = _subjects_by_id(build_subject_initial_data(db))
        assert subjects["capacity_license"]["state"] == "nodata"
    finally:
        db.close()


def test_commcell_header_empty_without_scoped_environment_artifact(migrated_db_path):
    """Fix 2 (b): the header reads the scoped environment artifact, never the
    global commserv.json — no artifact, no header identity."""
    db = _conn(migrated_db_path)
    try:
        header = build_subject_initial_data(db)["commcell"]
        assert header["exists"] is False
        assert header["name"] == "" and header["version"] == ""
    finally:
        db.close()


def test_commcell_header_from_scoped_environment_card(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
        res.sections["environment.metadata"] = [{}]
        res.section_output_types["environment.metadata"] = "card"
        res.section_titles["environment.metadata"] = "Metadata"
        res.section_card_specs["environment.metadata"] = {"items": []}
        artifact = result_to_artifact(res, subject_id="environment", subject_title="Environment")
        # graft a minimal identity card the way the catalog card spec labels it
        payload = artifact.model_dump(mode="json")
        payload["sections"] = [{
            "type": "card", "id": "environment.metadata", "title": "Metadata",
            "items": [
                {"label": "Hostname", "value": "cs01.lab"},
                {"label": "Version", "value": "11.40"},
                {"label": "CommCell GUID", "value": "ABC-123"},
                {"label": "Timezone", "value": "UTC"},
            ],
        }]
        from cvhealthcheck.artifacts.models import CanonicalArtifact
        customer_id, project_id = resolve_default_project(db)
        ArtifactStore(customer_id, project_id).save_artifact(
            CanonicalArtifact.model_validate(payload)
        )

        header = _initial_data_as(db, customer_id, project_id)["commcell"]
        assert header == {
            "exists": True, "name": "cs01.lab", "version": "11.40",
            "id": "ABC-123", "timezone": "UTC",
        }
    finally:
        db.close()


def test_get_commcell_identity_writes_no_global_file(tmp_path, monkeypatch):
    """Fix 2 (c): the identity GET returns the payload only — the global
    commserv.json provenance write is retired (ADR-0007's 'raw payload
    remains as provenance' clause superseded)."""
    import cvhealthcheck.reportsplus.catalog as catalog_module
    from cvhealthcheck.quickhc.commcell import get_commcell_identity

    monkeypatch.setattr(catalog_module, "CATALOG_DIR", tmp_path)

    class FakeResult:
        data = {"commcell": {"commCellName": "CS01"}, "hostName": "cs01.lab"}
        status_code = 200
        ok = True
        error = None

    class FakeClient:
        def get(self, endpoint):
            return FakeResult()

    payload = get_commcell_identity(api_client=FakeClient())
    assert payload["ok"] is True
    assert "artifact" not in payload                    # no write-path key
    assert list(tmp_path.rglob("commserv.json")) == []  # nothing on disk


def test_scoped_artifact_renders_for_its_project_only(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        # save into a project's store, then read it back under that project
        # EXPLICITLY selected (no Default fallback on reads anymore)
        customer_id, project_id = resolve_default_project(db)
        ArtifactStore(customer_id, project_id).save_artifact(
            _artifact("capacity_license")
        )
        subjects = _subjects_by_id(_initial_data_as(db, customer_id, project_id))
        assert subjects["capacity_license"]["state"] != "nodata"
        assert subjects["capacity_license"]["sections"]
        # siblings with no scoped artifact stay honest-empty
        for sid in ("client_growth", "backup_job_summary", "license_summary"):
            assert subjects[sid]["state"] == "nodata", sid
    finally:
        db.close()
