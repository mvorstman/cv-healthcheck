"""
Domain Labels — Phase 1 schema tests (migration 0029).

Covers: the migration applies cleanly and seeds exactly four vocabulary terms;
the association FK rejects an unknown label (and unknown subject row); a valid
association inserts; UNIQUE blocks a duplicate; the vocabulary accessor returns
the four terms; and the disjointness invariant between the `category` and
domain-label vocabularies holds.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.database import get_db
from cvhealthcheck.db.domain_labels import (
    domain_label_vocabulary,
    list_domain_labels,
)

# The four seeded domain-label terms (migration 0029).
EXPECTED_LABELS = {"compliance", "governance", "backup", "reporting"}

# The `category` vocabulary as defined today — the `_LABELS` constant inside
# `cvhealthcheck.db.subjects.create_subject_from_proposal`. Mirrored here as the
# disjointness reference; `category` is free-text in the schema (no DB enum), so
# this code constant is the authoritative term set. If a category term is ever
# added that collides with a domain label, this test must fail.
CATEGORY_VOCABULARY = {
    "identity",
    "security",
    "licensing",
    "performance",
    "operations",
    "storage",
}


def _a_subject_row_id(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT id FROM subjects LIMIT 1").fetchone()
    assert row is not None, "migrated DB should seed at least one subject row"
    return row["id"]


def test_migration_creates_tables_and_is_recorded(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        tables = {
            r["name"]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "domain_label" in tables
        assert "subject_domain_labels" in tables

        applied = {
            r["migration_id"]
            for r in db.execute("SELECT migration_id FROM schema_migrations")
        }
        assert "0029_domain_labels" in applied
    finally:
        db.close()


def test_domain_label_seeded_with_exactly_four_terms(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        rows = db.execute(
            "SELECT label, display_label FROM domain_label"
        ).fetchall()
        labels = {r["label"] for r in rows}
        assert labels == EXPECTED_LABELS
        assert len(rows) == 4  # no extras, no duplicates

        display = {r["label"]: r["display_label"] for r in rows}
        assert display == {
            "compliance": "Compliance",
            "governance": "Governance",
            "backup": "Backup",
            "reporting": "Reporting",
        }
    finally:
        db.close()


def test_subject_domain_labels_rows_are_structurally_valid(migrated_db_path: Path) -> None:
    """Migration 0029 creates the association empty; a later phase (the 0030
    backfill) populates it. Whatever rows exist must each resolve to a real
    subject row AND a real vocabulary label — the FK guarantee, which holds
    regardless of how many labels the backfill assigns."""
    db = get_db(migrated_db_path)
    try:
        orphans = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM subject_domain_labels sdl
            LEFT JOIN subjects s     ON s.id = sdl.subject_row_id
            LEFT JOIN domain_label dl ON dl.label = sdl.label
            WHERE s.id IS NULL OR dl.label IS NULL
            """
        ).fetchone()["c"]
        assert orphans == 0
    finally:
        db.close()


def test_association_fk_rejects_unknown_label(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        subject_row_id = _a_subject_row_id(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO subject_domain_labels (subject_row_id, label) VALUES (?, ?)",
                (subject_row_id, "not_a_real_label"),
            )
    finally:
        db.close()


def test_association_fk_rejects_unknown_subject_row(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO subject_domain_labels (subject_row_id, label) VALUES (?, ?)",
                (9_999_999, "compliance"),
            )
    finally:
        db.close()


def test_association_valid_insert_succeeds(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        subject_row_id = _a_subject_row_id(db)
        db.execute(
            "INSERT INTO subject_domain_labels (subject_row_id, label) VALUES (?, ?)",
            (subject_row_id, "compliance"),
        )
        db.commit()
        stored = db.execute(
            "SELECT label FROM subject_domain_labels WHERE subject_row_id = ?",
            (subject_row_id,),
        ).fetchall()
        assert [r["label"] for r in stored] == ["compliance"]
    finally:
        db.close()


def test_association_unique_blocks_duplicate(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        subject_row_id = _a_subject_row_id(db)
        db.execute(
            "INSERT INTO subject_domain_labels (subject_row_id, label) VALUES (?, ?)",
            (subject_row_id, "compliance"),
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO subject_domain_labels (subject_row_id, label) VALUES (?, ?)",
                (subject_row_id, "compliance"),
            )
    finally:
        db.close()


def test_vocabulary_accessor_returns_exactly_four_terms(migrated_db_path: Path) -> None:
    db = get_db(migrated_db_path)
    try:
        assert domain_label_vocabulary(db) == EXPECTED_LABELS

        rows = list_domain_labels(db)
        assert [r["label"] for r in rows] == [
            "compliance",
            "governance",
            "backup",
            "reporting",
        ]  # ordered by sort_order
        assert all(
            set(r.keys()) == {"label", "display_label", "description", "sort_order"}
            for r in rows
        )
    finally:
        db.close()


def test_category_and_domain_label_vocabularies_are_disjoint(
    migrated_db_path: Path,
) -> None:
    """The additive-only-by-construction invariant — must never silently regress.

    Asserted two ways: the defined `category` vocabulary is disjoint from the
    domain-label vocabulary, and no real subject's stored category collides with
    a domain label either.
    """
    db = get_db(migrated_db_path)
    try:
        labels = domain_label_vocabulary(db)

        # Defined vocabularies are disjoint.
        assert CATEGORY_VOCABULARY & labels == set()

        # No seeded subject's actual category collides with a domain label.
        categories_in_use = {
            r["category"] for r in db.execute("SELECT DISTINCT category FROM subjects")
        }
        assert categories_in_use & labels == set()
    finally:
        db.close()
