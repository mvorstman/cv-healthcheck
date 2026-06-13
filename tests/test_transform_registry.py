"""ADR-0016 transform layer slice 2 — closed registry + four simple transforms.

A recipe field may carry ``transforms: [name, ...]`` applied in order to the
(coalesced) source value; names resolve only against the closed, platform-owned
registry. Slice 2 ships the four pure coercions (trim, null_if_empty, to_integer,
to_float) — NOT mask (slice 3), number_with_unit (slice 4), to_float_percent,
metadata_pairs, or computed sections. Unknown name → raises (interim enforcement
until the ADR-0015 compile gate).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.extractors.column_map import (
    TRANSFORMS,
    UnknownTransformError,
    apply_transforms,
    extract_row,
    resolve_columns,
)
from cvhealthcheck.extractors.csv import CSVExtractor

from test_column_coalesce import _seed_subject  # sibling helper (tests/ on sys.path)


def _resolved(column_map, header_map):
    return resolve_columns(column_map, header_map, section_id="s", warnings=[])


# ── the registry is exactly the four simple transforms (no mask / units yet) ──

def test_registry_contains_the_four_simple_transforms():
    # Slice 2 introduced exactly these four; later slices add more by ADR
    # amendment (mask_registration_code in slice 3), so this is a subset check.
    assert {"trim", "null_if_empty", "to_integer", "to_float"} <= set(TRANSFORMS)


# ── each of the four in isolation ────────────────────────────────────────────

def test_trim():
    assert apply_transforms(["trim"], "  x  ") == "x"


def test_null_if_empty_blank_to_none():
    assert apply_transforms(["null_if_empty"], "   ") is None


def test_null_if_empty_keeps_nonempty():
    assert apply_transforms(["null_if_empty"], "y") == "y"


def test_to_integer():
    assert apply_transforms(["to_integer"], "5") == 5


def test_to_integer_nonnumeric_is_none():
    assert apply_transforms(["to_integer"], "abc") is None


def test_to_float():
    assert apply_transforms(["to_float"], "1.5") == 1.5


def test_to_float_nonnumeric_is_none():
    assert apply_transforms(["to_float"], "x") is None


# ── ordered application ───────────────────────────────────────────────────────

def test_ordered_trim_then_to_integer():
    assert apply_transforms(["trim", "to_integer"], " 5 ") == 5


def test_ordered_three_step_chain_applies_left_to_right():
    # trim → null_if_empty → to_integer, applied in sequence:
    assert apply_transforms(["trim", "null_if_empty", "to_integer"], "  9  ") == 9
    assert apply_transforms(["trim", "null_if_empty", "to_integer"], "   ") is None


# ── unknown transform name → raises, clear message (interim enforcement) ─────

def test_unknown_transform_apply_raises():
    with pytest.raises(UnknownTransformError) as exc:
        apply_transforms(["nope"], "x")
    msg = str(exc.value)
    assert "nope" in msg and "Known transforms" in msg


def test_unknown_transform_resolve_raises_with_field_and_section():
    with pytest.raises(UnknownTransformError) as exc:
        resolve_columns(
            [{"source": "A", "canonical": "a", "transforms": ["bogus"]}],
            {"a": 0}, section_id="sec", warnings=[],
        )
    msg = str(exc.value)
    assert "bogus" in msg and "'a'" in msg and "sec" in msg


def test_unknown_transform_raises_even_when_source_absent():
    # validation is eager — a typo'd transform fails regardless of column presence
    with pytest.raises(UnknownTransformError):
        resolve_columns(
            [{"source": "MISSING", "canonical": "a", "transforms": ["bogus"]}],
            {"other": 0}, section_id="sec", warnings=[],
        )


# ── composition with slice-1 coalesce ────────────────────────────────────────

def test_coalesce_then_transform_chain():
    cmap = [{"source": ["A", "B"], "canonical": "v", "transforms": ["trim", "to_integer"]}]
    resolved = _resolved(cmap, {"a": 0, "b": 1})
    out = extract_row(["  ", " 7 "], resolved, ["N/A", ""], "s", [])
    assert out == {"v": 7}  # A empty → B " 7 " → trim → "7" → to_integer → 7


def test_coalesce_none_present_stays_null_no_transform_error():
    cmap = [{"source": ["X", "Y"], "canonical": "v", "transforms": ["to_integer"]}]
    resolved = _resolved(cmap, {"a": 0})
    out = extract_row(["a"], resolved, ["N/A", ""], "s", [])
    assert out == {"v": None}  # nothing selected → null; chain not applied to None


# ── no-transforms field → unchanged (regression) ─────────────────────────────

def test_no_transforms_integer_type_coercion_unchanged():
    cmap = [{"source": "A", "canonical": "a", "type": "integer"}]
    resolved = _resolved(cmap, {"a": 0})
    out = extract_row(["42"], resolved, ["N/A", ""], "s", [])
    assert out == {"a": 42}


def test_no_transforms_string_type_strips_as_before():
    cmap = [{"source": "A", "canonical": "a", "type": "string"}]
    resolved = _resolved(cmap, {"a": 0})
    out = extract_row(["  hi  "], resolved, ["N/A", ""], "s", [])
    assert out == {"a": "hi"}  # existing string coercion strips — unchanged


# ── end-to-end through the real CSV extractor ────────────────────────────────

def test_csv_extractor_transforms_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "tx_csv", "tx_csv.tbl", "csv",
        {"format": "single_table", "column_map": [
            {"source": "License", "canonical": "license", "type": "string"},
            {"source": "Count", "canonical": "count", "transforms": ["trim", "to_integer"]},
        ], "null_values": ["N/A", "-", ""], "output_as": "table"},
    )
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"License","Count"\n"L1"," 12 "\n', encoding="utf-8")

    result = CSVExtractor(conn).extract(csv_path, "tx_csv")
    conn.close()
    # transforms produce an int (12), not the string "12" a plain column would give
    assert result.sections["tx_csv.tbl"] == [{"license": "L1", "count": 12}]
