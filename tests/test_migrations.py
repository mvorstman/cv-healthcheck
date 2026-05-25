from __future__ import annotations

from pathlib import Path

import pytest

from cvhealthcheck.db.migrations import migration_status, run_migrations


@pytest.fixture()
def fresh_db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    run_migrations(db_path=path)
    return path


# ---------------------------------------------------------------------------
# Migration runner basics
# ---------------------------------------------------------------------------

def test_run_migrations_creates_all_tables(fresh_db: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    expected = {
        "schema_migrations",
        "customers",
        "engagements",
        "staged_artifacts",
        "subjects",
        "subject_sections",
        "subject_sources",
        "subject_section_sources",
        "collector_schemas",
    }
    assert expected <= tables


def test_run_migrations_is_idempotent(fresh_db: Path) -> None:
    run_migrations(db_path=fresh_db)
    run_migrations(db_path=fresh_db)

    statuses = migration_status(db_path=fresh_db)
    assert all(s["status"] == "applied" for s in statuses)


def test_schema_migrations_contains_all_three_migrations(fresh_db: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        applied = {
            row[0]
            for row in conn.execute(
                "SELECT migration_id FROM schema_migrations"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "0001_initial" in applied
    assert "0002_staged_artifacts" in applied
    assert "0003_report_inventory" in applied


# ---------------------------------------------------------------------------
# Seed data verification
# ---------------------------------------------------------------------------

def test_subjects_table_contains_six_rows_after_migration(fresh_db: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        count = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        subject_ids = {
            row[0]
            for row in conn.execute("SELECT subject_id FROM subjects").fetchall()
        }
    finally:
        conn.close()

    assert count == 6
    assert subject_ids == {
        "environment",
        "security_assessment",
        "license_summary",
        "client_growth",
        "capacity_license",
        "backup_job_summary",
    }


def test_all_seeded_subjects_are_active(fresh_db: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        statuses = {
            row[0]
            for row in conn.execute("SELECT DISTINCT status FROM subjects").fetchall()
        }
    finally:
        conn.close()

    assert statuses == {"active"}


def test_migration_status_reports_all_applied(fresh_db: Path) -> None:
    statuses = migration_status(db_path=fresh_db)
    assert len(statuses) == 4
    assert all(s["status"] == "applied" for s in statuses)
    migration_ids = [s["migration_id"] for s in statuses]
    assert migration_ids == sorted(migration_ids)
