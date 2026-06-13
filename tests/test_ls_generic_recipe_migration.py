"""ADR-0017 LS promotion — commit 1 acceptance: the generated migration.

Proves the nine gates for commit 1: the generated SQL migration is committed and
byte-identical to the recipe render (deterministic generator), the drift guard
genuinely fails on a recipe mutation, the migration installs the generic recipe
under subject_id ``license_summary`` with ``created_by='system'`` preserved and no
stale ``license_summary.*`` ids, the compile gate accepts the recipe, and commit 1
does NOT touch recognition / the D2 enrichment seam / the upload route (commits
2–4).
"""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from cvhealthcheck.db.compile_gate import compile_validate_proposal
from cvhealthcheck.license_summary.generic_recipe import (
    LS_RECIPE_PROPOSAL,
    render_migration_sql,
)
from ls_parity_harness import LS_FIXTURE_DIR

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = _REPO_ROOT / "src" / "cvhealthcheck" / "db" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / "0034_license_summary_generic_recipe.sql"


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── gate 1: the generated migration exists and is committed ───────────────────

def test_migration_file_exists():
    assert _MIGRATION_PATH.is_file(), "generated migration 0034 must exist"
    assert _MIGRATION_PATH.suffix == ".sql"


# ── gate 2: the migration system still runs SQL only (no runner change) ───────

def test_migration_system_runs_sql_only():
    # The only .py in the migrations dir is the runner package itself. A .py
    # migration would mean the migration system changed — forbidden for commit 1.
    py_migrations = [p.name for p in _MIGRATIONS_DIR.glob("*.py") if p.name != "__init__.py"]
    assert py_migrations == [], f"unexpected non-SQL migrations: {py_migrations}"
    # The runner globs *.sql — confirm the contract is intact.
    from cvhealthcheck.db import migrations as mig
    src = (Path(mig.__file__)).read_text(encoding="utf-8")
    assert 'glob("*.sql")' in src


# ── gate 3: recipe source regenerates the committed SQL BYTE-IDENTICALLY ───────

def test_render_is_byte_identical_to_committed_migration():
    committed = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert render_migration_sql(LS_RECIPE_PROPOSAL) == committed


def test_render_is_deterministic():
    assert render_migration_sql(LS_RECIPE_PROPOSAL) == render_migration_sql(LS_RECIPE_PROPOSAL)


# ── gate 4: the drift guard FAILS on a real recipe mutation (not a trivial pass)

def test_drift_guard_detects_a_recipe_mutation():
    committed = _MIGRATION_PATH.read_text(encoding="utf-8")
    mutated = copy.deepcopy(LS_RECIPE_PROPOSAL)
    # change a single transform deep in the recipe
    mutated["extraction_instructions"]["csv"]["sections"]["other_licenses"][
        "column_map"][1]["transforms"] = ["to_integer"]
    assert render_migration_sql(mutated) != committed, (
        "drift guard is vacuous — a recipe change did not change the rendered SQL"
    )
    # and the UNmutated render still matches → the guard is real, not always-fail
    assert render_migration_sql(LS_RECIPE_PROPOSAL) == committed


def test_drift_guard_detects_a_section_addition():
    committed = _MIGRATION_PATH.read_text(encoding="utf-8")
    mutated = copy.deepcopy(LS_RECIPE_PROPOSAL)
    mutated["sections"].append(
        {"section_id": "bogus", "title": "bogus", "section_type": "table",
         "default_selected": True, "sort_order": 99})
    assert render_migration_sql(mutated) != committed


# ── gates 5/6/7: the migrated catalog state ───────────────────────────────────

def test_migration_installs_generic_recipe_under_license_summary(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        # gate 5 — subject_id is license_summary (NOT license_summary_generic)
        assert conn.execute(
            "SELECT 1 FROM subjects WHERE subject_id='license_summary' AND version=1"
        ).fetchone() is not None
        assert conn.execute(
            "SELECT 1 FROM subjects WHERE subject_id='license_summary_generic'"
        ).fetchone() is None

        sec_ids = [r["section_id"] for r in conn.execute(
            "SELECT section_id FROM subject_sections WHERE subject_id='license_summary'"
        )]
        # the generic recipe's bare ids are present
        assert {"other_licenses", "agent_feature_licenses", "other_license_count",
                "capacity_licenses", "_commcell_observed"} <= set(sec_ids)

        # gate 7 — no stale 0003-era license_summary.* section ids remain, in either
        # subject_sections or subject_section_sources
        assert all(not s.startswith("license_summary.") for s in sec_ids)
        stale_ss = conn.execute(
            """
            SELECT sss.section_id FROM subject_section_sources sss
            JOIN subject_sources ss ON ss.id = sss.source_id
            WHERE ss.subject_id='license_summary' AND sss.section_id LIKE 'license_summary.%'
            """
        ).fetchall()
        assert stale_ss == [], f"stale prefixed section_sources remain: {stale_ss}"
    finally:
        conn.close()


def test_created_by_system_preserved(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        row = conn.execute(
            "SELECT created_by FROM subjects WHERE subject_id='license_summary' AND version=1"
        ).fetchone()
        assert row["created_by"] == "system"  # gate 6
    finally:
        conn.close()


def test_migrated_recipe_extracts_workload_only_file(migrated_db_path: Path):
    """Functional proof the migrated catalog recipe works end-to-end via the LIVE
    extractor: the workload-only 2 MB export (the file the bespoke HTML upload
    rejects with 'no license rows') yields the recipe's workload sections."""
    from cvhealthcheck.extractors.html import HTMLExtractor

    workload_files = sorted(LS_FIXTURE_DIR.glob("License20summary_2026-05-28-11-12-42-*.html"))
    assert workload_files, "workload-only fixture missing from the corpus"
    conn = _conn(migrated_db_path)
    try:
        result = HTMLExtractor(conn).extract(workload_files[0], "license_summary")
        assert result.sections.get("capacity_licenses"), "recipe did not extract via the catalog"
        # the observational staging section is extracted by the recipe (D2 enrichment
        # consumes it later — commit 2 — so it is still PRESENT here)
        assert "_commcell_observed" in result.sections
    finally:
        conn.close()


# ── gate 8: the compile gate ACCEPTS the generated recipe ─────────────────────

def test_compile_gate_accepts_the_recipe():
    # Raises ProposalCompileError if the gate rejects it.
    compile_validate_proposal(LS_RECIPE_PROPOSAL)


# ── gate 9: commit 1 does NOT do D2-live / recognition / route (commits 2–4) ──

def test_recognition_broadened_by_commit3(migrated_db_path: Path):
    # Commit 1 did NOT touch recognition; commit 3 (migration 0035) broadens it.
    # The migrated db includes 0035, so the live html recognition is now the
    # broadened form: accepts .reportstabletitle OR <h2>, with the over-strict
    # table_count + first_table_headers fingerprints removed.
    conn = _conn(migrated_db_path)
    try:
        row = conn.execute(
            "SELECT recognition_hints FROM subject_sources"
            " WHERE subject_id='license_summary' AND source_type='html'"
        ).fetchone()
        rec = json.loads(row["recognition_hints"])
        assert rec.get("has_selector") == ".reportstabletitle, h2"
        assert "table_count" not in rec
        assert "first_table_headers" not in rec
        assert rec.get("title_contains") == "License summary"  # retained — keeps titleless out
    finally:
        conn.close()


def test_upload_route_switched_to_generic_after_commit4():
    # Commit 4b: the bespoke license_summary handler is UNREGISTERED — LS upload
    # falls through to the generic dispatcher. The handler object is retained for
    # a one-line revert (safety net; commit 4 deletes nothing).
    from cvhealthcheck.web.routes import upload_dispatch as ud
    assert "license_summary" not in ud.UPLOAD_HANDLERS
    assert ud.get_handler("license_summary") is None
    assert ud._LICENSE_SUMMARY_BESPOKE_HANDLER is not None  # revert path retained


def test_d2_enrichment_is_live_in_result_to_artifact():
    # Commit 2: result_to_artifact now calls the D2 enrichment seam (caller-fed).
    import inspect

    import cvhealthcheck.extractors.result_to_artifact as rta

    assert "enrich_commcell_info" in inspect.getsource(rta)
