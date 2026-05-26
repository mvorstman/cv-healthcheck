"""Tests for the project CRUD UI routes + active-project API (ADR 0002 phase 4)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import cvhealthcheck.web.routes.customers as customers_routes
import cvhealthcheck.web.routes.projects as projects_routes
from cvhealthcheck.web.app import create_app


@pytest.fixture()
def projects_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Flask test client wired up against an isolated migrated DB.

    Patches get_db in both the customers and projects route modules so
    all the routes used in phase-4 tests share the same db.
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


def _insert_finalization(db_path: Path, project_id: str, number: int = 1) -> None:
    """Directly insert a finalization row. Phase 5 will build the finalize
    action; phase 4 tests that need finalization state set it up manually.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO finalizations"
            " (finalization_id, project_id, finalization_number, finalized_at)"
            " VALUES (?, ?, ?, ?)",
            (f"finz_{project_id}_{number}", project_id, number, "2026-05-27T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def _create_customer(db_path: Path, customer_id: str, name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO customers"
            " (customer_id, customer_name, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (customer_id, name, "2026-05-27T00:00:00Z", "2026-05-27T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Customer detail view (step 1)
# ---------------------------------------------------------------------------


def test_customer_detail_lists_projects(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/default")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Default" in body
    # The seeded Default project should appear in the projects table.
    assert "DEFAULT" in body
    # The Active badge renders for the default project (it's the session fallback).
    assert "cust-active-badge" in body


def test_customer_detail_returns_404_when_unknown(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/does_not_exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Project create (step 2)
# ---------------------------------------------------------------------------


def test_project_create_get_renders_empty(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/default/projects/new")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "New project" in body


def test_project_create_post_valid_creates_and_redirects(projects_client) -> None:
    client, db_path = projects_client
    with client.session_transaction() as sess:
        sess.clear()
    r = client.post(
        "/customers/default/projects/new",
        data={"project_number": "P-001", "ticket_reference": "TD-42"},
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/customers/default/projects/p_001")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT project_id, project_number, ticket_reference"
            " FROM projects WHERE project_number = 'P-001'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "p_001"
    assert row[2] == "TD-42"

    # The new project should be set as active.
    with client.session_transaction() as sess:
        assert sess.get("active_project") == {
            "customer_id": "default",
            "project_id": "p_001",
        }


def test_project_create_post_empty_number_rerenders(projects_client) -> None:
    client, _ = projects_client
    r = client.post("/customers/default/projects/new", data={"project_number": ""})
    assert r.status_code == 200
    assert "required" in r.get_data(as_text=True)


def test_project_create_post_duplicate_same_customer_rejects(projects_client) -> None:
    client, _ = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "DUP"})
    r = client.post("/customers/default/projects/new", data={"project_number": "DUP"})
    assert r.status_code == 200
    assert "already exists for this customer" in r.get_data(as_text=True)


def test_project_create_post_duplicate_different_customer_succeeds(projects_client) -> None:
    client, db_path = projects_client
    _create_customer(db_path, "acme", "Acme Corp")
    client.post("/customers/default/projects/new", data={"project_number": "DUP"})
    r = client.post("/customers/acme/projects/new", data={"project_number": "DUP"})
    assert r.status_code == 302


# ---------------------------------------------------------------------------
# Project detail (step 3)
# ---------------------------------------------------------------------------


def test_project_detail_renders_metadata(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/default/projects/default")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "DEFAULT" in body
    assert "Project ID" in body
    assert "Finalizations" in body
    assert "No finalizations yet" in body


def test_project_detail_shows_active_badge_when_active(projects_client) -> None:
    client, _ = projects_client
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "default", "project_id": "default"}
    r = client.get("/customers/default/projects/default")
    body = r.get_data(as_text=True)
    assert "cust-active-badge" in body
    assert "Set as active" not in body


def test_project_detail_shows_set_active_when_not_active(projects_client) -> None:
    client, _ = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "OTHER"})
    # Reset active back to default so OTHER is non-active.
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "default", "project_id": "default"}
    r = client.get("/customers/default/projects/other")
    body = r.get_data(as_text=True)
    assert "Set as active" in body


def test_project_detail_returns_404_when_unknown(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/default/projects/no_such_project")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Project edit (step 4)
# ---------------------------------------------------------------------------


def test_project_edit_get_prepopulates(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/customers/default/projects/default/edit")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Edit project" in body
    assert 'value="DEFAULT"' in body


def test_project_edit_post_updates_row(projects_client) -> None:
    client, db_path = projects_client
    r = client.post(
        "/customers/default/projects/default/edit",
        data={"project_number": "RENAMED", "ticket_reference": "TD-99"},
    )
    assert r.status_code == 302
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT project_number, ticket_reference"
            " FROM projects WHERE project_id = 'default'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("RENAMED", "TD-99")


def test_project_edit_post_collision_rejects(projects_client) -> None:
    client, _ = projects_client
    # Create a second project for the same customer.
    client.post("/customers/default/projects/new", data={"project_number": "OTHER"})
    # Try to rename default → OTHER.
    r = client.post(
        "/customers/default/projects/default/edit",
        data={"project_number": "OTHER"},
    )
    assert r.status_code == 200
    assert "already exists for this customer" in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Project delete (step 5)
# ---------------------------------------------------------------------------


def test_project_delete_get_no_finalizations_shows_confirm(projects_client) -> None:
    client, _ = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "DEL"})
    r = client.get("/customers/default/projects/del/delete")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Delete permanently" in body
    assert "Cannot delete" not in body


def test_project_delete_get_with_finalizations_shows_blocked(projects_client) -> None:
    client, db_path = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "FINAL"})
    _insert_finalization(db_path, "final", number=1)
    r = client.get("/customers/default/projects/final/delete")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Cannot delete" in body
    assert "Delete (blocked)" in body


def test_project_delete_post_succeeds_when_no_finalizations(projects_client) -> None:
    client, db_path = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "GONE"})
    r = client.post("/customers/default/projects/gone/delete")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/customers/default")
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE project_id = 'gone'"
        ).fetchone()
    finally:
        conn.close()
    assert row is None


def test_project_delete_post_blocked_when_finalizations_exist(projects_client) -> None:
    client, db_path = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "STAY"})
    _insert_finalization(db_path, "stay", number=1)
    r = client.post("/customers/default/projects/stay/delete")
    assert r.status_code == 400
    assert "Cannot delete" in r.get_data(as_text=True)


def test_project_delete_falls_back_to_default_when_deleting_active(projects_client) -> None:
    client, _ = projects_client
    # Create a new project (auto-activates) then delete it.
    client.post("/customers/default/projects/new", data={"project_number": "TEMP"})
    with client.session_transaction() as sess:
        assert sess.get("active_project") == {
            "customer_id": "default",
            "project_id": "temp",
        }
    client.post("/customers/default/projects/temp/delete")
    with client.session_transaction() as sess:
        assert sess.get("active_project") == {
            "customer_id": "default",
            "project_id": "default",
        }


# ---------------------------------------------------------------------------
# Active-project API (step 6)
# ---------------------------------------------------------------------------


def test_api_active_project_get_returns_current(projects_client) -> None:
    client, _ = projects_client
    r = client.get("/api/active-project")
    assert r.status_code == 200
    data = r.get_json()
    assert data["active"]["customer_id"] == "default"
    assert data["active"]["project_id"] == "default"
    assert data["active"]["customer_name"] == "Default"
    assert data["active"]["project_number"] == "DEFAULT"
    assert isinstance(data["customers"], list)


def test_api_active_project_post_switches_active(projects_client) -> None:
    client, _ = projects_client
    client.post("/customers/default/projects/new", data={"project_number": "SWITCH"})
    # Switch back to default explicitly.
    r = client.post(
        "/api/active-project",
        data={"customer_id": "default", "project_id": "default"},
    )
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess["active_project"]["project_id"] == "default"


def test_api_active_project_post_invalid_pair_returns_400(projects_client) -> None:
    client, _ = projects_client
    r = client.post(
        "/api/active-project",
        data={"customer_id": "default", "project_id": "does_not_exist"},
    )
    assert r.status_code == 400
    assert "No project" in r.get_json()["error"]


def test_api_active_project_post_empty_returns_400(projects_client) -> None:
    client, _ = projects_client
    r = client.post("/api/active-project", data={})
    assert r.status_code == 400


def test_api_active_project_post_with_redirect_to_returns_302(projects_client) -> None:
    client, _ = projects_client
    r = client.post(
        "/api/active-project",
        data={
            "customer_id": "default",
            "project_id": "default",
            "redirect_to": "/customers",
        },
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/customers")
