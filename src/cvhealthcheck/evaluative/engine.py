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
from cvhealthcheck.artifacts.models import RecommendationIntent, VerdictEntry
from cvhealthcheck.evaluative.threshold import _SEVERITY_RANK, evaluate_threshold_rule


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


def build_override_verdict(override: dict[str, Any]) -> VerdictEntry:
    """Build a ``layer="override"`` VerdictEntry directly from a rule_overrides
    row (``{rule_id, severity, reason}``).

    DP5: an override is a *direct* (severity, reason) assignment for a rule_id —
    it is NOT re-thresholded against a value. The ``reason`` is the audit value
    (e.g. "waived for Acme burst window").
    """
    return VerdictEntry(
        layer="override",
        rule_id=override["rule_id"],
        severity=FindingSeverity(override["severity"]),
        reason=str(override.get("reason") or ""),
    )


def evaluate(
    value: float | int | None,
    template_rules: list[dict[str, Any]],
    *,
    label: str,
    unit: str | None = None,
    vendor_verdicts: tuple[VerdictEntry, ...] | list[VerdictEntry] = (),
    override_verdicts: tuple[VerdictEntry, ...] | list[VerdictEntry] = (),
) -> tuple[FindingSeverity | None, list[VerdictEntry]]:
    """The single layered evaluation locus (phase 8 step 3).

    Composes **vendor → template → override** into one ``(severity,
    verdict_chain)``:

    - ``vendor_verdicts`` — pre-produced ``layer="vendor"`` VerdictEntry list
      (from a section's ``severity_source``; **empty for metric/card** until the
      Shapes step — the slot is here so Shapes 2/3 compose without touching
      resolution).
    - ``template_rules`` — resolved threshold rule dicts; each is evaluated
      against ``value`` at ``layer="template_default"``.
    - ``override_verdicts`` — direct ``layer="override"`` VerdictEntry list (DP5).

    Resolution (DP4 / DP6):
    - The ``verdict_chain`` records **every** fired verdict in layer order
      (vendor, template, override), including muted/suppressed ones — full audit.
    - The headline ``severity`` is the **most-severe surviving** verdict, where
      "surviving" = the latest-layer verdict per ``rule_id`` (later layer wins
      for the same rule_id), and ``muted`` is **excluded** from most-severe
      selection (muted suppresses, never becomes the headline). All-surviving-
      muted → ``muted``.

    No verdicts at all (no vendor/template/override) → ``(None, [])`` — unjudged.

    Empty ``vendor``/``override`` + a single ``template_rules`` entry reduces to
    the step-1/2 single-rule behavior, byte-identically.
    """
    chain: list[VerdictEntry] = list(vendor_verdicts)
    for rule in template_rules:
        chain.append(
            evaluate_threshold_rule(rule, value, label=label, unit=unit, layer="template_default")
        )
    chain.extend(override_verdicts)
    if not chain:
        return None, []
    return _resolve_headline(chain), chain


def _surviving(chain: list[VerdictEntry]) -> dict[Any, VerdictEntry]:
    """The surviving verdict per ``rule_id`` (later layer wins). The chain is in
    layer order, so the last verdict for a rule_id wins; verdicts with no rule_id
    (a vendor source with no id) each survive independently."""
    surviving: dict[Any, VerdictEntry] = {}
    for i, verdict in enumerate(chain):
        key = verdict.rule_id if verdict.rule_id is not None else ("__anon__", i)
        surviving[key] = verdict
    return surviving


def _resolve_headline(chain: list[VerdictEntry]) -> FindingSeverity:
    """DP4 headline: most-severe surviving verdict (muted excluded)."""
    best: FindingSeverity | None = None
    for verdict in _surviving(chain).values():
        if verdict.severity == FindingSeverity.muted:
            continue
        if best is None or _SEVERITY_RANK[verdict.severity] > _SEVERITY_RANK[best]:
            best = verdict.severity
    # All surviving verdicts muted -> the headline is muted (suppressed): the
    # value WAS judged, the judgment is "deliberately not assessed / waived".
    return best if best is not None else FindingSeverity.muted


def surface_recommendation(
    template_rules: list[dict[str, Any]],
    severity: FindingSeverity | None,
    verdict_chain: list[VerdictEntry],
    value_context: dict[str, Any] | None = None,
) -> "RecommendationIntent | None":
    """Recommend-seam §3b: copy a fired, surviving rule's declared
    ``recommendation`` payload onto the verdict (no generation).

    Returns a RecommendationIntent iff a template rule declared a
    ``recommendation`` payload AND that rule's verdict survives **non-muted**.
    SC4: a muted/waived unit (or an unjudged one) carries no intent. ``inputs``
    are resolved to their measured values from ``value_context`` (the section's
    computed item values) at judge time, so the recommender needs no catalog
    round-trip.
    """
    if severity is None or severity is FindingSeverity.muted:
        return None  # SC4 (waived) + unjudged: no intent
    values = value_context or {}
    surviving = _surviving(verdict_chain)
    for rule in template_rules:
        rec = rule.get("recommendation")
        if not rec:
            continue
        survivor = surviving.get(rule.get("rule_id"))
        if survivor is None or survivor.severity is FindingSeverity.muted:
            continue  # this rule was overridden/muted — don't surface its intent
        return RecommendationIntent(
            intent_kind=rec.get("intent_kind"),
            signal=rec.get("signal"),
            inputs_resolved={f: values.get(f) for f in (rec.get("inputs") or [])},
            note=rec.get("note"),
        )
    return None
