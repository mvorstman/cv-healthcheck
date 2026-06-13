"""ADR-0015 compile gate (transform-aware, ADR-0016 D2) — publish-time validation.

The gate runs at the publish chokepoint (create_subject_from_proposal) BEFORE any
write, rejecting a proposal whose recipe fails any of the four checks. The interim
apply-time raises stay as defense-in-depth.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.compile_gate import (
    ProposalCompileError,
    compile_validate_proposal,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal, get_subject
from cvhealthcheck.extractors.column_map import UnknownTransformError, resolve_columns


def _proposal(subject_id, source_type, section_id, recipe):
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": subject_id,
        "description": "",
        "category": "operations",
        "sections": [
            {"section_id": section_id, "title": section_id, "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {
            source_type: {"extractable": True, "sections": {section_id: recipe}},
        },
    }


# ── unit: compile_validate_proposal collects violations ──────────────────────

def test_clean_proposal_passes():
    p = _proposal("ok", "csv", "s", {
        "format": "single_table",
        "column_map": [{"source": "A", "canonical": "a", "transforms": ["trim"]}],
    })
    compile_validate_proposal(p)  # no raise


def test_unknown_transform_rejected():
    p = _proposal("bad", "csv", "s", {
        "column_map": [{"source": "A", "canonical": "a", "transforms": ["bogus"]}],
    })
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    assert "bogus" in str(exc.value)


def test_sensitive_field_missing_mask_rejected():
    p = _proposal("bad", "csv", "s", {
        "column_map": [{"source": "Reg", "canonical": "registration_code"}],
    })
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    assert "registration_code" in str(exc.value) and "mask_registration_code" in str(exc.value)


def test_unknown_computed_type_rejected():
    p = _proposal("bad", "csv", "s", {
        "format": "computed", "computed_type": "average", "source_section": "x",
    })
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    assert "average" in str(exc.value)


def test_format_invalid_for_source_type_rejected():
    # single_table is a CSV format; in an HTML section it must be rejected
    p = _proposal("bad", "html", "s", {"format": "single_table",
                                        "column_map": [{"source": "A", "canonical": "a"}]})
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    assert "single_table" in str(exc.value) and "html" in str(exc.value)


def test_bogus_format_in_csv_rejected():
    p = _proposal("bad", "csv", "s", {"format": "nonsense"})
    with pytest.raises(ProposalCompileError):
        compile_validate_proposal(p)


def test_metadata_pairs_label_map_transforms_and_sensitive_checked():
    # label_map entries feed the same checks as column_map
    p = _proposal("bad", "csv", "s", {
        "format": "metadata_pairs",
        "label_map": [{"source": "Registration Code", "canonical": "registration_code"}],
    })
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    assert "registration_code" in str(exc.value)


def test_multiple_violations_reported_in_one_rejection():
    p = _proposal("bad", "csv", "s", {
        "format": "computed", "computed_type": "average",   # bad computed_type
        "column_map": [
            {"source": "A", "canonical": "a", "transforms": ["bogus"]},   # bad transform
            {"source": "Reg", "canonical": "registration_code"},          # missing mask
        ],
    })
    with pytest.raises(ProposalCompileError) as exc:
        compile_validate_proposal(p)
    msg = str(exc.value)
    assert "average" in msg and "bogus" in msg and "registration_code" in msg
    assert "3 violation" in msg  # all three, not fail-on-first


def test_clean_html_default_format_passes():
    # html with no format (table-via-selector default) is valid
    p = _proposal("ok", "html", "s", {
        "section_title_selector": ".t", "section_title_match": "X",
        "column_map": [{"source": "A", "canonical": "a"}],
    })
    compile_validate_proposal(p)


def test_non_csv_html_source_format_not_checked():
    # rest has no format dispatch — a 'format' key on it is not gate-checked
    p = _proposal("ok", "rest", "s", {"format": "whatever", "column_map": []})
    compile_validate_proposal(p)


# ── end-to-end: rejection happens AT PUBLISH, before any write ───────────────

def test_publish_rejected_before_write(migrated_db_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    p = _proposal("pub_bad", "csv", "pub_bad.s", {
        "column_map": [{"source": "A", "canonical": "a", "transforms": ["bogus"]}],
    })
    with pytest.raises(ProposalCompileError):
        create_subject_from_proposal(conn, p)
    # nothing became catalog-live — rejected before the transaction started
    assert get_subject(conn, "pub_bad") is None
    conn.close()


def test_publish_succeeds_for_clean_proposal(migrated_db_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    p = _proposal("pub_ok", "csv", "pub_ok.s", {
        "format": "single_table",
        "column_map": [{"source": "A", "canonical": "a", "transforms": ["trim", "to_integer"]}],
    })
    created = create_subject_from_proposal(conn, p)
    assert created["subject_id"] == "pub_ok"
    assert get_subject(conn, "pub_ok") is not None
    conn.close()


def test_publish_sensitive_without_mask_rejected_before_write(migrated_db_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    p = _proposal("pub_sec", "csv", "pub_sec.s", {
        "format": "metadata_pairs",
        "label_map": [{"source": "Registration Code", "canonical": "registration_code"}],
    })
    with pytest.raises(ProposalCompileError):
        create_subject_from_proposal(conn, p)
    assert get_subject(conn, "pub_sec") is None
    conn.close()


# ── defense-in-depth: the apply-time backstop still raises ───────────────────

def test_apply_time_backstop_still_raises():
    # a recipe that bypassed the gate and reached extraction still fails
    with pytest.raises(UnknownTransformError):
        resolve_columns(
            [{"source": "A", "canonical": "a", "transforms": ["bogus"]}],
            {"a": 0}, section_id="s", warnings=[],
        )
