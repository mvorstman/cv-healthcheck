"""Subject-specific upload dispatch — data-driven replacement for the
session-2 branch dispatch in quick_hc_subject_import.

A system subject with custom upload behavior appears as an entry in
UPLOAD_HANDLERS keyed by its subject_id. The route handler reads from
this dict instead of branching on hard-coded subject_ids. AI subjects
have no entry; the route handler falls through to its generic
dispatcher path for them.

Adding a new system subject with custom upload behavior is one entry
in UPLOAD_HANDLERS. No schema migration, no MCP-tool contract change.

This is Option δ from the session 5a design. The δ → β
(database-stored typed columns) migration path is reserved for if/when
the set of subjects with custom upload behavior grows enough that
code-side maintenance becomes painful. See
docs/refactor_unified_upload_session_5a_design.md for the full
analysis of why δ was chosen over α/β/γ.

This module contains data only. It imports nothing from Flask; the
route handler is the only consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class UploadHandler:
    """Per-subject upload behavior used by the unified upload route.

    The five fields cover everything the route handler needs that
    differs between subjects. Anything else (extension whitelists,
    redirect destinations of redirect endpoints, X-Inline / ?stage=1
    support) either lives inside the import function itself or is
    derived from subjects.created_by.

    Fields:
        form_field         — multipart form field name carrying the
                             uploaded file (e.g. "assessment_file").
        import_fn          — callable invoked with (stream,
                             original_filename=...) that returns the
                             persisted artifact dict.
        error_class        — subject-specific exception class raised
                             by import_fn for known import failures;
                             caught and its str() flashed as an
                             error.
        success_format     — callable taking the persisted artifact
                             dict and returning the success-flash
                             text.
        redirect_endpoint  — Flask endpoint name url_for'd after the
                             upload completes (success or failure).
    """

    form_field: str
    import_fn: Callable[..., dict[str, Any]]
    error_class: type[Exception]
    success_format: Callable[[dict[str, Any]], str]
    redirect_endpoint: str


# SA migration: security_assessment was removed here — SA uploads fall through to
# the generic dispatcher path (extract_file -> result_to_artifact -> canonical
# store), like the other catalog subjects.
#
# ADR-0017 promotion: license_summary CSV/HTML upload was switched to the generic
# dispatcher too, and the routing cleanup retired the bespoke upload orchestrator +
# handler entirely. UPLOAD_HANDLERS is now empty — every subject routes through the
# generic dispatcher. The UploadHandler / get_handler machinery is retained for any
# FUTURE subject that needs custom upload behavior (one entry brings it back). The
# bespoke LS REST collect path + parsers (import_html/import_csv) remain in place
# for REST and the parity harness; only the live UPLOAD routing was removed.
UPLOAD_HANDLERS: dict[str, UploadHandler] = {}


def get_handler(subject_id: str) -> UploadHandler | None:
    """Return the upload handler for subject_id, or None if the subject
    uses the generic dispatcher path (AI subjects, plus the system subjects
    without custom upload behavior — environment, client_growth,
    capacity_license, backup_job_summary, and security_assessment, which now
    routes through the generic extractor).
    """
    return UPLOAD_HANDLERS.get(subject_id)
