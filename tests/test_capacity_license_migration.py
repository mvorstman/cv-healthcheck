"""ADR 0004 phase 5 — capacity_license three-face migration, driven end-to-end
through the migrated catalog + REST extractor against the REAL dev-box capture
shape (13 monthly rows, -1 inactive / 0 active, single entity CS01 - 337F).

This is the offline twin of the live browser-verification: it proves the three
sections build correctly from the catalog bindings, the sentinel/null handling
(metric muted n/a, chart gaps), and that nothing errors.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity
from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    ChartSection,
    MetricSection,
    TableSection,
)
from cvhealthcheck.extractors.rest import RESTExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# The real "Capacity License Usage" rows captured against the dev box.
_INACTIVE_2025 = [
    {"Month": f"{m} 1, 2025", "Entity Name": "CS01 - 337F",
     "Used Capacity": -1, "Purchased Capacity": -1}
    for m in ("May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
]
_INACTIVE_2026 = [
    {"Month": f"{m} 1, 2026", "Entity Name": "CS01 - 337F",
     "Used Capacity": -1, "Purchased Capacity": -1}
    for m in ("Jan", "Feb", "Mar")
]
_ACTIVE_2026 = [
    {"Month": "Apr 1, 2026", "Entity Name": "CS01 - 337F", "Used Capacity": 0, "Purchased Capacity": 0},
    {"Month": "May 1, 2026", "Entity Name": "CS01 - 337F", "Used Capacity": 0, "Purchased Capacity": 0},
]
CAP_ROWS = _INACTIVE_2025 + _INACTIVE_2026 + _ACTIVE_2026  # 13 rows


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _session(rows):
    s = MagicMock()
    s.get_report.return_value = {}            # name->guid resolution falls back to the catalog guid hint
    s.fetch_dataset.return_value = rows
    return s


def _collect(db_path: Path):
    conn = _conn(db_path)
    try:
        extractor = RESTExtractor(conn, _session(CAP_ROWS), "default", "default")
        result = extractor.extract("capacity_license", 1)
    finally:
        conn.close()
    return result


def test_capacity_license_collects_three_faces(migrated_db_path: Path):
    result = _collect(migrated_db_path)
    assert not result.errors, result.errors
    artifact = result_to_artifact(result, "capacity_license", "Capacity Licenses")
    CanonicalArtifact.model_validate(artifact.model_dump())
    kinds = {type(s).__name__ for s in artifact.sections}
    assert {"MetricSection", "TableSection", "ChartSection"} <= kinds


def test_metric_utilisation_is_muted_na_on_zero_data(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "capacity_license", "Capacity Licenses")
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    util = next(i for i in metric.items if i.id == "utilisation_pct")
    # Latest month is 0/0 -> sentinel_when (purchased == 0) -> muted n/a, NOT 0% or a crash.
    assert util.value is None
    assert util.severity == FindingSeverity.muted
    # The raw used/purchased items: latest month 0 is a real value (not sentinel).
    used = next(i for i in metric.items if i.id == "used")
    assert used.value == 0


def test_chart_used_line_has_gaps_at_sentinel_months(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "capacity_license", "Capacity Licenses")
    chart = next(s for s in artifact.sections if isinstance(s, ChartSection))
    assert chart.chart_type.value == "line"
    assert len(chart.labels) == 13
    data = chart.series[0].data
    assert len(data) == 13
    assert data[0] is None        # May 2025 (-1) -> gap
    assert data[-1] == 0.0        # May 2026 (0)  -> real value, plotted at zero
    assert data[-2] == 0.0        # Apr 2026 (0)
    assert all(d is None for d in data[:11])  # the eleven -1 inactive months are gaps


def test_table_renders_monthly_rows_with_clean_columns(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "capacity_license", "Capacity Licenses")
    table = next(s for s in artifact.sections if isinstance(s, TableSection))
    assert len(table.items) == 13
    # column_map produced clean canonical keys.
    assert set(table.items[0].keys()) == {"month", "entity", "used_capacity", "purchased_capacity"}
