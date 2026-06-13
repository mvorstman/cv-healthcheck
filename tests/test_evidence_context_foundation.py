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


def test_stamped_row_matching_context_approves(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        _seed_customer_project(db, "cm", "pm")
        create_staged_artifact(
            db, "st_match", "users", _mk_artifact("users").model_dump_json(),
            source_type="html", customer_id="cm", project_id="pm",
        )
        result = execute_approval(db, "st_match", customer_id="cm", project_id="pm")
        assert result["status"] == "approved"
        assert _store_exists("cm", "pm", "users")
    finally:
        db.close()


def test_stamped_row_mismatched_project_refuses(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        _seed_customer_project(db, "cm", "pm")
        _seed_customer_project(db, "cm", "pOTHER")
        create_staged_artifact(
            db, "st_projmiss", "users", _mk_artifact("users").model_dump_json(),
            source_type="html", customer_id="cm", project_id="pm",
        )
        with pytest.raises(ContextMismatchError):
            execute_approval(db, "st_projmiss", customer_id="cm", project_id="pOTHER")
        assert db.execute(
            "SELECT status FROM staged_artifacts WHERE stage_id='st_projmiss'"
        ).fetchone()["status"] == "pending"          # row untouched
        assert not _store_exists("cm", "pOTHER", "users")
    finally:
        db.close()


def test_stamped_row_mismatched_customer_refuses(migrated_db_path):
    db = _conn(migrated_db_path)
    try:
        _seed_customer_project(db, "cm", "pm")
        _seed_customer_project(db, "cOTHER", "pm2")
        create_staged_artifact(
            db, "st_custmiss", "users", _mk_artifact("users").model_dump_json(),
            source_type="html", customer_id="cm", project_id="pm",
        )
        with pytest.raises(ContextMismatchError):
            execute_approval(db, "st_custmiss", customer_id="cOTHER", project_id="pm2")
    finally:
        db.close()


def test_legacy_null_project_row_keeps_d5_behaviour(migrated_db_path):
    """A pre-0033 row (project_id NULL, customer_id NULL) -> D5 unchanged:
    approval context is authority, customer_id back-stamped, lands scoped."""
    db = _conn(migrated_db_path)
    try:
        customer_id, project_id = "cm", "pm"
        _seed_customer_project(db, customer_id, project_id)
        create_staged_artifact(
            db, "st_legacy", "users", _mk_artifact("users").model_dump_json(),
            source_type="html",   # no customer_id, no project_id
        )
        result = execute_approval(
            db, "st_legacy", reviewed_by="t",
            customer_id=customer_id, project_id=project_id,
        )
        assert result["status"] == "approved"
        row = db.execute(
            "SELECT customer_id, project_id, ai_notes FROM staged_artifacts"
            " WHERE stage_id='st_legacy'"
        ).fetchone()
        assert row["customer_id"] == customer_id        # back-stamped (D5)
        assert row["project_id"] is None                # D5 unchanged: not back-stamped
        assert "back-stamped" in (row["ai_notes"] or "")
        assert _store_exists(customer_id, project_id, "users")
    finally:
        db.close()


def test_d5_refusal_without_context_preserved(migrated_db_path):
    """D5's refusal-without-context still stands for artifact approvals."""
    from cvhealthcheck.context import NoExplicitContextError
    db = _conn(migrated_db_path)
    try:
        _seed_customer_project(db, "cm", "pm")
        create_staged_artifact(
            db, "st_noctx", "users", _mk_artifact("users").model_dump_json(),
            source_type="html", customer_id="cm", project_id="pm",
        )
        with pytest.raises(NoExplicitContextError):
            execute_approval(db, "st_noctx", reviewed_by="t")
    finally:
        db.close()


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
