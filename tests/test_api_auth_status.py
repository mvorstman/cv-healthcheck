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


def test_api_auth_status_authenticated_returns_true_and_username(authenticate) -> None:
    # Token present but not bound to the active customer, so the Collect-gate
    # flag authenticated_for_active stays False even though authenticated is True.
    app = create_app()
    client = app.test_client()
    authenticate(client, token="test-token", username="alice")   # store token + cookie username marker
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {
        "authenticated": True,
        "authenticated_for_active": False,
        "username": "alice",
    }


def test_api_auth_status_authenticated_without_username_returns_null(authenticate) -> None:
    # A held token with no username marker. The endpoint must still respond cleanly
    # with username=None rather than crashing or omitting the field.
    app = create_app()
    client = app.test_client()
    authenticate(client, token="test-token")   # store token, no username marker
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.get_json() == {
        "authenticated": True,
        "authenticated_for_active": False,
        "username": None,
    }


def test_api_auth_status_token_bound_to_active_customer_sets_for_active(authenticate) -> None:
    # When the session token is bound to the active customer, the Collect gate
    # is satisfied — authenticated_for_active is True, so REST Collect proceeds
    # without opening the connect modal. The default active customer is "default".
    app = create_app()
    client = app.test_client()
    authenticate(client, token="test-token", username="alice", customer_id="default")
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    body = response.get_json()
    assert body["authenticated"] is True
    assert body["authenticated_for_active"] is True


def test_api_auth_status_treats_empty_token_as_unauthenticated(authenticate) -> None:
    # Defence-in-depth (moved to the store): a blank / whitespace-only HELD token must
    # not count as authenticated — get_active_token() returns None for those, so
    # is_authenticated() returns False.
    app = create_app()
    client = app.test_client()
    authenticate(client, token="   ", username="alice")   # blank held token + username marker
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    # username is gated on the authenticated flag, so it must be None here.
    assert response.get_json() == {
        "authenticated": False,
        "authenticated_for_active": False,
        "username": None,
    }


def test_logout_post_clears_session_and_status_returns_unauthenticated(authenticate) -> None:
    """End-to-end signout contract used by submitSignOut() in quick_hc.js.

    1. Start authenticated (held token in the store + username marker).
    2. POST /logout — expect a 302 redirect to /login (this is what
       submitSignOut() treats as success).
    3. Hit /api/auth/status — expect authenticated=False, username=None.
       The store + session markers must have been cleared by clear_current_token().
    """
    from cvhealthcheck import token_store
    app = create_app()
    client = app.test_client()
    authenticate(client, token="test-token", username="alice")

    logout_response = client.post("/logout")
    assert logout_response.status_code == 302
    assert "/login" in logout_response.headers["Location"]
    assert token_store.get_active_token() is None    # store cleared on logout

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
