"""Tests for the customer CRUD UI routes (ADR 0002 phase 3)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import cvhealthcheck.web.routes.customers as customers_routes
from cvhealthcheck.web.app import create_app


@pytest.fixture()
def customers_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Flask test client wired up against an isolated migrated DB."""
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(customers_routes, "get_db", open_db)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c, migrated_db_path


def _has_default_customer(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM customers WHERE customer_id = 'default'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _delete_default_project(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM projects WHERE project_id = 'default'")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------


def test_list_renders_default_customer(customers_client) -> None:
    client, _db = customers_client
    r = client.get("/customers")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Customers" in body
    assert "Default" in body
    assert "+ New customer" in body


def test_list_shows_project_count(customers_client) -> None:
    client, db_path = customers_client
    r = client.get("/customers")
    body = r.get_data(as_text=True)
    # Default customer has the seeded Default project → count 1.
    assert ">1<" in body or ">1\n" in body or "1</td>" in body, \
        "expected project_count cell for Default to show 1"


# ---------------------------------------------------------------------------
# Create form
# ---------------------------------------------------------------------------


def test_create_form_get_renders_empty(customers_client) -> None:
    client, _ = customers_client
    r = client.get("/customers/new")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "New customer" in body
    assert 'value=""' in body or 'value=""\n' in body  # empty name input


def test_create_form_post_valid_creates_and_redirects(customers_client) -> None:
    client, db_path = customers_client
    r = client.post(
        "/customers/new",
        data={
            "customer_name": "Acme Corp",
            "commcell_id": "cs-001",
            "notes": "Test notes",
        },
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/customers")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT customer_id, customer_name, commcell_id, notes"
            " FROM customers WHERE customer_name = 'Acme Corp'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "acme_corp"
    assert row[2] == "cs-001"
    assert row[3] == "Test notes"


def test_create_form_post_empty_name_rerenders_with_error(customers_client) -> None:
    client, _ = customers_client
    r = client.post("/customers/new", data={"customer_name": ""})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Customer name is required" in body


def test_create_slugify_collision_appends_disambiguator(customers_client) -> None:
    client, db_path = customers_client
    client.post("/customers/new", data={"customer_name": "Acme"})
    client.post("/customers/new", data={"customer_name": "Acme"})
    conn = sqlite3.connect(str(db_path))
    try:
        ids = {
            row[0]
            for row in conn.execute(
                "SELECT customer_id FROM customers WHERE customer_name = 'Acme'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert ids == {"acme", "acme_2"}


# ---------------------------------------------------------------------------
# Edit form
# ---------------------------------------------------------------------------


def test_edit_form_get_prepopulates_fields(customers_client) -> None:
    client, _ = customers_client
    r = client.get("/customers/default/edit")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Edit customer" in body
    assert 'value="Default"' in body


def test_edit_form_get_returns_404_when_unknown(customers_client) -> None:
    client, _ = customers_client
    r = client.get("/customers/does_not_exist/edit")
    assert r.status_code == 404


def test_edit_form_post_updates_row(customers_client) -> None:
    client, db_path = customers_client
    r = client.post(
        "/customers/default/edit",
        data={
            "customer_name": "Renamed Default",
            "commcell_id": "cs-999",
            "notes": "Updated",
        },
    )
    assert r.status_code == 302
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT customer_name, commcell_id, notes"
            " FROM customers WHERE customer_id = 'default'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Renamed Default", "cs-999", "Updated")


def test_edit_form_post_empty_name_rerenders_with_error(customers_client) -> None:
    client, _ = customers_client
    r = client.post("/customers/default/edit", data={"customer_name": ""})
    assert r.status_code == 200
    assert "Customer name is required" in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Delete (with strict project-count guard)
# ---------------------------------------------------------------------------


def test_delete_confirm_get_renders_when_no_projects(customers_client) -> None:
    client, db_path = customers_client
    _delete_default_project(db_path)

    r = client.get("/customers/default/delete")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Delete permanently" in body
    assert "Cannot delete" not in body


def test_delete_confirm_get_shows_block_message_when_has_projects(customers_client) -> None:
    client, _ = customers_client
    # Default customer has the seeded Default project still in place.
    r = client.get("/customers/default/delete")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Cannot delete" in body
    assert "Delete (blocked)" in body


def test_delete_post_succeeds_when_no_projects(customers_client) -> None:
    client, db_path = customers_client
    _delete_default_project(db_path)

    r = client.post("/customers/default/delete")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/customers")
    assert not _has_default_customer(db_path)


def test_delete_post_blocked_when_has_projects(customers_client) -> None:
    client, db_path = customers_client
    # Default customer still has the seeded Default project.
    r = client.post("/customers/default/delete")
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    assert "Cannot delete" in body
    # Customer row still in place.
    assert _has_default_customer(db_path)


def test_delete_get_returns_404_when_unknown(customers_client) -> None:
    client, _ = customers_client
    r = client.get("/customers/does_not_exist/delete")
    assert r.status_code == 404
