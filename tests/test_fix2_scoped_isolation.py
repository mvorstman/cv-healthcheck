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

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.web.active_project import resolve_default_project

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


def test_scoped_artifact_renders_for_its_project_only(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        # save into the ACTIVE (fallback: Default) project's store
        customer_id, project_id = resolve_default_project(db)
        ArtifactStore(customer_id, project_id).save_artifact(
            _artifact("capacity_license")
        )
        subjects = _subjects_by_id(build_subject_initial_data(db))
        assert subjects["capacity_license"]["state"] != "nodata"
        assert subjects["capacity_license"]["sections"]
        # siblings with no scoped artifact stay honest-empty
        for sid in ("client_growth", "backup_job_summary", "license_summary"):
            assert subjects[sid]["state"] == "nodata", sid
    finally:
        db.close()
