"""
cvhealthcheck.evaluative.format_rule
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase-8 follow-on — the ``format`` rule kind: judge whether a field's
value matches a configured pattern / naming convention (e.g. CommCell Name
matches an approved regex), rather than thresholding a number, checking set-ness,
or membership.

Rule shape (rides the same plumbing presence/threshold use — the kind-specific
config is carried as keys on the rule dict):

    {
        "kind": "format",
        "pattern": "^[A-Za-z][A-Za-z0-9_-]*$",   # the required regex
        "severity_when_match":    "good",        # optional, default "good"
        "severity_when_no_match": "warning",     # optional, default "warning"
        "severity_when_missing":  "warning"      # optional, default "warning"
    }

The value is matched with ``re.fullmatch`` — the WHOLE value must conform to the
pattern (anchored), which is the natural reading of "matches the naming
convention". The value is coerced to ``str`` before matching.

Behaviour, chosen to be consistent with ``presence`` (always returns a safe
VerdictEntry for missing config; raises loudly only on an *authoring* error):
  - missing value (None / "")          -> ``severity_when_missing``  ("is not set")
  - value fully matches the pattern     -> ``severity_when_match``    ("matches the required format")
  - value does not match                -> ``severity_when_no_match`` ("does not match the required format")
  - NO pattern configured (absent/"")   -> PASS (``good``): no convention to
    enforce. (A field with no rule renders bare at the integration layer — the
    "informational / no indicator" case; an *authored* rule always yields a verdict.)
  - an INVALID regex pattern            -> raise ValueError (loud-fail at
    evaluation, consistent with threshold's unsupported-comparison guard — a bad
    pattern is an authoring error, not a runtime severity).

Returns the SAME ``VerdictEntry`` shape as the other evaluators so the engine's
layering/override resolution and the recommend-seam surfacing compose
identically regardless of kind.
"""
from __future__ import annotations

import re
from typing import Any

from cvhealthcheck.artifacts.models import VerdictEntry
from cvhealthcheck.evaluative.threshold import _coerce_severity


def evaluate_format_rule(
    rule: dict[str, Any],
    value: Any,
    *,
    label: str,
    unit: str | None = None,
    layer: str = "template_default",
) -> VerdictEntry:
    """Evaluate a ``format`` rule against ``value``; return a VerdictEntry.

    ``unit`` is accepted for a uniform evaluator signature but unused (format
    judges shape, not magnitude)."""
    rule_id = rule.get("rule_id")
    pattern = rule.get("pattern")

    if not pattern:
        # No pattern configured -> nothing to enforce. Pass (mirrors the
        # never-raise robustness of presence; see module docstring).
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_match", "good")),
            reason=f"{label}: no format pattern configured",
        )

    if value is None or value == "":
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_missing", "warning")),
            reason=f"{label} is not set",
        )

    try:
        matched = re.fullmatch(pattern, str(value)) is not None
    except re.error as exc:
        raise ValueError(f"Invalid format pattern {pattern!r} for {label!r}: {exc}") from exc

    if matched:
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_match", "good")),
            reason=f"{label} matches the required format",
        )

    return VerdictEntry(
        layer=layer, rule_id=rule_id,
        severity=_coerce_severity(rule.get("severity_when_no_match", "warning")),
        reason=f"{label} does not match the required format",
    )
