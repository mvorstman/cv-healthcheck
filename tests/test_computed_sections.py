"""ADR-0016 transform layer slice 6 — computed sections (the last transform slice).

Exactly three extraction-time row aggregates over an already-extracted section's
rows: row_count, distinct_count, grouped_count. A minimal, enumerated, CLOSED set
(ADR-0016 D1d) — no expressions/filters/arithmetic/custom functions. Unknown type
raises (interim enforcement). Computed sections SHAPE; the ADR-0010 rules JUDGE.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    TableColumn,
    TableSection,
)
from cvhealthcheck.extractors.column_map import (
    UnknownComputedTypeError,
    compute_section,
    extract_computed,
)
from cvhealthcheck.extractors.csv import CSVExtractor

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
_ROWS = [{"g": "A"}, {"g": "A"}, {"g": "B"}]


# ── compute_section: the three aggregates ────────────────────────────────────

def test_row_count():
    assert compute_section("row_count", _ROWS, None) == 3


def test_distinct_count():
    assert compute_section("distinct_count", _ROWS, "g") == 2


def test_grouped_count():
    assert compute_section("grouped_count", _ROWS, "g") == {"A": 2, "B": 1}


def test_distinct_count_excludes_none():
    rows = [{"g": "A"}, {"g": None}, {"g": "A"}]
    assert compute_section("distinct_count", rows, "g") == 1


def test_grouped_count_excludes_none():
    rows = [{"g": "A"}, {"g": None}, {"g": "B"}, {"g": "B"}]
    assert compute_section("grouped_count", rows, "g") == {"A": 1, "B": 2}


# ── missing / empty source → 0 / empty, not crash ────────────────────────────

def test_empty_source_aggregates():
    assert compute_section("row_count", [], None) == 0
    assert compute_section("distinct_count", None, "g") == 0
    assert compute_section("grouped_count", [], "g") == {}


# ── unknown computed type → raises (interim enforcement) ─────────────────────

def test_unknown_computed_type_raises():
    with pytest.raises(UnknownComputedTypeError) as exc:
        compute_section("sum", _ROWS, "g")
    assert "sum" in str(exc.value) and "Known" in str(exc.value)


# ── extract_computed (the section builder) ───────────────────────────────────

def test_extract_computed_row_count():
    sections = {"src": [{"x": 1}, {"x": 1}, {"x": 2}]}
    assert extract_computed(
        {"computed_type": "row_count", "source_section": "src"}, sections, "c", []
    ) == [{"value": 3}]


def test_extract_computed_grouped_count_and_output_field():
    sections = {"src": [{"x": 1}, {"x": 1}, {"x": 2}]}
    out = extract_computed(
        {"computed_type": "grouped_count", "source_section": "src", "field": "x",
         "output_field": "by_x"},
        sections, "c", [],
    )
    assert out == [{"by_x": {"1": 2, "2": 1}}]


def test_extract_computed_missing_source_is_zero_with_warning():
    warnings: list[str] = []
    out = extract_computed(
        {"computed_type": "row_count", "source_section": "nope"}, {}, "c", warnings
    )
    assert out == [{"value": 0}]
    assert any("not found" in w for w in warnings)


def test_extract_computed_unknown_type_raises():
    with pytest.raises(UnknownComputedTypeError):
        extract_computed(
            {"computed_type": "average", "source_section": "src"},
            {"src": [{"x": 1}]}, "c", [],
        )


# ── grouped_count {group: count} round-trips through the canonical artifact ───

def test_grouped_count_round_trips_through_canonical_artifact():
    artifact = CanonicalArtifact(
        artifact_type="demo",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="demo", title="Demo"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=[
            TableSection(
                type="table", id="g", title="G",
                columns=[TableColumn(id="value", label="Value")],
                items=[{"value": {"A": 2, "B": 1}}],
            ),
        ],
    )
    reloaded = CanonicalArtifact.model_validate(artifact.model_dump(mode="json"))
    assert reloaded.sections[0].items[0]["value"] == {"A": 2, "B": 1}


# ── compose: table + metadata_pairs + computed in one extraction ─────────────

def _seed_multi(conn, subject_id, source_type, sections):
    conn.execute(
        "INSERT INTO subjects (subject_id, version, title, description, category,"
        " category_label, status, created_by)"
        " VALUES (?, 1, ?, '', 'storage', 'Storage', 'active', 'user')",
        (subject_id, subject_id),
    )
    cur = conn.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type, extractable)"
        " VALUES (?, 1, ?, 1)",
        (subject_id, source_type),
    )
    source_id = cur.lastrowid
    for section_id, section_type, sort_order, instructions in sections:
        conn.execute(
            "INSERT INTO subject_sections (subject_id, subject_version, section_id, title,"
            " section_type, default_selected, sort_order) VALUES (?, 1, ?, ?, ?, 1, ?)",
            (subject_id, section_id, section_id, section_type, sort_order),
        )
        conn.execute(
            "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
            " VALUES (?, ?, ?)",
            (source_id, section_id, json.dumps(instructions)),
        )
    conn.commit()


def test_csv_compose_table_metadata_computed(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_multi(conn, "comp_csv", "csv", [
        ("comp_csv.tbl", "table", 1, {
            "format": "single_table",
            "column_map": [
                {"source": "License", "canonical": "license", "type": "string"},
                {"source": "Count", "canonical": "count", "type": "integer"},
            ],
            "null_values": ["N/A", "-", ""], "output_as": "table",
        }),
        ("comp_csv.meta", "metric", 2, {
            "format": "metadata_pairs",
            "label_map": [{"source": "CommCell ID", "canonical": "commcell_id"}],
            "null_values": [], "output_as": "metric",
        }),
        ("comp_csv.rowcount", "metric", 3, {
            "format": "computed", "computed_type": "row_count",
            "source_section": "comp_csv.tbl", "output_as": "metric",
        }),
        ("comp_csv.bylicense", "metric", 4, {
            "format": "computed", "computed_type": "grouped_count",
            "source_section": "comp_csv.tbl", "field": "license", "output_as": "metric",
        }),
    ])
    csv_path = tmp_path / "d.csv"
    csv_path.write_text(
        "License summary\nCommCell ID: 337f\n\nLicense,Count\nL1,5\nL2,3\n",
        encoding="utf-8",
    )

    result = CSVExtractor(conn).extract(csv_path, "comp_csv")
    conn.close()
    assert result.sections["comp_csv.tbl"] == [
        {"license": "L1", "count": 5}, {"license": "L2", "count": 3},
    ]
    assert result.sections["comp_csv.meta"] == [{"commcell_id": "337f"}]
    assert result.sections["comp_csv.rowcount"] == [{"value": 2}]
    assert result.sections["comp_csv.bylicense"] == [{"value": {"L1": 1, "L2": 1}}]
