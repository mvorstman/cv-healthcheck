"""ADR-0011 — version-aware comparison primitive + version_lt/version_gte.

The comparator (coerce.parse_version / compare_versions), authoring-time literal
validation (D4: unparseable literal rejected), and evaluation (D4: below-min row
flags, at/above stays good, unparseable ROW value → not_evaluated, never a false
good). Includes the exact lexical trap ADR-0011 fixes (11.40.9 < 11.40.51).
Fixture-based; never reads data/app.db at runtime beyond the migrated fixture.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.rules import validate_row_match_rule
from cvhealthcheck.evaluative.coerce import compare_versions, parse_version
from cvhealthcheck.evaluative.row_match import evaluate_section_rows


# ── comparator primitive ──────────────────────────────────────────────────────

def test_parse_version_grammar():
    assert parse_version("11.40.51") == (11, 40, 51)
    assert parse_version("11.40.9") == (11, 40, 9)
    assert parse_version("11.40") == (11, 40)
    assert parse_version("v11.40") == (11, 40)          # optional leading token ignored
    assert parse_version("SP11") == (11,)
    assert parse_version("11.40.47") == (11, 40, 47)    # the real cache_contents value
    for bad in ("", "Unknown", "Unlimited", "N/A", "-", None, True):
        assert parse_version(bad) is None               # unparseable → sentinel

def test_compare_versions():
    assert compare_versions("11.40.9", "11.40.51") == -1   # THE lexical trap, now correct
    assert compare_versions("11.40", "11.40.0") == 0        # missing trailing = 0
    assert compare_versions("11.40.51", "11.40.51") == 0    # equal strings
    assert compare_versions("11.41", "11.40.99") == 1       # ascending (a > b)
    assert compare_versions("11.39.5", "11.40") == -1       # descending (a < b)
    assert compare_versions("Unknown", "11.40") is None     # unparseable → sentinel
    assert compare_versions("11.40", "junk") is None


# ── authoring-time validation (D4: literal must parse) ────────────────────────

def _conn(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(p)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON"); return conn

@pytest.fixture()
def db(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        yield conn
    finally:
        conn.close()

_RULE = {"rule_id": "min_sp", "kind": "row_match", "scope": "row", "emit": "per_row",
         "severity": "warning", "title": "t", "message": "m",
         "conditions": [{"target": "service_pack", "operator": "version_lt", "value": "11.40.51"}]}

def test_version_lt_with_valid_literal_accepted(db):
    validate_row_match_rule(db, _RULE)                  # no bind, no raise — operator + literal OK

def test_version_lt_with_unparseable_literal_rejected(db):
    bad = {**_RULE, "conditions": [{"target": "service_pack", "operator": "version_lt",
                                    "value": "eleven-forty"}]}
    with pytest.raises(ValueError, match="parseable version literal"):
        validate_row_match_rule(db, bad)


# ── evaluation (D4: split rows; unparseable ROW → not_evaluated) ──────────────

_ROWS = [
    {"id": 1, "os": "WinX64",      "service_pack": "11.40.9"},   # below min → finding (lexical trap)
    {"id": 2, "os": "linux-x8664", "service_pack": "11.40.51"},  # at min    → good
    {"id": 3, "os": "linux-arm64", "service_pack": "11.41.0"},   # above min → good
    {"id": 4, "os": "other",       "service_pack": "Unknown"},   # unparseable → not_evaluated
]

def test_version_lt_evaluation_splits_rows_and_greys_unparseable():
    findings, per_row = evaluate_section_rows([_RULE], _ROWS)
    verdict = {pr["row_ref"]: pr["verdict"] for pr in per_row}
    assert verdict == {"1": "warning", "2": "good", "3": "good", "4": "not_evaluated"}
    assert [f["row_ref"] for f in findings] == ["1"]            # only the below-min row flags
    # the unparseable row is greyed with a recorded reason — never a false good
    assert next(pr for pr in per_row if pr["row_ref"] == "4")["reason"] == "unparseable version value"

def test_version_gte_is_the_complement():
    rule = {**_RULE, "rule_id": "ok_sp",
            "conditions": [{"target": "service_pack", "operator": "version_gte", "value": "11.40.51"}]}
    findings, per_row = evaluate_section_rows([rule], _ROWS)
    assert {f["row_ref"] for f in findings} == {"2", "3"}       # at/above min match version_gte
    v = {pr["row_ref"]: pr["verdict"] for pr in per_row}
    assert v["1"] == "good" and v["4"] == "not_evaluated"       # below = good; unparseable = grey
