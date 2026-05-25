"""Snapshot test for build_subject_initial_data() — session 3 of the
unified-upload refactor.

This test is the contract for "behavior didn't change" across the
session 3 source-builder unification and write_legacy retirement.

How it works:
    - First run: serialises build_subject_initial_data() against the
      migrated test DB (6 system subjects, empty canonical store, no
      legacy state files) to deterministic JSON, writes the result to
      tests/fixtures/subject_initial_data_snapshot.json, and FAILS so
      the developer notices the snapshot was just created (and commits
      it).
    - Subsequent runs: compares the live output against the stored
      snapshot. Any diff prints a readable inline diff and fails.

If session 3's refactor changes the URL shape (the intended diff —
/quick-hc/import?subject_id=… → /quick-hc/<id>/import), the snapshot
fixture is regenerated alongside a CHANGELOG note. Any other diff is
a regression — fix the refactor, don't regenerate.

After session 3, this snapshot becomes a permanent regression pin.
"""
from __future__ import annotations

import json
import sqlite3
from difflib import unified_diff
from pathlib import Path

import pytest

from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.web.app import create_app


SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "subject_initial_data_snapshot.json"


def _serialise(payload) -> str:
    """Stable, sorted-keys JSON. Deterministic ordering for diffing."""
    return json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n"


def test_build_subject_initial_data_snapshot(
    migrated_db_path: Path,
) -> None:
    """Snapshot pin for build_subject_initial_data().

    Uses the migrated test DB (6 system subjects, no AI subjects).
    The autouse _isolate_canonical_stores fixture in conftest.py
    redirects the canonical store to a tmp dir, so the canonical-read
    branch returns None for every subject. The legacy loaders look at
    file-based state (e.g. commserv.json) that doesn't exist in tests,
    so they return None too. Net effect: deterministic output from
    a clean-slate environment.
    """
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    app = create_app()
    try:
        with app.test_request_context("/quick-hc"):
            payload = build_subject_initial_data(db)
    finally:
        db.close()

    serialised = _serialise(payload)

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(serialised, encoding="utf-8")
        pytest.fail(
            f"Snapshot did not exist; wrote {SNAPSHOT_PATH.relative_to(Path(__file__).parent.parent)}. "
            f"Commit the fixture and re-run."
        )

    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if serialised == expected:
        return

    diff = "".join(
        unified_diff(
            expected.splitlines(keepends=True),
            serialised.splitlines(keepends=True),
            fromfile=str(SNAPSHOT_PATH.name),
            tofile="live build_subject_initial_data() output",
            n=3,
        )
    )
    pytest.fail(
        "build_subject_initial_data() output diverges from snapshot.\n\n"
        "If the diff is intentional (e.g. a URL shape change during the "
        "unified-upload refactor), regenerate the fixture by deleting it "
        "and re-running the test, AND add a CHANGELOG note.\n\n"
        "If the diff is unexpected, treat as a regression.\n\n"
        + diff
    )
