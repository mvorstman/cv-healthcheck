"""
cvhealthcheck.evaluative.engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 8 — the single evaluation locus for metric/card sections.

``evaluate(value, rule, *, label, unit)`` is the one place a metric item or a
card section turns a value + a ``template_default`` threshold rule into a
resolved ``(severity, verdict_chain)``.

Phase 8 step 1 is a **pure refactor**: it unifies the two previously-duplicated
call sites (``metric_section`` per item, ``card_section`` per section) onto this
single function, with **no behavior change** — it delegates to the existing
``evaluate_threshold_rule`` primitive and produces the identical single-entry
``template_default`` chain phase 2 produced.

Later phase-8 steps EXTEND this locus (vendor → template → override layering,
the rules registry, Shapes 2/3); they do not add a second evaluator. Per ADR
0004 phase-8 design DP7 option (i): **findings are transcribed at extraction**
(``status_to_severity``), not evaluated here — only metric/card route through
this engine.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import VerdictEntry
from cvhealthcheck.evaluative.threshold import evaluate_threshold_rule


# Keys that make up a rule *body* (the definition), as opposed to *binding*
# keys (ref / target / target_field / unit) that a section carries to point a
# rule at a value. Used by the DP2 guard to reject a ref entry that also smuggles
# an inline body.
_RULE_BODY_KEYS = frozenset({"kind", "comparison", "bands", "default_severity", "mute_on_sentinel"})


def resolve_rule(
    rule: dict[str, Any],
    rules_registry: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve a section's rule entry to a concrete rule definition (step 2).

    ADR 0004 phase 8 step 2 (registry + reference-by-id, DP2 registry-or-inline):

    - **Inline** (no ``ref``): returned unchanged — an anonymous template-default
      rule, exactly as phases 5–7 / the test subjects use today.
    - **Ref** (``{"ref": rule_id, …binding…}``): looked up in the registry and
      merged with the entry's binding keys (``target`` / ``target_field`` /
      ``unit``), so the resolved dict is byte-identical to what the inline body
      was — same ``rule_id``, bands, thresholds.

    Guards (loud-fail, collection-time — the project's load locus for
    extraction_instructions):
    - **DP2:** a ref entry that *also* carries inline body keys is ambiguous → raise.
    - An unknown ``ref`` (not in the registry) → raise.

    (The other half of the DP2 guard — an inline rule and a ref both targeting
    the same target within one section — is enforced by ``build_metric_section``,
    which sees the whole rule list.)
    """
    ref = rule.get("ref")
    if ref is None:
        return rule
    if _RULE_BODY_KEYS & rule.keys():
        raise ValueError(
            f"Rule entry references {ref!r} but also carries an inline body "
            f"({sorted(_RULE_BODY_KEYS & rule.keys())}) — ambiguous; use a ref OR an inline rule, not both."
        )
    definition = (rules_registry or {}).get(ref)
    if definition is None:
        raise ValueError(f"Rule ref {ref!r} not found in the rules registry")
    binding = {k: v for k, v in rule.items() if k != "ref"}
    return {**definition, **binding}


def evaluate(
    value: float | int | None,
    rule: dict[str, Any] | None,
    *,
    label: str,
    unit: str | None = None,
) -> tuple[FindingSeverity | None, list[VerdictEntry]]:
    """Resolve ``(severity, verdict_chain)`` for one evaluated value.

    No rule → the value is unjudged → ``(None, [])`` (a metric item / card with
    no evaluative rule). With a ``template_default`` threshold rule, return a
    single-entry verdict chain — byte-identical to the prior per-call-site
    ``evaluate_threshold_rule`` usage, now funnelled through one locus.
    """
    if rule is None:
        return None, []
    verdict = evaluate_threshold_rule(rule, value, label=label, unit=unit)
    return verdict.severity, [verdict]
