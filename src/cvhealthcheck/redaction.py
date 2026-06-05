"""Shared user-description redaction (ADR-0008 component D).

Extracted from the MCP probe so BOTH the MCP layer and the app-mediated loopback
endpoint can import it — the app-mediated path MUST redact before returning, so
redaction cannot live only in the MCP module. Self-contained (standard library
only); imports nothing from the MCP / web / Flask layers, so either side can use
it without a circular import.
"""
from __future__ import annotations

from typing import Any


def redact_user_descriptions(data: Any) -> Any:
    """Return a copy of ``data`` with every ``description`` string replaced by
    ``[redacted: <n> chars]``.

    A direct fetch has no human scrub step, and the user ``description`` field is
    free-text observed carrying secret-like values — keep it out of the transcript.
    Shape-agnostic (the V4 ``/user`` response shape is not pinned here): walks
    dicts/lists and redacts any ``description`` wherever it appears. Secret *detection*
    stays a propose-stage evaluator authored from field shape, not contents."""
    if isinstance(data, dict):
        return {
            k: (f"[redacted: {len(v)} chars]" if k == "description" and isinstance(v, str)
                else redact_user_descriptions(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_user_descriptions(item) for item in data]
    return data
