"""
Core solidity tests — verify the nine structural invariants from the
feature/basic-healthcheck-report-output consolidation spec.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingsSection,
)
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.migrations import run_migrations
from cvhealthcheck.db.staging import create_staged_artifact, execute_approval
from cvhealthcheck.quickhc.registry import (
    HTML_IMPORT_SOURCE_ID,
    get_tiles,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def migrated_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    run_migrations(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _make_artifact(subject_id: str = "security_assessment") -> CanonicalArtifact:
    now = datetime.now(timezone.utc)
    finding = Finding(
        id="abc123",
        severity=FindingSeverity.warning,
        status=FindingStatus.open,
        category="test_section",
        title="Test finding",
    )
    section = FindingsSection(type="findings", id="test_section", title="Test", items=[finding])
    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=now,
        source=ArtifactSource(type=SourceType.html_import, imported_at=now),
        subject=ArtifactSubject(id=subject_id, title="Test Subject"),
        summary=ArtifactSummary(status=ArtifactStatus.warning),
        sections=[section],
    )


# ---------------------------------------------------------------------------
# 1. System subject has import actions
# ---------------------------------------------------------------------------


def test_system_subject_has_import_actions(migrated_db: sqlite3.Connection) -> None:
    from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data

    initial_data = build_subject_initial_data(migrated_db)
    all_subjects = [s for cat in initial_data.get("cats", []) for s in cat.get("subjects", [])]
    sa_subject = next((s for s in all_subjects if s["id"] == "security_assessment"), None)
    assert sa_subject is not None, "security_assessment subject not found in initial_data"
    sources = sa_subject["sources"]
    html_src = next((s for s in sources if s["id"] == HTML_IMPORT_SOURCE_ID), None)
    assert html_src is not None, f"no {HTML_IMPORT_SOURCE_ID} source on security_assessment"
    assert html_src.get("actions"), "html_import source has no actions"


# ---------------------------------------------------------------------------
# 2. REST source has collect button when section instructions exist
# ---------------------------------------------------------------------------


def test_system_subject_has_collect_button_when_instructions_exist(
    migrated_db: sqlite3.Connection,
) -> None:
    tiles = get_tiles(migrated_db)
    bjs_tile = next((t for t in tiles if t["id"] == "backup_job_summary"), None)
    assert bjs_tile is not None, "backup_job_summary tile not found"
    from cvhealthcheck.quickhc.registry import REST_REPORTS_PLUS_SOURCE_ID
    rest_src = next(
        (s for s in bjs_tile["sources"] if s["id"] == REST_REPORTS_PLUS_SOURCE_ID), None
    )
    assert rest_src is not None, "no REST source on backup_job_summary"
    assert rest_src.get("collect_url"), "REST source should have a collect_url"


def test_subject_specific_redirects_carry_subject_fragment() -> None:
    # The Collect form posts to a server route that flashes and
    # redirects back to /quick-hc. Without the #subject=<id> fragment
    # the JS init falls back to the default (environment) and the user
    # loses their place. The fix is server-side: subject-specific
    # redirects must include the fragment so quick_hc.js can re-open
    # the subject after the full-page reload.
    from cvhealthcheck.web.app import create_app
    app = create_app()
    client = app.test_client()

    # Legacy GETs that the SA/LS collect handlers chain through.
    r = client.get("/quick-hc/security-assessment")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/quick-hc#subject=security_assessment")

    r = client.get("/quick-hc/license-summary")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/quick-hc#subject=license_summary")


def test_dispatched_subjects_rest_source_shows_validated_with_collect_action(
    migrated_db: sqlite3.Connection, tmp_path: Path,
) -> None:
    # SA and LS have a provenance builder registered in
    # source_provenance_dispatch — when _build_generic_subject runs
    # (canonical artifact present), the dispatch fires and the
    # workspace tile shows REST as "Validated" with a Collect action.
    # Post ADR 0003 phase 4, SA's Collect URL is the underscored
    # generic-handler URL (catalog-driven); LS still uses the
    # hyphenated bespoke URL until phase 5.
    from cvhealthcheck.quickhc import subject_data_service as sds

    expected_collect = {
        "security_assessment": "/quick-hc/security_assessment/collect",
        "license_summary": "/quick-hc/license-summary/collect",
    }
    store = ArtifactStore("default", "default", base_dir=tmp_path / "artifacts")
    for subject_id, _ in expected_collect.items():
        store.save_artifact(_make_artifact(subject_id))
    original_store = sds._canonical_store
    sds._canonical_store = lambda: store
    try:
        data = sds.build_subject_initial_data(migrated_db)
    finally:
        sds._canonical_store = original_store

    seen = {}
    for cat in data["cats"]:
        for sub in cat["subjects"]:
            if sub["id"] in expected_collect:
                rest = next(
                    (s for s in sub.get("sources", []) if s.get("id") == "rest_reports_plus"),
                    None,
                )
                seen[sub["id"]] = rest
    for subject_id, want_url in expected_collect.items():
        rest = seen.get(subject_id)
        assert rest is not None, f"no REST source for {subject_id}"
        assert rest.get("status") == "v", f"{subject_id} REST status was {rest.get('status')!r}"
        actions = rest.get("actions") or []
        collect_actions = [a for a in actions if a.get("kind") == "collect"]
        assert len(collect_actions) == 1, f"{subject_id} REST missing collect action"
        assert collect_actions[0].get("collectUrl") == want_url


# ---------------------------------------------------------------------------
# 3. Canonical store wins over legacy pipeline
# ---------------------------------------------------------------------------


def test_canonical_store_wins_over_legacy(tmp_path: Path, migrated_db: sqlite3.Connection) -> None:
    from cvhealthcheck.quickhc import subject_data_service as sds

    store = ArtifactStore("default", "default", base_dir=tmp_path / "artifacts")
    artifact = _make_artifact("security_assessment")
    store.save_artifact(artifact)

    legacy_called = []

    def fake_legacy():
        legacy_called.append(True)
        return None

    original_store = sds._canonical_store
    sds._canonical_store = store
    try:
        initial_data = sds.build_subject_initial_data(migrated_db)
    finally:
        sds._canonical_store = original_store

    all_subjects = [s for cat in initial_data.get("cats", []) for s in cat.get("subjects", [])]
    sa_subject = next((s for s in all_subjects if s["id"] == "security_assessment"), None)
    assert sa_subject is not None
    assert not legacy_called, "legacy loader should not have been called"


# ---------------------------------------------------------------------------
# 4. ArtifactStore base_dir is absolute when no base_dir provided
# ---------------------------------------------------------------------------


def test_artifact_store_anchored_path() -> None:
    store = ArtifactStore("default", "default")
    assert store.base_dir.is_absolute(), "ArtifactStore.base_dir should be absolute"
    assert store.base_dir.parts[-1] == "artifacts"
    assert store.base_dir.parts[-2] == "catalog"
    assert store.base_dir.parts[-3] == "data"


# ---------------------------------------------------------------------------
# 5. staged_artifacts.status CHECK constraint (migration 0004)
# ---------------------------------------------------------------------------


def test_staged_artifacts_status_constraint(migrated_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            "INSERT INTO staged_artifacts"
            " (stage_id, subject_id, artifact_json, status, artifact_type, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("bad-stage-id", "security_assessment", '{"x":1}', "invalid", "artifact", "2024-01-01T00:00:00+00:00"),
        )


# ---------------------------------------------------------------------------
# 6. ArtifactSource commcell_id / commcell_name round-trip
# ---------------------------------------------------------------------------


def test_artifact_source_commcell_fields() -> None:
    now = datetime.now(timezone.utc)
    source = ArtifactSource(
        type=SourceType.rest,
        imported_at=now,
        commcell_id="abc-123",
        commcell_name="MyCommCell",
    )
    dumped = source.model_dump()
    assert dumped["commcell_id"] == "abc-123"
    assert dumped["commcell_name"] == "MyCommCell"

    reloaded = ArtifactSource.model_validate(dumped)
    assert reloaded.commcell_id == "abc-123"
    assert reloaded.commcell_name == "MyCommCell"


# ---------------------------------------------------------------------------
# 7. execute_approval for a regular artifact
# ---------------------------------------------------------------------------


def test_execute_approval_artifact(tmp_path: Path, migrated_db: sqlite3.Connection) -> None:
    from cvhealthcheck.quickhc import subject_data_service as sds

    store = ArtifactStore("default", "default", base_dir=tmp_path / "artifacts")
    artifact = _make_artifact("security_assessment")
    artifact_json = artifact.model_dump_json()

    create_staged_artifact(
        migrated_db,
        "stage-001",
        "security_assessment",
        artifact_json,
        source_type="html",
    )

    original_store = sds._canonical_store
    sds._canonical_store = store

    try:
        result = execute_approval(migrated_db, "stage-001", reviewed_by="tester", store=store)
    finally:
        sds._canonical_store = original_store

    assert result["status"] == "approved"
    assert result["type"] == "artifact"
    assert result["subject_id"] == "security_assessment"


# ---------------------------------------------------------------------------
# 8. execute_approval for a subject_proposal
# ---------------------------------------------------------------------------


def test_execute_approval_subject_proposal(migrated_db: sqlite3.Connection) -> None:
    proposal = {
        "subject_id": "test_ai_subject",
        "title": "Test AI Subject",
        "version": 1,
        "created_by": "ai",
        "category": "operations",
        "sources": [],
        "sections": [],
    }
    proposal_json = json.dumps(proposal)

    migrated_db.execute(
        "INSERT INTO staged_artifacts"
        " (stage_id, subject_id, artifact_json, status, artifact_type, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            "stage-proposal-001",
            "test_ai_subject",
            proposal_json,
            "pending",
            "subject_proposal",
            "2024-01-01T00:00:00+00:00",
        ),
    )
    migrated_db.commit()

    result = execute_approval(migrated_db, "stage-proposal-001", reviewed_by="tester")
    assert result["status"] == "approved"
    assert result["type"] == "subject_proposal"
    assert result["subject_id"] == "test_ai_subject"


# ---------------------------------------------------------------------------
# 9. execute_approval raises ValueError for non-pending artifact
# ---------------------------------------------------------------------------


def test_execute_approval_not_pending(migrated_db: sqlite3.Connection) -> None:
    artifact = _make_artifact("security_assessment")
    artifact_json = artifact.model_dump_json()

    create_staged_artifact(
        migrated_db,
        "stage-already",
        "security_assessment",
        artifact_json,
        source_type="html",
    )

    migrated_db.execute(
        "UPDATE staged_artifacts SET status = 'approved' WHERE stage_id = 'stage-already'"
    )
    migrated_db.commit()

    with pytest.raises(ValueError, match="not pending"):
        execute_approval(migrated_db, "stage-already")
