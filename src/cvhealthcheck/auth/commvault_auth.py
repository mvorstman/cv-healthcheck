from __future__ import annotations

import base64
from typing import Any

import requests
from flask import has_request_context, session
from urllib3.exceptions import InsecureRequestWarning

from cvhealthcheck.config import load_settings, warn_if_ssl_verification_disabled

SESSION_TOKEN_KEY = "commvault_token"


class AuthError(RuntimeError):
    pass


def login_to_commvault(base_url: str, username: str, password: str) -> str:
    settings = load_settings()
    normalized_base_url = base_url.rstrip("/")
    if not normalized_base_url:
        raise AuthError("Commvault base URL is not configured.")
    if not username.strip() or not password:
        raise AuthError("Username and password are required.")

    if not settings.verify_ssl:
        warn_if_ssl_verification_disabled(settings, component="Commvault login")
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    password_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    try:
        response = requests.post(
            f"{normalized_base_url}/commandcenter/api/Login",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"username": username, "password": password_b64},
            verify=settings.verify_ssl,
            timeout=settings.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Login request failed: {exc}") from exc

    if not response.ok:
        raise AuthError(_login_error(response))

    token = _extract_token(_response_json(response))
    if not token:
        raise AuthError("Login response did not include a token.")
    return token


def set_current_token(token: str) -> None:
    if not has_request_context():
        return
    session[SESSION_TOKEN_KEY] = token


def get_current_token() -> str | None:
    if not has_request_context():
        return None
    token = session.get(SESSION_TOKEN_KEY)
    return token if isinstance(token, str) and token.strip() else None


def clear_current_token() -> None:
    if has_request_context():
        session.pop(SESSION_TOKEN_KEY, None)


def is_authenticated() -> bool:
    return get_current_token() is not None


def _response_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _extract_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("token", "accessToken", "access_token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _login_error(response: requests.Response) -> str:
    payload = _response_json(response)
    if isinstance(payload, dict):
        for key in ("errorMessage", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"Login failed with HTTP {response.status_code}."
