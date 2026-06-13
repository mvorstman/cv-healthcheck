# HANDOVER — Provenance arc complete (Fix 4 live-verified); ADR-0015 redesign next

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Current state

- **Branch:** `main`
- **Current main:** `b78f897` — **1102 tests green** (full pytest, exit 0).
- **In flight:** none.
- **Completed (the provenance arc, all on `main`, all pushed):** Fix 2
  (unscoped global-file layer retired), D5 (Context Integrity enforced at the
  write layer), Fix 3 (identity-schema split — three identity values kept
  distinct), the evidence-context foundation (project_id stamp + approval
  coherence-read + verification-result home on ArtifactSource), and **Fix 4
  (declared-vs-wire CommCell ID guard)** — the arc is complete and
  **LIVE-VERIFIED** (see the ground-truth block below).

## Verified Ground Truth — Fix 4 Live Validation (2026-06-13)

Collected `environment` against **HomeLab / gw02** and captured the wire value:

- **declared** (customer row) CommCell ID = **337f**
- **wire** (`commcell.commCellId`, GET CommServ on gw02:4433) = **337f**
- **Fix 4 verdict = `verified`**, persisted on the canonical artifact via
  `ArtifactSource.verification_status / verification_sources /
  verification_notes / verified_at` (notes carry both normalized inputs:
  `declared_normalized=337f / wire_normalized=337f`).

This was the **first end-to-end provenance verification** — collect → read
wire → normalize both → compare → stamp → surface — proven against a real
CommServe, not a fixture.

Architectural implications (resolved, not open):

1. There is **one** CommCell ID field on the wire (`commcell.commCellId`).
   The Fix-4 brief's "internal sequence id `2` distinct from a licensed CCID"
   distinction does **not** exist — confirmed against a live payload.
2. **gw02 and the `.129` lab box front genuinely different CommServes**
   (gw02 = `337f`; `.129` = `commCellId=2`). The two customers map to
   distinct CommCells — not one CommCell mislabelled.
3. The earlier **`33f7` was a transposition typo in the *declared* value**,
   not an architectural ambiguity. This **closes the ADR-0007 §189 open
   question** about the CommCell ID — it is settled, nothing further to verify.
4. Normalization neutralizes hex/decimal/case, so declared `337f` == wire
   `337f` → `verified` with **zero false-mismatch risk** — the #1
   false-positive risk is retired in practice, not just in unit tests.
5. The verdict and **both** normalized inputs live on
   `ArtifactSource.verification_*` only — **provenance, never workflow**;
   nothing was written to `staged_artifacts.status`, `ai_notes`, `subjects`,
   or `subject_sources`.
6. The declared-vs-wire pipeline is proven end-to-end, so **future tiers
   plug into the same seam** (License Summary, RP scoping-id) without
   re-architecting the guard.

## Next architectural focus — ADR-0015 compile/publish redesign

Start with a **read-only design pass** (no code). The redesign separates the
catalog lifecycle into **template / profile / runtime** (ADR-0015) and splits
the staging table accordingly. The gap-audit already scoped the problem:

- **Staging conflates template-drafts with evidence** — `staged_artifacts`
  holds both `subject_proposal` rows (catalog-global template drafts) and
  `artifact` rows (customer evidence) in one table with one status lifecycle.
- **`execute_approval` is overloaded** — one function branches on
  `artifact_type` to do two unrelated jobs (promote a catalog subject vs
  persist scoped evidence with the D5/0033 context coherence checks).
- **Open question: "is artifact-approval even needed?"** — with collection now
  scoped + context-gated + provenance-verified, whether staged *artifacts*
  (as opposed to *proposals*) still need a human approval step is genuinely
  open; the design pass should answer it before any table split.

## Deferred / named register (none of these is forgotten)

- **License Summary verification** — Fix-4 v1 scoped it out (LS collects via a
  bespoke service path, not `result_to_artifact`; its artifacts carry no
  verdict, handled as None). Wire it into the same seam later.
- **RP scoping-id auto-resolution** — `rp_scoping_id` column exists (Fix 3);
  resolving it live (#34 dataset-GUID portability) is future work.
- **`commcell_hostname` legacy-column drop** + removal of the read-time
  fallback in `identity.effective_connection_url` and the three connect sites
  — once no row needs the legacy value (its own cleanup commit).
- **Customer detail-page trim** — the detail view grew identity rows in Fix 3;
  a layout pass is deferred.
- **Read-path Default fallback** (lower severity, transitional) —
  `get_active_project` still falls back to the Default project for READS; D5
  only gated writes. Revisit when active context moves into app.db.
- **Approval authority-flip follow-on** — `project_id` is now stamped on
  staged rows and approval coherence-reads it, but the "approval reads the
  row's creation context instead of re-asking" UX flip is deliberately
  deferred (the current behaviour is identical-to-D5 on the match case).

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
- Restart the MCP server after any code change with
  **`pkill -f bin/cv-healthcheck-mcp`** (the narrow `bin/` pattern avoids the
  self-match where the kill command's own line matches `cv-healthcheck-mcp`),
  then relaunch / reconnect Desktop.

## Validation

- `python -m compileall src`
- `venv/bin/python -m pytest` (1102 must keep passing)
- Never gate a commit on piped pytest output — check the exit code.

## Commit granularity

One commit per coherent piece; ADR drafts committed separately.
