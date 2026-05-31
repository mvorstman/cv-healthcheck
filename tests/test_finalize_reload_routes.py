"""Route tests for the finalize and reload UI (ADR 0002 phase 5)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cvhealthcheck.web.routes.customers as customers_routes
import cvhealthcheck.web.routes.projects as projects_routes
from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.web.app import create_app


@pytest.fixture()
def finz_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Flask test client wired to an isolated migrated DB. The active-
    project session starts empty; tests choose their working project via
    the create-project handler which auto-activates, or via direct
    session manipulation.
    """
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(customers_routes, "get_db", open_db)
    monkeypatch.setattr(projects_routes, "get_db", open_db)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c, migrated_db_path


def _make_artifact(subject_id: str,
                   status: ArtifactStatus = ArtifactStatus.good) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=datetime.now(timezone.utc),
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id=subject_id, title="Test"),
        summary=ArtifactSummary(status=status),
        sections=[],
    )


def _save(customer_id: str, project_id: str, subject_id: str,
          status: ArtifactStatus = ArtifactStatus.good) -> None:
    ArtifactStore(customer_id, project_id).save_artifact(
        _make_artifact(subject_id, status)
    )


def _create_project(client, project_number: str) -> str:
    """Use the create-project handler to set up state and return the
    slugified project_id."""
    r = client.post(
        "/customers/default/projects/new", data={"project_number": project_number}
    )
    assert r.status_code == 302
    return r.headers["Location"].rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Finalize UI
# ---------------------------------------------------------------------------


def test_finalize_get_shows_confirmation_when_artifacts_exist(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-1")
    _save("default", pid, "security_assessment")

    r = client.get(f"/customers/default/projects/{pid}/finalize")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Finalize as #1" in body
    assert "security_assessment" in body
    assert "Finalize (blocked)" not in body


def test_finalize_get_shows_block_when_working_empty(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-EMPTY")

    r = client.get(f"/customers/default/projects/{pid}/finalize")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "no artifacts collected" in body
    assert "Finalize (blocked)" in body


def test_finalize_post_creates_finalization_and_redirects(finz_client) -> None:
    client, db_path = finz_client
    pid = _create_project(client, "P-1")
    _save("default", pid, "security_assessment")

    r = client.post(
        f"/customers/default/projects/{pid}/finalize", follow_redirects=False
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/customers/default/projects/{pid}")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT finalization_number FROM finalizations WHERE project_id = ?",
            (pid,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 1

    # Follow the redirect to confirm the flash made it through.
    r = client.get(r.headers["Location"])
    assert "Finalized as #1" in r.get_data(as_text=True)


def test_finalize_post_on_empty_working_returns_block(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-EMPTY")

    r = client.post(f"/customers/default/projects/{pid}/finalize")
    assert r.status_code == 400
    assert "Cannot finalize" in r.get_data(as_text=True)


def test_finalize_twice_produces_one_then_two(finz_client) -> None:
    client, db_path = finz_client
    pid = _create_project(client, "P-1")
    _save("default", pid, "security_assessment")

    client.post(f"/customers/default/projects/{pid}/finalize")
    client.post(f"/customers/default/projects/{pid}/finalize")

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT finalization_number FROM finalizations"
            " WHERE project_id = ? ORDER BY finalization_number",
            (pid,),
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == [1, 2]


# ---------------------------------------------------------------------------
# Reload UI
# ---------------------------------------------------------------------------


def test_reload_get_shows_soft_warning_when_working_matches(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-R1")
    _save("default", pid, "security_assessment")
    client.post(f"/customers/default/projects/{pid}/finalize")

    r = client.get(f"/customers/default/projects/{pid}/reload")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "currently matches finalization" in body
    # Firm-warning copy not present.
    assert "discard" not in body or "discarded" not in body
    assert "Reload (blocked)" not in body


def test_reload_get_shows_firm_warning_when_working_differs(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-R2")
    _save("default", pid, "security_assessment", status=ArtifactStatus.good)
    client.post(f"/customers/default/projects/{pid}/finalize")
    _save("default", pid, "security_assessment", status=ArtifactStatus.warning)

    r = client.get(f"/customers/default/projects/{pid}/reload")
    body = r.get_data(as_text=True)
    assert "discard" in body
    assert "security_assessment" in body


def test_reload_get_shows_block_when_no_finalizations(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-R3")
    _save("default", pid, "security_assessment")

    r = client.get(f"/customers/default/projects/{pid}/reload")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "no finalizations exist yet" in body
    assert "Reload (blocked)" in body


def test_reload_post_restores_working_from_latest(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-R4")
    _save("default", pid, "security_assessment", status=ArtifactStatus.good)
    client.post(f"/customers/default/projects/{pid}/finalize")
    _save("default", pid, "security_assessment", status=ArtifactStatus.warning)

    r = client.post(f"/customers/default/projects/{pid}/reload", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/customers/default/projects/{pid}")

    loaded = ArtifactStore("default", pid).load_latest_artifact("security_assessment")
    assert loaded.summary.status == ArtifactStatus.good


def test_reload_post_blocked_when_no_finalizations(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-R5")
    _save("default", pid, "security_assessment")

    r = client.post(f"/customers/default/projects/{pid}/reload")
    assert r.status_code == 400
    assert "Cannot reload" in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Finalizations list on project detail
# ---------------------------------------------------------------------------


def test_project_detail_lists_finalizations_descending(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-LIST")
    _save("default", pid, "security_assessment")
    client.post(f"/customers/default/projects/{pid}/finalize")
    client.post(f"/customers/default/projects/{pid}/finalize")
    client.post(f"/customers/default/projects/{pid}/finalize")

    r = client.get(f"/customers/default/projects/{pid}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # All three finalization numbers visible; descending order shows
    # 3 before 1 in the rendered HTML.
    assert ">3<" in body
    assert ">2<" in body
    assert ">1<" in body
    assert body.index(">3<") < body.index(">2<") < body.index(">1<")


# ---------------------------------------------------------------------------
# Project deletion regression — phase 4 guard against finalized projects
# still works once finalizations exist via the new finalize UI.
# ---------------------------------------------------------------------------


def test_project_delete_blocked_after_real_finalization(finz_client) -> None:
    client, _ = finz_client
    pid = _create_project(client, "P-DEL")
    _save("default", pid, "security_assessment")
    client.post(f"/customers/default/projects/{pid}/finalize")

    r = client.get(f"/customers/default/projects/{pid}/delete")
    body = r.get_data(as_text=True)
    assert "Cannot delete" in body
    assert "Delete (blocked)" in body

    r = client.post(f"/customers/default/projects/{pid}/delete")
    assert r.status_code == 400
