# HANDOVER — ADR-0015 redesign slice 1 done (artifact-approval deleted); compile gate next

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Current state

- **Branch:** `main`
- **Local HEAD:** ADR-0015 slice 1 (`e9acf2e`/`6971734`/`a12d59e`/`03f00c4` +
  a docs commit) — **1075 tests green** (full pytest, exit 0).
- **UNPUSHED:** slice 1's commits are local-only — **awaiting Michiel's review +
  a browser check** (proposal-publish still works; collect still lands scoped +
  verified) before push. The provenance-arc commits below are already pushed
  (`b78f897`).
- **In flight:** ADR-0015 redesign, slice 1 done (see "Next architectural focus").
- **Completed (the provenance arc, pushed, LIVE-VERIFIED):** Fix 2 (unscoped
  global-file layer retired), D5 (Context Integrity enforced at the write
  layer), Fix 3 (identity-schema split), the evidence-context foundation, and
  **Fix 4 (declared-vs-wire CommCell ID guard)** — ground-truth block below.

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

The design pass answered the headline question: artifact-approval was
**vestigial**, and the redesign is **mostly subtraction**. **Slice 1 is done**
(CHANGELOG 2026-06-13 refactor — ADR-0015 slice 1): the `?stage=1` branch,
`execute_approval`'s artifact branch, the MCP `save_staged_artifact` tool, and
the staging page's approved-artifact column are deleted. `execute_approval` is
now proposal-only — the clean compile/publish boundary. `staged_artifacts`
holds only `subject_proposal` rows; collection writes evidence directly to the
scoped store (context-gated + provenance-verified), never through staging.

**Next slice — the only construction:** attach the **compile gate** to the
now-clean `execute_approval` publish boundary — allocation-table validation
(no profile/runtime content in a template, per ADR-0015 §1), transferability,
Catalog Purity, Publication Integrity (published templates immutable). Today
`create_subject_from_proposal` writes the proposal verbatim with no such
check; that's the gap to close.

**Then, deferred — lands WITH the redesign, never before:** the profile schema
(per-customer resolved ids, parameter overrides, customer-assertion rule
packs). ADR-0015 defers it; the compile gate must precede it.

**Documented-dead from slice 1** (drop in a deliberate later schema cleanup,
not piecemeal): the now-inert `staged_artifacts` columns (`customer_id`,
`project_id`, `engagement_id`, `verification_*`, `user_edits_json`,
`filter_state_json`); `db.staging.create_staged_artifact` (test-only now); the
accepted-but-unused `execute_approval` / MCP `approve_staged_artifact` context
params; `.staging-badge-approved` CSS. Named in the CHANGELOG slice-1 entry.

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
- `venv/bin/python -m pytest` (1075 must keep passing)
- Never gate a commit on piped pytest output — check the exit code.

## Commit granularity

One commit per coherent piece; ADR drafts committed separately.
