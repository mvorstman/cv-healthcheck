"""Tests for ADR 0003 phase 3: customer-bound auth.

Covers:
- The customer-binding session key and the is_authenticated_for helper.
- /login as the customer-aware CommCell credentials prompt.
- /api/login as the JSON variant.
- /quick-hc/<subject_id>/collect's redirect-to-login behavior when the
  active customer's token is missing or bound to a different customer,
  and the artifact provenance now coming from the customer row.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from cvhealthcheck.auth.commvault_auth import (
    SESSION_CUSTOMER_ID_KEY,
    SESSION_TOKEN_KEY,
    SESSION_USERNAME_KEY,
    AuthError,
    is_authenticated_for,
    set_current_token,
)
from cvhealthcheck import token_store
from cvhealthcheck.web.app import create_app


# ── is_authenticated_for ─────────────────────────────────────────────────────

def test_is_authenticated_for_returns_false_outside_request_context() -> None:
    assert is_authenticated_for("any-customer") is False


def test_is_authenticated_for_returns_true_when_held_token_bound_to_customer() -> None:
    app = create_app()
    token_store.set_active_token("tok")                  # token in the store (ADR-0008 B)
    with app.test_request_context("/"):
        from flask import session as flask_session
        flask_session[SESSION_CUSTOMER_ID_KEY] = "acme"  # binding marker stays in the cookie
        assert is_authenticated_for("acme") is True
        assert is_authenticated_for("other") is False    # binding required (mismatch → False)


def test_is_authenticated_for_returns_false_when_no_token() -> None:
    app = create_app()
    with app.test_request_context("/"):
        from flask import session as flask_session
        flask_session[SESSION_CUSTOMER_ID_KEY] = "acme"  # customer marker but no held token
        assert is_authenticated_for("acme") is False


def test_is_authenticated_for_requires_a_customer_marker() -> None:
    """A held token with NO customer marker does not satisfy is_authenticated_for —
    the binding-required property (replacing the old legacy-unbound-cookie-token case)."""
    app = create_app()
    token_store.set_active_token("tok")
    with app.test_request_context("/"):
        assert is_authenticated_for("acme") is False     # no SESSION_CUSTOMER_ID_KEY in the cookie


# ── set_current_token (de-cookie invariant) ──────────────────────────────────

def test_set_current_token_holds_token_in_store_not_cookie() -> None:
    """ADR-0008 B: the CommServe token lands in the in-process store; the cookie keeps
    ONLY the non-secret customer/username markers — the token is no longer at rest in
    the browser."""
    app = create_app()
    with app.test_request_context("/"):
        from flask import session as flask_session
        set_current_token("tok", customer_id="acme", username="alice")
        assert token_store.get_active_token() == "tok"        # token in the store
        assert SESSION_TOKEN_KEY not in flask_session         # NOT in the cookie
        assert flask_session[SESSION_CUSTOMER_ID_KEY] == "acme"
        assert flask_session[SESSION_USERNAME_KEY] == "alice"


def test_set_current_token_raises_on_empty_customer_id() -> None:
    app = create_app()
    with app.test_request_context("/"):
        with pytest.raises(ValueError, match="customer_id"):
            set_current_token("tok", customer_id="")
        with pytest.raises(ValueError, match="customer_id"):
            set_current_token("tok", customer_id="   ")


def test_logout_clears_store_and_session_markers() -> None:
    app = create_app()
    client = app.test_client()
    token_store.set_active_token("tok", principal="alice")     # held token in the store
    with client.session_transaction() as session:
        session[SESSION_CUSTOMER_ID_KEY] = "acme"
        session[SESSION_USERNAME_KEY] = "alice"

    response = client.post("/logout")
    assert response.status_code == 302

    assert token_store.get_active_token() is None              # store cleared
    with client.session_transaction() as session:
        assert SESSION_TOKEN_KEY not in session
        assert SESSION_CUSTOMER_ID_KEY not in session
        assert SESSION_USERNAME_KEY not in session


# ── /login GET ───────────────────────────────────────────────────────────────

_FAKE_CUSTOMER_WITH_HOSTNAME = {
    "customer_id": "acme",
    "customer_name": "ACME Corp",
    "commcell_hostname": "https://commcell.acme.local",
    "commcell_id": "CS-ACME-001",
    "company_guid": None,
    "contact_info": None,
    "notes": None,
}

_FAKE_CUSTOMER_NO_HOSTNAME = {
    "customer_id": "default",
    "customer_name": "Default",
    "commcell_hostname": None,
    "commcell_id": None,
    "company_guid": None,
    "contact_info": None,
    "notes": None,
}


def test_login_get_shows_active_customer_name_and_hostname(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "ACME Corp" in body
    assert "https://commcell.acme.local" in body
    # The form should not be disabled when hostname is set.
    assert 'disabled' not in body.split('<button')[1].split('</button>')[0]


def test_login_get_renders_disabled_when_hostname_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.get_active_customer",
        lambda: _FAKE_CUSTOMER_NO_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "No CommCell URL configured" in body
    # Inputs and button should be disabled.
    assert body.count("disabled") >= 3  # username, password, submit


# ── /login POST ──────────────────────────────────────────────────────────────

def test_login_post_success_binds_token_to_customer(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.login_to_commvault",
        lambda base_url, username, password: "issued-token",
    )
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
    )
    assert response.status_code == 302
    assert token_store.get_active_token() == "issued-token"   # token to the store
    with client.session_transaction() as session:
        assert SESSION_TOKEN_KEY not in session               # not the cookie
        assert session[SESSION_CUSTOMER_ID_KEY] == "acme"
        assert session[SESSION_USERNAME_KEY] == "alice"


def test_login_post_failure_renders_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    def _fail(*args, **kwargs):
        raise AuthError("Invalid credentials")
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.login_to_commvault", _fail
    )
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "alice", "password": "wrong"},
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Invalid credentials" in body
    assert token_store.get_active_token() is None             # failed login → no held token
    with client.session_transaction() as session:
        assert SESSION_TOKEN_KEY not in session


def test_login_post_without_hostname_errors_without_calling_login(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.get_active_customer",
        lambda: _FAKE_CUSTOMER_NO_HOSTNAME,
    )
    calls: list[tuple] = []
    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return "should-not-be-issued"
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.basic.login_to_commvault", _spy
    )
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "no commcell url configured" in body.lower()
    assert calls == []  # login_to_commvault was not called


# ── /api/login ───────────────────────────────────────────────────────────────

def test_api_login_success_binds_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc_api.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc_api.login_to_commvault",
        lambda base_url, username, password: "issued-token",
    )
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/login",
        json={"username": "alice", "password": "secret"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert token_store.get_active_token() == "issued-token"   # token to the store
    with client.session_transaction() as session:
        assert SESSION_TOKEN_KEY not in session               # not the cookie
        assert session[SESSION_CUSTOMER_ID_KEY] == "acme"


def test_api_login_without_hostname_returns_400(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc_api.get_active_customer",
        lambda: _FAKE_CUSTOMER_NO_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/login",
        json={"username": "alice", "password": "secret"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "commcell_hostname" in payload["error"].lower() or "commcell url" in payload["error"].lower()


# ── /quick-hc/<subject_id>/collect ───────────────────────────────────────────

def test_collect_redirects_to_login_when_no_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session["active_project"] = {"customer_id": "default", "project_id": "default"}
    response = client.post("/quick-hc/client_growth/collect")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_collect_clears_and_redirects_when_token_bound_to_wrong_customer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc.get_active_customer",
        lambda: _FAKE_CUSTOMER_WITH_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    token_store.set_active_token("old-token")                   # held token...
    with client.session_transaction() as session:
        session[SESSION_CUSTOMER_ID_KEY] = "different_customer"  # ...bound to the wrong customer
        session["active_project"] = {"customer_id": "default", "project_id": "default"}

    response = client.post("/quick-hc/client_growth/collect")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    # The wrong-customer held token must have been cleared (store + marker).
    assert token_store.get_active_token() is None
    with client.session_transaction() as session:
        assert SESSION_CUSTOMER_ID_KEY not in session


def test_collect_errors_when_active_customer_has_no_hostname(monkeypatch) -> None:
    monkeypatch.setattr(
        "cvhealthcheck.web.routes.quick_hc.get_active_customer",
        lambda: _FAKE_CUSTOMER_NO_HOSTNAME,
    )
    app = create_app()
    client = app.test_client()
    token_store.set_active_token("tok")
    with client.session_transaction() as session:
        session[SESSION_CUSTOMER_ID_KEY] = "default"

    response = client.post("/quick-hc/client_growth/collect")
    # Redirect to workspace with a flash error — the form-disabled /login
    # would be a dead end, so we don't bounce there.
    assert response.status_code == 302
    assert "/login" not in response.headers["Location"]


# ── get_active_customer ──────────────────────────────────────────────────────

def test_get_active_customer_returns_default_customer_row() -> None:
    """The helper resolves the active project then loads the customer row.

    Runs against the real seeded DB so we can verify the projects→customers
    join behavior end-to-end.
    """
    from cvhealthcheck.web.active_project import get_active_customer

    app = create_app()
    with app.test_request_context("/"):
        customer = get_active_customer()
    # Default customer always exists per migration 0005.
    assert customer["customer_id"] == "default"
    assert customer["customer_name"] == "Default"
