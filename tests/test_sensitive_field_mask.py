"""ADR-0016 transform layer slice 3 — Security-by-Construction.

`mask_registration_code` (fail-closed, idempotent) + the sensitive-field
mandatory-transform rule: a canonical field tagged sensitive
(`SENSITIVE_FIELD_REQUIREMENTS`) MUST carry its specific required transform, or
recipe resolution raises. Slice 3 only — NOT number_with_unit, metadata_pairs,
computed sections, compile gate, or LS recipe.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.extractors.column_map import (
    SENSITIVE_FIELD_REQUIREMENTS,
    TRANSFORMS,
    SensitiveFieldError,
    apply_transforms,
    resolve_columns,
)
from cvhealthcheck.extractors.csv import CSVExtractor

from test_column_coalesce import _seed_subject  # sibling helper (tests/ on sys.path)


def _resolve(column_map, header_map=None):
    return resolve_columns(
        column_map, header_map or {"a": 0}, section_id="s", warnings=[]
    )


def _raw_survives(out, raw: str) -> bool:
    """True if any recognizable form of the raw code leaks into the output."""
    if out is None:
        return False
    text = str(out)
    return raw in text or raw.replace("-", "") in text.replace("-", "")


# ── mask_registration_code is in the closed registry ─────────────────────────

def test_mask_in_registry():
    assert "mask_registration_code" in TRANSFORMS


# ── canonical masking ────────────────────────────────────────────────────────

def test_mask_canonical_form():
    assert (
        apply_transforms(["mask_registration_code"], "XXXX-XXXX-XXXX-1234")
        == "****-****-****-1234"
    )


def test_mask_two_segments_reveals_only_trailing():
    assert apply_transforms(["mask_registration_code"], "ABCD-1234") == "****-1234"


def test_mask_preserves_segment_lengths():
    assert apply_transforms(["mask_registration_code"], "AB-CDEF-1234") == "**-****-1234"


# ── FAIL CLOSED: unexpected input → raw never survives ───────────────────────

@pytest.mark.parametrize(
    "raw",
    [
        "ABCD1234EFGH5678",      # no dashes — cannot identify segments
        "12345678",             # bare digits, no structure
        "plain text value",     # spaces, no dashes
        "AB#CD-1234",           # illegal char in a segment
        "XXXX-XXXX-XXXX-",       # trailing empty segment
        "-1234",                # leading empty segment
        "REGCODE",              # single token, no dash
    ],
)
def test_mask_fail_closed_unexpected_format(raw):
    out = apply_transforms(["mask_registration_code"], raw)
    assert not _raw_survives(out, raw), f"raw must not survive masking, got {out!r}"


# ── idempotent ───────────────────────────────────────────────────────────────

def test_mask_idempotent():
    once = apply_transforms(["mask_registration_code"], "XXXX-XXXX-XXXX-1234")
    twice = apply_transforms(["mask_registration_code"], once)
    assert once == "****-****-****-1234"
    assert twice == once  # not double-masked / corrupted


def test_mask_already_masked_input_stays_safe():
    out = apply_transforms(["mask_registration_code"], "****-****-****-1234")
    assert out == "****-****-****-1234"


# ── null / empty → safe (no leak, no crash) ──────────────────────────────────

def test_mask_null_empty_whitespace_safe():
    assert apply_transforms(["mask_registration_code"], None) is None
    assert apply_transforms(["mask_registration_code"], "") is None
    assert apply_transforms(["mask_registration_code"], "   ") is None


# ── composes after trim ──────────────────────────────────────────────────────

def test_mask_after_trim_composes():
    assert (
        apply_transforms(["trim", "mask_registration_code"], "  XXXX-XXXX-XXXX-1234  ")
        == "****-****-****-1234"
    )


# ── sensitive-field mandatory-transform enforcement ──────────────────────────

def test_requirements_table_contents():
    assert SENSITIVE_FIELD_REQUIREMENTS == {"registration_code": ["mask_registration_code"]}


def test_registration_code_without_any_transform_raises():
    with pytest.raises(SensitiveFieldError):
        _resolve([{"source": "A", "canonical": "registration_code"}])


def test_registration_code_with_only_trim_raises():
    # a transform IS present, but not the SPECIFIC required one
    with pytest.raises(SensitiveFieldError):
        _resolve([{"source": "A", "canonical": "registration_code", "transforms": ["trim"]}])


def test_sensitive_error_message_names_field_and_requirement():
    with pytest.raises(SensitiveFieldError) as exc:
        _resolve([{"source": "A", "canonical": "registration_code", "transforms": ["trim"]}])
    msg = str(exc.value)
    assert "registration_code" in msg and "mask_registration_code" in msg


def test_registration_code_with_mask_accepted():
    rc = _resolve([
        {"source": "A", "canonical": "registration_code",
         "transforms": ["mask_registration_code"]},
    ])
    assert rc[0].canonical == "registration_code"


def test_registration_code_with_trim_then_mask_accepted():
    rc = _resolve([
        {"source": "A", "canonical": "registration_code",
         "transforms": ["trim", "mask_registration_code"]},
    ])
    assert rc[0].transforms == ["trim", "mask_registration_code"]


def test_no_registration_code_field_accepted():
    rc = _resolve([{"source": "A", "canonical": "other", "type": "string"}])
    assert rc[0].canonical == "other"


def test_non_sensitive_field_without_mask_accepted():
    rc = _resolve([
        {"source": "A", "canonical": "available_total", "transforms": ["to_integer"]},
    ])
    assert rc[0].canonical == "available_total"


# ── end-to-end through the real CSV extractor ────────────────────────────────

def test_csv_registration_code_masked_end_to_end(migrated_db_path: Path, tmp_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "rc_ok", "rc_ok.tbl", "csv",
        {"format": "single_table", "column_map": [
            {"source": "Reg", "canonical": "registration_code",
             "transforms": ["trim", "mask_registration_code"]},
        ], "null_values": ["N/A", "-", ""], "output_as": "table"},
    )
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"Reg"\n"XXXX-XXXX-XXXX-1234"\n', encoding="utf-8")

    result = CSVExtractor(conn).extract(csv_path, "rc_ok")
    conn.close()
    rows = result.sections["rc_ok.tbl"]
    assert rows == [{"registration_code": "****-****-****-1234"}]


def test_csv_registration_code_without_mask_raises_end_to_end(
    migrated_db_path: Path, tmp_path: Path
):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _seed_subject(
        conn, "rc_bad", "rc_bad.tbl", "csv",
        {"format": "single_table", "column_map": [
            {"source": "Reg", "canonical": "registration_code", "type": "string"},
        ], "null_values": ["N/A", "-", ""], "output_as": "table"},
    )
    csv_path = tmp_path / "d.csv"
    csv_path.write_text('"Reg"\n"XXXX-XXXX-XXXX-1234"\n', encoding="utf-8")

    with pytest.raises(SensitiveFieldError):
        CSVExtractor(conn).extract(csv_path, "rc_bad")
    conn.close()
