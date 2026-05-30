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

def test_subjects_table_seeded_after_migration(fresh_db: Path) -> None:
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

    # Six system subjects + the internal "_metric_test" (0010, phase 2),
    # "_chart_test" (0011, phase 3), and "_card_test" (0013, phase 4) subjects,
    # all hidden in the UI by default.
    assert count == 9
    assert subject_ids == {
        "environment",
        "security_assessment",
        "license_summary",
        "client_growth",
        "capacity_license",
        "backup_job_summary",
        "_metric_test",
        "_chart_test",
        "_card_test",
    }


def test_migration_0012_allows_card_section_type(fresh_db: Path) -> None:
    """After 0012, subject_sections.section_type accepts 'card' (and still
    rejects an unknown type), and existing rows survived the table rebuild."""
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # Existing rows preserved through the rebuild.
        existing = conn.execute("SELECT COUNT(*) FROM subject_sections").fetchone()[0]
        assert existing > 0

        # A card section now inserts cleanly (FK satisfied by a real subject).
        conn.execute(
            "INSERT INTO subject_sections (subject_id, subject_version, section_id,"
            " title, section_type) VALUES ('environment', 1, 'environment.card_probe',"
            " 'Probe', 'card')"
        )
        # An unknown type is still rejected by the widened CHECK.
        import pytest as _pytest
        with _pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO subject_sections (subject_id, subject_version, section_id,"
                " title, section_type) VALUES ('environment', 1, 'environment.bad_probe',"
                " 'Probe', 'bogus')"
            )
    finally:
        conn.close()


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
    assert len(statuses) == 20  # 0020 added _metric_test per-field rules + recommend-seam exercise
    assert all(s["status"] == "applied" for s in statuses)
    migration_ids = [s["migration_id"] for s in statuses]
    assert migration_ids == sorted(migration_ids)
