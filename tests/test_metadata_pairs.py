"""ADR-0016 transform layer slice 5 — metadata_pairs section format.

Deterministic exact-label → value extraction from scattered "label: value"
rows/lines. Trim-only, CASE-SENSITIVE exact match; NO regex/fuzzy/hierarchical/
multi-line. Routes through the SAME resolve_columns + extract_row path (one
registry, one enforcement point), so transforms, the unknown-transform check, and
sensitive-field enforcement are shared with table sections — proven here for the
metadata_pairs path too (registration_code is the primary real use).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.extractors.column_map import (
    SensitiveFieldError,
    extract_metadata_pairs,
    split_label_value,
)
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import HTMLExtractor

from test_column_coalesce import _seed_subject  # sibling helper (tests/ on sys.path)


def _mp(pairs, label_map, *, null_values=None):
    warnings: list[str] = []
    row = extract_metadata_pairs(
        pairs, label_map, section_id="s",
        null_values=null_values or ["N/A", "-", ""], warnings=warnings,
    )
    return row, warnings


# ── split_label_value (deterministic, first-colon, trim) ─────────────────────

def test_split_basic():
    assert split_label_value("CommCell ID: 337f") == ("CommCell ID", "337f")


def test_split_first_colon_only_value_keeps_rest():
    assert split_label_value("Last Collection: 2026-01-01 10:30") == (
        "Last Collection", "2026-01-01 10:30",
    )


def test_split_trims_both_sides():
    assert split_label_value("  CommCell ID  :   337f  ") == ("CommCell ID", "337f")


def test_split_no_colon_is_none():
    assert split_label_value("no colon here") is None


def test_split_empty_side_is_none():
    assert split_label_value("Label:") is None
    assert split_label_value(": value") is None


# ── exact label matching (the core constraint) ───────────────────────────────

def test_exact_label_extracts_value():
    row, _ = _mp({"CommCell ID": "337f"}, [{"source": "CommCell ID", "canonical": "commcell_id"}])
    assert row == {"commcell_id": "337f"}


def test_case_difference_does_not_match():
    # label "CommCell ID" (recipe) vs "commcell id" (source) — exact, not fuzzy
    row, _ = _mp({"commcell id": "337f"}, [{"source": "CommCell ID", "canonical": "commcell_id"}])
    assert "commcell_id" not in row


def test_unknown_source_label_ignored():
    row, _ = _mp(
        {"CommCell ID": "337f", "Junk Label": "ignore me"},
        [{"source": "CommCell ID", "canonical": "commcell_id"}],
    )
    assert row == {"commcell_id": "337f"}


def test_mapped_label_absent_yields_no_key():
    row, _ = _mp({"Other": "x"}, [{"source": "CommCell ID", "canonical": "commcell_id"}])
    assert "commcell_id" not in row


# ── transform chain via the shared registry ──────────────────────────────────

def test_transform_chain_inside_metadata_pairs():
    row, _ = _mp(
        {"Count": "  5 "},
        [{"source": "Count", "canonical": "count", "transforms": ["trim", "to_integer"]}],
    )
    assert row == {"count": 5}


# ── sensitive-field enforcement (shared with table path) ─────────────────────

def test_registration_code_without_mask_raises():
    with pytest.raises(SensitiveFieldError):
        _mp(
            {"Registration Code": "XXXX-XXXX-XXXX-1234"},
            [{"source": "Registration Code", "canonical": "registration_code"}],
        )


def test_registration_code_with_mask_is_masked():
    row, _ = _mp(
        {"Registration Code": "XXXX-XXXX-XXXX-1234"},
        [{"source": "Registration Code", "canonical": "registration_code",
          "transforms": ["mask_registration_code"]}],
    )
    assert row == {"registration_code": "****-****-****-1234"}


def test_registration_code_raw_value_fails_closed():
    row, _ = _mp(
        {"Registration Code": "RAWCODE12345678"},   # unexpected shape
        [{"source": "Registration Code", "canonical": "registration_code",
          "transforms": ["mask_registration_code"]}],
    )
    assert row["registration_code"] is None              # fail-closed
    assert "RAWCODE12345678" not in str(row)             # raw never leaks


# ── end-to-end through the real CSV extractor ────────────────────────────────

def test_csv_metadata_pairs_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "md_csv", "md_csv.meta", "csv",
        {"format": "metadata_pairs", "label_map": [
            {"source": "CommCell ID", "canonical": "commcell_id"},
            {"source": "Registration Code", "canonical": "registration_code",
             "transforms": ["mask_registration_code"]},
        ], "null_values": ["N/A", "-", ""], "output_as": "metric"},
    )
    # 2-cell row with a whitespace label (trim), a "label: value" single cell,
    # and an unmapped row that must be ignored.
    csv_path = tmp_path / "d.csv"
    csv_path.write_text(
        '"License summary"\n'
        '"  CommCell ID  ","337f"\n'
        '"Registration Code: XXXX-XXXX-XXXX-1234"\n'
        '"Junk","ignore"\n',
        encoding="utf-8",
    )
    result = CSVExtractor(conn).extract(csv_path, "md_csv")
    conn.close()
    assert result.sections["md_csv.meta"] == [
        {"commcell_id": "337f", "registration_code": "****-****-****-1234"},
    ]


def test_csv_metadata_pairs_registration_without_mask_raises(
    migrated_db_path: Path, tmp_path: Path
):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "md_bad", "md_bad.meta", "csv",
        {"format": "metadata_pairs", "label_map": [
            {"source": "Registration Code", "canonical": "registration_code"},
        ], "null_values": ["N/A", "-", ""], "output_as": "metric"},
    )
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"Registration Code","XXXX-XXXX-XXXX-1234"\n', encoding="utf-8")
    with pytest.raises(SensitiveFieldError):
        CSVExtractor(conn).extract(csv_path, "md_bad")
    conn.close()


# ── end-to-end through the real HTML extractor ───────────────────────────────

def test_html_metadata_pairs_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "md_html", "md_html.meta", "html",
        {"format": "metadata_pairs", "label_map": [
            {"source": "CommCell ID", "canonical": "commcell_id"},
            {"source": "Registration Code", "canonical": "registration_code",
             "transforms": ["mask_registration_code"]},
        ], "null_values": [], "output_as": "metric"},
    )
    html = (
        "<html><body>"
        "<p>CommCell ID: 337f</p>"
        "<p>Registration Code: XXXX-XXXX-XXXX-1234</p>"
        "<p>Other: ignore</p>"
        "</body></html>"
    )
    html_path = tmp_path / "d.html"
    html_path.write_text(html, encoding="utf-8")
    result = HTMLExtractor(conn).extract(html_path, "md_html")
    conn.close()
    assert result.sections["md_html.meta"] == [
        {"commcell_id": "337f", "registration_code": "****-****-****-1234"},
    ]


def test_html_metadata_pairs_case_difference_does_not_match(
    migrated_db_path: Path, tmp_path: Path
):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "md_case", "md_case.meta", "html",
        {"format": "metadata_pairs", "label_map": [
            {"source": "CommCell ID", "canonical": "commcell_id"},
        ], "null_values": [], "output_as": "metric"},
    )
    # document label is lower-case — must NOT match the exact "CommCell ID"
    html = "<html><body><p>commcell id: 337f</p></body></html>"
    html_path = tmp_path / "d.html"
    html_path.write_text(html, encoding="utf-8")
    result = HTMLExtractor(conn).extract(html_path, "md_case")
    conn.close()
    assert result.sections["md_case.meta"] == []  # no exact label → nothing matched
