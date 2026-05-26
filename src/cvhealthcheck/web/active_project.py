"""Active-project session helper — phase 2 of ADR 0002.

The "active project" is the customer/project the consultant is currently
working on. It lives in the Flask session (server-side, cookie-backed).
Phase 2 only needs the read/write/fallback plumbing; the UI for switching
between projects lands in phase 4.

When no active project is set in the session, the fallback path resolves
to the "Default" customer's "Default" project — both auto-created by
migration 0005. In a normally-migrated database both always exist, so
this fallback is always satisfiable; the helper raises a clear error if
something has corrupted that invariant.

See docs/adr/0002-customer-and-project-entities.md for the design
rationale (active-project session state, first-run experience).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import has_request_context, session

from cvhealthcheck.db import get_db

_SESSION_KEY = "active_project"

_DEFAULT_CUSTOMER_ID = "default"


class ActiveProjectMissingError(RuntimeError):
    """Raised when the Default customer/project fallback is unavailable.

    In production this should never fire — migration 0005 guarantees the
    Default customer and Default project exist. It fires only on a
    corrupted or partially-migrated database.
    """


def get_active_project(db: sqlite3.Connection | None = None) -> tuple[str, str]:
    """Return (customer_id, project_id) for the active project.

    Reads the Flask session first. If nothing is set there (no request
    context, or the user hasn't switched projects yet), falls back to
    the Default customer's earliest-created project.
    """
    if has_request_context():
        stored = session.get(_SESSION_KEY)
        if isinstance(stored, dict):
            customer_id = stored.get("customer_id")
            project_id = stored.get("project_id")
            if isinstance(customer_id, str) and isinstance(project_id, str):
                return customer_id, project_id

    return resolve_default_project(db)


def set_active_project(customer_id: str, project_id: str) -> None:
    """Persist the active project in the Flask session.

    Requires a request context. Raises RuntimeError if called outside
    one (the session is request-scoped).
    """
    if not has_request_context():
        raise RuntimeError("set_active_project requires a Flask request context")
    session[_SESSION_KEY] = {
        "customer_id": customer_id,
        "project_id": project_id,
    }


def clear_active_project() -> None:
    """Remove the active project from the session (falls back to Default)."""
    if has_request_context():
        session.pop(_SESSION_KEY, None)


def resolve_default_project(db: sqlite3.Connection | None = None) -> tuple[str, str]:
    """Return (customer_id, project_id) for the Default customer's
    earliest-created project.

    Used as the session-empty fallback by get_active_project, and as the
    direct lookup from non-request contexts (MCP staging, tests, CLI).
    Pass an explicit db connection to avoid an implicit get_db() call.
    """
    own_db = db is None
    if own_db:
        db = get_db()
    try:
        row = db.execute(
            "SELECT project_id, customer_id"
            " FROM projects"
            " WHERE customer_id = ?"
            " ORDER BY created_at ASC, project_id ASC"
            " LIMIT 1",
            (_DEFAULT_CUSTOMER_ID,),
        ).fetchone()
    finally:
        if own_db:
            db.close()

    if row is None:
        raise ActiveProjectMissingError(
            f"No project found for default customer '{_DEFAULT_CUSTOMER_ID}'. "
            "Migration 0005 should have created one — run migrations or "
            "check schema_migrations table state."
        )
    # sqlite3.Row supports both index and key access; cope with either.
    if isinstance(row, sqlite3.Row):
        return row["customer_id"], row["project_id"]
    return _value_at(row, "customer_id", 1), _value_at(row, "project_id", 0)


def _value_at(row: Any, key: str, fallback_index: int) -> str:
    try:
        return row[key]
    except (KeyError, TypeError):
        return row[fallback_index]
