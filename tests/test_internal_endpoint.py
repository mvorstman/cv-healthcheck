"""Loopback internal endpoint (ADR-0008 C) — guard correctness + envelope.

The CommServe is mocked (CommvaultApiClient patched); no real call is made. The store
is the real token_store, reset around each test.
"""
from __future__ import annotations

import pytest

from cvhealthcheck import token_store
from cvhealthcheck.api_client import ApiResult
import cvhealthcheck.web.routes.internal as internal_mod
from cvhealthcheck.web.app import create_app

_SECRET = "s3cr3t-shared"
_URL = "/internal/commserve"
_GOOD_BODY = {"path": "/commandcenter/api/v4/user", "principal": "operator", "capability": "read"}


@pytest.fixture()
def client():
    return create_app().test_client()


@pytest.fixture(autouse=True)
def _reset_store():
    token_store.clear_active_token()
    yield
    token_store.clear_active_token()


@pytest.fixture()
def configured(monkeypatch):
    """Shared secret present — guards can be reached."""
    monkeypatch.setenv("CV_INTERNAL_SECRET", _SECRET)


def _fake_client(result, built: list):
    """A CommvaultApiClient stand-in: records the token it was built with, returns
    `result` from .get(). `built` stays empty if the endpoint never constructs it."""
    class _Fake:
        def __init__(self, *a, **k):
            built.append(k.get("token"))

        def get(self, path, params=None):
            return result

    return _Fake


def _hdr(secret: str = _SECRET) -> dict:
    return {"X-Internal-Secret": secret}


# ── guards ──

def test_not_configured_returns_503_and_never_builds_client(client, monkeypatch):
    monkeypatch.delenv("CV_INTERNAL_SECRET", raising=False)
    built: list = []
    monkeypatch.setattr(internal_mod, "CommvaultApiClient", _fake_client(None, built))
    resp = client.post(_URL, json=_GOOD_BODY, headers=_hdr())
    assert resp.status_code == 503
    assert built == []


def test_wrong_or_missing_secret_returns_403(client, configured):
    assert client.post(_URL, json=_GOOD_BODY, headers=_hdr("nope")).status_code == 403
    assert client.post(_URL, json=_GOOD_BODY).status_code == 403   # no header


def test_non_loopback_returns_403(client, configured):
    resp = client.post(_URL, json=_GOOD_BODY, headers=_hdr(),
                       environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
    assert resp.status_code == 403


# ── request contract → 400 ──

@pytest.mark.parametrize("body", [
    {"principal": "op", "capability": "read"},                            # missing path
    {"path": "/x", "capability": "read"},                                 # missing principal
    {"path": "/x", "principal": "op"},                                    # missing capability
    {"path": "/x", "principal": "op", "capability": "write"},             # bad capability
    {"path": "https://evil/x", "principal": "op", "capability": "read"},  # absolute url
    {"path": "//evil/x", "principal": "op", "capability": "read"},        # protocol-relative
])
def test_bad_request_returns_400(client, configured, body):
    assert client.post(_URL, json=body, headers=_hdr()).status_code == 400


# ── token + call ──

def test_disconnected_returns_200_envelope_and_never_builds_client(client, configured, monkeypatch):
    token_store.clear_active_token()               # no active token
    built: list = []
    monkeypatch.setattr(internal_mod, "CommvaultApiClient", _fake_client(None, built))
    resp = client.post(_URL, json=_GOOD_BODY, headers=_hdr())
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["ok"] is False and j["state"] == "disconnected"
    assert j["status_code"] is None and j["data"] is None
    assert built == []                             # client NEVER constructed with token=None


def test_connected_happy_path_redacts_description(client, configured, monkeypatch):
    token_store.set_active_token("live-tok", principal="operator")
    desc = "secret blurb"
    result = ApiResult(ok=True, status_code=200, url="u",
                       data={"users": [{"name": "alice", "description": desc}]},
                       text="", error=None)
    built: list = []
    monkeypatch.setattr(internal_mod, "CommvaultApiClient", _fake_client(result, built))
    resp = client.post(_URL, json=_GOOD_BODY, headers=_hdr())
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["state"] == "connected" and j["status_code"] == 200 and j["ok"] is True
    assert j["data"]["users"][0]["name"] == "alice"                       # sibling intact
    assert j["data"]["users"][0]["description"] == f"[redacted: {len(desc)} chars]"
    assert built == ["live-tok"]                   # built with the HELD token


def test_commserve_non_200_passes_through(client, configured, monkeypatch):
    token_store.set_active_token("live-tok")
    result = ApiResult(ok=False, status_code=401, url="u", data=None,
                       text="Unauthorized", error="Unauthorized")
    monkeypatch.setattr(internal_mod, "CommvaultApiClient", _fake_client(result, []))
    resp = client.post(_URL, json=_GOOD_BODY, headers=_hdr())
    assert resp.status_code == 200                 # OUR endpoint succeeded
    j = resp.get_json()
    assert j["state"] == "connected" and j["status_code"] == 401 and j["ok"] is False
