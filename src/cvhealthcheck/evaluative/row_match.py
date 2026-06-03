"""
cvhealthcheck.evaluative.row_match
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0010 D3 — the row-scope evaluator. A NEW grain alongside the per-value
``engine.evaluate``: a ``row_match`` rule ANDs a list of predicates over each
row of a table section, and emits findings.

This is *not* a branch in ``engine._evaluate_rule`` (that dispatcher is value-
grained, scalar → one verdict). It reuses the severity vocabulary and the
``coerce`` primitives, but operates on whole rows (dicts) → findings.

A ``row_match`` rule definition (stored in the ``rules`` registry, kind
``row_match``)::

    {
      "kind": "row_match",
      "conditions": [ {"target","operator","value"?,"value2"?}, ... ],   # all AND-ed
      "emit": "per_row" | "count",
      "count_operator": "lt|lte|gt|gte|eq|ne",   # emit=count only
      "count_value": <number>,                    # emit=count only
      "severity": "critical|warning|info|good",
      "title": "<template>", "message": "<template>", "recommendation": "<template>"?
    }

Operators: ``lt lte gt gte eq ne contains not_contains exists not_exists between
stale_days``. A predicate ``value`` is a literal, or ``{"ref": "<other column>"}``
to compare field-to-field (``used > available``). A comparison against an
**absent** cell is **false** (never an error); ``exists`` / ``not_exists`` test
absence directly.

Pure and side-effect free — returns finding dicts; persistence (a derived
FindingsSection) is the caller's job in ``result_to_artifact``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.evaluative import coerce

_NUMERIC_OPS = frozenset({"lt", "lte", "gt", "gte", "between"})
_KNOWN_OPS = frozenset({
    "lt", "lte", "gt", "gte", "eq", "ne", "contains", "not_contains",
    "exists", "not_exists", "between", "stale_days",
})
_COUNT_OPS = {
    "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
}
_TEMPLATE_TOKEN = re.compile(r"\{([a-zA-Z0-9_.]+)\}")

# Public aliases for the authoring-time validator (db.rules.validate_row_match_rule).
KNOWN_OPERATORS = _KNOWN_OPS
COUNT_OPERATORS = frozenset(_COUNT_OPS)


def evaluate_row_rule(
    rule: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    id_field: str = "id",
) -> list[dict[str, Any]]:
    """Run one ``row_match`` rule over ``rows``; return rendered finding dicts.

    ``emit=per_row`` → one finding per matching row (``row_ref`` = the row's
    ``id_field``, NOT a name — ADR 0010 open-Q: duplicate names collide, ids do
    not). ``emit=count`` → one finding iff the match count satisfies
    ``count_operator``/``count_value``."""
    now = now or datetime.now(timezone.utc)
    conditions = rule.get("conditions") or []
    matched: list[tuple[int, dict[str, Any]]] = [
        (i, row) for i, row in enumerate(rows)
        if isinstance(row, dict) and all(_eval_predicate(p, row, now=now) for p in conditions)
    ]

    emit = rule.get("emit", "per_row")
    if emit == "count":
        count = len(matched)
        op = _COUNT_OPS.get(rule.get("count_operator"))
        cval = coerce.to_number(rule.get("count_value"))
        if op is not None and cval is not None and op(count, cval):
            return [_render(rule, conditions=conditions, count=count)]
        return []
    if emit == "per_row":
        findings = []
        for index, row in matched:
            raw_id = row.get(id_field)
            row_ref = str(raw_id) if not coerce.is_absent(raw_id) else str(index)
            findings.append(_render(rule, conditions=conditions, row=row, row_ref=row_ref))
        return findings
    raise ValueError(f"row_match emit must be 'per_row' or 'count', got {emit!r}")


# ── predicate evaluation ──────────────────────────────────────────────────────

def _operand(pred: dict[str, Any], row: dict[str, Any]) -> Any:
    """A predicate's comparison operand: a literal, or ``{ref}`` → another column."""
    value = pred.get("value")
    if isinstance(value, dict) and "ref" in value:
        return row.get(value["ref"])
    return value


def _eval_predicate(pred: dict[str, Any], row: dict[str, Any], *, now: datetime) -> bool:
    op = pred.get("operator")
    if op not in _KNOWN_OPS:
        raise ValueError(f"unknown predicate operator {op!r}")
    raw = row.get(pred.get("target"))

    if op == "exists":
        return not coerce.is_absent(raw)
    if op == "not_exists":
        return coerce.is_absent(raw)

    # ADR 0010 D6: a comparison against an absent cell is false, not an error.
    if coerce.is_absent(raw):
        return False

    if op == "stale_days":
        age = coerce.age_days(raw, now=now)
        threshold = coerce.to_number(pred.get("value"))
        return age is not None and threshold is not None and age > threshold

    if op in ("eq", "ne"):
        equal = _equal(raw, _operand(pred, row))
        return equal if op == "eq" else not equal

    if op in ("contains", "not_contains"):
        present = str(_operand(pred, row)).strip().lower() in str(raw).lower()
        return present if op == "contains" else not present

    if op == "between":
        left = coerce.to_number(raw)
        lo = coerce.to_number(pred.get("value"))
        hi = coerce.to_number(pred.get("value2"))
        return None not in (left, lo, hi) and lo <= left <= hi

    # numeric comparisons (lt/lte/gt/gte)
    left = coerce.to_number(raw)
    right = coerce.to_number(_operand(pred, row))
    if left is None or right is None:
        return False
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "gt":
        return left > right
    return left >= right  # gte


def _equal(raw: Any, operand: Any) -> bool:
    """Equality: numeric when both sides coerce to numbers, else case-insensitive
    string compare. (So ``count eq 0`` and ``license_type eq 'capacity'`` both
    work without the caller declaring a type.)"""
    ln, rn = coerce.to_number(raw), coerce.to_number(operand)
    if ln is not None and rn is not None:
        return ln == rn
    return str(raw).strip().lower() == str(operand).strip().lower()


# ── finding rendering ─────────────────────────────────────────────────────────

def _render(
    rule: dict[str, Any],
    *,
    conditions: list[dict[str, Any]],
    row: dict[str, Any] | None = None,
    row_ref: str | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    first_target = conditions[0].get("target") if conditions else None
    context: dict[str, str] = {
        "target": str(first_target) if first_target is not None else "",
        "value": "" if row is None or first_target is None else str(row.get(first_target, "")),
        "count": "" if count is None else str(count),
    }
    if row is not None:
        for col, val in row.items():
            context[f"row.{col}"] = "" if val is None else str(val)
    return {
        "rule_id": rule.get("rule_id"),
        "severity": rule.get("severity", "info"),
        "row_ref": row_ref,
        "title": _fill(rule.get("title", ""), context),
        "message": _fill(rule.get("message", ""), context),
        "recommendation": _fill(rule.get("recommendation"), context),
    }


def _fill(template: str | None, context: dict[str, str]) -> str | None:
    """Replace ``{value}`` / ``{target}`` / ``{count}`` / ``{row.<col>}`` tokens.
    An unknown token is left verbatim (authoring is visible, not silently lost)."""
    if not template:
        return template
    return _TEMPLATE_TOKEN.sub(
        lambda m: context.get(m.group(1), m.group(0)), template
    )
