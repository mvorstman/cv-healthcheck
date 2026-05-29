"""ADR 0004 phase 3 (3b) — build_chart_section column mapping (line + pie) and
result_to_artifact emission of ChartSection on output_as == "chart"."""
import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, ChartType
from cvhealthcheck.artifacts.models import CanonicalArtifact, ChartSection
from cvhealthcheck.extractors.chart_section import build_chart_section
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


LINE_ROWS = [
    {"month": "2024-06", "added": 10, "total": 100},
    {"month": "2024-07", "added": 8, "total": 108},
    {"month": "2024-08", "added": 12, "total": 120},
]
LINE_SPEC = {
    "chart_type": "line",
    "x_axis": {"label": "Month"},
    "y_axis": {"label": "Clients"},
    "labels": {"source": "column", "column": "month"},
    "series": [
        {"id": "added", "label": "Added", "source": "column", "column": "added"},
        {"id": "total", "label": "Total", "source": "column", "column": "total"},
    ],
}

PIE_ROWS = [
    {"status": "Completed", "count": 45},
    {"status": "Failed", "count": 3},
    {"status": "Running", "count": 2},
]
PIE_SPEC = {
    "chart_type": "pie",
    "labels": {"source": "column", "column": "status"},
    "series": [{"id": "breakdown", "label": "Jobs", "source": "column", "column": "count"}],
}


def test_line_shape_maps_multiple_series():
    sec = build_chart_section("_chart_test.trend", "Trend", LINE_SPEC, LINE_ROWS)
    assert sec.chart_type == ChartType.line
    assert sec.labels == ["2024-06", "2024-07", "2024-08"]
    by_id = {s.id: s for s in sec.series}
    assert by_id["added"].data == [10.0, 8.0, 12.0]
    assert by_id["total"].data == [100.0, 108.0, 120.0]
    assert sec.x_axis.label == "Month" and sec.y_axis.label == "Clients"


def test_pie_shape_single_series():
    sec = build_chart_section("_chart_test.status", "Status", PIE_SPEC, PIE_ROWS)
    assert sec.chart_type == ChartType.pie
    assert sec.labels == ["Completed", "Failed", "Running"]
    assert len(sec.series) == 1
    assert sec.series[0].data == [45.0, 3.0, 2.0]


def test_missing_cell_becomes_gap_keeping_alignment():
    rows = [{"month": "2024-06", "added": 10}, {"month": "2024-07"}]  # 2nd row missing 'added'
    sec = build_chart_section("s", "S", LINE_SPEC, rows)
    added = next(s for s in sec.series if s.id == "added")
    assert added.data == [10.0, None]            # None = gap, not 0
    assert len(added.data) == len(sec.labels)    # validator-safe


def test_iso_datetime_labels_truncated_to_date():
    # client_growth: MonthStart converts (unix_seconds) to an ISO datetime;
    # the chart axis shows the date part. Non-ISO labels pass through.
    rows = [
        {"month": "2025-05-01T00:00:00+00:00", "total": 0},
        {"month": "2026-04-01T00:00:00+00:00", "total": 5},
        {"month": "May 1, 2025", "total": 1},  # non-ISO -> unchanged
    ]
    spec = {
        "chart_type": "line",
        "labels": {"source": "column", "column": "month"},
        "series": [{"id": "total", "label": "Total", "column": "total"}],
    }
    sec = build_chart_section("cg.chart", "Total", spec, rows)
    assert sec.labels == ["2025-05-01", "2026-04-01", "May 1, 2025"]


def test_gap_values_and_null_become_gaps_zero_stays_real():
    # capacity_license shape: -1 (inactive) and null -> gap; 0 -> real value.
    rows = [
        {"month": "2025-05", "used": -1},
        {"month": "2026-04", "used": 0},
        {"month": "2026-05", "used": None},
    ]
    spec = {
        "chart_type": "line",
        "labels": {"source": "column", "column": "month"},
        "series": [{"id": "used", "label": "Used", "column": "used"}],
        "gap_values": [-1],
    }
    sec = build_chart_section("cl.chart", "Used", spec, rows)
    assert sec.series[0].data == [None, 0.0, None]   # -1->gap, 0->real, null->gap


# ── result_to_artifact emission ──

def _chart_result(spec, rows, sid="_chart_test.trend") -> ExtractionResult:
    result = ExtractionResult(subject_id="_chart_test", source_type="json")
    result.sections[sid] = rows
    result.section_output_types[sid] = "chart"
    result.section_titles[sid] = "Chart"
    result.section_chart_specs[sid] = spec
    return result


def test_result_to_artifact_emits_chart_section():
    artifact = result_to_artifact(_chart_result(LINE_SPEC, LINE_ROWS), "_chart_test", "Chart Test")
    CanonicalArtifact.model_validate(artifact.model_dump())
    charts = [s for s in artifact.sections if isinstance(s, ChartSection)]
    assert len(charts) == 1
    assert charts[0].chart_type == ChartType.line
    # A chart-only artifact registers as good (data available), not unknown.
    assert artifact.summary.status == ArtifactStatus.good


def test_chart_roundtrips_through_json():
    artifact = result_to_artifact(_chart_result(PIE_SPEC, PIE_ROWS, "_chart_test.status"),
                                  "_chart_test", "Chart Test")
    reloaded = CanonicalArtifact.model_validate(artifact.model_dump(mode="json"))
    sec = next(s for s in reloaded.sections if isinstance(s, ChartSection))
    assert sec.chart_type == ChartType.pie
    assert sec.series[0].data == [45.0, 3.0, 2.0]
