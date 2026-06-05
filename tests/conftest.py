"""
Global test fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_canonical_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Prevent tests from touching the real canonical artifact store on disk.

    Monkeypatches the ArtifactStore module's _DEFAULT_BASE_DIR so any
    ArtifactStore(customer_id, project_id) constructed without an explicit
    base_dir writes under tmp_path. Tests that explicitly pass base_dir
    are unaffected.
    """
    import cvhealthcheck.artifacts.store as store_module
    # Mirror the production directory name ('artifacts' under 'catalog' under
    # 'data') so tests that assert on the path structure still pass.
    monkeypatch.setattr(
        store_module, "_DEFAULT_BASE_DIR", tmp_path / "data" / "catalog" / "artifacts"
    )


@pytest.fixture()
def migrated_db_path(tmp_path: Path) -> Path:
    """Isolated SQLite database with all migrations applied (including seed data)."""
    from cvhealthcheck.db.migrations import run_migrations
    path = tmp_path / "test.db"
    run_migrations(db_path=path)
    return path


@pytest.fixture(autouse=True)
def _reset_token_store():
    """Clear the process-global held-token store around every test (ADR-0008 B).

    Tests now establish auth by populating the store, so a token set in one test must
    not leak into the next.
    """
    from cvhealthcheck import token_store
    token_store.clear_active_token()
    yield
    token_store.clear_active_token()


@pytest.fixture()
def authenticate():
    """Establish an authenticated session the ADR-0008 way: the held CommServe token
    goes to the in-process store; the non-secret customer/username markers go to the
    session cookie. Replaces the old ``session[SESSION_TOKEN_KEY] = ...`` poke — the
    cookie no longer carries the token.
    """
    from cvhealthcheck import token_store
    from cvhealthcheck.auth.commvault_auth import (
        SESSION_CUSTOMER_ID_KEY,
        SESSION_USERNAME_KEY,
    )

    def _auth(client, *, token: str = "test-token", customer_id=None, username=None):
        token_store.set_active_token(token, principal=username)
        if customer_id is not None or username is not None:
            with client.session_transaction() as sess:
                if customer_id is not None:
                    sess[SESSION_CUSTOMER_ID_KEY] = customer_id
                if username is not None:
                    sess[SESSION_USERNAME_KEY] = username

    return _auth
