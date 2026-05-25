from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from cvhealthcheck.db import get_db, init_db
import cvhealthcheck.db.staging as staging_db_mod
import cvhealthcheck.web.routes.staging as staging_routes
from cvhealthcheck.web.app import create_app


_ARTIFACT_JSON = json.dumps({
    "schema_version": 1,
    "artifact_type": "security_assessment",
    "generated_at": "2026-01-01T00:00:00Z",
    "source": {"type": "json_import"},
    "subject": {"id": "security_assessment", "title": "Security Assessment"},
    "summary": {"status": "good", "metrics": []},
    "sections": [],
})


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(db_path=path)
    return path


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, db_path: Path):
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(staging_routes, "get_db", open_db)

    class _FakeArtifactStore:
        def save_artifact(self, artifact: Any) -> Path:
            return Path("/tmp/fake.json")

    monkeypatch.setattr(staging_db_mod, "ArtifactStore", _FakeArtifactStore)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c


def _create_artifact(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    from cvhealthcheck.db.staging import create_staged_artifact
    record = create_staged_artifact(conn, "stage-test-1", "security_assessment", _ARTIFACT_JSON)
    conn.close()
    return record["stage_id"]


def test_staging_page_returns_200(client) -> None:
    response = client.get("/quick-hc/staging")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Staging Review" in body
    assert "No pending staged artifacts." in body
    assert "No approved staged artifacts yet." in body
    assert "No rejected staged artifacts." in body


def test_approve_pending_artifact_redirects(client, db_path: Path) -> None:
    stage_id = _create_artifact(db_path)
    response = client.post(
        f"/quick-hc/staging/{stage_id}/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Approved staged artifact" in body


def test_double_approval_flashes_error(client, db_path: Path) -> None:
    stage_id = _create_artifact(db_path)
    client.post(f"/quick-hc/staging/{stage_id}/approve")
    response = client.post(
        f"/quick-hc/staging/{stage_id}/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "artifact is not pending" in response.get_data(as_text=True)


def test_reject_pending_artifact_redirects(client, db_path: Path) -> None:
    stage_id = _create_artifact(db_path)
    response = client.post(
        f"/quick-hc/staging/{stage_id}/reject",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Rejected staged artifact" in response.get_data(as_text=True)


def test_double_rejection_flashes_error(client, db_path: Path) -> None:
    stage_id = _create_artifact(db_path)
    client.post(f"/quick-hc/staging/{stage_id}/reject")
    response = client.post(
        f"/quick-hc/staging/{stage_id}/reject",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "artifact is not pending" in response.get_data(as_text=True)


def test_approve_missing_stage_id_flashes_error(client) -> None:
    response = client.post(
        "/quick-hc/staging/nonexistent-id/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "not found" in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# subject_proposal approval via web UI
# ---------------------------------------------------------------------------

@pytest.fixture()
def migrated_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    from cvhealthcheck.db.migrations import run_migrations  # noqa: F401 — fixture dependency

    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(staging_routes, "get_db", open_db)

    class _FakeArtifactStore:
        def save_artifact(self, artifact: Any) -> Path:
            return Path("/tmp/fake.json")

    monkeypatch.setattr(staging_db_mod, "ArtifactStore", _FakeArtifactStore)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c


def _create_subject_proposal(db_path: Path, stage_id: str = "stage-proposal-1") -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    proposal_json = json.dumps({
        "subject_id": "test_subject",
        "version": 1,
        "title": "Test Subject",
        "description": "A test subject.",
        "category": "storage",
        "sections": [],
        "extraction_instructions": {},
        "supersedes": None,
        "change_notes": None,
        "related_subjects": [],
    })
    conn.execute(
        """
        INSERT INTO staged_artifacts
            (stage_id, subject_id, artifact_type, subject_version,
             source_type, status, artifact_json, ai_notes, created_at)
        VALUES (?, ?, 'subject_proposal', 1, 'ai', 'pending', ?, 'test',
                strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        """,
        (stage_id, "test_subject", proposal_json),
    )
    conn.commit()
    conn.close()
    return stage_id


def test_approve_subject_proposal_redirects(
    migrated_client, migrated_db_path: Path
) -> None:
    stage_id = _create_subject_proposal(migrated_db_path)
    response = migrated_client.post(
        f"/quick-hc/staging/{stage_id}/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "added to catalog" in response.get_data(as_text=True)


def test_approve_subject_proposal_flash_contains_title(
    migrated_client, migrated_db_path: Path
) -> None:
    stage_id = _create_subject_proposal(migrated_db_path)
    response = migrated_client.post(
        f"/quick-hc/staging/{stage_id}/approve",
        follow_redirects=True,
    )
    assert "Test Subject" in response.get_data(as_text=True)


def test_approve_subject_proposal_creates_subject_row(
    migrated_client, migrated_db_path: Path
) -> None:
    stage_id = _create_subject_proposal(migrated_db_path)
    migrated_client.post(f"/quick-hc/staging/{stage_id}/approve")

    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM subjects WHERE subject_id = 'test_subject'"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["title"] == "Test Subject"
    assert row["status"] == "active"


def test_approve_subject_proposal_marks_staged_artifact_approved(
    migrated_client, migrated_db_path: Path
) -> None:
    stage_id = _create_subject_proposal(migrated_db_path)
    migrated_client.post(f"/quick-hc/staging/{stage_id}/approve")

    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM staged_artifacts WHERE stage_id = ?", (stage_id,)
    ).fetchone()
    conn.close()

    assert row["status"] == "approved"


def test_approve_regular_artifact_still_works_after_proposal_changes(
    client, db_path: Path
) -> None:
    stage_id = _create_artifact(db_path)
    response = client.post(
        f"/quick-hc/staging/{stage_id}/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Approved staged artifact" in response.get_data(as_text=True)
