"""ADR-0016 transform layer slice 4 — number_with_unit.

Parses a "<number> <unit>" cell into {value, unit} (Amendment A: parse-and-keep,
no normalization; Amendment B: cell contents only — header-encoded units
deferred). Slice 4 only — NOT metadata_pairs (slice 5), computed sections,
to_float_percent, header-unit extraction, or the LS recipe.
"""
from __future__ import annotations

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
from cvhealthcheck.extractors.column_map import TRANSFORMS, apply_transforms
from cvhealthcheck.extractors.csv import CSVExtractor

from test_column_coalesce import _seed_subject  # sibling helper (tests/ on sys.path)

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _nwu(v):
    return apply_transforms(["number_with_unit"], v)


# ── in the registry ──────────────────────────────────────────────────────────

def test_number_with_unit_in_registry():
    assert "number_with_unit" in TRANSFORMS


# ── unit-bearing values ──────────────────────────────────────────────────────

def test_tb():
    assert _nwu("25 TB") == {"value": 25, "unit": "TB"}


def test_vms():
    assert _nwu("500 VMs") == {"value": 500, "unit": "VMs"}


def test_users():
    assert _nwu("100 users") == {"value": 100, "unit": "users"}


# ── plain counts (no unit) ───────────────────────────────────────────────────

def test_plain_count():
    assert _nwu("500") == {"value": 500, "unit": None}


def test_zero_plain():
    assert _nwu("0") == {"value": 0, "unit": None}


# ── empty / null → safe (shape: whole-field None) ────────────────────────────

def test_null_empty_whitespace_is_none():
    assert _nwu(None) is None
    assert _nwu("") is None
    assert _nwu("   ") is None


def test_non_numeric_is_none():
    assert _nwu("N/A") is None
    assert _nwu("abc") is None


# ── whitespace tolerance ─────────────────────────────────────────────────────

def test_whitespace_tolerance():
    assert _nwu("25  TB") == {"value": 25, "unit": "TB"}
    assert _nwu(" 25 TB ") == {"value": 25, "unit": "TB"}
    assert _nwu("25TB") == {"value": 25, "unit": "TB"}


# ── value is a numeric type, not a string ────────────────────────────────────

def test_value_is_int_when_integral():
    out = _nwu("25 TB")
    assert isinstance(out["value"], int) and not isinstance(out["value"], bool)


def test_value_is_float_when_decimal():
    out = _nwu("25.5 TB")
    assert out == {"value": 25.5, "unit": "TB"}
    assert isinstance(out["value"], float)


def test_thousands_separator_tolerated():
    assert _nwu("1,000 TB") == {"value": 1000, "unit": "TB"}


# ── composes after trim ──────────────────────────────────────────────────────

def test_composes_after_trim():
    assert apply_transforms(["trim", "number_with_unit"], "  25 TB  ") == {
        "value": 25, "unit": "TB",
    }


# ── the {value, unit} shape round-trips through the canonical artifact ────────

def test_value_unit_pair_round_trips_through_canonical_artifact():
    artifact = CanonicalArtifact(
        artifact_type="demo",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="demo", title="Demo"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=[
            TableSection(
                type="table", id="t", title="T",
                columns=[
                    TableColumn(id="license", label="License"),
                    TableColumn(id="entitlement", label="Entitlement"),
                ],
                items=[{"license": "L1", "entitlement": _nwu("25 TB")}],
            ),
        ],
    )
    dumped = artifact.model_dump(mode="json")
    reloaded = CanonicalArtifact.model_validate(dumped)
    item = reloaded.sections[0].items[0]
    assert item["entitlement"] == {"value": 25, "unit": "TB"}


# ── end-to-end through the real CSV extractor ────────────────────────────────

def test_csv_extractor_number_with_unit_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "nwu_csv", "nwu_csv.tbl", "csv",
        {"format": "single_table", "column_map": [
            {"source": "License", "canonical": "license", "type": "string"},
            {"source": "Avail", "canonical": "entitlement",
             "transforms": ["trim", "number_with_unit"]},
        ], "null_values": ["N/A", "-", ""], "output_as": "table"},
    )
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"License","Avail"\n"L1","25 TB"\n"L2","500"\n', encoding="utf-8")

    result = CSVExtractor(conn).extract(csv_path, "nwu_csv")
    conn.close()
    assert result.sections["nwu_csv.tbl"] == [
        {"license": "L1", "entitlement": {"value": 25, "unit": "TB"}},
        {"license": "L2", "entitlement": {"value": 500, "unit": None}},
    ]
