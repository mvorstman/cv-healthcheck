"""Tests for ADR 0004 per-customer template version pinning + family versions.

Exercises migration 0009's customer_subject_pin table and the resolution
helpers in db/subjects.py. Today every family has exactly one version, so
the seeded catalog drives the "single version" path; multi-version cases are
simulated by inserting extra subject rows.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.subjects import (
    get_pinned_subject_id,
    list_family_versions,
    resolve_active_version,
    set_pinned_subject_id,
    version_number,
)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_subject(conn: sqlite3.Connection, subject_id: str) -> None:
    conn.execute(
        "INSERT INTO subjects (subject_id, version, title, category, category_label) "
        "VALUES (?, 1, ?, 'licensing', 'Licensing')",
        (subject_id, subject_id),
    )
    conn.commit()


def test_version_number():
    assert version_number("capacity_license") == 1
    assert version_number("capacity_license_v2") == 2
    assert version_number("capacity_license_v10") == 10


def test_list_family_versions_single(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        assert list_family_versions(conn, "capacity_license") == ["capacity_license"]
    finally:
        conn.close()


def test_list_family_versions_multi_natural_sort(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _add_subject(conn, "capacity_license_v10")
        _add_subject(conn, "capacity_license_v2")
        # Unsuffixed v1 first, then ascending by version number.
        assert list_family_versions(conn, "capacity_license") == [
            "capacity_license",
            "capacity_license_v2",
            "capacity_license_v10",
        ]
    finally:
        conn.close()


def test_list_family_versions_excludes_false_prefix_matches(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        # LIKE 'capacity_license\_v%' would match this, but its family differs.
        _add_subject(conn, "capacity_license_v2_archived")
        assert list_family_versions(conn, "capacity_license") == ["capacity_license"]
    finally:
        conn.close()


def test_pin_set_and_get(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        assert get_pinned_subject_id(conn, "default", "capacity_license") is None
        _add_subject(conn, "capacity_license_v2")
        set_pinned_subject_id(conn, "default", "capacity_license", "capacity_license_v2")
        assert get_pinned_subject_id(conn, "default", "capacity_license") == "capacity_license_v2"
        # Re-pinning overwrites (PK is customer + family).
        set_pinned_subject_id(conn, "default", "capacity_license", "capacity_license")
        assert get_pinned_subject_id(conn, "default", "capacity_license") == "capacity_license"
    finally:
        conn.close()


def test_resolve_active_version_defaults_to_latest(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        # Unpinned, single version -> the only version.
        assert resolve_active_version(conn, "default", "capacity_license") == "capacity_license"
        # Unpinned, multi version -> latest.
        _add_subject(conn, "capacity_license_v2")
        assert resolve_active_version(conn, "default", "capacity_license") == "capacity_license_v2"
    finally:
        conn.close()


def test_resolve_active_version_honors_pin(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        _add_subject(conn, "capacity_license_v2")
        set_pinned_subject_id(conn, "default", "capacity_license", "capacity_license")
        # Pinned to v1 even though v2 exists.
        assert resolve_active_version(conn, "default", "capacity_license") == "capacity_license"
        # Passing a version-suffixed id resolves through the family.
        assert resolve_active_version(conn, "default", "capacity_license_v2") == "capacity_license"
    finally:
        conn.close()


def test_resolve_active_version_ignores_stale_pin(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        # Pin points at a version that no longer exists -> fall back to latest.
        set_pinned_subject_id(conn, "default", "capacity_license", "capacity_license_v9")
        assert resolve_active_version(conn, "default", "capacity_license") == "capacity_license"
    finally:
        conn.close()


def test_resolve_active_version_no_customer(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        assert resolve_active_version(conn, None, "capacity_license") == "capacity_license"
    finally:
        conn.close()


# ── Source-tile UI injection (ADR 0004 2d) ──

def test_version_info_helper(migrated_db_path: Path):
    from cvhealthcheck.quickhc.subject_data_service import _version_info

    conn = _conn(migrated_db_path)
    try:
        info = _version_info(conn, "default", "capacity_license")
        assert info == {
            "family": "capacity_license",
            "versions": ["capacity_license"],
            "active": "capacity_license",
        }
        # No db handle -> subject is its own only version.
        offline = _version_info(None, "default", "capacity_license_v2")
        assert offline["versions"] == ["capacity_license_v2"]
        assert offline["family"] == "capacity_license"
    finally:
        conn.close()


def test_last_collected_helper():
    from datetime import datetime, timezone

    from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
    from cvhealthcheck.artifacts.models import (
        ArtifactSource,
        ArtifactSubject,
        ArtifactSummary,
        CanonicalArtifact,
    )
    from cvhealthcheck.quickhc.subject_data_service import _last_collected

    assert _last_collected(None) is None

    ts = datetime(2026, 5, 28, 14, 23, tzinfo=timezone.utc)
    artifact = CanonicalArtifact(
        artifact_type="capacity_license",
        generated_at=ts,
        source=ArtifactSource(type=SourceType.rest, collected_at=ts),
        subject=ArtifactSubject(id="capacity_license", title="Capacity Licenses"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
    )
    assert _last_collected(artifact) == ts.isoformat()


def test_build_subject_initial_data_injects_version_info(migrated_db_path: Path):
    from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data

    conn = _conn(migrated_db_path)
    try:
        data = build_subject_initial_data(conn, customer_id="default")
        subjects = [s for cat in data["cats"] for s in cat["subjects"]]
        assert subjects, "expected at least one subject"
        for subj in subjects:
            assert "version_info" in subj
            assert subj["version_info"]["active"] in subj["version_info"]["versions"]
            assert "last_collected" in subj
            assert "is_test" in subj
    finally:
        conn.close()


def test_is_test_flag_marks_underscore_subjects(migrated_db_path: Path):
    from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data

    conn = _conn(migrated_db_path)
    try:
        data = build_subject_initial_data(conn, customer_id="default")
        by_id = {s["id"]: s for cat in data["cats"] for s in cat["subjects"]}
        # The seeded internal subject is flagged; the real subjects are not.
        assert by_id["_metric_test"]["is_test"] is True
        assert by_id["capacity_license"]["is_test"] is False
        assert by_id["security_assessment"]["is_test"] is False
    finally:
        conn.close()
