"""ADR 0004 phase 3 (3d) — Python renderer for chart sections."""
from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import ArtifactStatus, ChartType, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    ChartAxis,
    ChartSection,
    ChartSeries,
)
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

_NOW = datetime(2026, 5, 29, tzinfo=timezone.utc)


def _artifact(section: ChartSection) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="_chart_test", generated_at=_NOW,
        source=ArtifactSource(type=SourceType.json_import),
        subject=ArtifactSubject(id="_chart_test", title="Chart Test"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[section],
    )


def test_line_chart_view():
    sec = ChartSection(
        type="chart", id="_chart_test.trend", title="Trend", chart_type=ChartType.line,
        x_axis=ChartAxis(label="Month"), y_axis=ChartAxis(label="Clients"),
        labels=["2024-06", "2024-07"],
        series=[ChartSeries(id="added", label="Added", data=[10.0, 8.0]),
                ChartSeries(id="total", label="Total", data=[100.0, 108.0])],
    )
    view = artifact_to_view(_artifact(sec))["sections"][0]
    assert view["type"] == "chart"
    chart = view["chart"]
    assert chart["chart_type"] == "line"
    assert chart["labels"] == ["2024-06", "2024-07"]
    assert len(chart["series"]) == 2
    assert chart["series"][0] == {"id": "added", "label": "Added", "data": [10.0, 8.0]}
    assert chart["x_axis"] == "Month" and chart["y_axis"] == "Clients"


def test_pie_chart_view():
    sec = ChartSection(
        type="chart", id="_chart_test.status", title="Status", chart_type=ChartType.pie,
        labels=["Completed", "Failed"],
        series=[ChartSeries(id="b", label="Jobs", data=[45.0, 3.0])],
    )
    chart = artifact_to_view(_artifact(sec))["sections"][0]["chart"]
    assert chart["chart_type"] == "pie"
    assert len(chart["series"]) == 1
    assert chart["series"][0]["data"] == [45.0, 3.0]
    assert chart["x_axis"] is None and chart["y_axis"] is None
