from __future__ import annotations

import json
import os
from pathlib import Path

from .commvault_auth import (
    AuthError,
    clear_current_token,
    get_current_token,
    is_authenticated,
    login_to_commvault,
    set_current_token,
)


def load_token(token_path: Path | str = ".token") -> str | None:
    path = Path(token_path)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if isinstance(parsed, dict):
        for key in ("access_token", "accessToken", "token"):
            token = parsed.get(key)
            if isinstance(token, str) and token.strip():
                return token.strip()

    return raw


def load_login_token(token_path: Path | str = ".login_token") -> str | None:
    env_token = os.getenv("CV_LOGIN_TOKEN", "").strip()
    if env_token:
        return env_token

    configured_path = os.getenv("CV_LOGIN_TOKEN_FILE")
    return load_token(configured_path or token_path)


__all__ = [
    "AuthError",
    "clear_current_token",
    "get_current_token",
    "is_authenticated",
    "load_login_token",
    "load_token",
    "login_to_commvault",
    "set_current_token",
]
