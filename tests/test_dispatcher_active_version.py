"""Regression: the dispatcher's explicit-subject_id branch must extract with
the subject's ACTIVE version's instructions, not a hardcoded version 1.

The bug: ``extract_file(file, db, subject_id=...)`` (the upload route's call —
it never passes a version) defaulted ``v = version or 1``. Once a superseding
v2 existed, imports silently read the superseded v1's extraction instructions:
HTML failed with "missing selector or title_match" (a key only v2 carried) and
CSV "succeeded" with 0 rows (v1's empty column_map default). First observed on
storage_policy_copy_jobs v1→v2 (2026-06-11).

Seeds v1 (thin instructions, the live-bug shape) and an active superseding v2
(full selector + column_map) through the real proposal-approval write, then
imports a v2-conforming HTML file by subject_id.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.extractors.dispatcher import extract_file

_SUBJECT = "_disp_ver_test"


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _proposal(version: int, html_instr: dict, supersedes: int | None = None) -> dict:
    return {
        "subject_id": _SUBJECT,
        "version": version,
        "title": f"Dispatcher Version Test v{version}",
        "description": "regression fixture",
        "category": "operations",
        "sections": [
            {"section_id": "jobs", "title": "Jobs", "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {
            "html": {"extractable": True, "sections": {"jobs": html_instr}},
        },
        "supersedes": supersedes,
    }


# v1: the live-bug shape — no selector, no column_map (notes only).
_V1_HTML = {"output_as": "table", "notes": "thin v1 instructions"}

# v2: full instructions a conforming export needs.
_V2_HTML = {
    "output_as": "table",
    "section_title_selector": "span.component-title-text",
    "section_title_match": "Job Stats",
    "column_map": [
        {"source": "Job ID", "canonical": "job_id", "type": "integer"},
        {"source": "Client", "canonical": "client", "type": "string"},
    ],
    "null_values": ["N/A"],
}

_HTML_FILE = """<html><body><div>
  <span class="component-title-text">Job Stats</span>
  <table>
    <thead><tr><th>Job ID</th><th>Client</th></tr></thead>
    <tbody>
      <tr><td>101</td><td>alpha</td></tr>
      <tr><td>102</td><td>beta</td></tr>
    </tbody>
  </table>
</div></body></html>"""


def _seed_superseded_v1_active_v2(db: sqlite3.Connection) -> None:
    created_v1 = create_subject_from_proposal(db, _proposal(1, _V1_HTML))
    create_subject_from_proposal(db, _proposal(2, _V2_HTML, supersedes=created_v1["id"]))
    statuses = {
        r["version"]: r["status"]
        for r in db.execute(
            "SELECT version, status FROM subjects WHERE subject_id = ?", (_SUBJECT,)
        )
    }
    assert statuses == {1: "superseded", 2: "active"}  # seeding sanity


def test_import_by_subject_id_uses_active_version_instructions(
    migrated_db_path: Path, tmp_path: Path
):
    db = _conn(migrated_db_path)
    try:
        _seed_superseded_v1_active_v2(db)
        f = tmp_path / "export.html"
        f.write_text(_HTML_FILE)

        # The upload route's exact call shape: subject_id, NO version.
        dispatch = extract_file(f, db, subject_id=_SUBJECT)

        assert dispatch.extraction_errors == []   # v1 would: "missing selector or title_match"
        assert dispatch.version == 2
        assert dispatch.artifact is not None
        section = dispatch.artifact.sections[0]
        # v2's column_map projected + coerced the rows — proof v2 instructions ran
        assert [it["job_id"] for it in section.items] == [101, 102]
        assert [it["client"] for it in section.items] == ["alpha", "beta"]
    finally:
        db.close()


def test_explicit_version_still_pins_the_superseded_one(
    migrated_db_path: Path, tmp_path: Path
):
    """A caller that pins version=1 gets v1's instructions (and v1's failure
    mode here) — the active-version resolution is a default, not an override."""
    db = _conn(migrated_db_path)
    try:
        _seed_superseded_v1_active_v2(db)
        f = tmp_path / "export.html"
        f.write_text(_HTML_FILE)

        dispatch = extract_file(f, db, subject_id=_SUBJECT, version=1)

        assert dispatch.version == 1
        assert any("selector or title_match" in e for e in dispatch.extraction_errors)
    finally:
        db.close()


def test_no_active_version_errors_loudly(migrated_db_path: Path, tmp_path: Path):
    """All versions superseded (or unknown subject) -> a named error, never a
    silent fall-back to version 1."""
    db = _conn(migrated_db_path)
    try:
        _seed_superseded_v1_active_v2(db)
        db.execute(
            "UPDATE subjects SET status = 'superseded' WHERE subject_id = ?",
            (_SUBJECT,),
        )
        db.commit()
        f = tmp_path / "export.html"
        f.write_text(_HTML_FILE)

        dispatch = extract_file(f, db, subject_id=_SUBJECT)

        assert dispatch.recognized is False
        assert dispatch.artifact is None
        assert any("No active version" in e for e in dispatch.extraction_errors)
    finally:
        db.close()
