"""
cvhealthcheck.mcp.server
~~~~~~~~~~~~~~~~~~~~~~~~
MCP server exposing cv-healthcheck as AI-callable tools.

Run with:
    cv-healthcheck-mcp

or:
    python -m cvhealthcheck.mcp.server
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - fallback for environments without the SDK
    class FastMCP:
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self):  # type: ignore[no-untyped-def]
            def decorator(func):
                return func

            return decorator

        def run(self) -> None:
            raise RuntimeError("mcp SDK is not installed")

from pydantic import ValidationError

from cvhealthcheck.artifacts.enums import (
    ArtifactStatus,
    ChartType,
    FindingSeverity,
    FindingStatus,
    SourceType,
)
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db import get_db
from cvhealthcheck.db.migrations import run_migrations
from cvhealthcheck.db.staging import (
    create_staged_artifact,
    execute_approval,
    get_staged_artifact,
    list_staged_artifacts as db_list_staged_artifacts,
    reject_staged_artifact as db_reject_staged_artifact,
)
from cvhealthcheck.db.subjects import delete_subject as db_delete_subject


run_migrations()

mcp = FastMCP("cv-healthcheck")


def _canonical_schema() -> dict[str, Any]:
    return {
        "artifact_type": {"type": "string", "description": "Canonical artifact subject type."},
        "schema_version": {"type": "integer", "default": 1},
        "generated_at": {"type": "datetime"},
        "source": {
            "type": "object",
            "fields": {
                "type": {"type": "enum", "values": [item.value for item in SourceType]},
                "report_id": {"type": "integer|null"},
                "report_name": {"type": "string|null"},
                "endpoint": {"type": "string|null"},
                "collected_at": {"type": "datetime|null"},
                "imported_at": {"type": "datetime|null"},
            },
        },
        "subject": {
            "type": "object",
            "fields": {
                "id": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        "summary": {
            "type": "object",
            "fields": {
                "status": {"type": "enum", "values": [item.value for item in ArtifactStatus]},
                "metrics": {
                    "type": "list",
                    "items": {
                        "id": "string",
                        "label": "string",
                        "value": "number",
                        "unit": "string|null",
                    },
                },
            },
        },
        "sections": {
            "type": "list",
            "description": "One or more report content sections.",
            "valid_section_types": ["findings", "table", "metric", "chart"],
            "section_definitions": {
                "findings": {
                    "type": "findings",
                    "fields": {
                        "id": "string",
                        "title": "string",
                        "items": {
                            "type": "list",
                            "item_fields": {
                                "id": "string",
                                "severity": {
                                    "type": "enum",
                                    "values": [item.value for item in FindingSeverity],
                                },
                                "status": {
                                    "type": "enum",
                                    "values": [item.value for item in FindingStatus],
                                },
                                "category": "string",
                                "title": "string",
                                "description": "string|null",
                                "recommendation": "string|null",
                                "references": "list",
                                "raw_ref": "any|null",
                            },
                        },
                    },
                },
                "table": {
                    "type": "table",
                    "fields": {
                        "id": "string",
                        "title": "string",
                        "columns": "list",
                        "items": "list",
                    },
                },
                "metric": {
                    "type": "metric",
                    "fields": {
                        "id": "string",
                        "title": "string",
                        "items": "list",
                    },
                },
                "chart": {
                    "type": "chart",
                    "fields": {
                        "id": "string",
                        "title": "string",
                        "chart_type": {
                            "type": "enum",
                            "values": [item.value for item in ChartType],
                        },
                        "x_axis": "object|null",
                        "y_axis": "object|null",
                        "labels": "list[string]",
                        "series": "list",
                    },
                },
            },
        },
        "metadata": {"type": "object", "additional_properties": True},
    }


def _load_pending_staged_record(db: sqlite3.Connection, stage_id: str) -> dict[str, Any]:
    record = get_staged_artifact(db, stage_id)
    if record is None:
        raise ValueError(f"staged artifact not found: {stage_id}")
    if record["status"] != "pending":
        raise ValueError("artifact is not pending")
    return record


@mcp.tool()
def get_canonical_schema() -> dict:
    """
    Return the canonical artifact schema so Claude understands
    the target format for interpreting unknown reports.
    """
    return _canonical_schema()


@mcp.tool()
def list_subjects(status: str | None = None) -> list[dict]:
    """List all subjects in the Report Inventory catalog."""
    db = get_db()
    try:
        query = (
            "SELECT subject_id, version, title, description, category,"
            " category_label, status, created_by FROM subjects"
        )
        params: list[str] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY category, title"
        return [dict(row) for row in db.execute(query, params)]
    finally:
        db.close()


@mcp.tool()
def save_staged_artifact(
    subject_id: str,
    artifact_json: str,
    source_file: str | None = None,
    source_type: str | None = None,
    ai_notes: str | None = None,
    customer_id: str | None = None,
    engagement_id: str | None = None,
) -> dict:
    """
    Validate and save an AI-interpreted canonical artifact to staging
    for human review. Returns the created staging record.
    """
    try:
        CanonicalArtifact.model_validate_json(artifact_json)
    except ValidationError as exc:
        raise ValueError(f"artifact_json is not a valid CanonicalArtifact: {exc}") from exc

    stage_id = f"stage_{uuid4().hex}"
    db = get_db()
    try:
        return create_staged_artifact(
            db,
            stage_id,
            subject_id,
            artifact_json,
            source_file=source_file,
            source_type=source_type,
            ai_notes=ai_notes,
            engagement_id=engagement_id,
            customer_id=customer_id,
        )
    finally:
        db.close()


@mcp.tool()
def list_staged_artifacts(
    status: str | None = None,
    subject_id: str | None = None,
) -> list[dict]:
    """
    List staged artifacts pending human review.
    Optionally filter by status ('pending', 'approved', 'rejected')
    or subject_id.
    """
    db = get_db()
    try:
        return db_list_staged_artifacts(db, status=status, subject_id=subject_id)
    finally:
        db.close()


@mcp.tool()
def approve_staged_artifact(
    stage_id: str,
    reviewed_by: str | None = None,
) -> dict:
    """
    Approve a staged artifact and promote it to the production
    canonical store. Only pending artifacts can be approved.
    """
    db = get_db()
    try:
        return execute_approval(db, stage_id, reviewed_by=reviewed_by)
    finally:
        db.close()


@mcp.tool()
def reject_staged_artifact(
    stage_id: str,
    reviewed_by: str | None = None,
) -> dict:
    """
    Reject a staged artifact. Only pending artifacts can be rejected.
    """
    db = get_db()
    try:
        _load_pending_staged_record(db, stage_id)
        rejected = db_reject_staged_artifact(db, stage_id, reviewed_by=reviewed_by)
        if rejected is None:
            raise ValueError(f"staged artifact not found: {stage_id}")
        return rejected
    finally:
        db.close()


@mcp.tool()
def propose_new_subject(
    subject_id: str,
    version: int,
    title: str,
    description: str,
    category: str,
    sections: list[dict],
    extraction_instructions: dict,
    ai_notes: str,
    supersedes: int | None = None,
    change_notes: str | None = None,
    related_subjects: list[str] | None = None,
) -> dict:
    """
    Propose a new subject (report type) for the Report Inventory.

    Parameters
    ----------
    subject_id : str
        Snake-case identifier, e.g. "storage_utilization"
    version : int
        Version number. Use 1 for new subjects, increment for updates to existing.
    title : str
        Human-readable title, e.g. "Storage Utilization"
    description : str
        One-sentence description of what this report covers.
    category : str
        One of: identity | security | licensing | performance | operations | storage
    sections : list[dict]
        Each entry: {"section_id": str, "title": str, "section_type": str,
                     "default_selected": bool, "sort_order": int}
        section_type: findings | table | metric | chart
    extraction_instructions : dict
        Keys are source types ("html", "csv", "rest", "json").
        Each value is a dict with:
          - "extractable": bool
          - "non_extractable_reason": str | None  ("charts_only" | "client_side_rendered")
          - "recognition_hints": dict
          - "sections": dict mapping section_id to extraction instruction dict
    ai_notes : str
        Notes on confidence, data quality, empty-export caveats, etc.
    supersedes : int | None
        The subjects.id of the version this supersedes (for versioning).
    change_notes : str | None
        What changed from the superseded version.
    related_subjects : list[str] | None
        subject_id values of related subjects (e.g. dashboard to drill-down).
    """
    proposal_json = json.dumps({
        "subject_id": subject_id,
        "version": version,
        "title": title,
        "description": description,
        "category": category,
        "sections": sections,
        "extraction_instructions": extraction_instructions,
        "supersedes": supersedes,
        "change_notes": change_notes,
        "related_subjects": related_subjects or [],
    })

    stage_id = f"stage_{uuid4().hex}"
    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO staged_artifacts
                (stage_id, subject_id, artifact_type, subject_version,
                 source_type, status, artifact_json, ai_notes, created_at)
            VALUES (?, ?, 'subject_proposal', ?, 'ai', 'pending', ?, ?,
                    strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            """,
            (stage_id, subject_id, version, proposal_json, ai_notes),
        )
        db.commit()
    finally:
        db.close()
    return {"stage_id": stage_id, "subject_id": subject_id, "status": "pending"}


@mcp.tool()
def list_proposed_subjects(status: str | None = None) -> list[dict]:
    """
    List subject proposals in the staging queue.

    Parameters
    ----------
    status : str | None
        Filter by status: "pending" | "approved" | "rejected" | None (all)
    """
    db = get_db()
    try:
        query = """
            SELECT stage_id, subject_id, subject_version, status,
                   artifact_json, ai_notes, created_at, reviewed_at, reviewed_by
            FROM staged_artifacts
            WHERE artifact_type = 'subject_proposal'
        """
        params: list[str] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        rows = db.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                d["proposal"] = json.loads(d.pop("artifact_json"))
            except Exception:
                d["proposal"] = {}
            result.append(d)
        return result
    finally:
        db.close()


@mcp.tool()
def delete_subject(subject_id: str) -> dict:
    """
    Delete a subject from the Report Inventory catalog.

    Only subjects created by AI or user can be deleted.
    System subjects (created_by='system') cannot be deleted.

    Also removes any imported artifact data for this subject.

    Parameters
    ----------
    subject_id : str
        The subject to delete, e.g. "storage_utilization"
    """
    db = get_db()
    try:
        result = db_delete_subject(db, subject_id)
    finally:
        db.close()
    ArtifactStore().delete_artifact(subject_id)
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
