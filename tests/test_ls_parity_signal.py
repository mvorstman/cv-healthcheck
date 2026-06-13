"""ADR-0017 LS recipe — first parity SIGNAL (not green).

Confirms the generic recipe publishes through the compile gate, the generic
candidate produces an artifact for every fixture, and the generic-vs-bespoke
comparison runs over the corpus. The pass/fail breakdown is the report
deliverable (read together before any fix); these tests pin the machinery, not
green parity.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ls_generic_recipe import (
    GENERIC_SUBJECT_ID,
    publish_ls_recipe,
    run_signal,
)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_ls_recipe_publishes_through_compile_gate(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        created = publish_ls_recipe(conn)  # raises ProposalCompileError if rejected
        assert created["subject_id"] == GENERIC_SUBJECT_ID
    finally:
        conn.close()


def test_generic_candidate_runs_over_corpus_and_signal_is_produced(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        signal = run_signal(conn)
    finally:
        conn.close()
    # The generic candidate produced a CanonicalArtifact for every fixture (no crashes).
    assert signal["candidate_errors"] == []
    # ADR-0017: unit fields are actively compared (no quarantine left).
    assert signal["totals"]["pending"] == 0
    # The comparison ran and produced real pass results (sections that match).
    assert signal["totals"]["pass"] > 0
    # First-signal slice — genuine differences exist and are reported, not hidden.
    assert signal["totals"]["fail"] > 0
    assert len(signal["failure_classes"]) > 0
