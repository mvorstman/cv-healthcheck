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

from cvhealthcheck.artifacts.models import CardItem, CardSection
from cvhealthcheck.cel import evaluate as cel_evaluate
from cvhealthcheck.evaluative import engine
from cvhealthcheck.extractors.metric_section import _aggregate


def build_card_section(
    section_id: str,
    title: str,
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
) -> CardSection:
    """Build a CardSection: map one row's fields to labeled items, and apply an
    optional template-default verdict (reusing the metric threshold evaluator)."""
    # A card is "typically one row" — the first row carries the identity.
    row = rows[0] if rows else {}

    items: list[CardItem] = []
    for it in spec.get("items") or []:
        label = it["label"]
        source = it.get("source", "field")
        if source == "field":
            field = it.get("field", label)
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
        items.append(CardItem(label=label, value=value, unit=it.get("unit")))

    section = CardSection(
        type="card",
        id=section_id,
        title=title,
        items=items,
        columns=spec.get("columns"),
    )

    rule = (spec.get("evaluative") or {}).get("rule")
    if rule:
        value = _coerce_number(row.get(rule.get("target_field")))
        section.severity, section.verdict_chain = engine.evaluate(
            value, rule, label=title, unit=rule.get("unit")
        )

    return section


def _coerce_number(value: Any) -> float | None:
    """Threshold rules judge a number; a non-numeric identity field -> None
    (the rule then mutes / defaults, never crashes)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
