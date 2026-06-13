"""Identity-value normalization (Fix 3, ADR-0015 profile layer).

Leaf module (stdlib only) so the db layer, the web layer, and the collect
path can all share one canonical form without import cycles.

Two seams, kept distinct (do not collapse — they are different values):
  - the CommCell ID is a licensed number (hex or decimal on input; F9EE5 ==
    1023717); canonical storage is lowercase hex.
  - the connection URL is the WebServer/gateway base the app reaches;
    schemeless input is repaired to https://, then validated.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

_HEX_LETTERS = set("abcdefABCDEF")
_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def normalize_commcell_id(raw: object) -> str | None:
    """Canonical CommCell ID = lowercase hex string.

    Accepts hex (``F9EE5``, ``0xF9EE5``) or decimal (``1023717``) — the two are
    equal (F9EE5 == 1023717) and both normalize to ``f9ee5``. Disambiguation:
    a ``0x`` prefix or any hex letter (a-f) marks hex; an all-digit value is
    read as DECIMAL (so the licensed decimal id round-trips to its hex form).
    Already-hex stored values are stable (``337f`` -> ``337f``).

    Returns None for empty input. Raises ValueError for non-numeric junk
    (e.g. a name mistakenly entered in the id field) so the customers page
    can surface it rather than store garbage.

    NB the one ambiguous case: an all-digit value whose intended base is hex
    (e.g. hex ``1234``) is read as decimal. The licensed id is read off the
    Command Center either as hex (which carries letters and self-identifies)
    or as the decimal number — both handled; a bare all-digit hex id is the
    documented edge, not supported by guess."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    body = s[2:] if s[:2].lower() == "0x" else s
    if not body:
        raise ValueError(f"not a valid CommCell ID: {raw!r}")
    if s[:2].lower() == "0x" or any(c in _HEX_LETTERS for c in body):
        if not all(c in "0123456789abcdefABCDEF" for c in body):
            raise ValueError(f"not a valid CommCell ID: {raw!r}")
        value = int(body, 16)
    elif body.isdigit():
        value = int(body, 10)
    else:
        raise ValueError(f"not a valid CommCell ID: {raw!r}")
    return format(value, "x")


def normalize_connection_url(raw: object) -> str | None:
    """A customer-facing connection URL repaired to a fetchable base URL.

    Schemeless input gets ``https://`` prepended (this kills the ``gw02:4433``
    error class, where a bare host:port made urllib read ``gw02`` as a
    scheme). Validated as http(s) with a non-empty host; trailing slash
    stripped. Returns None for empty; raises ValueError for input that has no
    host after repair."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if not _SCHEME_RE.match(s):
        s = "https://" + s
    parsed = urlsplit(s)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"not a valid connection URL: {raw!r}")
    return s.rstrip("/")


def effective_connection_url(customer: Mapping[str, object]) -> str | None:
    """The reach URL for a customer row: prefer the new ``connection_url``,
    fall back to the READ-ONLY-LEGACY ``commcell_hostname`` during the
    transition (the fallback is removed when migration 0032's column is
    dropped). Junk legacy values normalize to None (treated as not-configured
    by the connect sites) rather than raising into a 500."""
    raw = customer.get("connection_url") or customer.get("commcell_hostname")
    try:
        return normalize_connection_url(raw)
    except ValueError:
        return None


def verify_commcell_id(
    declared: object,
    wire: object,
    *,
    wire_source: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Declared-vs-wire CommCell ID verdict (Fix 4) — PROVENANCE, not workflow.

    Compares ``normalize_commcell_id(declared)`` against
    ``normalize_commcell_id(wire)`` and returns the four ArtifactSource
    verification_* field values. NEVER raises on bad input (un-normalizable ->
    None) and NEVER blocks: the caller stamps the verdict and continues.

    The caller's per-source resolver decides what ``wire`` value a source can
    provide; this function only compares. A ``wire`` that resolves to None means
    the source offered no identity to compare against ("no proof possible").

    Verdicts (attested != unverifiable — never collapsed):
      verified     declared and wire both normalize present and equal.
      mismatch     both present and differ.
      attested     declared present, but the source offered NO wire identity
                   (wire absent / un-normalizable) — no proof possible. This is
                   the normal import case and the non-identity CC-API endpoint
                   case (server_groups, storage_policies, … carry no CommCell
                   ID), which is why those are attested, not unverifiable.
      unverifiable declared absent / un-normalizable — there is nothing to
                   compare against, regardless of what the source carries.

    The returned verification_notes records BOTH normalized inputs (the
    evidence that produced the verdict), and verification_sources records where
    the wire value was looked for. ``now`` stamps verified_at."""
    def _safe_norm(value: object) -> str | None:
        try:
            return normalize_commcell_id(value)
        except ValueError:
            return None

    declared_norm = _safe_norm(declared)
    wire_norm = _safe_norm(wire)

    if declared_norm is None:
        status = "unverifiable"           # nothing declared to compare against
    elif wire_norm is None:
        status = "attested"               # source offered no identity to compare
    elif declared_norm == wire_norm:
        status = "verified"
    else:
        status = "mismatch"

    sources = [wire_source] if (wire_norm is not None and wire_source) else []
    notes = (
        f"declared_normalized={declared_norm or 'none'}; "
        f"wire_normalized={wire_norm or 'none'}"
    )
    return {
        "verification_status": status,
        "verification_sources": sources,
        "verification_notes": notes,
        "verified_at": now,
    }
