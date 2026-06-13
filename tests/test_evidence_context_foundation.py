"""Evidence-context + verification-result foundation (pre-Fix-4).

PART 1: project_id completes the creation-context stamp on staged artifacts;
approval reads a stamped row's own (customer, project) as authority (coherence
check on the approver's context), with legacy NULL rows keeping D5 behaviour.

PART 2: ArtifactSource gains the verification-result home (status/sources/
notes/verified_at) — nothing populates it yet (Fix 4 does); this only creates
the home and proves it round-trips.

This slice is an inert enabler: NO declared-vs-wire check, NO approval
authority flip, NO D5 weakening.
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _mk_artifact(subject_id: str = "storage_policies"):
    res = ExtractionResult(subject_id=subject_id, source_type="csv")
    res.sections["rows"] = [{"col": "v"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    return result_to_artifact(res, subject_id=subject_id, subject_title=subject_id)


# ── PART 1 (commit 1): project_id stamped on new artifact rows ────────────────

def _seed_ai_subject(db: sqlite3.Connection, subject_id: str) -> None:
    from cvhealthcheck.db.subjects import create_subject_from_proposal
    create_subject_from_proposal(db, {
        "subject_id": subject_id, "version": 1, "title": subject_id,
        "description": "", "category": "operations",
        "sections": [{"section_id": "s", "title": "S", "section_type": "table",
                      "default_selected": True, "sort_order": 0}],
        "extraction_instructions": {"html": {"extractable": True, "sections": {"s": {}}}},
    })


def test_subject_proposal_stays_catalog_global_null(monkeypatch, migrated_db_path):
    """A subject_proposal carries no customer/project — catalog-global by design."""
    import cvhealthcheck.mcp.server as mcp
    monkeypatch.setattr(mcp, "get_db", lambda: _conn(migrated_db_path))
    result = mcp.propose_new_subject(
        subject_id="_ev_prop", version=1, title="P", description="",
        category="operations",
        sections=[{"section_id": "s", "title": "S", "section_type": "table",
                   "default_selected": True, "sort_order": 0}],
        extraction_instructions={"html": {"extractable": True, "sections": {"s": {}}}},
        ai_notes="",
    )
    db = _conn(migrated_db_path)
    row = db.execute(
        "SELECT artifact_type, customer_id, project_id FROM staged_artifacts"
        " WHERE stage_id = ?", (result["stage_id"],),
    ).fetchone()
    db.close()
    assert row["artifact_type"] == "subject_proposal"
    assert row["customer_id"] is None
    assert row["project_id"] is None


# ── PART 1 (commit 2): approval reads the row's creation context ──────────────

from cvhealthcheck.context import ContextMismatchError
from cvhealthcheck.db.staging import create_staged_artifact, execute_approval


def _seed_customer_project(db, customer_id, project_id):
    db.execute(
        "INSERT OR IGNORE INTO customers (customer_id, customer_name, created_at, updated_at)"
        " VALUES (?, ?, '2026-01-01', '2026-01-01')", (customer_id, customer_id),
    )
    db.execute(
        "INSERT OR IGNORE INTO projects (project_id, customer_id, project_number)"
        " VALUES (?, ?, ?)", (project_id, customer_id, f"P-{project_id}"),
    )
    db.commit()


def _store_exists(customer_id, project_id, subject_id) -> bool:
    try:
        ArtifactStore(customer_id, project_id).load_latest_artifact(subject_id)
        return True
    except FileNotFoundError:
        return False


# ── PART 2 (commit 3): verification-result home on ArtifactSource ─────────────

from datetime import datetime, timezone

from cvhealthcheck.artifacts.models import ArtifactSource, CanonicalArtifact


def test_artifact_source_defaults_verification_fields_to_none():
    src = ArtifactSource(type="rest")
    assert src.verification_status is None
    assert src.verification_sources is None
    assert src.verification_notes is None
    assert src.verified_at is None


def test_artifact_round_trips_verification_fields(migrated_db_path, tmp_path):
    """A fully-populated verification home survives ArtifactStore save/load."""
    artifact = _mk_artifact("users")
    src = artifact.source
    populated = src.model_copy(update={
        "verification_status": "verified",
        "verification_sources": ["rest", "csv"],
        "verification_notes": "declared CCID matched wire",
        "verified_at": datetime(2026, 6, 13, 9, 0, tzinfo=timezone.utc),
    })
    artifact = artifact.model_copy(update={"source": populated})

    store = ArtifactStore("ev_rt_cust", "ev_rt_proj", base_dir=tmp_path / "store")
    store.save_artifact(artifact)
    loaded = store.load_latest_artifact("users")

    assert loaded.source.verification_status == "verified"
    assert loaded.source.verification_sources == ["rest", "csv"]
    assert loaded.source.verification_notes == "declared CCID matched wire"
    assert loaded.source.verified_at == datetime(2026, 6, 13, 9, 0, tzinfo=timezone.utc)


def test_preexisting_artifact_without_verification_fields_loads(tmp_path):
    """An artifact JSON predating these fields loads cleanly (additive/optional)."""
    artifact = _mk_artifact("users")
    payload = artifact.model_dump(mode="json")
    # Simulate an on-disk artifact written before the fields existed.
    payload["source"].pop("verification_status", None)
    payload["source"].pop("verification_sources", None)
    payload["source"].pop("verification_notes", None)
    payload["source"].pop("verified_at", None)

    reloaded = CanonicalArtifact.model_validate(payload)
    assert reloaded.source.verification_status is None
    assert reloaded.source.verification_sources is None
    assert reloaded.source.verified_at is None
