from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.customers import create_customer
from cvhealthcheck.db.engagements import create_engagement
from cvhealthcheck.db.staging import (
    approve_staged_artifact,
    create_staged_artifact,
    delete_staged_artifact,
    get_staged_artifact,
    list_staged_artifacts,
    reject_staged_artifact,
)


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "cvhealthcheck"
    / "db"
    / "migrations"
    / "0002_staged_artifacts.sql"
)


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    from cvhealthcheck.db.migrations import run_migrations
    db_path = tmp_path / "test.db"
    run_migrations(db_path=db_path)
    # Migration 0005 seeds a default customer + project; staging tests
    # exercise empty-table behaviour, so clean the seeds.
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM projects")
    conn.execute("DELETE FROM customers")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def test_create_staged_artifact_creates_record_with_defaults(db: sqlite3.Connection) -> None:
    record = create_staged_artifact(
        db,
        "stage-1",
        "security_assessment",
        '{"ok": true}',
    )

    assert record["stage_id"] == "stage-1"
    assert record["subject_id"] == "security_assessment"
    assert record["status"] == "pending"
    assert record["artifact_json"] == '{"ok": true}'
    assert record["created_at"]
    assert record["reviewed_at"] is None
    assert record["reviewed_by"] is None


def test_create_staged_artifact_invalid_json_raises(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="artifact_json is not valid JSON"):
        create_staged_artifact(db, "stage-1", "security_assessment", "{not json}")


def test_create_staged_artifact_empty_json_raises(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="artifact_json is not valid JSON"):
        create_staged_artifact(db, "stage-1", "security_assessment", "")


def test_create_staged_artifact_duplicate_stage_id_raises(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "dup", "security_assessment", '{"a": 1}')
    with pytest.raises(sqlite3.IntegrityError):
        create_staged_artifact(db, "dup", "license_summary", '{"a": 2}')


def test_get_staged_artifact_returns_existing_record(db: sqlite3.Connection) -> None:
    created = create_staged_artifact(db, "stage-1", "security_assessment", '{"ok": true}')
    fetched = get_staged_artifact(db, "stage-1")
    assert fetched == created


def test_get_staged_artifact_returns_none_for_missing(db: sqlite3.Connection) -> None:
    assert get_staged_artifact(db, "missing") is None


def test_list_staged_artifacts_returns_all(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    create_staged_artifact(db, "stage-2", "license_summary", '{"a": 2}')
    assert len(list_staged_artifacts(db)) == 2


def test_list_staged_artifacts_filters_by_status(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    create_staged_artifact(db, "stage-2", "license_summary", '{"a": 2}')
    approve_staged_artifact(db, "stage-1")

    records = list_staged_artifacts(db, status="approved")
    assert [record["stage_id"] for record in records] == ["stage-1"]


def test_list_staged_artifacts_filters_by_subject_id(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    create_staged_artifact(db, "stage-2", "license_summary", '{"a": 2}')

    records = list_staged_artifacts(db, subject_id="license_summary")
    assert [record["stage_id"] for record in records] == ["stage-2"]


def test_list_staged_artifacts_filters_by_status_and_subject_id(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    create_staged_artifact(db, "stage-2", "security_assessment", '{"a": 2}')
    create_staged_artifact(db, "stage-3", "license_summary", '{"a": 3}')
    approve_staged_artifact(db, "stage-2")

    records = list_staged_artifacts(
        db,
        status="approved",
        subject_id="security_assessment",
    )
    assert [record["stage_id"] for record in records] == ["stage-2"]


def test_list_staged_artifacts_returns_newest_first(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    create_staged_artifact(db, "stage-2", "security_assessment", '{"a": 2}')
    db.execute(
        "UPDATE staged_artifacts SET created_at = ? WHERE stage_id = ?",
        ("2026-05-24T10:00:00+00:00", "stage-1"),
    )
    db.execute(
        "UPDATE staged_artifacts SET created_at = ? WHERE stage_id = ?",
        ("2026-05-24T11:00:00+00:00", "stage-2"),
    )
    db.commit()

    records = list_staged_artifacts(db)
    assert [record["stage_id"] for record in records] == ["stage-2", "stage-1"]


def test_list_staged_artifacts_returns_empty_list_when_no_matches(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    assert list_staged_artifacts(db, status="approved") == []


def test_approve_staged_artifact_sets_status_and_review_fields(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')

    record = approve_staged_artifact(db, "stage-1", reviewed_by="alice")

    assert record is not None
    assert record["status"] == "approved"
    assert record["reviewed_at"]
    assert record["reviewed_by"] == "alice"


def test_approve_staged_artifact_raises_when_already_approved(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    approve_staged_artifact(db, "stage-1")

    with pytest.raises(ValueError, match="artifact is not pending"):
        approve_staged_artifact(db, "stage-1")


def test_approve_staged_artifact_raises_when_rejected(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    reject_staged_artifact(db, "stage-1")

    with pytest.raises(ValueError, match="artifact is not pending"):
        approve_staged_artifact(db, "stage-1")


def test_approve_staged_artifact_returns_none_for_missing(db: sqlite3.Connection) -> None:
    assert approve_staged_artifact(db, "missing") is None


def test_reject_staged_artifact_sets_status_and_review_fields(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')

    record = reject_staged_artifact(db, "stage-1", reviewed_by="alice")

    assert record is not None
    assert record["status"] == "rejected"
    assert record["reviewed_at"]
    assert record["reviewed_by"] == "alice"


def test_reject_staged_artifact_raises_when_already_rejected(
    db: sqlite3.Connection,
) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    reject_staged_artifact(db, "stage-1")

    with pytest.raises(ValueError, match="artifact is not pending"):
        reject_staged_artifact(db, "stage-1")


def test_reject_staged_artifact_raises_when_approved(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    approve_staged_artifact(db, "stage-1")

    with pytest.raises(ValueError, match="artifact is not pending"):
        reject_staged_artifact(db, "stage-1")


def test_reject_staged_artifact_returns_none_for_missing(db: sqlite3.Connection) -> None:
    assert reject_staged_artifact(db, "missing") is None


def test_delete_staged_artifact_returns_true_when_deleted(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    assert delete_staged_artifact(db, "stage-1") is True


def test_delete_staged_artifact_returns_false_for_missing(db: sqlite3.Connection) -> None:
    assert delete_staged_artifact(db, "missing") is False


def test_delete_staged_artifact_removes_record(db: sqlite3.Connection) -> None:
    create_staged_artifact(db, "stage-1", "security_assessment", '{"a": 1}')
    assert delete_staged_artifact(db, "stage-1") is True
    assert get_staged_artifact(db, "stage-1") is None


def test_create_staged_artifact_accepts_customer_and_engagement_foreign_keys(
    db: sqlite3.Connection,
) -> None:
    customer = create_customer("Acme", customer_id="c1", db_path=Path(db.execute("PRAGMA database_list").fetchone()[2]))
    engagement = create_engagement("c1", "Q1", engagement_id="e1", db_path=Path(db.execute("PRAGMA database_list").fetchone()[2]))

    record = create_staged_artifact(
        db,
        "stage-1",
        "security_assessment",
        '{"a": 1}',
        customer_id=customer["customer_id"],
        engagement_id=engagement["engagement_id"],
    )

    assert record["customer_id"] == "c1"
    assert record["engagement_id"] == "e1"
