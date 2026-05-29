"""ADR 0004 phase 7 — backup_job_summary three-face migration, driven end-to-end
through the migrated catalog + REST extractor against the lab's REAL shape:
ZERO rows (the "Job details" dataset returns totalRecordCount: 0).

This is the offline twin of the live browser-verification, and it asserts the
phase's actual deliverable: the four faces all build and render an empty state
cleanly and informatively — the all-zero card (no verdict/badge), the
informational Total-Jobs metric, the empty findings, and the Recent-jobs table
with its subject-specific "No jobs in the selected window" empty message.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    CardSection,
    FindingsSection,
    MetricSection,
    TableSection,
)
from cvhealthcheck.extractors.rest import RESTExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


_BUCKETS = ["Completed", "Failed", "Completed with errors/warnings",
            "Running", "Killed", "Other"]


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


def _collect(db_path: Path, rows=()):
    conn = _conn(db_path)
    try:
        return RESTExtractor(conn, _session(list(rows)), "default", "default").extract(
            "backup_job_summary", 1
        )
    finally:
        conn.close()


def _artifact(db_path, rows=()):
    return result_to_artifact(_collect(db_path, rows), "backup_job_summary", "Backup Job Summary")


def test_collects_all_four_faces(migrated_db_path: Path):
    result = _collect(migrated_db_path)
    assert not result.errors, result.errors
    artifact = _artifact(migrated_db_path)
    CanonicalArtifact.model_validate(artifact.model_dump())
    kinds = {type(s).__name__ for s in artifact.sections}
    assert kinds == {"MetricSection", "CardSection", "FindingsSection", "TableSection"}


def test_card_is_all_zero_no_verdict_on_empty_lab(migrated_db_path: Path):
    artifact = _artifact(migrated_db_path)
    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    assert [i.label for i in card.items] == _BUCKETS
    assert all(i.value == 0 for i in card.items)          # count() on empty -> 0, not blank
    # Emptiness is shown, not graded — no verdict, no badge.
    assert card.severity is None and card.verdict_chain == []


def test_metric_is_informational_total_jobs(migrated_db_path: Path):
    artifact = _artifact(migrated_db_path)
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    assert metric.render_mode == "meta"
    items = {i.id: i for i in metric.items}
    assert items["total_jobs"].value == 0
    assert all(i.severity is None and i.verdict_chain == [] for i in metric.items)


def test_table_empty_with_custom_message(migrated_db_path: Path):
    artifact = _artifact(migrated_db_path)
    table = next(s for s in artifact.sections if isinstance(s, TableSection))
    assert table.items == []
    assert table.empty_message == "No jobs in the selected window"


def test_findings_empty_on_empty_lab(migrated_db_path: Path):
    artifact = _artifact(migrated_db_path)
    findings = next(s for s in artifact.sections if isinstance(s, FindingsSection))
    assert findings.items == []


def test_card_counts_populate_when_rows_exist(migrated_db_path: Path):
    # Proves the wiring is real, not just zero-by-accident: with rows present
    # (raw "Job Status" column -> canonical status via column_map), the buckets
    # count. (Bucket *accuracy* on freetext is phase 8; these are canonical
    # status strings.)
    rows = [{"Job Status": "Completed"}, {"Job Status": "Completed"},
            {"Job Status": "Failed"}]
    artifact = _artifact(migrated_db_path, rows)
    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    by = {i.label: i.value for i in card.items}
    assert by["Completed"] == 2 and by["Failed"] == 1 and by["Running"] == 0
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    assert {i.id: i.value for i in metric.items}["total_jobs"] == 3
