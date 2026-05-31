"""
cvhealthcheck.extractors.card_section
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 4 — build a canonical CardSection from raw collected rows and a
catalog card declaration. Reusable (mirrors build_metric_section /
build_chart_section).

A card is a flat labeled key-value identity block ("typically one row"): it
maps declared `{label, field}` items off ONE row. Per the phase-4 steering
decision, a card also carries a section-level verdict — produced by the SAME
phase-2 threshold evaluator a metric uses, set on CardSection.severity +
verdict_chain (single template_default layer). The duplication of the
evaluative shape across metric and card is intentional and temporary (phase 8
unifies the evaluative face).

Spec = the ``card`` block of a section's ``extraction_instructions``:

    {
      "columns": 4,                                  # optional presentational grid hint
      "items": [
        {"label": "CommCell Name", "field": "host"},
        {"label": "Free Space", "field": "free_pct", "unit": "%"}
      ],
      "evaluative": {                                # optional — a card CAN be judged
        "rule": {"rule_id": "free_space", "target_field": "free_pct",
                 "comparison": "<=", "bands": [{"at": 5, "severity": "critical"},
                 {"at": 15, "severity": "warning"}], "default_severity": "good",
                 "unit": "%"}
      }
    }

Item value sources (ADR 0004 phase 7 — mirror ``build_metric_section``):

  - ``"source": "field"`` (default) reads ONE row. Without ``agg`` it reads the
    first row's field (the identity-card default, unchanged from phase 4); with
    ``agg`` (sum/count/avg/min/max/latest/first) it reduces the column across
    all rows.
  - ``"source": "cel"`` evaluates ``expr`` over the section's ``records`` — the
    aggregated/categorical variant. Phase 7's first consumer is the BJS status
    breakdown: each of the six classify_job_status buckets is a CEL
    ``count(records.filter(r, r.status == "..."))``. On the empty lab every
    count is ``0`` (count() of an empty filter is 0, not n/a) — the all-zero
    card that is phase 7's empty-state. (Bucket accuracy on REAL freetext
    statuses — "Completed w/ errors" etc. — is a phase-8 item; the exact-match
    counts are correct only for the canonical status strings until then.)

Derivations run once here at collection time and are stored on the CardSection;
they are never re-derived at render time (ADR 0004 §"Formula language"). Bad CEL
raises (loud-fail) via the phase-1 evaluator.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import CardItem, CardSection
from cvhealthcheck.cel import evaluate as cel_evaluate
from cvhealthcheck.evaluative import engine
from cvhealthcheck.extractors.metric_section import _aggregate


def build_card_section(
    section_id: str,
    title: str,
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
    rules_registry: dict[str, dict[str, Any]] | None = None,
    overrides: list[dict[str, Any]] | None = None,
) -> CardSection:
    """Build a CardSection: map one row's fields to labeled items, and apply an
    optional template-default verdict (reusing the metric threshold evaluator)."""
    # A card is "typically one row" — the first row carries the identity.
    row = rows[0] if rows else {}

    items: list[CardItem] = []
    # field -> the CardItem built from it, so per-field rules (below) attach by
    # target_field. Last item wins on a duplicate field (rules judge one value).
    item_by_field: dict[str, CardItem] = {}
    # field -> the item's value, used as the recommend-seam input context so a
    # card rule's `recommendation.inputs` resolve to measured field values.
    field_values: dict[str, Any] = {}
    for it in spec.get("items") or []:
        label = it["label"]
        source = it.get("source", "field")
        field = it.get("field")
        if source == "field":
            field = field or label
            if "agg" in it:
                value = _aggregate(rows, field, it["agg"])
            else:
                value = row.get(field)
        elif source == "cel":
            # Card items don't cross-reference each other (no item id), so the
            # CEL context is just the section's records.
            value = cel_evaluate(it["expr"], {"records": rows})
        else:
            raise ValueError(f"Unknown card item source {source!r} for {label!r}")
        card_item = CardItem(label=label, value=value, unit=it.get("unit"))
        items.append(card_item)
        if field is not None:
            item_by_field[field] = card_item
            field_values[field] = value

    section = CardSection(
        type="card",
        id=section_id,
        title=title,
        items=items,
        columns=spec.get("columns"),
    )

    evaluative = spec.get("evaluative") or {}
    if evaluative.get("rules"):
        # Per-field judging (phase-8 follow-on): each rule names a target_field,
        # resolved through the same single engine locus as metric items. Each
        # judged field carries its own severity + verdict_chain (+ recommendation
        # intent); the section severity rolls up most-severe-surviving (DP4),
        # mirroring how a metric section's overall severity is the worst item.
        _apply_per_field_rules(
            section, evaluative["rules"], item_by_field, field_values,
            rules_registry, overrides,
        )
    elif evaluative.get("rule"):
        # Legacy section-level verdict (one rule, one target_field → CardSection
        # severity/verdict_chain). Unchanged — existing card subjects stay
        # byte-identical. A subject opts into per-field judging by declaring
        # `rules` (plural) instead of `rule` (singular).
        rule = engine.resolve_rule(evaluative["rule"], rules_registry)
        value = _coerce_number(row.get(rule.get("target_field")))
        rule_id = rule.get("rule_id")
        override_verdicts = [
            engine.build_override_verdict(o)
            for o in (overrides or [])
            if o.get("rule_id") == rule_id
        ]
        section.severity, section.verdict_chain = engine.evaluate(
            value, [rule], label=title, unit=rule.get("unit"),
            override_verdicts=override_verdicts,
        )

    return section


# Severity rank for the section-level roll-up (mirrors worst_metric_severity).
_ROLLUP_RANK = {
    FindingSeverity.good: 0,
    FindingSeverity.info: 1,
    FindingSeverity.warning: 2,
    FindingSeverity.critical: 3,
}


def _apply_per_field_rules(
    section: CardSection,
    rule_entries: list[dict[str, Any]],
    item_by_field: dict[str, CardItem],
    field_values: dict[str, Any],
    rules_registry: dict[str, dict[str, Any]] | None,
    overrides: list[dict[str, Any]] | None,
) -> None:
    """Resolve each rule onto its target field's CardItem, then roll the section
    severity up from the per-field verdicts.

    Mirrors ``build_metric_section``'s per-item resolution: group resolved rules
    by target, compose vendor→template→override through ``engine.evaluate`` (one
    locus, no second evaluator), and surface a fired rule's recommendation intent
    onto the field. The DP2 inline⨉ref guard is enforced per target_field."""
    template_by_field: dict[str, list[dict[str, Any]]] = {}
    seen_kind: dict[str, str] = {}  # target_field -> "ref"|"inline" (DP2 guard)
    for entry in rule_entries:
        kind = "ref" if "ref" in entry else "inline"
        resolved = engine.resolve_rule(entry, rules_registry)
        target_field = resolved.get("target_field")
        if target_field not in item_by_field:
            raise ValueError(
                f"Card rule targets unknown field {target_field!r} "
                f"(section {section.id!r})"
            )
        if seen_kind.get(target_field, kind) != kind:
            raise ValueError(
                f"Card section {section.id!r} has both an inline rule and a registry "
                f"ref targeting {target_field!r} — define one, not both (DP2)."
            )
        seen_kind[target_field] = kind
        template_by_field.setdefault(target_field, []).append(resolved)

    override_rows = overrides or []
    for target_field, template_rules in template_by_field.items():
        item = item_by_field[target_field]
        target_rule_ids = {r.get("rule_id") for r in template_rules}
        override_verdicts = [
            engine.build_override_verdict(o)
            for o in override_rows
            if o.get("rule_id") in target_rule_ids
        ]
        # Threshold rules judge a number; presence rules judge set-ness of the
        # raw value (a string field is "present"). Coerce only when a threshold
        # rule is on this field, so presence-on-a-string still sees the value.
        needs_number = any(r.get("kind", "threshold") == "threshold" for r in template_rules)
        raw = field_values.get(target_field)
        value = _coerce_number(raw) if needs_number else raw
        item.severity, item.verdict_chain = engine.evaluate(
            value, template_rules, label=item.label, unit=item.unit,
            override_verdicts=override_verdicts,
        )
        item.recommendation_intent = engine.surface_recommendation(
            template_rules, item.severity, item.verdict_chain, field_values
        )

    section.severity = _rollup_section_severity(section.items)


def _rollup_section_severity(items: list[CardItem]) -> FindingSeverity | None:
    """Section headline from per-field verdicts: most-severe surviving non-muted
    (DP4). All judged fields muted → muted; no field judged → None. The per-field
    chains carry the provenance, so section.verdict_chain stays empty here."""
    worst: FindingSeverity | None = None
    saw_muted = False
    for item in items:
        sev = item.severity
        if sev is None:
            continue
        if sev == FindingSeverity.muted:
            saw_muted = True
            continue
        if worst is None or _ROLLUP_RANK.get(sev, -1) > _ROLLUP_RANK.get(worst, -1):
            worst = sev
    if worst is not None:
        return worst
    return FindingSeverity.muted if saw_muted else None


def _coerce_number(value: Any) -> float | None:
    """Threshold rules judge a number; a non-numeric identity field -> None
    (the rule then mutes / defaults, never crashes)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
