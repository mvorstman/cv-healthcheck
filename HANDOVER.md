# HANDOVER — Phase 1: Fix 2 + D5 + Fix 3 landed (isolation, context, identity)

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Current state

- **Branch:** `main`
- **Latest commit:** evidence-context foundation (`a6cccd3`/`754287e`/`a3d0dd0`)
  + a docs commit
- **Test suite:** 1082 passed (full pytest, exit 0)
- **Unpushed:** the whole Phase-1 batch is local-only — D5 (`ef6adfb`..
  `261f7d8`), Fix 3 (`1fc94d2`/`6a4ae97`/`8a52589`), and the evidence-context
  foundation (`a6cccd3`/`754287e`/`a3d0dd0`) plus their docs commits. They go
  together after the browser pass (Michiel's call).
- **In flight:** Phase 1. **Fix 2, D5, and Fix 3 are done** (CHANGELOG
  2026-06-12 fix(isolation), 2026-06-13 feat(context), 2026-06-13 feat Fix 3):
  scoped store is the only workspace data source; Context Integrity is
  enforced at every write choke point; the three identity values are split
  into distinct normalized columns (connection_url / commserve_name /
  commcell_id / registration_code / rp_server_url / rp_scoping_id),
  commcell_hostname frozen READ-ONLY-LEGACY, the conflation killed.
  Pending human step: authenticated fresh-browser check (D5: no project →
  clean prompt, selected → scoped; Fix 3: edit a customer, see the new
  fields, save). Anonymous + headless live checks passed.
  The evidence-context foundation is also in (migration 0033 project_id stamp;
  approval coherence-reads the row's creation context; the verification-result
  home on ArtifactSource) — all inert enablers, nothing populates the
  verification fields yet.
  **Next: Fix 4 — report-identity / dataset-GUID portability (#34)**, which
  consumes the identity columns (rp_scoping_id resolution) AND writes the
  ArtifactSource verification fields via the declared-vs-wire check, per
  ADR-0015's profile layer. Also queued: the later cleanup commit to drop
  commcell_hostname + its read-time fallback once no row needs it.

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
