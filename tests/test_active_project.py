"""Tests for the active-project session helper (phase 2 of ADR 0002)."""
from __future__ import annotations

from pathlib import Path

import pytest

from cvhealthcheck.web.active_project import (
    ActiveProjectMissingError,
    clear_active_project,
    get_active_project,
    resolve_default_project,
    set_active_project,
)
from cvhealthcheck.web.app import create_app


def test_resolve_default_returns_seeded_default_project(migrated_db_path: Path) -> None:
    import sqlite3
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    try:
        customer_id, project_id = resolve_default_project(conn)
        assert customer_id == "default"
        assert project_id == "default"
    finally:
        conn.close()


def test_resolve_default_raises_when_default_project_missing(tmp_path: Path) -> None:
    import sqlite3
    from cvhealthcheck.db.migrations import run_migrations
    db_path = tmp_path / "no_default.db"
    run_migrations(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("DELETE FROM projects WHERE customer_id = 'default'")
        conn.commit()
        with pytest.raises(ActiveProjectMissingError):
            resolve_default_project(conn)
    finally:
        conn.close()


def test_get_active_project_returns_default_when_session_empty() -> None:
    app = create_app()
    with app.test_request_context("/"):
        customer_id, project_id = get_active_project()
        assert customer_id == "default"
        assert project_id == "default"


def test_get_active_project_returns_session_value_when_set() -> None:
    app = create_app()
    with app.test_request_context("/"):
        set_active_project("acme_corp", "p_2026_042")
        assert get_active_project() == ("acme_corp", "p_2026_042")


def test_clear_active_project_restores_default() -> None:
    app = create_app()
    with app.test_request_context("/"):
        set_active_project("acme_corp", "p_2026_042")
        assert get_active_project() == ("acme_corp", "p_2026_042")
        clear_active_project()
        assert get_active_project() == ("default", "default")


def test_set_active_project_outside_request_context_raises() -> None:
    with pytest.raises(RuntimeError):
        set_active_project("acme_corp", "p_2026_042")
