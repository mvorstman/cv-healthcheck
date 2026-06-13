"""ADR-0016 transform layer slice 1 — `source` coalesce.

A recipe column's ``source`` may be a string (1:1, unchanged) or a list
(first-present / first-non-empty among the candidates, in order; no merge —
ADR-0016 D4). The CSV and HTML extractors share one resolver
(`cvhealthcheck.extractors.column_map`), so the unit tests below exercise the
logic for both; two end-to-end tests confirm each extractor is wired.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.extractors.column_map import (
    extract_row,
    header_has_all,
    resolve_columns,
)
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import HTMLExtractor


def _row(column_map, header_cols, cells, *, null_values=None, fuzzy=False):
    header_map = {c.lower(): i for i, c in enumerate(header_cols)}
    warnings: list[str] = []
    resolved = resolve_columns(
        column_map, header_map, section_id="s", warnings=warnings, fuzzy=fuzzy
    )
    out = extract_row(cells, resolved, null_values or ["N/A", "-", ""], "s", warnings)
    return out, warnings


# ── string source → identical to current behavior (regression guard) ─────────

def test_string_source_one_to_one():
    out, _ = _row([{"source": "A", "canonical": "a", "type": "string"}], ["A", "B"], ["x", "y"])
    assert out == {"a": "x"}


def test_string_source_null_value_becomes_none():
    out, _ = _row([{"source": "A", "canonical": "a", "type": "string"}], ["A"], ["N/A"])
    assert out == {"a": None}


def test_string_source_integer_coercion():
    out, _ = _row([{"source": "A", "canonical": "a", "type": "integer"}], ["A"], ["5"])
    assert out == {"a": 5}


def test_string_source_missing_column_is_skipped():
    out, warns = _row([{"source": "Z", "canonical": "z", "type": "string"}], ["A"], ["x"])
    assert out == {}  # column absent → key omitted, as before
    assert any("not found" in w for w in warns)


# ── list, first candidate present → uses it ──────────────────────────────────

def test_list_first_candidate_present_used():
    out, _ = _row(
        [{"source": ["A", "B"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["first", "second"],
    )
    assert out == {"v": "first"}


# ── list, first absent / empty, second present → uses second ─────────────────

def test_list_first_column_absent_uses_second():
    out, _ = _row(
        [{"source": ["MISSING", "B"], "canonical": "v", "type": "string"}],
        ["B"], ["bval"],
    )
    assert out == {"v": "bval"}


def test_list_first_cell_empty_uses_second():
    out, _ = _row(
        [{"source": ["A", "B"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["", "bval"],
    )
    assert out == {"v": "bval"}


def test_list_first_cell_null_value_uses_second():
    out, _ = _row(
        [{"source": ["A", "B"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["N/A", "bval"],
    )
    assert out == {"v": "bval"}


# ── list, none present → null ────────────────────────────────────────────────

def test_list_none_present_is_null():
    out, warns = _row(
        [{"source": ["X", "Y"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["a", "b"],
    )
    assert out == {"v": None}
    assert any("coalesce candidate" in w for w in warns)


def test_list_all_candidates_empty_is_null():
    out, _ = _row(
        [{"source": ["A", "B"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["", "N/A"],
    )
    assert out == {"v": None}


# ── list order is honored (first wins even if later also present) ─────────────

def test_list_order_first_wins_when_both_present():
    out, _ = _row(
        [{"source": ["A", "B"], "canonical": "v", "type": "string"}],
        ["A", "B"], ["aval", "bval"],
    )
    assert out == {"v": "aval"}


# ── header detection treats a coalesce column as satisfied by any candidate ──

def test_header_has_all_string_and_coalesce():
    assert header_has_all([{"source": "A"}], {"a"}) is True
    assert header_has_all([{"source": "A"}], {"c"}) is False
    assert header_has_all([{"source": ["A", "B"]}], {"b"}) is True   # any candidate
    assert header_has_all([{"source": ["A", "B"]}], {"c"}) is False


# ── end-to-end wiring through the real extractors ─────────────────────────────

def _seed_subject(conn, subject_id, section_id, source_type, instructions):
    conn.execute(
        "INSERT INTO subjects (subject_id, version, title, description, category,"
        " category_label, status, created_by)"
        " VALUES (?, 1, ?, '', 'storage', 'Storage', 'active', 'user')",
        (subject_id, subject_id),
    )
    conn.execute(
        "INSERT INTO subject_sections (subject_id, subject_version, section_id, title,"
        " section_type, default_selected, sort_order) VALUES (?, 1, ?, 'Tbl', 'table', 1, 1)",
        (subject_id, section_id),
    )
    cur = conn.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type, extractable)"
        " VALUES (?, 1, ?, 1)",
        (subject_id, source_type),
    )
    conn.execute(
        "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
        " VALUES (?, ?, ?)",
        (cur.lastrowid, section_id, json.dumps(instructions)),
    )
    conn.commit()


_COALESCE_COLUMNS = [
    {"source": "License", "canonical": "license", "type": "string"},
    {
        "source": ["Available Total (TB)", "Available Total (instances)", "Available Total"],
        "canonical": "entitlement",
        "type": "string",
    },
]


def test_csv_extractor_coalesce_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "coalesce_csv", "coalesce_csv.tbl", "csv",
        {"format": "single_table", "column_map": _COALESCE_COLUMNS,
         "null_values": ["N/A", "-", ""], "output_as": "table"},
    )
    # Header carries the THIRD candidate only ("Available Total") — coalesce must
    # fall through the two absent candidates to it.
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"License","Available Total"\n"L1","500"\n', encoding="utf-8")

    result = CSVExtractor(conn).extract(csv_path, "coalesce_csv")
    conn.close()
    assert result.sections["coalesce_csv.tbl"] == [{"license": "L1", "entitlement": "500"}]


def test_html_extractor_coalesce_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "coalesce_html", "coalesce_html.tbl", "html",
        {"section_title_selector": ".sect-title", "section_title_match": "Demo",
         "column_map": _COALESCE_COLUMNS, "null_values": ["N/A", "-", ""],
         "output_as": "table"},
    )
    # Header carries the SECOND candidate ("Available Total (instances)").
    html = (
        '<div><div class="sect-title">Demo</div>'
        "<table><thead><tr><th>License</th><th>Available Total (instances)</th></tr></thead>"
        "<tbody><tr><td>L1</td><td>42</td></tr></tbody></table></div>"
    )
    html_path = tmp_path / "d.html"
    html_path.write_text(html, encoding="utf-8")

    result = HTMLExtractor(conn).extract(html_path, "coalesce_html")
    conn.close()
    assert result.sections["coalesce_html.tbl"] == [{"license": "L1", "entitlement": "42"}]
