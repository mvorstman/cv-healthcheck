"""Tests for the /api/auth/status endpoint.

This endpoint backs the Quick HC connection badge's periodic refresh.
window.IS_AUTHENTICATED is set server-side at page render time and goes
stale on long-lived sessions after token expiry; the badge polls this
endpoint every 60s (and on window focus) to stay accurate.
"""
from __future__ import annotations

from cvhealthcheck.auth.commvault_auth import SESSION_TOKEN_KEY
from cvhealthcheck.web.app import create_app


def test_api_auth_status_unauthenticated_returns_false() -> None:
    app = create_app()
    client = app.test_client()
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"authenticated": False}


def test_api_auth_status_authenticated_returns_true() -> None:
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"authenticated": True}


def test_api_auth_status_treats_empty_token_as_unauthenticated() -> None:
    # Defence-in-depth: an empty / whitespace-only session token must not
    # count as authenticated. get_current_token() returns None for those,
    # so is_authenticated() returns False.
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "   "
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}
