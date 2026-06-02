"""Token-store (ADR-0008 component A) — single-slot, expiry-aware, thread-guarded.

Built but not yet wired into login/reads (that is a later brief); these exercise the
module's contract in isolation.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from cvhealthcheck import token_store


@pytest.fixture(autouse=True)
def _reset():
    token_store.clear_active_token()
    yield
    token_store.clear_active_token()


def test_set_then_get_returns_token():
    token_store.set_active_token("tok-123", principal="operator")
    assert token_store.get_active_token() == "tok-123"


def test_unset_status_is_disconnected():
    assert token_store.get_active_token() is None
    assert token_store.status() == {
        "state": "disconnected", "principal": None,
        "connected_at": None, "expires_at": None,
    }


def test_clear_then_get_is_none_and_status_disconnected():
    token_store.set_active_token("tok")
    token_store.clear_active_token()
    assert token_store.get_active_token() is None
    assert token_store.status()["state"] == "disconnected"


def test_expired_token_reads_none_and_status_expired():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    token_store.set_active_token("tok", expires_at=past, principal="op")
    assert token_store.get_active_token() is None          # dead token -> None, not stale
    st = token_store.status()
    assert st["state"] == "expired"                         # distinct from disconnected
    assert st["principal"] == "op"                          # metadata still visible


def test_future_expiry_is_connected():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token_store.set_active_token("tok", expires_at=future)
    assert token_store.get_active_token() == "tok"
    assert token_store.status()["state"] == "connected"


def test_metadata_roundtrips_through_status():
    future = datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
    token_store.set_active_token("tok", expires_at=future, principal="operator")
    st = token_store.status()
    assert st["state"] == "connected"
    assert st["principal"] == "operator"
    assert st["expires_at"] == "2026-12-31T23:59:00Z"      # ISO-8601 Z
    assert st["connected_at"].endswith("Z")                # set at store time


def test_expires_at_accepts_epoch_float():
    token_store.set_active_token("tok", expires_at=time.time() + 3600)
    assert token_store.get_active_token() == "tok"
    token_store.set_active_token("tok2", expires_at=time.time() - 5)
    assert token_store.get_active_token() is None


def test_overwrite_replaces_slot():
    token_store.set_active_token("first", principal="a")
    token_store.set_active_token("second", principal="b")
    assert token_store.get_active_token() == "second"
    assert token_store.status()["principal"] == "b"


# ── ADR-0008 A wiring: login populates the store, logout clears it ──

def test_set_current_token_populates_store_and_clear_empties_it():
    """`set_current_token` (the login chokepoint) ALSO fills the store; the
    `clear_current_token` chokepoint (logout + auto-clear paths) empties it."""
    from cvhealthcheck.web.app import create_app
    from cvhealthcheck.auth.commvault_auth import set_current_token, clear_current_token
    app = create_app()
    with app.test_request_context():
        set_current_token("live-tok", customer_id="default", username="operator")
        assert token_store.get_active_token() == "live-tok"
        st = token_store.status()
        assert st["state"] == "connected" and st["principal"] == "operator"

        clear_current_token()
        assert token_store.get_active_token() is None
        assert token_store.status()["state"] == "disconnected"


def test_set_current_token_leaves_session_cookie_writes_unchanged():
    """The wiring is an ADDITION — the session cookie still holds the token, customer,
    and username exactly as before (read seam not repointed this brief)."""
    from flask import session
    from cvhealthcheck.web.app import create_app
    from cvhealthcheck.auth.commvault_auth import (
        set_current_token, SESSION_TOKEN_KEY, SESSION_CUSTOMER_ID_KEY, SESSION_USERNAME_KEY,
    )
    app = create_app()
    with app.test_request_context():
        set_current_token("live-tok", customer_id="default", username="operator")
        assert session[SESSION_TOKEN_KEY] == "live-tok"
        assert session[SESSION_CUSTOMER_ID_KEY] == "default"
        assert session[SESSION_USERNAME_KEY] == "operator"
