"""ADR 0004 phase 3 (3a) — the ChartSection model carries BOTH chart data
shapes with no change (the architectural settle): line/bar = labels + N series
over a shared X; pie = labels (slices) + one proportional series. The existing
validator (each series.data length == labels length) holds for both."""
import pytest
from pydantic import ValidationError

from cvhealthcheck.artifacts.enums import ChartType
from cvhealthcheck.artifacts.models import ChartAxis, ChartSection, ChartSeries


def test_line_multi_series_over_shared_x():
    sec = ChartSection(
        type="chart", id="_chart_test.trend", title="Client Trend",
        chart_type=ChartType.line,
        x_axis=ChartAxis(label="Month"), y_axis=ChartAxis(label="Clients"),
        labels=["2024-06", "2024-07", "2024-08"],
        series=[
            ChartSeries(id="added", label="Added", data=[10.0, 8.0, 12.0]),
            ChartSeries(id="total", label="Total", data=[100.0, 108.0, 120.0]),
        ],
    )
    assert sec.chart_type == ChartType.line
    assert len(sec.series) == 2
    assert all(len(s.data) == len(sec.labels) for s in sec.series)


def test_pie_single_proportional_series():
    # Pie = labels (slice names) + ONE series whose data are the slice values.
    sec = ChartSection(
        type="chart", id="_chart_test.status", title="Job Status",
        chart_type=ChartType.pie,
        labels=["Completed", "Failed", "Running"],
        series=[ChartSeries(id="breakdown", label="Jobs", data=[45.0, 3.0, 2.0])],
    )
    assert sec.chart_type == ChartType.pie
    assert len(sec.series) == 1
    assert sec.series[0].data == [45.0, 3.0, 2.0]
    assert len(sec.series[0].data) == len(sec.labels)


def test_validator_rejects_series_length_mismatch():
    with pytest.raises(ValidationError):
        ChartSection(
            type="chart", id="x", title="X", chart_type=ChartType.line,
            labels=["a", "b", "c"],
            series=[ChartSeries(id="s", label="S", data=[1.0, 2.0])],  # 2 != 3
        )


def test_chart_type_enum_has_line_and_pie():
    assert ChartType.line.value == "line"
    assert ChartType.pie.value == "pie"
