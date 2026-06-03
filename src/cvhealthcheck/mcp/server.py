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
import os
import sqlite3
from typing import Any
from uuid import uuid4

import anyio
import requests

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
from cvhealthcheck.db.rules import (
    bind_rule as db_bind_rule,
    delete_rule as db_delete_rule,
    list_rules as db_list_rules,
    save_rule as db_save_rule,
    validate_row_match_rule,
)
from cvhealthcheck.evaluative.subject_eval import (
    evaluate_subject as _evaluate_subject_service,
)


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
        Keys are source types ("html", "csv", "rest", "json",
        "rest_command_center_api").
        Each value is a dict with:
          - "extractable": bool
          - "non_extractable_reason": str | None  ("charts_only" | "client_side_rendered")
          - "recognition_hints": dict
          - "sections": dict mapping section_id to extraction instruction dict
        ADR 0009 — Command Center API source ("rest_command_center_api"):
        use this (NOT "rest") for a subject collected live through the Command
        Center API, so it is classified as Command Center API rather than
        flattened to Reports Plus. Its value dict additionally takes:
          - "endpoint": str — the RELATIVE, read-only Command Center API path to
            collect from, e.g. "/commandcenter/api/v4/servergroup". Omit to
            default to the CommServ identity endpoint. The app validates it as
            relative + read-only before persisting or collecting (an absolute
            URL, or a path outside "/commandcenter/api/", is rejected — the AI
            asserts only a classification + a relative path, never a token or a
            host; ADR 0008/0009 D4).
        Each section under "sections" sets "output_as": "card" (a single object)
        or "output_as": "table" (a multi-record collection, with
        {"table": {"root_key": <list key in the response>,
        "columns": [{"id": <col>, "field": <dot-path into each element>}]}}).
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


# ── probe: app-mediated Command Center REST GET (ADR-0008 E — retired) ───────
#
# The probe NO LONGER holds a CommServe token or calls the CommServe directly. It
# POSTs to the app's loopback internal endpoint with the shared secret; the APP makes
# the GET with its own held token, redacts, and returns. cv-healthcheck is the trust
# boundary — the MCP layer reaches the CommServe ONLY through the app.

_INTERNAL_ENDPOINT_DEFAULT = "http://127.0.0.1:5001/internal/commserve"


def probe(path: str) -> dict:
    """Exploratory read-only GET of a Command Center REST path (e.g.
    ``/commandcenter/api/v4/user``), **mediated by the app** (ADR-0008). The MCP layer
    holds NO CommServe token and never calls the CommServe directly: this POSTs to the
    app's loopback internal endpoint with the shared secret, and the app fetches with its
    own held token and returns the response **already redacted**. GET-only/read-only is
    enforced app-side. Persists nothing.

    Returns the redacted ``data`` plus ``status_code`` / ``ok`` / ``error`` so a CommServe
    non-200 (e.g. 401) is visible, not swallowed. If the app is not connected (the operator
    is signed out, or the held token expired) it returns a clear ``state`` of
    ``disconnected`` / ``expired`` with a reconnect message — the visible-not-silent expiry
    signal. Raises only when it cannot reach or authenticate to the app (missing
    ``CV_INTERNAL_SECRET``, app unreachable, or a guard rejection).

    Parameters
    ----------
    path : str
        A Command Center REST path, e.g. ``/commandcenter/api/v4/user``.
    """
    secret = os.environ.get("CV_INTERNAL_SECRET")
    if not secret:
        # No direct fallback by design — the AI never holds a CommServe token.
        raise ValueError(
            "internal secret not configured (set CV_INTERNAL_SECRET); the probe reaches "
            "the CommServe only through the app's internal endpoint"
        )
    url = os.environ.get("CV_INTERNAL_ENDPOINT_URL", _INTERNAL_ENDPOINT_DEFAULT)

    try:
        resp = requests.post(
            url,
            headers={"X-Internal-Secret": secret},
            json={"path": path, "principal": "mcp-operator", "capability": "read"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ValueError(f"probe could not reach the app at {url}: {exc}")

    if resp.status_code != 200:
        # 503 not-configured (app side), 403 forbidden (secret mismatch / non-loopback),
        # 400 bad request — surface the app's reason clearly rather than guessing.
        try:
            detail = resp.json().get("error", "")
        except ValueError:
            detail = resp.text[:200]
        raise ValueError(f"app internal endpoint returned HTTP {resp.status_code}: {detail}")

    envelope = resp.json()
    state = envelope.get("state")
    if state in ("disconnected", "expired"):
        return {
            "state": state,
            "data": None,
            "error": "not connected — log in via the app to reconnect",
        }
    # Connected: `data` is already redacted by the app; surface the CommServe verdict too.
    return {
        "state": state,
        "ok": envelope.get("ok"),
        "status_code": envelope.get("status_code"),
        "data": envelope.get("data"),
        "error": envelope.get("error"),
    }


def evaluate_subject(subject_id: str) -> dict:
    """Dry-run the subject's enabled row-scope rules over its latest collected
    artifact and return a findings PREVIEW — persists nothing (ADR 0010). The
    rules-side parallel to ``probe``: reads the canonical/approved store's latest
    artifact (not the staging queue), never re-collects, never mutates it.

    Parameters
    ----------
    subject_id : str
        The subject to evaluate, e.g. "server_groups".
    """
    db = get_db()
    try:
        return _evaluate_subject_service(db, subject_id)
    finally:
        db.close()


def list_rules(subject_id: str | None = None, enabled: bool | None = None) -> list[dict]:
    """List registered evaluation rules.

    Parameters
    ----------
    subject_id : str | None
        If given, only rules BOUND to this subject's sections (incl. disabled).
    enabled : bool | None
        If given, filter on the rule's ``enabled`` flag.
    """
    db = get_db()
    try:
        return db_list_rules(db, subject_id=subject_id, enabled=enabled)
    finally:
        db.close()


def save_rule(rule: dict, bind: dict | None = None) -> dict:
    """Author (upsert) a row-scope (``kind:"row_match"``) evaluation rule,
    optionally binding it to a table section in one call.

    Validated at authoring time (rejected, not silently dropped at collection):
    unknown operator; ``between`` without ``value2``; ``emit:"count"`` without
    ``count_operator``/``count_value``; ``scope`` other than "row"; and, when
    binding, a missing section, a non-table section, or a condition target /
    ``{"ref":col}`` that is not a column of that section.

    Parameters
    ----------
    rule : dict
        The rule definition. Required: ``rule_id``; ``conditions`` (list of
        ``{target, operator, value?/value2?/{"ref":col}}`` — all AND-ed);
        ``emit`` ("per_row" | "count"; count needs ``count_operator`` +
        ``count_value``); ``severity`` (critical|warning|info|good); and the
        ``title``/``message`` templates (``{value}/{target}/{count}/{row.<col>}``).
        Optional: ``recommendation``, ``enabled`` (default true). ``kind`` defaults
        to "row_match", ``scope`` to "row"; ``version`` is managed automatically
        (bumped when the body changes).
    bind : dict | None
        Optional ``{"subject_id", "section_id"}`` — adds the rule's ref onto that
        table section's ``evaluative.row_rules`` (idempotent). Omit to save unbound
        (bind later with another ``save_rule`` carrying a target). Rule body and
        section binding stay separable, so one rule can bind to several sections.
    """
    db = get_db()
    try:
        validate_row_match_rule(db, rule, bind=bind)
        saved = db_save_rule(db, rule)
        bound_sections = 0
        if bind is not None:
            bound_sections = db_bind_rule(
                db, saved["rule_id"], bind["subject_id"], bind["section_id"]
            )
        return {"rule": saved, "bound_sections": bound_sections}
    finally:
        db.close()


def delete_rule(rule_id: str) -> dict:
    """Delete an evaluation rule from the registry and strip its ``{ref}`` from
    every section binding (so a later collection can't hit a dangling-ref
    failure).

    Parameters
    ----------
    rule_id : str
        The rule to delete.
    """
    db = get_db()
    try:
        return db_delete_rule(db, rule_id)
    finally:
        db.close()


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
    evaluate_subject,
    list_rules,
    save_rule,
    delete_rule,
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
