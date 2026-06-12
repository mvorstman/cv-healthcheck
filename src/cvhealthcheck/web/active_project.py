"""Active-project session helper — phase 2 of ADR 0002, hardened by D5.

The "active project" is the customer/project the consultant is currently
working on. It lives in the Flask session (server-side, cookie-backed).

READ/WRITE SPLIT (ADR-0015 D5 — Context Integrity invariant):

- READ paths may use ``get_active_project`` / ``resolve_default_project``:
  when no active project is set in the session, reads fall back to the
  "Default" customer's earliest project (both auto-created by migration
  0005) so the workspace, status displays, and canonical reads keep
  rendering.
- WRITE paths must use ``require_active_context()``: it returns the pair
  ONLY when the operator explicitly selected it this session, and raises
  :class:`NoExplicitContextError` otherwise. It never falls through to
  ``resolve_default_project`` — the fallback can NEVER satisfy a write.
  Absence of explicit selection is an error, never a silent default.

See docs/adr/0002-customer-and-project-entities.md (entities, session
state) and docs/adr/0015-template-profile-runtime.md (the invariant).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from flask import has_request_context, session

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.context import NoExplicitContextError
from cvhealthcheck.db import get_db
from cvhealthcheck.db.customers import get_customer

_SESSION_KEY = "active_project"

_DEFAULT_CUSTOMER_ID = "default"


class ActiveProjectMissingError(RuntimeError):
    """Raised when the Default customer/project fallback is unavailable.

    In production this should never fire — migration 0005 guarantees the
    Default customer and Default project exist. It fires only on a
    corrupted or partially-migrated database.
    """


def _explicit_context() -> tuple[str, str] | None:
    """The session's explicitly selected (customer_id, project_id), or None.

    The single place that decides "explicit": a well-formed session entry
    written by ``set_active_project``. No DB, no fallback."""
    if not has_request_context():
        return None
    stored = session.get(_SESSION_KEY)
    if isinstance(stored, dict):
        customer_id = stored.get("customer_id")
        project_id = stored.get("project_id")
        if isinstance(customer_id, str) and isinstance(project_id, str):
            return customer_id, project_id
    return None


def get_active_project(db: sqlite3.Connection | None = None) -> tuple[str, str]:
    """Return (customer_id, project_id) for the active project — READ paths.

    Reads the Flask session first. If nothing is set there (no request
    context, or the user hasn't switched projects yet), falls back to
    the Default customer's earliest-created project. Write paths must use
    :func:`require_active_context` instead — the fallback here can never
    authorize a write.
    """
    explicit = _explicit_context()
    if explicit is not None:
        return explicit
    return resolve_default_project(db)


def require_active_context() -> tuple[str, str]:
    """Return the explicitly selected (customer_id, project_id) — WRITE paths.

    The D5 enforcement primitive: succeeds ONLY when the operator selected
    a customer/project this session (``set_active_project``). Raises
    :class:`NoExplicitContextError` otherwise — it never consults
    ``resolve_default_project``, so the Default fallback cannot silently
    absorb a customer-data write.
    """
    explicit = _explicit_context()
    if explicit is None:
        raise NoExplicitContextError()
    return explicit


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


def get_active_customer(db: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return the customer row backing the active project.

    Chains get_active_project → get_customer. Used by the CommCell auth
    flow and the collect handler under ADR 0003 phase 3: both need the
    active customer's commcell_hostname, commcell_id, and customer_name.
    Raises ActiveProjectMissingError if the customer row is missing (the
    project FK should make this impossible in a healthy DB).
    """
    customer_id, _ = get_active_project(db)
    customer = get_customer(customer_id)
    if customer is None:
        raise ActiveProjectMissingError(
            f"Active project references customer_id={customer_id!r} but no "
            "matching row exists in customers. The projects.customer_id FK "
            "should make this impossible — check DB integrity."
        )
    return customer


def make_active_project_store(db: sqlite3.Connection | None = None) -> ArtifactStore:
    """Construct an ArtifactStore scoped to the active project.

    Resolves the active (customer_id, project_id) via get_active_project
    and returns a fresh ArtifactStore. Web routes call this when they
    need to read or write artifacts.
    """
    customer_id, project_id = get_active_project(db)
    return ArtifactStore(customer_id, project_id)

