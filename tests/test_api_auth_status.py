"""Tests for the /api/auth/status endpoint.

This endpoint backs the Quick HC connection badge's periodic refresh.
window.IS_AUTHENTICATED is set server-side at page render time and goes
stale on long-lived sessions after token expiry; the badge polls this
endpoint every 60s (and on window focus) to stay accurate.
"""
from __future__ import annotations

from cvhealthcheck.auth.commvault_auth import (
    SESSION_CUSTOMER_ID_KEY,
    SESSION_TOKEN_KEY,
    SESSION_USERNAME_KEY,
)
from cvhealthcheck.web.app import create_app


def test_api_auth_status_unauthenticated_returns_false_and_no_username() -> None:
    app = create_app()
    client = app.test_client()
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {
        "authenticated": False,
        "authenticated_for_active": False,
        "username": None,
    }


def test_api_auth_status_authenticated_returns_true_and_username() -> None:
    # Token present but not bound to the active customer, so the Collect-gate
    # flag authenticated_for_active stays False even though authenticated is True.
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"
        session[SESSION_USERNAME_KEY] = "alice"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {
        "authenticated": True,
        "authenticated_for_active": False,
        "username": "alice",
    }


def test_api_auth_status_authenticated_without_username_returns_null() -> None:
    # Legacy sessions created before SESSION_USERNAME_KEY was added had only
    # the token. The endpoint must still respond cleanly with username=None
    # rather than crashing or omitting the field.
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.get_json() == {
        "authenticated": True,
        "authenticated_for_active": False,
        "username": None,
    }


def test_api_auth_status_token_bound_to_active_customer_sets_for_active() -> None:
    # When the session token is bound to the active customer, the Collect gate
    # is satisfied — authenticated_for_active is True, so REST Collect proceeds
    # without opening the connect modal. The default active customer is "default".
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"
        session[SESSION_USERNAME_KEY] = "alice"
        session[SESSION_CUSTOMER_ID_KEY] = "default"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    body = response.get_json()
    assert body["authenticated"] is True
    assert body["authenticated_for_active"] is True


def test_api_auth_status_treats_empty_token_as_unauthenticated() -> None:
    # Defence-in-depth: an empty / whitespace-only session token must not
    # count as authenticated. get_current_token() returns None for those,
    # so is_authenticated() returns False.
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "   "
        session[SESSION_USERNAME_KEY] = "alice"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    # username is gated on the authenticated flag, so it must be None here.
    assert response.get_json() == {
        "authenticated": False,
        "authenticated_for_active": False,
        "username": None,
    }


def test_logout_post_clears_session_and_status_returns_unauthenticated() -> None:
    """End-to-end signout contract used by submitSignOut() in quick_hc.js.

    1. Start with a session that has both token and username.
    2. POST /logout — expect a 302 redirect to /login (this is what
       submitSignOut() treats as success).
    3. Hit /api/auth/status — expect authenticated=False, username=None.
       Both session keys must have been cleared by clear_current_token().
    """
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"
        session[SESSION_USERNAME_KEY] = "alice"

    logout_response = client.post("/logout")
    assert logout_response.status_code == 302
    assert "/login" in logout_response.headers["Location"]

    status_response = client.get("/api/auth/status")
    assert status_response.status_code == 200
    assert status_response.get_json() == {
        "authenticated": False,
        "authenticated_for_active": False,
        "username": None,
    }

    with client.session_transaction() as session:
        assert SESSION_TOKEN_KEY not in session
        assert SESSION_USERNAME_KEY not in session
