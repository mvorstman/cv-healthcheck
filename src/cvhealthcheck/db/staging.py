from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.artifacts.store import ArtifactStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_staged_artifact(
    db: sqlite3.Connection,
    stage_id: str,
    subject_id: str,
    artifact_json: str,
    *,
    source_file: str | None = None,
    source_type: str | None = None,
    ai_notes: str | None = None,
    engagement_id: str | None = None,
    customer_id: str | None = None,
) -> dict[str, Any]:
    if not str(artifact_json or "").strip():
        raise ValueError("artifact_json is not valid JSON")
    try:
        json.loads(artifact_json)
    except json.JSONDecodeError as exc:
        raise ValueError("artifact_json is not valid JSON") from exc

    created_at = _now()
    db.execute(
        "INSERT INTO staged_artifacts"
        " (stage_id, subject_id, source_file, source_type, status, artifact_json,"
        " ai_notes, created_at, reviewed_at, reviewed_by, engagement_id, customer_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            stage_id,
            subject_id,
            source_file,
            source_type,
            "pending",
            artifact_json,
            ai_notes,
            created_at,
            None,
            None,
            engagement_id,
            customer_id,
        ),
    )
    db.commit()
    return get_staged_artifact(db, stage_id)  # type: ignore[return-value]


def get_staged_artifact(db: sqlite3.Connection, stage_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM staged_artifacts WHERE stage_id = ?",
        (stage_id,),
    ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_staged_artifacts(
    db: sqlite3.Connection,
    *,
    status: str | None = None,
    subject_id: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM staged_artifacts"
    where: list[str] = []
    params: list[Any] = []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if subject_id is not None:
        where.append("subject_id = ?")
        params.append(subject_id)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, tuple(params)).fetchall()
    return [_row_to_dict(row) for row in rows]


def approve_staged_artifact(
    db: sqlite3.Connection,
    stage_id: str,
    *,
    reviewed_by: str | None = None,
) -> dict[str, Any] | None:
    existing = get_staged_artifact(db, stage_id)
    if existing is None:
        return None
    if existing["status"] != "pending":
        raise ValueError("artifact is not pending")
    reviewed_at = _now()
    db.execute(
        "UPDATE staged_artifacts"
        " SET status = ?, reviewed_at = ?, reviewed_by = ?"
        " WHERE stage_id = ?",
        ("approved", reviewed_at, reviewed_by, stage_id),
    )
    db.commit()
    return get_staged_artifact(db, stage_id)


def reject_staged_artifact(
    db: sqlite3.Connection,
    stage_id: str,
    *,
    reviewed_by: str | None = None,
) -> dict[str, Any] | None:
    existing = get_staged_artifact(db, stage_id)
    if existing is None:
        return None
    if existing["status"] != "pending":
        raise ValueError("artifact is not pending")
    reviewed_at = _now()
    db.execute(
        "UPDATE staged_artifacts"
        " SET status = ?, reviewed_at = ?, reviewed_by = ?"
        " WHERE stage_id = ?",
        ("rejected", reviewed_at, reviewed_by, stage_id),
    )
    db.commit()
    return get_staged_artifact(db, stage_id)


def execute_approval(
    db: sqlite3.Connection,
    stage_id: str,
    reviewed_by: str | None = None,
    store: ArtifactStore | None = None,
) -> dict[str, Any]:
    """
    Execute the approval for a staged artifact.
    Handles both artifact and subject_proposal types.
    Returns a result dict with type, subject_id, and outcome.
    Raises ValueError if not pending or not found.
    """
    from cvhealthcheck.db.subjects import create_subject_from_proposal

    existing = get_staged_artifact(db, stage_id)
    if existing is None:
        raise ValueError(f"staged artifact not found: {stage_id}")
    if existing["status"] != "pending":
        raise ValueError("artifact is not pending")

    if existing.get("artifact_type") == "subject_proposal":
        proposal = json.loads(existing["artifact_json"])
        created = create_subject_from_proposal(db, proposal)
        approve_staged_artifact(db, stage_id, reviewed_by=reviewed_by)
        return {
            "type": "subject_proposal",
            "stage_id": stage_id,
            "status": "approved",
            "subject_id": created["subject_id"],
            "version": created["version"],
            "title": created["title"],
        }

    artifact = CanonicalArtifact.model_validate_json(existing["artifact_json"])
    (store or ArtifactStore()).save_artifact(artifact)
    approved = approve_staged_artifact(db, stage_id, reviewed_by=reviewed_by)
    return {
        "type": "artifact",
        "stage_id": stage_id,
        "status": "approved",
        "subject_id": existing["subject_id"],
        "artifact_type": existing.get("artifact_type"),
        "reviewed_at": approved["reviewed_at"] if approved else None,
        "reviewed_by": reviewed_by,
    }


def delete_staged_artifact(db: sqlite3.Connection, stage_id: str) -> bool:
    cursor = db.execute(
        "DELETE FROM staged_artifacts WHERE stage_id = ?",
        (stage_id,),
    )
    db.commit()
    return cursor.rowcount > 0
