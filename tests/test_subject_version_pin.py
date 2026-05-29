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
