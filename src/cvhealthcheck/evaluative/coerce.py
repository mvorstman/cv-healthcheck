"""
cvhealthcheck.evaluative.coerce
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0010 D6 — value coercion for row-scope predicate evaluation.

Artifact cell values are frequently strings carrying units or sentinels
(``"0 TB"``, ``"4 clients"``, ``"10 millions"``, ``"Unlimited"``, ``"N/A"``,
``"-"``, ``""``). One centralized, unit-tested helper normalizes them so the
predicate evaluator (``row_match.py``) never re-implements parsing.

Three notions, kept distinct:
- **absent** — ``None`` / ``"N/A"`` / ``"-"`` / ``""`` / ``null``. A *comparison*
  against an absent value is **false** (not an error); ``exists`` / ``not_exists``
  test exactly this.
- **number** — a real numeric, with the leading numeric parsed out of a unit
  string (``"0 TB"`` → ``0``, ``"4 clients"`` → ``4``); ``"Unlimited"`` → ``+inf``
  (so ``used > Unlimited`` is always false, ``used < Unlimited`` always true).
- **temporal** — a unix epoch (``users.lastLoggedIn``; ``0`` = never → epoch 1970,
  which reads as very stale) **or** an ISO-8601 date/datetime. ``age_days`` turns
  either into an age in days for ``stale_days``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Strings that mean "no value here" — a comparison against one of these is false.
_ABSENT_STRINGS = {"", "n/a", "na", "-", "—", "null", "none", "not available"}
# Strings that mean "no ceiling" — treated as +infinity for numeric comparison.
_UNLIMITED_STRINGS = {"unlimited", "no limit", "infinite", "∞"}

UNLIMITED = float("inf")

# Leading numeric: optional sign, digits, optional dot-decimal. Thousands commas
# are stripped before matching (so "10,000 TB" → 10000), so the regex itself
# never sees a comma.
_LEADING_NUM = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)")


def is_absent(value: Any) -> bool:
    """True iff ``value`` is None or an absent-sentinel string."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _ABSENT_STRINGS
    return False


def to_number(value: Any) -> float | None:
    """Coerce to a float, or ``None`` when absent / non-numeric.

    ``bool`` is rejected (it is not a measurement). ``"Unlimited"`` → ``+inf``.
    Unit strings yield their leading numeric (``"0 TB"`` → ``0.0``)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    low = s.lower()
    if low in _ABSENT_STRINGS:
        return None
    if low in _UNLIMITED_STRINGS:
        return UNLIMITED
    match = _LEADING_NUM.match(s.replace(",", ""))
    return float(match.group(1)) if match else None


def to_datetime(value: Any) -> datetime | None:
    """Coerce to a tz-aware UTC datetime, or ``None``.

    A purely-numeric value (or numeric string) is read as **unix epoch seconds**
    (``users.lastLoggedIn``; ``0`` → 1970-01-01). Otherwise an ISO-8601 string
    (trailing ``Z`` accepted). Naive ISO datetimes are assumed UTC."""
    if is_absent(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    try:
        return _from_epoch(float(s))            # purely-numeric string → epoch
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def age_days(value: Any, *, now: datetime) -> float | None:
    """Age of a temporal value in days relative to ``now``; ``None`` if absent /
    unparseable. Used by the ``stale_days`` operator."""
    dt = to_datetime(value)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 86400.0


def _from_epoch(seconds: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
