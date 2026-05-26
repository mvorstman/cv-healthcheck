"""Unit tests for finalize/reload/diff core logic (ADR 0002 phase 5)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.finalizations import (
    FinalizationError,
    diff_working_vs_latest,
    finalize_project,
    reload_latest_finalization,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _make_artifact(subject_id: str, status: ArtifactStatus = ArtifactStatus.good) -> CanonicalArtifact:
    now = datetime.now(timezone.utc)
    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=now,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id=subject_id, title="Test"),
        summary=ArtifactSummary(status=status),
        sections=[],
    )


def _save(customer_id: str, project_id: str, subject_id: str,
          status: ArtifactStatus = ArtifactStatus.good) -> None:
    """Drop an artifact into working state via ArtifactStore."""
    ArtifactStore(customer_id, project_id).save_artifact(
        _make_artifact(subject_id, status)
    )


def _create_project(
    db: sqlite3.Connection,
    *,
    customer_id: str = "default",
    project_id: str = "p1",
    project_number: str = "P-1",
    ticket_reference: str | None = None,
    assigned_consultant: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO projects (project_id, customer_id, project_number,"
        " ticket_reference, assigned_consultant, created_at,"
        " working_state_modified_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            customer_id,
            project_number,
            ticket_reference,
            assigned_consultant,
            now,
            now,
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# finalize_project
# ---------------------------------------------------------------------------


def test_finalize_produces_row_and_files(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")
    _save("default", "p1", "license_summary")

    n = finalize_project(db, "default", "p1")

    assert n == 1
    row = db.execute(
        "SELECT finalization_number FROM finalizations WHERE project_id = 'p1'"
    ).fetchone()
    assert row["finalization_number"] == 1

    import cvhealthcheck.artifacts.store as store_module
    finalized_dir = store_module._DEFAULT_BASE_DIR / "default" / "p1" / "finalized" / "1"
    assert (finalized_dir / "security_assessment" / "latest.json").exists()
    assert (finalized_dir / "license_summary" / "latest.json").exists()


def test_finalize_twice_produces_one_then_two(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")

    n1 = finalize_project(db, "default", "p1")
    n2 = finalize_project(db, "default", "p1")

    assert (n1, n2) == (1, 2)
    rows = db.execute(
        "SELECT finalization_number FROM finalizations"
        " WHERE project_id = 'p1' ORDER BY finalization_number"
    ).fetchall()
    assert [r["finalization_number"] for r in rows] == [1, 2]


def test_finalize_empty_project_raises(db: sqlite3.Connection) -> None:
    _create_project(db)
    with pytest.raises(FinalizationError, match="no artifacts"):
        finalize_project(db, "default", "p1")


def test_finalize_unknown_project_raises(db: sqlite3.Connection) -> None:
    with pytest.raises(FinalizationError, match="not found"):
        finalize_project(db, "default", "p_nope")


def test_finalize_records_null_finalized_by_when_no_consultant(db: sqlite3.Connection) -> None:
    _create_project(db, assigned_consultant=None)
    _save("default", "p1", "security_assessment")

    finalize_project(db, "default", "p1")

    row = db.execute(
        "SELECT finalized_by FROM finalizations WHERE project_id = 'p1'"
    ).fetchone()
    assert row["finalized_by"] is None


def test_finalize_records_consultant_when_set(db: sqlite3.Connection) -> None:
    _create_project(db, assigned_consultant="Alice")
    _save("default", "p1", "security_assessment")

    finalize_project(db, "default", "p1")

    row = db.execute(
        "SELECT finalized_by FROM finalizations WHERE project_id = 'p1'"
    ).fetchone()
    assert row["finalized_by"] == "Alice"


def test_finalize_captures_ticket_reference_at_finalize_time(db: sqlite3.Connection) -> None:
    _create_project(db, ticket_reference="TD-100")
    _save("default", "p1", "security_assessment")

    finalize_project(db, "default", "p1")

    # Mutate the project's ticket_reference after finalization. The
    # finalization row's ticket_reference should still be TD-100 — it
    # was captured at the moment of finalize.
    db.execute(
        "UPDATE projects SET ticket_reference = 'TD-200' WHERE project_id = 'p1'"
    )
    db.commit()

    row = db.execute(
        "SELECT ticket_reference FROM finalizations WHERE project_id = 'p1'"
    ).fetchone()
    assert row["ticket_reference"] == "TD-100"


# ---------------------------------------------------------------------------
# reload_latest_finalization
# ---------------------------------------------------------------------------


def test_reload_copies_finalized_files_into_working(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment", status=ArtifactStatus.good)
    finalize_project(db, "default", "p1")

    # Modify working to status=warning.
    _save("default", "p1", "security_assessment", status=ArtifactStatus.warning)
    store = ArtifactStore("default", "p1")
    assert store.load_latest_artifact("security_assessment").summary.status == ArtifactStatus.warning

    n = reload_latest_finalization(db, "default", "p1")

    assert n == 1
    assert store.load_latest_artifact("security_assessment").summary.status == ArtifactStatus.good


def test_reload_overwrites_existing_working(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment", status=ArtifactStatus.good)
    finalize_project(db, "default", "p1")

    # Add a new subject in working after finalize, then reload — the new
    # subject should disappear.
    _save("default", "p1", "license_summary")
    reload_latest_finalization(db, "default", "p1")

    store = ArtifactStore("default", "p1")
    store.load_latest_artifact("security_assessment")  # exists, no raise
    with pytest.raises(FileNotFoundError):
        store.load_latest_artifact("license_summary")


def test_reload_on_project_without_finalizations_raises(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")
    with pytest.raises(FinalizationError, match="no finalizations"):
        reload_latest_finalization(db, "default", "p1")


# ---------------------------------------------------------------------------
# diff_working_vs_latest
# ---------------------------------------------------------------------------


def test_diff_returns_empty_when_files_match(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")
    _save("default", "p1", "license_summary")
    finalize_project(db, "default", "p1")

    assert diff_working_vs_latest(db, "default", "p1") == []


def test_diff_returns_subject_ids_when_files_differ(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment", status=ArtifactStatus.good)
    _save("default", "p1", "license_summary", status=ArtifactStatus.good)
    finalize_project(db, "default", "p1")

    # Modify security_assessment in working.
    _save("default", "p1", "security_assessment", status=ArtifactStatus.warning)

    diff = diff_working_vs_latest(db, "default", "p1")
    assert diff == ["security_assessment"]


def test_diff_flags_subject_present_in_working_but_not_in_finalized(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")
    finalize_project(db, "default", "p1")

    _save("default", "p1", "license_summary")  # added after finalize

    assert diff_working_vs_latest(db, "default", "p1") == ["license_summary"]


def test_diff_flags_subject_present_in_finalized_but_not_in_working(db: sqlite3.Connection, tmp_path: Path) -> None:
    import shutil
    _create_project(db)
    _save("default", "p1", "security_assessment")
    finalize_project(db, "default", "p1")

    # Remove the subject from working.
    import cvhealthcheck.artifacts.store as store_module
    working_subject = (
        store_module._DEFAULT_BASE_DIR / "default" / "p1" / "working" / "security_assessment"
    )
    shutil.rmtree(working_subject)

    assert diff_working_vs_latest(db, "default", "p1") == ["security_assessment"]


def test_diff_returns_empty_when_no_finalizations(db: sqlite3.Connection) -> None:
    _create_project(db)
    _save("default", "p1", "security_assessment")

    assert diff_working_vs_latest(db, "default", "p1") == []
