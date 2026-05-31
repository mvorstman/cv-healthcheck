"""
cvhealthcheck.evaluative.presence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase-8 follow-on — the ``presence`` rule kind: judge whether a field
is *set* rather than thresholding a number.

Rule shape (registry ``definition_json``):

    {
        "kind": "presence",
        "severity_when_missing": "warning",     # declared per rule (warning | critical | …)
        "severity_when_present": "good"         # optional, default "good"
    }

A field is **present** when its value is neither ``None`` nor an empty string
(``0`` / ``False`` are real values → present). Present → ``severity_when_present``
("<field> is set"); missing → ``severity_when_missing`` ("<field> is not set").

Returns the SAME ``VerdictEntry`` shape as ``evaluate_threshold_rule`` so the
engine's layering/override resolution and the recommend-seam surfacing compose
identically regardless of kind.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.models import VerdictEntry
from cvhealthcheck.evaluative.threshold import _coerce_severity


def evaluate_presence_rule(
    rule: dict[str, Any],
    value: Any,
    *,
    label: str,
    unit: str | None = None,
    layer: str = "template_default",
) -> VerdictEntry:
    """Evaluate a ``presence`` rule against ``value``; return a VerdictEntry.

    ``unit`` is accepted for a uniform evaluator signature but unused (presence
    judges set-ness, not magnitude).
    """
    missing = value is None or value == ""
    if missing:
        severity = _coerce_severity(rule.get("severity_when_missing", "warning"))
        reason = f"{label} is not set"
    else:
        severity = _coerce_severity(rule.get("severity_when_present", "good"))
        reason = f"{label} is set"
    return VerdictEntry(
        layer=layer,
        rule_id=rule.get("rule_id"),
        severity=severity,
        reason=reason,
    )
