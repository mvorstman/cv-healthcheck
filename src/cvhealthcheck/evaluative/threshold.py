"""
cvhealthcheck.evaluative.threshold
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase-2 minimum evaluative machinery: a template-default threshold
rule on a metric value, producing a severity + a one-entry verdict chain.

A rule (declared inline in the catalog's ``metric.evaluative.rules`` for
phase 2 — the rules *registry* and reference-by-id is phase 8) has the shape:

    {
        "rule_id": "utilisation_threshold",
        "target": "utilisation_pct",        # which metric item this judges
        "kind": "threshold",
        "comparison": ">=",                  # >= | > | <= | <
        "bands": [                            # value -> severity when predicate holds
            {"at": 90, "severity": "critical"},
            {"at": 70, "severity": "warning"}
        ],
        "default_severity": "good",          # when no band's predicate holds
        "mute_on_sentinel": true             # value is None/"n/a" -> muted, not judged
    }

The evaluator returns a single ``VerdictEntry`` at the ``template_default``
layer. Phase 8 prepends a ``vendor`` entry and appends ``override`` entries to
the same chain. The verdict ``reason`` is always populated so the verdict is
auditable.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import VerdictEntry

# Highest rank wins when multiple bands' predicates hold. `muted` and `info`
# are not produced by band selection; they're listed for completeness.
_SEVERITY_RANK: dict[FindingSeverity, int] = {
    FindingSeverity.muted:    -1,
    FindingSeverity.good:      0,
    FindingSeverity.info:      1,
    FindingSeverity.warning:   2,
    FindingSeverity.critical:  3,
}

_COMPARATORS = {
    ">=": lambda v, t: v >= t,
    ">":  lambda v, t: v > t,
    "<=": lambda v, t: v <= t,
    "<":  lambda v, t: v < t,
}


def evaluate_threshold_rule(
    rule: dict[str, Any],
    value: float | int | None,
    *,
    label: str,
    unit: str | None = None,
) -> VerdictEntry:
    """Evaluate a threshold ``rule`` against ``value``; return a VerdictEntry.

    ``value`` of None means the metric is a sentinel / "n/a". With
    ``mute_on_sentinel`` the verdict is ``muted`` (not judged); otherwise the
    rule still returns its ``default_severity`` (a None value with no mute is
    treated as not meeting any band).
    """
    rule_id = rule.get("rule_id")
    unit_str = unit or ""

    if value is None:
        if rule.get("mute_on_sentinel"):
            return VerdictEntry(
                layer="template_default",
                rule_id=rule_id,
                severity=FindingSeverity.muted,
                reason=f"{label} is not applicable (n/a) — verdict muted",
            )
        default = _coerce_severity(rule.get("default_severity", "good"))
        return VerdictEntry(
            layer="template_default",
            rule_id=rule_id,
            severity=default,
            reason=f"{label} has no value; defaulted to {default.value}",
        )

    comparison = rule.get("comparison", ">=")
    comparator = _COMPARATORS.get(comparison)
    if comparator is None:
        raise ValueError(f"Unsupported threshold comparison {comparison!r}")

    # Among all bands whose predicate holds, the highest-severity band wins.
    winner: dict[str, Any] | None = None
    winner_sev: FindingSeverity | None = None
    for band in rule.get("bands", []):
        threshold = band["at"]
        if not comparator(value, threshold):
            continue
        sev = _coerce_severity(band["severity"])
        if winner_sev is None or _SEVERITY_RANK[sev] > _SEVERITY_RANK[winner_sev]:
            winner, winner_sev = band, sev

    if winner is not None and winner_sev is not None:
        return VerdictEntry(
            layer="template_default",
            rule_id=rule_id,
            severity=winner_sev,
            reason=(
                f"{label} {_fmt(value)}{unit_str} {comparison} "
                f"{_fmt(winner['at'])}{unit_str} threshold"
            ),
        )

    default = _coerce_severity(rule.get("default_severity", "good"))
    return VerdictEntry(
        layer="template_default",
        rule_id=rule_id,
        severity=default,
        reason=f"{label} {_fmt(value)}{unit_str} within normal range",
    )


def _coerce_severity(value: Any) -> FindingSeverity:
    if isinstance(value, FindingSeverity):
        return value
    return FindingSeverity(str(value))


def _fmt(value: float | int) -> str:
    """Format a number without a trailing .0 for whole values."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
