"""
Domain Labels — Phase 4 sparse backfill (migration 0030).

The backfill resolves each target by subject_id + status='active' at apply time.
On a fresh migration-seeded catalog only the three *seeded* targets exist
(security_assessment, backup_job_summary, client_growth); the three runtime-only
targets (audit_trail, metrics_reporting, users) are AI-authored and absent here,
so the migration is a clean no-op for them. Their real-catalog result is covered
by the post-commit live smoke check, not these test-DB tests.
"""
from __future__ import annotations

from pathlib import Path

from cvhealthcheck.db.database import get_db
from cvhealthcheck.db.domain_labels import subject_labels_map
from cvhealthcheck.db.migrations import _MIGRATIONS_DIR, run_migrations

# Planned labels for the targets that exist in the migration-seeded catalog.
SEEDED_TARGETS = {
    "security_assessment": ["compliance", "governance"],
    "backup_job_summary": ["backup"],
    "client_growth": ["reporting"],
}
# Present only in the real catalog; absent from a fresh seed.
RUNTIME_ONLY_TARGETS = {"audit_trail", "metrics_reporting", "users"}

# Categories of the seeded targets — asserted unchanged by the data migration.
SEEDED_TARGET_CATEGORIES = {
    "security_assessment": "security",
    "backup_job_summary": "operations",
    "client_growth": "performance",
}


def _labels_for(db, subject_id: str) -> list[str]:
    row = db.execute(
        "SELECT id FROM subjects WHERE subject_id = ? AND status = 'active'",
        (subject_id,),
    ).fetchone()
    if row is None:
        return []
    return subject_labels_map(db).get(row["id"], [])


def test_migration_0030_recorded(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        applied = {
            r["migration_id"]
            for r in db.execute("SELECT migration_id FROM schema_migrations")
        }
        assert "0030_domain_label_backfill" in applied
    finally:
        db.close()


def test_seeded_targets_have_planned_labels(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        for subject_id, planned in SEEDED_TARGETS.items():
            assert _labels_for(db, subject_id) == planned, subject_id
    finally:
        db.close()


def test_runtime_only_targets_absent_so_no_labels(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        # Not in the seeded catalog → migration is a no-op for them (no error).
        for subject_id in RUNTIME_ONLY_TARGETS:
            present = db.execute(
                "SELECT 1 FROM subjects WHERE subject_id = ?", (subject_id,)
            ).fetchone()
            assert present is None, f"{subject_id} unexpectedly seeded"
        # Exactly the seeded targets' assignments landed (2 + 1 + 1 = 4 rows).
        total = db.execute(
            "SELECT COUNT(*) AS c FROM subject_domain_labels"
        ).fetchone()["c"]
        assert total == 4
    finally:
        db.close()


def test_non_target_subjects_unlabeled(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        for subject_id in ("capacity_license", "environment", "license_summary"):
            assert _labels_for(db, subject_id) == [], subject_id
    finally:
        db.close()


def test_categories_unchanged(migrated_db_path: Path) -> None:
    """The data migration must not touch `category`/`category_label`."""
    db = get_db(migrated_db_path)
    try:
        for subject_id, expected_category in SEEDED_TARGET_CATEGORIES.items():
            row = db.execute(
                "SELECT category, category_label FROM subjects"
                " WHERE subject_id = ? AND status = 'active'",
                (subject_id,),
            ).fetchone()
            assert row["category"] == expected_category, subject_id
            assert row["category_label"]  # still populated, not blanked
    finally:
        db.close()


def test_backfill_is_idempotent(migrated_db_path: Path) -> None:
    """Re-applying 0030's SQL adds nothing (INSERT OR IGNORE + UNIQUE)."""
    db = get_db(migrated_db_path)
    try:
        before = db.execute(
            "SELECT COUNT(*) AS c FROM subject_domain_labels"
        ).fetchone()["c"]
        sql = (_MIGRATIONS_DIR / "0030_domain_label_backfill.sql").read_text()
        db.executescript(sql)
        db.commit()
        after = db.execute(
            "SELECT COUNT(*) AS c FROM subject_domain_labels"
        ).fetchone()["c"]
        assert after == before  # no duplicates, no growth
        # Labels are still exactly the planned set (no dup slugs per subject).
        assert _labels_for(db, "security_assessment") == ["compliance", "governance"]
    finally:
        db.close()
