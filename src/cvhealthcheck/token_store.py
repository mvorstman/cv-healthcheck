"""In-process held-token store (ADR-0008 component A).

The app's single held CommServe token, kept **in memory only** (Flavour 1 — no
credential at rest). One slot, guarded by a lock because the dev server may serve
requests on multiple threads. Standard library only; imports nothing from Flask, the
web layer, the MCP layer, or ``shared.py``, so the web process and the future loopback
endpoint can both use it with no circular import.

Scope (ADR-0008 Consequences): **single-process, single-slot.** An in-memory slot
lives in ONE process; a multi-worker deployment (e.g. gunicorn) would reintroduce
cross-process sharing, which this module does NOT solve. ``get_active_token()`` is the
read seam a future shared backing store swaps in behind.

Expiry is enforced here: ``get_active_token()`` returns ``None`` once past
``expires_at`` (never a stale string), and ``status()`` distinguishes ``"expired"``
from ``"disconnected"`` so the Connections page can show "disconnected — reconnect"
rather than failing silently. The token value is never logged or returned by
``status()``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class _Held:
    token: str
    principal: str | None
    connected_at: datetime          # tz-aware UTC, set at store time
    expires_at: datetime | None     # tz-aware UTC, or None = no known expiry


_lock = threading.Lock()
_held: _Held | None = None


def _to_utc(value: datetime | float | int | None) -> datetime | None:
    """Normalise an ``expires_at`` (datetime / epoch seconds / None) to a tz-aware UTC
    datetime, or None for 'no known expiry'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if value.tzinfo is None:                       # naive datetime → treat as UTC
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt is not None else None


def set_active_token(
    token: str,
    *,
    expires_at: datetime | float | int | None = None,
    principal: str | None = None,
) -> None:
    """Store the held token + metadata in the single slot, replacing any prior one.
    Called by the Connect action after a successful login (wiring is a later brief)."""
    global _held
    with _lock:
        _held = _Held(
            token=token,
            principal=principal,
            connected_at=datetime.now(timezone.utc),
            expires_at=_to_utc(expires_at),
        )


def get_active_token() -> str | None:
    """The live token, or ``None`` if none is set OR it is past ``expires_at``. Mirrors
    today's ``_current_token()`` shape (``str | None``) so the read-seam swap is a
    drop-in; a dead token reads as ``None`` here, never a stale string."""
    with _lock:
        if _held is None:
            return None
        if _held.expires_at is not None and datetime.now(timezone.utc) >= _held.expires_at:
            return None
        return _held.token


def clear_active_token() -> None:
    """Drop the held token (on disconnect or observed expiry)."""
    global _held
    with _lock:
        _held = None


def status() -> dict[str, Any]:
    """Human-facing connection view for the Connections page and the endpoint's clean
    expiry signal. Distinguishes ``"expired"`` (was connected, token now dead) from
    ``"disconnected"`` (never connected / cleared) — which the bare ``None`` from
    ``get_active_token()`` cannot. Never includes the token value."""
    with _lock:
        if _held is None:
            return {"state": "disconnected", "principal": None,
                    "connected_at": None, "expires_at": None}
        expired = (_held.expires_at is not None
                   and datetime.now(timezone.utc) >= _held.expires_at)
        return {
            "state": "expired" if expired else "connected",
            "principal": _held.principal,
            "connected_at": _iso(_held.connected_at),
            "expires_at": _iso(_held.expires_at),
        }
