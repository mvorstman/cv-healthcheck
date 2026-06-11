"""Guard test: a subject proposal carrying EVERY ADR-0009 declarative field
round-trips through staging persistence (`create_subject_from_proposal`) with
nothing dropped or rewritten.

Exists as cheap insurance against a validator/persist path silently capping
the declarative surface below what the engine supports (the suspected — and
not reproduced — "validator strips ADR-0009 fields" failure mode from the
2026-06-11 reconciliation). The per-section `extraction_instructions` must be
stored byte-identical; the declared `endpoint` must land validated in
`recognition_hints` without displacing other hints.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.extractors.cc_endpoint import COMMAND_CENTER_SOURCE_TYPE


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Every section-level field the engine reads today on the CC-API path:
# output_as card (card spec, nested dot-path fields, agg), output_as table
# (root_key incl. nested form, columns id/field with list-index paths, and
# the transpose/property-table spec).
_CARD_INSTR = {
    "output_as": "card",
    "card": {
        "fields": [
            {"id": "name", "field": "commcell.name"},
            {"id": "version", "field": "commcell.version", "agg": "latest"},
        ],
    },
}

_TABLE_INSTR = {
    "output_as": "table",
    "table": {
        "root_key": "config.groups.list",
        "columns": [
            {"id": "Name", "field": "name"},
            {"id": "Count", "field": "stats.total"},
            {"id": "FirstTag", "field": "tags.0.label"},
        ],
        "transpose": [
            {"key": "retention", "label": "Retention", "field": "policy.retention.0.days"},
        ],
    },
}


def _full_proposal(subject_id: str) -> dict:
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": "Round-trip Guard",
        "description": "ADR 0009 full-field round-trip guard (throwaway).",
        "category": "operations",
        "sections": [
            {"section_id": "identity", "title": "Identity", "section_type": "table",
             "default_selected": True, "sort_order": 0},
            {"section_id": "groups", "title": "Groups", "section_type": "table",
             "default_selected": True, "sort_order": 1},
        ],
        "extraction_instructions": {
            COMMAND_CENTER_SOURCE_TYPE: {
                "extractable": True,
                "non_extractable_reason": None,
                "endpoint": "/commandcenter/api/v4/servergroup",
                # a pre-existing hint must survive the endpoint fold-in
                "recognition_hints": {"note": "kept"},
                "sections": {
                    "identity": _CARD_INSTR,
                    "groups": _TABLE_INSTR,
                },
            },
        },
    }


def test_full_adr0009_proposal_round_trips_without_dropping_fields(
    migrated_db_path: Path,
):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _full_proposal("_roundtrip_guard"))

        src = db.execute(
            "SELECT * FROM subject_sources"
            " WHERE subject_id = '_roundtrip_guard' AND source_type = ?",
            (COMMAND_CENTER_SOURCE_TYPE,),
        ).fetchone()
        assert src is not None
        assert src["extractable"] == 1
        assert src["non_extractable_reason"] is None

        hints = json.loads(src["recognition_hints"])
        # the declared endpoint is validated and persisted, alongside (not
        # instead of) the pre-existing hint
        assert hints["endpoint"] == "/commandcenter/api/v4/servergroup"
        assert hints["note"] == "kept"

        for section_id, want in (("identity", _CARD_INSTR), ("groups", _TABLE_INSTR)):
            row = db.execute(
                "SELECT sss.extraction_instructions"
                " FROM subject_section_sources sss"
                " JOIN subject_sources s ON s.id = sss.source_id"
                " WHERE s.subject_id = '_roundtrip_guard' AND sss.section_id = ?",
                (section_id,),
            ).fetchone()
            assert row is not None, f"section binding missing: {section_id}"
            got = json.loads(row["extraction_instructions"])
            assert got == want, (
                f"{section_id} instructions were altered in persistence:"
                f"\n want={want}\n got={got}"
            )
    finally:
        db.close()
