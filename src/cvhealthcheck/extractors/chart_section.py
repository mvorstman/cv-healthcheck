"""
cvhealthcheck.extractors.chart_section
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 3 — build a canonical ChartSection from raw collected rows and
a catalog chart declaration. Reusable (mirrors build_metric_section).

A chart is a VIEW over tabular data: it declares WHICH table columns map to the
labels (shared X / slice names) and to each series (a line, or the single
proportional series of a pie), plus HOW to draw it (chart_type). It stores no
different data — just the column→visual mapping.

Spec = the ``chart`` block of a section's ``extraction_instructions``:

    {
      "chart_type": "line",                       # ChartType: line | bar | pie
      "x_axis": {"label": "Month"},               # optional
      "y_axis": {"label": "Clients"},             # optional
      "labels": {"source": "column", "column": "month"},
      "series": [
        {"id": "added", "label": "Added", "source": "column", "column": "added"},
        {"id": "total", "label": "Total", "source": "column", "column": "total"}
      ]
    }

Both shapes use the same "column across rows" mapping; ``chart_type``
discriminates drawing:
  - line/bar: labels from one column, N series each from a column (shared X).
  - pie:      labels = slice names (one column), ONE series = slice values.

Charts map raw columns directly — no CEL derivation in phase 3 (a series could
gain an ``expr`` later, but it is not built now). Charts carry no verdict; the
evaluative face is empty for charts in phase 3.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.models import ChartAxis, ChartSection, ChartSeries


def build_chart_section(
    section_id: str,
    title: str,
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
) -> ChartSection:
    """Build a ChartSection by mapping table columns to labels + series."""
    chart_type = spec.get("chart_type", "line")

    labels_spec = spec.get("labels") or {}
    label_col = labels_spec.get("column")
    labels = [_label(row.get(label_col)) for row in rows] if label_col else []

    # Values equal to a declared gap value (e.g. capacity_license's -1 inactive
    # month) — and null — become None: a gap in the line, NOT a plotted zero or
    # a literal negative. 0 stays a real value.
    gap_values = spec.get("gap_values") or []
    series: list[ChartSeries] = []
    for s in spec.get("series") or []:
        col = s.get("column", s.get("id"))
        data = [_number(row.get(col), gap_values) for row in rows]
        series.append(ChartSeries(id=s["id"], label=s.get("label", s["id"]), data=data))

    return ChartSection(
        type="chart",
        id=section_id,
        title=title,
        chart_type=chart_type,
        x_axis=_axis(spec.get("x_axis")),
        y_axis=_axis(spec.get("y_axis")),
        labels=labels,
        series=series,
    )


def _axis(value: dict[str, Any] | None) -> ChartAxis | None:
    if not value:
        return None
    return ChartAxis(label=value.get("label", ""), unit=value.get("unit"))


def _label(value: Any) -> str:
    return "" if value is None else str(value)


def _number(value: Any, gap_values: list[Any] | None = None) -> float | None:
    """Coerce a cell to float for a chart series. None / a declared gap value
    (e.g. -1) -> None (a gap in the line, kept distinct from a real 0); an
    unparseable value -> None (gap). The series stays aligned to the labels
    (a None still occupies its position; the model validator requires equal
    lengths)."""
    if value is None or (gap_values and value in gap_values):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
