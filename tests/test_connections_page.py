"""Connections page (ADR-0008 B) — live status, connect link, disconnect.

The store is the real token_store (autouse-reset by conftest); no live CommServe call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cvhealthcheck import token_store
from cvhealthcheck.web.app import create_app


def _client():
    return create_app().test_client()


def test_disconnected_shows_reconnect_and_connect_link():
    body = _client().get("/connections").get_data(as_text=True)
    assert "Disconnected — reconnect" in body
    # Connect reuses /login, returning to /connections on success (no second login path).
    assert "/login?next=/connections" in body


def test_connected_shows_principal_and_disconnect_no_token():
    token_store.set_active_token("live-tok", principal="operator")
    body = _client().get("/connections").get_data(as_text=True)
    assert "Connected" in body
    assert "operator" in body                       # principal shown
    assert "/connections/disconnect" in body        # Disconnect action present
    assert "live-tok" not in body                    # the token is NEVER rendered


def test_expired_token_renders_as_reconnect_not_error():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    token_store.set_active_token("tok", expires_at=past)
    body = _client().get("/connections").get_data(as_text=True).lower()
    assert "reconnect" in body and "expired" in body   # worded as a reconnect


def test_disconnect_clears_store_and_redirects():
    token_store.set_active_token("live-tok", principal="operator")
    c = _client()
    resp = c.post("/connections/disconnect")
    assert resp.status_code == 302 and "/connections" in resp.headers["Location"]
    assert token_store.get_active_token() is None     # store cleared
    assert "Disconnected — reconnect" in c.get("/connections").get_data(as_text=True)


def test_target_shown_without_secrets(monkeypatch):
    monkeypatch.setenv("CV_BASE_URL", "https://192.168.182.129:4433")
    monkeypatch.setenv("CV_VERIFY_SSL", "false")
    token_store.set_active_token("live-tok", principal="operator")
    body = _client().get("/connections").get_data(as_text=True)
    assert "192.168.182.129:4433" in body            # read-only target URL
    assert "SSL verification" in body
    assert "live-tok" not in body                     # no token, no password
