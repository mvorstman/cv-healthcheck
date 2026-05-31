"""
cvhealthcheck.evaluative.enum_rule
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase-8 follow-on — the ``enum`` rule kind: judge whether a field's
value is a member of a configured allowed-set (e.g. CommCell Timezone is one of
an approved list), rather than thresholding a number or checking set-ness.

Rule shape (rides the same plumbing presence/threshold use — the kind-specific
config is carried as keys on the rule dict):

    {
        "kind": "enum",
        "allowed_values": ["UTC", "America/Danmarkshavn"],  # the approved set
        "severity_when_allowed":    "good",       # optional, default "good"
        "severity_when_disallowed": "warning",    # optional, default "warning"
        "severity_when_missing":    "warning"     # optional, default "warning"
    }

The evaluator compares the value it is handed against ``allowed_values`` — it
does NOT normalize the value (normalization, if any, is the caller's choice, the
same way the threshold evaluator receives an already-derived number). Membership
is exact equality (``value in allowed_values``).

Behaviour, chosen to be consistent with ``presence`` (always returns a safe
VerdictEntry, never raises on missing config):
  - missing value (None / "")            -> ``severity_when_missing``  ("is not set")
  - value in the allowed-set             -> ``severity_when_allowed``  ("is in the allowed set")
  - value not in the allowed-set         -> ``severity_when_disallowed`` ("is not in the allowed set")
  - NO allowed-set configured (absent/[]) -> PASS (``good``): an enum rule with
    nothing to disallow has nothing to flag. (A field with no rule renders bare
    at the integration layer — that is the "informational / no indicator" case;
    an *authored* rule always yields a verdict.)

Returns the SAME ``VerdictEntry`` shape as the other evaluators so the engine's
layering/override resolution and the recommend-seam surfacing compose
identically regardless of kind.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.models import VerdictEntry
from cvhealthcheck.evaluative.threshold import _coerce_severity


def evaluate_enum_rule(
    rule: dict[str, Any],
    value: Any,
    *,
    label: str,
    unit: str | None = None,
    layer: str = "template_default",
) -> VerdictEntry:
    """Evaluate an ``enum`` rule against ``value``; return a VerdictEntry.

    ``unit`` is accepted for a uniform evaluator signature but unused (enum
    judges membership, not magnitude)."""
    rule_id = rule.get("rule_id")
    allowed = rule.get("allowed_values")

    if not allowed:
        # No allowed-set configured -> nothing to enforce. Pass (mirrors the
        # never-raise robustness of presence; see module docstring).
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_allowed", "good")),
            reason=f"{label}: no allowed-set configured",
        )

    if value is None or value == "":
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_missing", "warning")),
            reason=f"{label} is not set",
        )

    if value in allowed:
        return VerdictEntry(
            layer=layer, rule_id=rule_id,
            severity=_coerce_severity(rule.get("severity_when_allowed", "good")),
            reason=f"{label} '{value}' is in the allowed set",
        )

    return VerdictEntry(
        layer=layer, rule_id=rule_id,
        severity=_coerce_severity(rule.get("severity_when_disallowed", "warning")),
        reason=f"{label} '{value}' is not in the allowed set",
    )
