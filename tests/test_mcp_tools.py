from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from cvhealthcheck.db.migrations import run_migrations
import cvhealthcheck.db.staging as staging_db_mod
from cvhealthcheck.mcp import server


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    run_migrations(db_path=path)
    return path


@pytest.fixture()
def patch_db(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(server, "get_db", open_db)


def _artifact_payload(subject_id: str = "security_assessment") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": subject_id,
        "generated_at": "2026-05-24T10:00:00Z",
        "source": {
            "type": "json_import",
            "report_id": 318,
            "report_name": "Sample Report",
            "endpoint": "/reports/318",
            "imported_at": "2026-05-24T10:00:00Z",
        },
        "subject": {
            "id": subject_id,
            "title": "Sample Subject",
        },
        "summary": {
            "status": "good",
            "metrics": [
                {
                    "id": "total",
                    "label": "Total",
                    "value": 3,
                }
            ],
        },
        "sections": [
            {
                "type": "findings",
                "id": "findings",
                "title": "Findings",
                "items": [
                    {
                        "id": "finding-1",
                        "severity": "warning",
                        "status": "open",
                        "category": "Security",
                        "title": "Example finding",
                    }
                ],
            }
        ],
        "metadata": {"source": "test"},
    }


def test_get_canonical_schema_returns_dict() -> None:
    schema = server.get_canonical_schema()
    assert isinstance(schema, dict)


def test_get_canonical_schema_is_derived_json_schema() -> None:
    # ADR 0004 #30: the schema is now derived from CanonicalArtifact, so it's a
    # standard JSON Schema ($defs / properties), not the old curated dict.
    schema = server.get_canonical_schema()
    assert "$defs" in schema and "properties" in schema
    assert "artifact_type" in schema["properties"]
    assert "schema_version" in schema["properties"]
    assert "sections" in schema["properties"]


def test_get_canonical_schema_supported_section_types_matches_runtime() -> None:
    # ADR 0004 #31: advertised supported types are sourced from the runtime
    # SUPPORTED_SECTION_TYPES — they cannot diverge.
    from cvhealthcheck.db.section_types import SUPPORTED_SECTION_TYPES
    schema = server.get_canonical_schema()
    assert schema["supported_section_types"] == sorted(SUPPORTED_SECTION_TYPES)
    assert "chart" in schema["supported_section_types"]


def test_get_canonical_schema_drift_guard() -> None:
    """NON-NEGOTIABLE drift guard (ADR 0004 #30): the schema must describe the
    live model. Because it's derived, this passes by construction — and would
    fail loudly if anyone reverted get_canonical_schema to a hand-maintained
    snapshot that omits a live field, or broke the derivation."""
    import json

    from cvhealthcheck.artifacts.models import CanonicalArtifact
    from cvhealthcheck.db.section_types import SUPPORTED_SECTION_TYPES

    schema = server.get_canonical_schema()
    blob = json.dumps(schema)

    # Load-bearing fields the hand-maintained schema had drifted past.
    for field in ("template_version", "render_mode", "verdict_chain", "derived"):
        assert field in blob, f"derived schema must describe {field!r}"

    # The derived schema must equal the live model's schema (plus our one
    # annotation key) — i.e. nobody slipped a hand-curated shape back in.
    expected = CanonicalArtifact.model_json_schema()
    expected["supported_section_types"] = sorted(SUPPORTED_SECTION_TYPES)
    assert schema == expected

    # The section discriminator enumerates the modelled section types; the
    # runtime-supported set must be a subset (never advertise a type the model
    # can't express).
    mapping = schema["properties"]["sections"]["items"]["discriminator"]["mapping"]
    assert SUPPORTED_SECTION_TYPES <= set(mapping.keys())


def test_list_subjects_returns_list(patch_db: None) -> None:
    subjects = server.list_subjects()
    assert isinstance(subjects, list)


def test_list_subjects_returns_seeded_subjects(patch_db: None) -> None:
    # Six system subjects + the internal "_metric_test" subject (migration
    # 0010, ADR 0004 phase 2).
    subjects = server.list_subjects()
    assert len(subjects) == 9


def test_list_subjects_items_have_expected_keys(patch_db: None) -> None:
    subjects = server.list_subjects()
    assert subjects
    assert {"subject_id", "title", "description", "category", "status"} <= set(subjects[0].keys())


def test_list_subjects_contains_security_assessment_and_license_summary(patch_db: None) -> None:
    ids = {item["subject_id"] for item in server.list_subjects()}
    assert "security_assessment" in ids
    assert "license_summary" in ids


def test_list_subjects_status_filter_returns_only_active(patch_db: None) -> None:
    active = server.list_subjects(status="active")
    assert all(s["status"] == "active" for s in active)
    assert len(active) == 9


def test_list_subjects_status_filter_returns_empty_for_proposed(patch_db: None) -> None:
    proposed = server.list_subjects(status="proposed")
    assert proposed == []


def test_save_staged_artifact_saves_valid_artifact(
    patch_db: None,
) -> None:
    record = server.save_staged_artifact(
        "security_assessment",
        json.dumps(_artifact_payload()),
        source_file="report.json",
    )
    assert record["stage_id"].startswith("stage_")
    assert record["status"] == "pending"
    assert record["source_file"] == "report.json"


def test_save_staged_artifact_invalid_json_raises(patch_db: None) -> None:
    with pytest.raises(ValueError):
        server.save_staged_artifact("security_assessment", "{not-json")


def test_save_staged_artifact_invalid_canonical_structure_raises(patch_db: None) -> None:
    invalid_payload = _artifact_payload()
    del invalid_payload["artifact_type"]
    with pytest.raises(ValueError):
        server.save_staged_artifact("security_assessment", json.dumps(invalid_payload))


def test_list_staged_artifacts_returns_list_when_empty(patch_db: None) -> None:
    assert server.list_staged_artifacts() == []


def test_list_staged_artifacts_status_filter_works(patch_db: None) -> None:
    pending = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))
    rejected = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))
    server.reject_staged_artifact(rejected["stage_id"], reviewed_by="reviewer")

    pending_records = server.list_staged_artifacts(status="pending")
    rejected_records = server.list_staged_artifacts(status="rejected")

    assert [record["stage_id"] for record in pending_records] == [pending["stage_id"]]
    assert [record["stage_id"] for record in rejected_records] == [rejected["stage_id"]]


def test_approve_staged_artifact_promotes_to_artifact_store(
    monkeypatch: pytest.MonkeyPatch,
    patch_db: None,
) -> None:
    saved_artifacts = []

    class FakeArtifactStore:
        def save_artifact(self, artifact):  # type: ignore[no-untyped-def]
            saved_artifacts.append(artifact)
            return Path("/tmp/fake.json")

    from cvhealthcheck.web import active_project as _active_project_mod; monkeypatch.setattr(_active_project_mod, "make_default_project_store", lambda db=None: FakeArtifactStore())
    staged = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))

    approved = server.approve_staged_artifact(staged["stage_id"], reviewed_by="alice")

    assert approved["status"] == "approved"
    assert approved["reviewed_by"] == "alice"
    assert saved_artifacts
    assert saved_artifacts[0].artifact_type == "security_assessment"


def test_approve_staged_artifact_double_approval_raises(
    monkeypatch: pytest.MonkeyPatch,
    patch_db: None,
) -> None:
    class FakeArtifactStore:
        def save_artifact(self, artifact):  # type: ignore[no-untyped-def]
            return Path("/tmp/fake.json")

    from cvhealthcheck.web import active_project as _active_project_mod; monkeypatch.setattr(_active_project_mod, "make_default_project_store", lambda db=None: FakeArtifactStore())
    staged = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))
    server.approve_staged_artifact(staged["stage_id"], reviewed_by="alice")

    with pytest.raises(ValueError, match="artifact is not pending"):
        server.approve_staged_artifact(staged["stage_id"], reviewed_by="bob")


def test_reject_staged_artifact_returns_rejected_record(patch_db: None) -> None:
    staged = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))

    rejected = server.reject_staged_artifact(staged["stage_id"], reviewed_by="alice")

    assert rejected["status"] == "rejected"
    assert rejected["reviewed_by"] == "alice"


def test_reject_staged_artifact_double_rejection_raises(patch_db: None) -> None:
    staged = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))
    server.reject_staged_artifact(staged["stage_id"], reviewed_by="alice")

    with pytest.raises(ValueError, match="artifact is not pending"):
        server.reject_staged_artifact(staged["stage_id"], reviewed_by="bob")


# ---------------------------------------------------------------------------
# propose_new_subject
# ---------------------------------------------------------------------------

def _proposal_kwargs() -> dict:
    return {
        "subject_id": "storage_utilization",
        "version": 1,
        "title": "Storage Utilization",
        "description": "Current storage capacity and utilization across entities.",
        "category": "storage",
        "sections": [
            {
                "section_id": "storage_utilization.summary",
                "title": "Summary",
                "section_type": "metric",
                "default_selected": True,
                "sort_order": 1,
            }
        ],
        "extraction_instructions": {
            "html": {
                "extractable": True,
                "non_extractable_reason": None,
                "recognition_hints": {"title_contains": "Storage Utilization"},
                "sections": {},
            }
        },
        "ai_notes": "Tested against 1 sample export. Structure looks stable.",
    }


def test_propose_new_subject_returns_stage_id_and_pending(patch_db: None) -> None:
    result = server.propose_new_subject(**_proposal_kwargs())
    assert result["stage_id"].startswith("stage_")
    assert result["status"] == "pending"
    assert result["subject_id"] == "storage_utilization"


def test_propose_new_subject_creates_subject_proposal_row(patch_db: None) -> None:
    result = server.propose_new_subject(**_proposal_kwargs())
    proposals = server.list_proposed_subjects()
    stage_ids = [p["stage_id"] for p in proposals]
    assert result["stage_id"] in stage_ids


def test_propose_new_subject_proposal_json_roundtrips(patch_db: None) -> None:
    result = server.propose_new_subject(**_proposal_kwargs())
    proposals = server.list_proposed_subjects()
    proposal = next(p for p in proposals if p["stage_id"] == result["stage_id"])
    assert proposal["proposal"]["subject_id"] == "storage_utilization"
    assert proposal["proposal"]["category"] == "storage"
    assert len(proposal["proposal"]["sections"]) == 1


# ---------------------------------------------------------------------------
# list_proposed_subjects
# ---------------------------------------------------------------------------

def test_list_proposed_subjects_empty_when_nothing_proposed(patch_db: None) -> None:
    assert server.list_proposed_subjects() == []


def test_list_proposed_subjects_returns_proposals_after_propose(patch_db: None) -> None:
    server.propose_new_subject(**_proposal_kwargs())
    proposals = server.list_proposed_subjects()
    assert len(proposals) == 1
    assert proposals[0]["subject_id"] == "storage_utilization"


def test_list_proposed_subjects_status_filter_pending(patch_db: None) -> None:
    server.propose_new_subject(**_proposal_kwargs())
    pending = server.list_proposed_subjects(status="pending")
    assert len(pending) == 1
    assert all(p["status"] == "pending" for p in pending)


def test_list_proposed_subjects_status_filter_approved_empty(patch_db: None) -> None:
    server.propose_new_subject(**_proposal_kwargs())
    approved = server.list_proposed_subjects(status="approved")
    assert approved == []


# ---------------------------------------------------------------------------
# approve_staged_artifact — subject_proposal path
# ---------------------------------------------------------------------------

def test_approve_subject_proposal_end_to_end(patch_db: None) -> None:
    result = server.propose_new_subject(**_proposal_kwargs())
    approved = server.approve_staged_artifact(result["stage_id"], reviewed_by="tester")

    assert approved["status"] == "approved"
    assert approved["subject_id"] == "storage_utilization"
    assert approved["title"] == "Storage Utilization"

    subjects = server.list_subjects()
    ids = [s["subject_id"] for s in subjects]
    assert "storage_utilization" in ids


def test_approve_subject_proposal_does_not_call_artifact_store(
    monkeypatch: pytest.MonkeyPatch,
    patch_db: None,
) -> None:
    store_calls: list = []

    class TrackingArtifactStore:
        def save_artifact(self, artifact):  # type: ignore[no-untyped-def]
            store_calls.append(artifact)

    from cvhealthcheck.web import active_project as _active_project_mod; monkeypatch.setattr(_active_project_mod, "make_default_project_store", lambda db=None: TrackingArtifactStore())
    result = server.propose_new_subject(**_proposal_kwargs())
    server.approve_staged_artifact(result["stage_id"])

    assert store_calls == []


def test_approve_subject_proposal_marks_staged_row_approved(patch_db: None) -> None:
    result = server.propose_new_subject(**_proposal_kwargs())
    server.approve_staged_artifact(result["stage_id"])
    proposals = server.list_proposed_subjects(status="approved")
    assert len(proposals) == 1
    assert proposals[0]["stage_id"] == result["stage_id"]


def test_approve_regular_artifact_still_calls_artifact_store_regression(
    monkeypatch: pytest.MonkeyPatch,
    patch_db: None,
) -> None:
    saved: list = []

    class FakeArtifactStore:
        def save_artifact(self, artifact):  # type: ignore[no-untyped-def]
            saved.append(artifact)
            return Path("/tmp/fake.json")

    from cvhealthcheck.web import active_project as _active_project_mod; monkeypatch.setattr(_active_project_mod, "make_default_project_store", lambda db=None: FakeArtifactStore())
    staged = server.save_staged_artifact("security_assessment", json.dumps(_artifact_payload()))
    approved = server.approve_staged_artifact(staged["stage_id"])

    assert approved["status"] == "approved"
    assert len(saved) == 1
