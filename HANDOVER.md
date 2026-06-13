# HANDOVER — License Summary CSV/HTML upload promoted to the generic declarative path (ADR-0017, live + browser-verified); next high-value move is a NEW subject

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Current state

- **Branch:** `main`. **HEAD = `a334b8f`** (all pushed; `HEAD == origin/main`).
- **Tests:** full pytest **1289 green** (exit 0); LS generic-vs-bespoke parity
  **738 / 0** over the distinct real-export corpus.
- **Just completed — the License Summary CSV/HTML UPLOAD de-bespoking (ADR-0017),
  live + browser-verified.** See the dedicated section below.
- **Completed earlier (the provenance arc, pushed, LIVE-VERIFIED):** Fix 2
  (unscoped global-file layer retired), D5 (Context Integrity enforced at the
  write layer), Fix 3 (identity-schema split), the evidence-context foundation,
  **Fix 4 (declared-vs-wire CommCell ID guard)** — ground-truth block below — and
  the **ADR-0015 compile/publish gate** (now live: the LS recipe publishes through
  it; `db/compile_gate.py`).

## License Summary upload promotion (ADR-0017) — DONE, browser-verified

LS **CSV/HTML upload** is promoted to the generic declarative path
(`extract_file → result_to_artifact`), replacing the bespoke upload. The commit
arc, in order:

| Step | What | Commit |
|---|---|---|
| recipe → migration | generic recipe authored in `src/` + generated SQL migration `0034` (drift-guarded; `subject_id=license_summary`, bare section ids) | `cc86df1` |
| D2 → live | `commcell_info` enrichment moved into the live `result_to_artifact` seam (caller-fed identity) | `9d673b9` |
| recognition | broadened (`.reportstabletitle, h2`; dropped exact `table_count` + `first_table_headers`) | `ab12157` |
| 4a extraction/threading | declared-but-absent HTML section → warning (not fatal); `commcell_name` threaded through `extract_file` | `7020e8b` |
| 4b route switch | `UPLOAD_HANDLERS["license_summary"]` removed → generic dispatcher; field auto-aligns to `"file"` | `a42ce43` |
| routing cleanup | retired the bespoke upload orchestrator/handler/scaffolding/vestigial re-exports/dead xlsx entry | `a334b8f` |

**Browser-verified live** on the **workload-only HTML**
(`License summary_2026-05-28-11-12-42.html`) — the file the bespoke parser
*cannot* import (its guard counts only other/agent rows, ignoring workload
sections), so its success is **unambiguous proof the generic path is live**. CSV
also verified; `commcell_info` enriched; `registration_code` masked.

### Boundaries (what is and isn't done)

- **LS REST collect REMAINS bespoke** — parity-UNCOVERED, and it shares
  `normalize` / `models` / adapter / `persist_license_summary_artifact` /
  `collect_rest`. Migrating it is **its own later slice and possibly a PRODUCT
  DECISION** (migrate + prove a generic REST path, or retire LS REST-collect
  entirely) — NOT just a parity exercise.
- **`import_html.py` is RETAINED as a parity/test reference only** (not a live
  upload path): 4 `parse_license_summary_html` unit tests + the parity harness's
  `bespoke_canonical` depend on it.
- **`_handle_system_upload` generic infra is retained but DORMANT** — LS was the
  last `UPLOAD_HANDLERS` registrant, so `UPLOAD_HANDLERS == {}`. Named backlog:
  add synthetic-handler coverage when a subject next registers one.
- **Parity harness is still generic-vs-bespoke** (738 / 0). Converting it to
  generic-vs-golden-fixtures is a parked **option-(b)** modernization, only
  if/when `import_html.py` is retired.

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

- **License Summary REST collect — migration / product decision (named).** LS
  CSV/HTML upload is now generic (ADR-0017, above); LS **REST collect** still runs
  the bespoke service path (parity-UNCOVERED, shares normalize/models/adapter/
  persist/collect_rest). Its own later slice: migrate + prove a generic REST path,
  OR retire LS REST-collect — a product decision, not just a parity exercise.
  (Upload now goes through `result_to_artifact`, so the Fix-4 declared-vs-wire
  verdict IS stamped on LS upload artifacts; the REST path's verdict wiring rides
  with that migration.)
- **Dormant `_handle_system_upload` machinery** — `UPLOAD_HANDLERS == {}` (LS was
  the last registrant). Retained as reusable infra but now untested; add
  synthetic-handler coverage when a subject next registers one.
- **Parity-harness option (b)** — convert generic-vs-bespoke to
  generic-vs-golden-fixtures, only if/when `import_html.py` retires (parked).
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

## Piece-B inputs (recipe-feasibility / LS de-bespoke specimens)

A concrete specimen for LS de-bespoke / recipe-feasibility work, NOT a Piece-A
fix. Leave the recipe untouched.

```
client_growth CSV/HTML import recipe mismatch:
Real Growth-and-Trends export has TWO sections —
  Summary: MonthStart, None_Added, None_Total (monthly time-series)
  Details: CommCell Name, year + month columns, Monthly Growth (per-CommCell pivot)
Current client_growth recipe does not match this export shape; import can
succeed while rendering zero rows (verdict stamps correctly; extraction yields
nothing). The None_-prefix is the report's unnamed series label.
Test fixtures saved for recipe/data-shape feasibility (Piece B):
Growth_20and_20Trends_2026-06-13-11-05-58.csv (data),
Growth_20and_20Trends_2026-06-13-11-05-38.html (charts_only — refused honestly).
```

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
- LS **upload** + security_assessment upload are now both on the generic
  declarative path. The remaining bespoke LS surface (REST collect + the
  retained `import_html.py`/`import_csv`/`normalize`/`models`/adapter that back
  it and the parity harness) STAYS until the REST migration/product decision —
  do not delete it as "legacy."

## Operational notes

- `flask run --debug`'s reloader wipes the in-memory held token on any `.py`
  edit — finish code edits before asking the operator to Connect.
- Restart the MCP server after any code change with
  **`pkill -f bin/cv-healthcheck-mcp`** (the narrow `bin/` pattern avoids the
  self-match where the kill command's own line matches `cv-healthcheck-mcp`),
  then relaunch / reconnect Desktop.

## Validation

- `python -m compileall src`
- `venv/bin/python -m pytest` (1289 must keep passing)
- Never gate a commit on piped pytest output — check the exit code.

## Commit granularity

One commit per coherent piece; ADR drafts committed separately.
