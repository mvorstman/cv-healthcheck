"""Loopback internal endpoint (ADR-0008 component C) — the ONE door the AI/MCP layer
may use to reach the CommServe.

``POST /internal/commserve``. The AI/MCP layer never holds a CommServe token nor calls
the CommServe directly; it calls here with a shared secret, and the APP makes the GET
with its own held token (``token_store``), redacts, and returns. GET-only, read-only.

Guards, in order of authority — every guard failure returns a **generic 403** (never
revealing which guard failed); a missing shared secret returns **503** (fail closed —
never serve unguarded); the secret and the token are never logged:
  1. shared secret configured (``CV_INTERNAL_SECRET``) — else 503.
  2. ``remote_addr`` is loopback — defense-in-depth, NOT the primary control (a
     request-level check; reliable here — no ProxyFix rewrites remote_addr).
  3. ``X-Internal-Secret`` matches, constant-time — the actual authenticator.

The request contract carries an acting-``principal`` and a requested-``capability`` from
day one (ADR-0008 Decision 6); only ``capability`` is enforced today (read-only), and
RBAC over the principal is the deferred future ADR — the fields exist so it can be added
at this one site without a contract change.

Out of scope here (deferred, NOT built):
  - oversized-response summarisation (the >1MB lesson) — payloads pass through as-is.
  - reactive expiry: flipping the store to "expired" on a CommServe 401 needs the
    identity / auth-failure distinction so one unauthorized request can't nuke the
    connection. A CommServe non-200 is passed through in the envelope, not acted on.
"""
from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from flask import jsonify, request

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.config import load_settings
from cvhealthcheck.redaction import redact_user_descriptions
from cvhealthcheck.token_store import get_active_token, status

from .shared import bp

# The single read-only capability accepted today.
_READ_CAPABILITY = "read"
_LOOPBACK = {"127.0.0.1", "::1"}


def _forbidden():
    # Generic — never reveal which guard failed (remote_addr vs secret).
    return jsonify({"error": "forbidden"}), 403


@bp.route("/internal/commserve", methods=["POST"])
def internal_commserve():
    settings = load_settings()

    # 1. Fail closed if no shared secret is configured — never serve unguarded.
    if not settings.internal_secret:
        return jsonify({"error": "internal endpoint not configured"}), 503

    # 2. Loopback only (defense-in-depth).
    if request.remote_addr not in _LOOPBACK:
        return _forbidden()

    # 3. Shared secret (the primary control), constant-time.
    provided = request.headers.get("X-Internal-Secret", "")
    if not hmac.compare_digest(provided, settings.internal_secret):
        return _forbidden()

    # ── request contract: acting-principal + requested-capability + target path ──
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid request body"}), 400
    path = body.get("path")
    principal = body.get("principal")
    capability = body.get("capability")
    if not (isinstance(path, str) and isinstance(principal, str) and isinstance(capability, str)):
        return jsonify({"error": "path, principal, and capability (strings) are required"}), 400
    if capability != _READ_CAPABILITY:
        # GET-only. principal is carried but not yet authorized (RBAC deferred).
        return jsonify({"error": f"capability must be {_READ_CAPABILITY!r} (read-only GET)"}), 400
    # path must be relative to the CommServe base — reject anything that could redirect
    # the GET off-host (scheme, network location, protocol-relative).
    split = urlsplit(path)
    if split.scheme or split.netloc or path.startswith("//"):
        return jsonify({"error": "path must be a relative CommServe path"}), 400

    # ── token + call ──
    tok = get_active_token()
    if tok is None:
        # Disconnected/expired: a clean envelope, never a bare 401 — and DO NOT build a
        # client (token=None would make CommvaultApiClient fall back to the .token file,
        # the path ADR-0008 kills).
        return jsonify({
            "ok": False,
            "state": status()["state"],          # "disconnected" | "expired"
            "status_code": None,
            "data": None,
            "error": "no active token; reconnect",
        }), 200

    # The app holds the token; settings default to env base_url / SSL. get() never raises.
    result = CommvaultApiClient(token=tok).get(path)
    return jsonify({
        "ok": result.ok,
        "state": "connected",
        "status_code": result.status_code,
        "data": redact_user_descriptions(result.data),   # redact structured data; None passes through
        "error": result.error,
    }), 200
