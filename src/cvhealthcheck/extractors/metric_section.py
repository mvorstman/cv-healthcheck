"""
cvhealthcheck.extractors.metric_section
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 2 — build a canonical MetricSection from raw collected rows and
a catalog metric declaration. Reusable: phase 5 (capacity_license) uses this
same helper with the same shape of spec.

The spec is the ``metric`` block of a section's ``extraction_instructions``:

    {
      "semantic": {"sentinel": -1},          # raw value meaning "n/a"
      "items": [
        {"id": "used", "label": "Used", "unit": "TB",
         "source": "field", "field": "used_capacity", "agg": "latest"},
        {"id": "utilisation_pct", "label": "Utilisation", "unit": "%",
         "source": "cel", "expr": "used / purchased * 100.0",
         "sentinel_when": "used == null"}        # optional: derived n/a guard
      ],
      "evaluative": {"rules": [ <threshold rule>, ... ]}
    }

Derivations run once here, at collection time, and are stored on the
MetricSection — never re-derived at render time (ADR 0004 §"Formula language").
Bad CEL expressions raise (loud-fail) via the phase-1 evaluator.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import MetricItem, MetricSection
from cvhealthcheck.cel import evaluate as cel_evaluate
from cvhealthcheck.evaluative import engine


def build_metric_section(
    section_id: str,
    title: str,
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
) -> MetricSection:
    """Build a MetricSection from rows + spec.

    render_mode comes from the spec (default "metric" — the rich evaluative
    renderer with per-item value/derived/severity badges). A spec may set
    render_mode "meta" for an INFORMATIONAL metric (e.g. client_growth's
    latest-Total headline): plain key/value, no verdict — declare no
    evaluative.rules and the section carries no severity. This is declared
    intent, not inferred from whether a rule happens to be present."""
    semantic = spec.get("semantic") or {}
    sentinel = semantic.get("sentinel")
    item_specs = spec.get("items") or []
    rules = (spec.get("evaluative") or {}).get("rules") or []

    items: list[MetricItem] = []
    # Computed values keyed by item id, available to later CEL items as context.
    computed: dict[str, Any] = {}

    for item_spec in item_specs:
        item_id = item_spec["id"]
        label = item_spec.get("label", item_id)
        unit = item_spec.get("unit")
        source = item_spec.get("source", "field")
        derived = bool(item_spec.get("derived", source == "cel"))

        if source == "field":
            value = _aggregate(rows, item_spec.get("field", item_id), item_spec.get("agg", "latest"))
            if sentinel is not None and value == sentinel:
                value = None  # sentinel -> "n/a"
        elif source == "cel":
            value = _derive_cel(item_spec, rows, computed)
        else:
            raise ValueError(f"Unknown metric item source {source!r} for {item_id!r}")

        computed[item_id] = value
        items.append(MetricItem(id=item_id, label=label, value=value, unit=unit, derived=derived))

    # Index items by id so rules can attach severities.
    items_by_id = {item.id: item for item in items}
    for rule in rules:
        target_id = rule.get("target")
        target = items_by_id.get(target_id)
        if target is None:
            raise ValueError(f"Threshold rule targets unknown metric item {target_id!r}")
        target.severity, target.verdict_chain = engine.evaluate(
            computed.get(target_id), rule, label=target.label, unit=target.unit
        )

    return MetricSection(
        type="metric",
        id=section_id,
        title=title,
        items=items,
        render_mode=spec.get("render_mode", "metric"),
    )


def worst_metric_severity(section: MetricSection) -> FindingSeverity | None:
    """The most severe non-muted severity across the section's items, or None."""
    rank = {
        FindingSeverity.good: 0,
        FindingSeverity.info: 1,
        FindingSeverity.warning: 2,
        FindingSeverity.critical: 3,
    }
    worst: FindingSeverity | None = None
    for item in section.items:
        sev = item.severity
        if sev is None or sev == FindingSeverity.muted:
            continue
        if worst is None or rank.get(sev, -1) > rank.get(worst, -1):
            worst = sev
    return worst


def _aggregate(rows: list[dict[str, Any]], field: str, agg: str) -> Any:
    """Reduce a column across rows. Default 'latest' = the last row's value."""
    present = [row[field] for row in rows if field in row and row[field] is not None]
    if agg == "latest":
        # Last row that has the field at all (preserve sentinels, so don't filter None here).
        for row in reversed(rows):
            if field in row:
                return row[field]
        return None
    if agg == "first":
        for row in rows:
            if field in row:
                return row[field]
        return None
    if not present:
        return None
    if agg == "sum":
        return sum(present)
    if agg == "max":
        return max(present)
    if agg == "min":
        return min(present)
    if agg == "avg":
        return sum(present) / len(present)
    raise ValueError(f"Unknown metric aggregation {agg!r}")


def _derive_cel(
    item_spec: dict[str, Any],
    rows: list[dict[str, Any]],
    computed: dict[str, Any],
) -> Any:
    """Evaluate a CEL-derived metric value. Context = records + prior item ids."""
    context = {"records": rows, **computed}
    # Optional explicit sentinel guard: if the predicate holds, the derived
    # value is "n/a" (None) rather than being computed.
    sentinel_when = item_spec.get("sentinel_when")
    if sentinel_when and cel_evaluate(sentinel_when, context):
        return None
    return cel_evaluate(item_spec["expr"], context)
