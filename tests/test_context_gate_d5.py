"""D5 — Context Integrity enforcement primitive (ADR-0015).

require_active_context() returns (customer_id, project_id) ONLY when the
operator explicitly selected it this session, and raises the typed
NoExplicitContextError otherwise. It never falls through to the Default
project — the read-path fallback can never satisfy a write.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.context import NoExplicitContextError
from cvhealthcheck.web.active_project import (
    get_active_project,
    require_active_context,
    resolve_default_project,
    set_active_project,
)
from cvhealthcheck.web.app import create_app


@pytest.fixture()
def app():
    return create_app()


def test_require_raises_outside_request_context():
    with pytest.raises(NoExplicitContextError):
        require_active_context()


def test_require_raises_in_request_without_selection(app):
    """The Default project EXISTS (migrations seed it) — and must still not
    satisfy the write primitive. Explicit means session-selected, full stop."""
    with app.test_request_context("/"):
        with pytest.raises(NoExplicitContextError):
            require_active_context()


def test_require_returns_pair_after_explicit_selection(app):
    with app.test_request_context("/"):
        set_active_project("cust_x", "proj_y")
        assert require_active_context() == ("cust_x", "proj_y")


def test_require_rejects_malformed_session_entry(app):
    from flask import session
    with app.test_request_context("/"):
        session["active_project"] = {"customer_id": "cust_x"}  # no project_id
        with pytest.raises(NoExplicitContextError):
            require_active_context()


def test_read_path_fallback_unchanged(app, migrated_db_path):
    """get_active_project (READ) keeps the Default fallback — the split is
    write-only enforcement, not a read regression."""
    import sqlite3
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    try:
        with app.test_request_context("/"):
            assert get_active_project(db) == resolve_default_project(db)
            set_active_project("cust_x", "proj_y")
            assert get_active_project(db) == ("cust_x", "proj_y")
    finally:
        db.close()


def test_error_message_is_actionable():
    err = NoExplicitContextError()
    assert "select a customer" in str(err).lower()
