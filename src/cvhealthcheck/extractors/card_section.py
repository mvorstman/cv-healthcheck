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

Direct field mapping — no CEL in phase 4 (a card reads raw identity fields).
The row-mapped categorical variant (one card item per row, e.g. BJS status
breakdown) is deferred to phase 7; the spec leaves room for a future
``"source": "rows"`` without restructuring.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.models import CardItem, CardSection
from cvhealthcheck.evaluative.threshold import evaluate_threshold_rule


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
        field = it.get("field", it["label"])
        items.append(CardItem(label=it["label"], value=row.get(field), unit=it.get("unit")))

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
        verdict = evaluate_threshold_rule(
            rule, value, label=title, unit=rule.get("unit")
        )
        section.severity = verdict.severity
        section.verdict_chain = [verdict]

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
