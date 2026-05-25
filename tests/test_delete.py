"""Tests for the delete-subject feature."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.db import get_db
from cvhealthcheck.db.migrations import run_migrations
from cvhealthcheck.db.subjects import (
    create_subject_from_proposal,
    delete_subject,
    get_subject,
)
import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.web.app import create_app


# ── helpers ───────────────────────────────────────────────────────────────────

def _sample_proposal(subject_id: str = "storage_utilization", **overrides) -> dict:
    base = {
        "subject_id": subject_id,
        "version": 1,
        "title": "Storage Utilization",
        "description": "Storage capacity and usage.",
        "category": "storage",
        "sections": [
            {
                "section_id": f"{subject_id}.summary",
                "title": "Summary",
                "section_type": "metric",
                "default_selected": True,
                "sort_order": 1,
            }
        ],
        "extraction_instructions": {
            "html": {
                "extractable": True,
                "non_extractable_reason": None,
                "recognition_hints": {"title_contains": "Storage"},
                "sections": {f"{subject_id}.summary": {"selector": ".summary"}},
            }
        },
        "supersedes": None,
        "change_notes": None,
        "related_subjects": [],
    }
    base.update(overrides)
    return base


def _minimal_artifact(artifact_type: str = "storage_utilization") -> CanonicalArtifact:
    from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
    from cvhealthcheck.artifacts.models import (
        ArtifactSource, ArtifactSubject, ArtifactSummary,
    )
    from datetime import datetime, timezone
    return CanonicalArtifact(
        artifact_type=artifact_type,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source=ArtifactSource(type=SourceType.json_import),
        subject=ArtifactSubject(id=artifact_type, title="Storage Utilization"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=[],
    )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path, tmp_path: Path):
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)

    artifact_dir = tmp_path / "artifacts"
    isolated_store = ArtifactStore(base_dir=artifact_dir)
    monkeypatch.setattr(quick_hc_routes, "ArtifactStore", lambda: isolated_store)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c, migrated_db_path, isolated_store


# ── 1. ArtifactStore.delete_artifact ─────────────────────────────────────────

def test_delete_artifact_data(tmp_path: Path) -> None:
    store = ArtifactStore(base_dir=tmp_path / "artifacts")
    artifact = _minimal_artifact("storage_utilization")
    store.save_artifact(artifact)

    assert store.delete_artifact("storage_utilization") is True
    assert not (tmp_path / "artifacts" / "storage_utilization" / "latest.json").exists()


def test_delete_artifact_not_found(tmp_path: Path) -> None:
    store = ArtifactStore(base_dir=tmp_path / "artifacts")
    assert store.delete_artifact("nonexistent") is False


# ── 2. delete_subject db function ────────────────────────────────────────────

def test_delete_subject_ai_created(db: sqlite3.Connection) -> None:
    create_subject_from_proposal(db, _sample_proposal("storage_utilization"))

    result = delete_subject(db, "storage_utilization")

    assert result["deleted"] == "storage_utilization"
    assert result["versions_removed"] == 1
    assert get_subject(db, "storage_utilization") is None

    # All related rows removed
    assert db.execute(
        "SELECT COUNT(*) FROM subject_sections WHERE subject_id = 'storage_utilization'"
    ).fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM subject_sources WHERE subject_id = 'storage_utilization'"
    ).fetchone()[0] == 0


def test_delete_subject_system_blocked(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="system subjects cannot be deleted"):
        delete_subject(db, "security_assessment")
    assert get_subject(db, "security_assessment") is not None


def test_delete_subject_not_found(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="subject not found"):
        delete_subject(db, "nonexistent")


# ── 3. Route tests ────────────────────────────────────────────────────────────

def test_delete_route_success(client) -> None:
    flask_client, db_path, store = client

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_subject_from_proposal(conn, _sample_proposal("storage_utilization"))
    conn.close()

    store.save_artifact(_minimal_artifact("storage_utilization"))

    resp = flask_client.post(
        "/quick-hc/storage_utilization/delete",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/quick-hc")

    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row
    assert get_subject(conn2, "storage_utilization") is None
    conn2.close()

    assert not store.delete_artifact("storage_utilization")


def test_delete_route_flash_contains_title(client) -> None:
    flask_client, db_path, store = client

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_subject_from_proposal(conn, _sample_proposal("storage_utilization"))
    conn.close()

    resp = flask_client.post(
        "/quick-hc/storage_utilization/delete",
        follow_redirects=True,
    )
    assert b"Storage Utilization" in resp.data


def test_delete_route_system_blocked(client) -> None:
    flask_client, db_path, store = client

    resp = flask_client.post(
        "/quick-hc/security_assessment/delete",
        follow_redirects=False,
    )
    assert resp.status_code == 302

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    assert get_subject(conn, "security_assessment") is not None
    conn.close()


# ── 4. MCP tool ───────────────────────────────────────────────────────────────

def test_delete_mcp_tool(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path, tmp_path: Path) -> None:
    from cvhealthcheck.mcp import server as mcp_server

    artifact_dir = tmp_path / "artifacts"
    isolated_store = ArtifactStore(base_dir=artifact_dir)

    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(mcp_server, "get_db", open_db)
    monkeypatch.setattr(mcp_server, "ArtifactStore", lambda: isolated_store)

    # Create an ai-created subject and approve it
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_subject_from_proposal(conn, _sample_proposal("storage_utilization"))
    conn.close()

    before = mcp_server.list_subjects()
    ids_before = {s["subject_id"] for s in before}
    assert "storage_utilization" in ids_before

    result = mcp_server.delete_subject("storage_utilization")
    assert result["deleted"] == "storage_utilization"

    after = mcp_server.list_subjects()
    ids_after = {s["subject_id"] for s in after}
    assert "storage_utilization" not in ids_after
