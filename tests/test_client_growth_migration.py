"""ADR 0004 phase 6 — client_growth three-face migration, driven end-to-end
through the migrated catalog + REST extractor against the REAL dev-box capture
shape (13 fully-populated monthly rows, no sentinel, single entity).

The offline twin of the live browser-verification: proves the three sections
build, the metric is INFORMATIONAL (meta render_mode, no verdict), the chart is
a continuous line (no gaps), and net change reads the same latest month as the
Total headline.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    ChartSection,
    MetricSection,
    TableSection,
)
from cvhealthcheck.extractors.rest import RESTExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# Real "Client Count" rows captured against the dev box (MonthStart unix secs).
_ZERO_MONTHS = [
    {"MonthStart": ts, "Added": 0, "Removed": 0, "Total": 0}
    for ts in (1746057600, 1748736000, 1751328000, 1754006400, 1756684800,
               1759276800, 1761955200, 1764547200, 1767225600, 1769904000, 1772323200)
]
CC_ROWS = _ZERO_MONTHS + [
    {"MonthStart": 1775001600, "Added": 8, "Removed": 3, "Total": 5},   # Apr 2026
    {"MonthStart": 1777593600, "Added": 0, "Removed": 0, "Total": 5},   # May 2026 (latest)
]


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _session(rows):
    s = MagicMock()
    s.get_report.return_value = {}            # name->guid falls back to the catalog guid hint
    s.fetch_dataset.return_value = rows
    return s


def _collect(db_path: Path):
    conn = _conn(db_path)
    try:
        return RESTExtractor(conn, _session(CC_ROWS), "default", "default").extract("client_growth", 1)
    finally:
        conn.close()


def test_client_growth_collects_three_faces(migrated_db_path: Path):
    result = _collect(migrated_db_path)
    assert not result.errors, result.errors
    artifact = result_to_artifact(result, "client_growth", "Client Growth")
    CanonicalArtifact.model_validate(artifact.model_dump())
    assert {type(s).__name__ for s in artifact.sections} >= {"MetricSection", "TableSection", "ChartSection"}


def test_metric_is_informational_no_verdict(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "client_growth", "Client Growth")
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    assert metric.render_mode == "meta"          # plain k/v, not the rich evaluative renderer
    items = {i.id: i for i in metric.items}
    assert items["total"].value == 5             # latest-month Total headline
    # No verdict on any item (informational metric — no rule, no badge).
    assert all(i.severity is None and i.verdict_chain == [] for i in metric.items)
    # net change reads the SAME latest month (May 2026: 0 - 0 = 0) as the Total headline.
    assert items["net_change"].value == 0


def test_chart_is_continuous_line_no_gaps(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "client_growth", "Client Growth")
    chart = next(s for s in artifact.sections if isinstance(s, ChartSection))
    assert chart.chart_type.value == "line"
    data = chart.series[0].data
    assert len(data) == 13
    assert None not in data                       # no sentinel -> no gaps
    assert data[:11] == [0.0] * 11                # genuine zeros, plotted (not gaps)
    assert data[-1] == 5.0
    # ISO datetime labels truncated to date.
    assert chart.labels[0] == "2025-05-01"


def test_table_clean_columns(migrated_db_path: Path):
    artifact = result_to_artifact(_collect(migrated_db_path), "client_growth", "Client Growth")
    table = next(s for s in artifact.sections if isinstance(s, TableSection))
    assert len(table.items) == 13
    assert set(table.items[0].keys()) == {"month", "added", "removed", "total"}
