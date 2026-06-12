# HANDOVER — Phase 1: Fix 2 + D5 landed (Context Integrity enforced)

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Current state

- **Branch:** `main`
- **Latest commit:** `261f7d8` (D5 commit 4 — session-secret persistence)
- **Test suite:** 1052 passed (full pytest, exit 0)
- **In flight:** Phase 1 (Context Integrity). **Fix 2 and D5 are done** (see
  the 2026-06-12 fix(isolation) and 2026-06-13 feat(context) CHANGELOG
  entries): the scoped store is the only workspace data source, and the
  Context Integrity invariant is ENFORCED — every named write choke point
  requires `require_active_context()` (typed `NoExplicitContextError`,
  never a silent Default); approval takes explicit context as an input
  with stamp-coherence checks; the session secret persists across
  restarts. Pending human step: authenticated fresh-browser check
  (no project selected → collect yields the clean prompt; select a
  project → collect lands scoped). Anonymous live check passed.
  **Next: identity schema** — the connection_url / commserve_name split
  on customers, + CCID + optional Reports Plus server (per the Phase-1
  audit's F recommendation and ADR-0015's profile layer).

## What was just completed (Phase 0)

See the CHANGELOG entries for 2026-06-11 (×3) and 2026-06-12 — re-read them
before starting work:

- **ADR-0014 `reportsplus_dataset` source type** — implemented, live-gated,
  end-to-end verified (propose → human approval → collect), throwaway subject
  cleaned up. Key traps are encoded in code + `docs/research/adr0014-gate-findings.md`.
- **Wide-table horizontal scroll** in /quick-hc (`2eee3c4`; sticky first
  column deferred).
- **Dispatcher active-version fix** (`6359f57`) — imports extract with the
  ACTIVE subject version, not a hardcoded v1.
- **`delete_subject` orphan-rule reaping** (`39758f1`) + one-time sweep of the
  12 dangling csc_*/ccprop_* registry rules.
- **Dead-code sweeps** (`16d0dec`, `5b91fbf`) — with one correction:
  `SecurityAssessmentService` is NOT dead (live consumer
  `quick_hc_api.py:142`); see CHANGELOG 2026-06-12 Notes.
- **#36 scoped (read-only):** SA module retirement is an LS-coupled decision
  (SA `ArtifactRegistry` alias + 7 shared model classes), not an API cleanup.

## Recommended next action — Phase 1: Customer/Project Context Integrity

Per ROADMAP (Now). The first concrete step is **read-only**: stand up the
two-customer lab (one REST-collected customer, one JSON-import customer with
multiple report versions) and run an isolation audit across
collection/storage/evaluation/reporting **before any fix**. The known
wrong-customer hazard to audit first: `web/active_project.py:42-57` —
`get_active_project` silently falls back to the Default customer's earliest
project when the session key is absent or there is no request context. The
design direction (move active context out of the Flask session into app.db)
follows the audit, not the other way around. Couple report-identity /
dataset-GUID portability (#34) into this work.

## Hard constraints (non-negotiable)

- **Never approve staged artifacts.** Approval is always the human's
  manual step via the web interface. Do not call approval endpoints, do
  not set `reviewed_by`, do not bypass staging.
- ADR-0008 trust boundary stays intact: no credentials in the AI/MCP layer;
  live reads go through the loopback probe only.
- Never probe or collect the `PackageDetails` catalog dataset
  (credential-exposure risk).
- `delete_subject` removes **all** versions, and now also reaps rules its
  deletion orphaned (zero bindings across all subjects + zero overrides,
  scoped to the deleted subject's own refs); re-proposing without
  `supersedes` creates duplicate actives — be careful with all of these.
- Keep the legacy builder path working; LS/security_assessment conversion is
  a Later item gated by the ADR-0006 D5 re-assessment.

## Operational notes

- `flask run --debug`'s reloader wipes the in-memory held token on any `.py`
  edit — finish code edits before asking the operator to Connect.
- MCP server must be restarted after any code change
  (`pkill -f cv-healthcheck-mcp`, relaunch).

## Validation

- `python -m compileall src`
- `venv/bin/python -m pytest` (1070 must keep passing)
- Never gate a commit on piped pytest output — check the exit code.

## Commit granularity

One commit per coherent piece; ADR drafts committed separately.
