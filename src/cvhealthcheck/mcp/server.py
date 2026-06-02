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

import functools
import json
import logging
import sqlite3
from dataclasses import asdict
from typing import Any
from uuid import uuid4

import anyio

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

from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.db.section_types import SUPPORTED_SECTION_TYPES
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
from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.auth import load_login_token, load_token
from cvhealthcheck.redaction import redact_user_descriptions


run_migrations()

mcp = FastMCP("cv-healthcheck")


def _canonical_schema() -> dict[str, Any]:
    """Derive the canonical artifact schema from the live Pydantic models.

    ADR 0004 backlog #30: previously this was a hand-maintained dict that
    drifted two phases behind the models (missing template_version, the rich
    MetricItem surface, render_mode, VerdictEntry, …) while save_staged_artifact
    validated against the live model — so the schema advertised shapes the
    validator then rejected. Deriving from ``model_json_schema()`` makes drift
    structurally impossible: any model change is reflected automatically.

    ``supported_section_types`` is sourced from the runtime's
    SUPPORTED_SECTION_TYPES (backlog #31) — the schema's ``$defs`` describe what
    the model can *express*, this lists what the runtime currently *accepts*.
    The two coincide today but the split stays honest when a section type is
    modelled before its renderer lands (e.g. card / multi_section).
    """
    schema = CanonicalArtifact.model_json_schema()
    schema["supported_section_types"] = sorted(SUPPORTED_SECTION_TYPES)
    return schema


def _load_pending_staged_record(db: sqlite3.Connection, stage_id: str) -> dict[str, Any]:
    record = get_staged_artifact(db, stage_id)
    if record is None:
        raise ValueError(f"staged artifact not found: {stage_id}")
    if record["status"] != "pending":
        raise ValueError("artifact is not pending")
    return record


def get_canonical_schema() -> dict:
    """
    Return the canonical artifact schema so Claude understands
    the target format for interpreting unknown reports.
    """
    return _canonical_schema()


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
    from cvhealthcheck.web.active_project import make_default_project_store
    db = get_db()
    try:
        result = db_delete_subject(db, subject_id)
        store = make_default_project_store(db)
    finally:
        db.close()
    store.delete_artifact(subject_id)
    return result


# ── probe: exploratory Command Center REST GET (no persistence) ──────────────

def _probe_token() -> str | None:
    """The single, swappable token seam for ``probe``.

    Returns the operator-maintained, **session-less** Command Center token: the login
    token (``.login_token`` / ``CV_LOGIN_TOKEN`` / ``CV_LOGIN_TOKEN_FILE``), falling
    back to ``.token`` (``CV_TOKEN_FILE`` / ``CV_TOKEN_PATH``) — both via the existing
    ``auth`` seam. It never reads the Flask web session (the MCP server is a separate
    process with no request context).

    TOKEN MODEL — interim and deliberate. This auth is **decoupled from the web
    Connections flow on purpose**: connecting in the web UI binds a token to the Flask
    *session* only (``set_current_token`` → signed cookie) and persists nothing to
    disk/env, so a separate process cannot read it. The operator therefore keeps
    ``.login_token`` / ``CV_LOGIN_TOKEN`` fresh out-of-band. This is **not** the intended
    end state: the known destination is a SHARED server-side token store both the web and
    MCP processes read (Option 3), to be adopted when the MCP server becomes a routine
    companion to the web app; a connect-writes-token-to-disk bridge (Option 2) is a
    possible stopgap that may be skipped. Moving to the shared store swaps THIS function
    only — ``probe`` is unaware of where the token comes from.
    """
    return load_login_token() or load_token()


def probe(path: str) -> dict:
    """Exploratory authenticated GET against a Command Center REST path (e.g.
    ``/commandcenter/api/v4/user``); returns the raw response with each user
    ``description`` redacted, and persists NOTHING (no artifact store, catalog, or db
    write). GET only — no method or body. Auth uses the operator-maintained, session-less
    token (``.login_token`` / ``CV_LOGIN_TOKEN``), **decoupled from the web Connections
    flow** — interim; see ``_probe_token``. A non-200 response is returned as a readable
    dict (``status_code`` / ``error`` intact, so the first live call doubles as the
    auth-acceptance check); only a transport failure (connection / DNS / timeout, or an
    unset ``CV_BASE_URL``) raises.

    Parameters
    ----------
    path : str
        A Command Center REST path under the configured ``CV_BASE_URL`` host, e.g.
        ``/commandcenter/api/v4/user``.
    """
    client = CommvaultApiClient(token=_probe_token())
    result = client.get(path)

    # CommvaultApiClient.get() never raises: a transport failure / unset CV_BASE_URL
    # comes back as status_code=None (there is no HTTP response to read). Surface that as
    # an exception; a real HTTP non-200 (401/403/5xx) falls through and is returned
    # readable so the caller can see the auth/permission verdict.
    if result.status_code is None:
        raise ValueError(f"probe transport failure for {path!r}: {result.error}")

    payload = asdict(result)
    payload["data"] = redact_user_descriptions(payload.get("data"))
    # `text` is the verbatim, pre-redaction response body — it duplicates `data` for a
    # JSON response, so returning it would bypass redaction. Drop it; `data` is the
    # structured (redacted) form.
    payload.pop("text", None)
    return payload


# ── Tool registration (ADR 0004 #35 hardening) ──
#
# FastMCP (mcp 1.27.1) runs a SYNC tool function *inline on the asyncio event
# loop* that also drives the stdio transport — call_fn_with_arg_validation does
# `else: return fn(...)`, with no thread offload. So a slow/blocking tool (a live
# REST/CommCell call, or DB lock contention) would freeze the transport, not just
# that one call. We register each tool wrapped so its blocking body runs in a
# worker thread, keeping the event loop free to service stdio.
#
# The module-level functions above stay SYNC — directly callable and unit-tested
# as-is; only their REGISTERED form is thread-offloaded, and tool LOGIC is
# unchanged (this includes the writers — only their execution context moves off
# the loop). This is proactive hardening against the confirmed loop-blocking
# fragility; it is NOT the fix for the client->SSH->transport hang (#35), which
# is separate and remains open pending the client launch config.
def _run_in_thread(fn):
    """Register-time wrapper: run a sync tool's blocking body in a worker thread
    so it never blocks the MCP event loop / stdio transport. Preserves the
    function's signature + annotations (functools.wraps) so FastMCP's schema
    introspection is unchanged."""
    @functools.wraps(fn)
    async def _wrapper(*args, **kwargs):
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
    return _wrapper


for _tool in (
    get_canonical_schema,
    list_subjects,
    save_staged_artifact,
    list_staged_artifacts,
    approve_staged_artifact,
    reject_staged_artifact,
    propose_new_subject,
    list_proposed_subjects,
    delete_subject,
    probe,
):
    mcp.tool()(_run_in_thread(_tool))


def _quiet_sdk_logging() -> None:
    """ADR 0004 #35 hardening: the mcp SDK logs one INFO line per request
    ("Processing request of type ...") to stderr. Over stdio, if the client
    does not drain the server's stderr, the OS pipe buffer can fill and a sync
    stderr write then blocks the event loop — a backpressure path to the same
    transport freeze. Raise the SDK logger to WARNING so routine per-request
    chatter can't accumulate. Targeted at the `mcp` logger only — root logging
    and the project's own loggers are untouched. (Hardening, not the client-hang
    fix.)"""
    logging.getLogger("mcp").setLevel(logging.WARNING)


def main() -> None:
    _quiet_sdk_logging()
    mcp.run()


if __name__ == "__main__":
    main()
