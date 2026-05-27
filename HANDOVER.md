# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (ADR 0003 phase 1 — schema extended)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `4d7b722` — Phase 1 wrap-up: CHANGELOG entry, HANDOVER for ADR 0003 implementation arc
**Test status:** 554 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — fully implemented. Read it as the spec for what's in place.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Still active; orthogonal to ADR 0002.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives.

---

## What was just completed

**ADR 0003 phase 1 — extraction_instructions extended for catalog-driven REST.** Two code commits: `40e8f3f` (ADR 0003 doc itself, status Proposed) and `71a9c8f` (migration 0006 + test count update), plus this session's wrap-up. The three existing REST catalog rows now carry `report_id` + `dataset_name` (the new canonical reference under ADR 0003); `dataset_guid` persists in the JSON as an optional cache hint. backup_job_summary's stored `dataset_guid` was wrong (it was the report-level GUID for report 194, stored under the wrong key in migration 0004) and has been corrected in the same migration to the real "Job details" dataset GUID. No application code reads the new fields yet — phase 2 builds the new extractor.

---

## What is in-flight

**ADR 0003 implementation, phase 2.** Phase 1 (schema extended) committed; phase 2 (new generic REST extractor with cacheId-aware session + runtime dataset_name resolution) is the next implementation step. Working tree is clean.

---

## Single recommended next action

**ADR 0003 phase 2 — build the new generic REST extractor.**

Spec: `docs/adr/0003-rest-extractor-with-credentials.md`, particularly the "Extractor shape" section. Phase 1 (this session) landed the catalog half: every REST row in `subject_section_sources.extraction_instructions` now has `report_id` and `dataset_name`. Phase 2 builds the runtime half — the new extractor that consumes those fields.

### What phase 2 needs to do

1. **New extractor class** that takes `(customer_id, project_id, subject_id, token, base_url)` as explicit constructor arguments. No Flask request context dependency. Replaces (and will eventually delete) `RESTExtractor` at `src/cvhealthcheck/extractors/rest.py`.
2. **Opens a `CommvaultSession(base_url, token)`** — the cacheId-aware session at `src/cvhealthcheck/reportsplus/session.py` is the protocol building block; reuse it. POSTs `reportBuilder.do` once per subject collection with the subject's `report_id` (resolved from the catalog: all sections in a subject share one report_id; assert this at load time).
3. **Walks the returned report definition** to build a `dataset_name → dataset_guid` map. Resolution is runtime-only; the catalog's stored `dataset_guid` is treated as untrusted (phase 1 surfaced one case where it was wrong — backup_job_summary's GUID was a report-level GUID, not a dataset GUID).
4. **For each section**: resolves `dataset_name` to a runtime `dataset_guid`, calls `session.fetch_dataset(guid, fields, orderby, limit, parameters)`, applies the existing post-processing (timestamp parsing, null normalization). Same `output_as: "table" | "findings"` handling as the current `RESTExtractor`; `"card"` is documented but no row uses it yet.
5. **Returns an `ExtractionResult`** that `result_to_artifact(...)` converts to a `CanonicalArtifact`, written via `project_store.save_artifact(artifact)`.
6. **Error handling is fail-whole** per ADR 0003. If any section's fetch fails, the run aborts; partial artifacts are not written. The cacheId is acquired once per run; expiry is not auto-recovered.
7. **Route handler integration**: `/quick-hc/<subject_id>/collect` is the v1 entry point. The route resolves the active customer (for `commcell_hostname` and `commcell_id`/`commcell_name` provenance) and the active project (for the artifact store), checks/prompts for a token bound to that customer, constructs the new extractor, runs it, saves the artifact. The current handler at `src/cvhealthcheck/web/routes/quick_hc.py:157-207` is the starting point.

### Constraints

- **Don't delete SA/LS REST paths yet.** Phase 2 lands the new extractor and routes the generic-collect path through it. Phase 4 (SA seed) and phase 5 (LS seed) delete the SA/LS-specific REST modules. This keeps phase 2's blast radius small.
- **Don't touch the catalog rows.** Phase 1 set them; phase 2 reads them.
- **Customer-bound token semantics.** Per ADR 0003: the Flask session holds one CommCell token at a time, bound to a customer; switching active customer invalidates the token and forces re-auth. Implement that binding in phase 2 even though only `Default` customer exists in most dev sessions today.

### Priority-ordered backlog (everything else)

1. **ADR 0003 phase 2 — generic REST extractor** (the single recommended next action above).
2. **ADR 0003 phase 3 — route handler + auth wiring** for the new customer-bound token model.
3. **ADR 0003 phase 4 — SA migration**: seed `subject_section_sources` for Security Assessment (report 336, the 6+ tables it renders), delete `SecurityAssessmentService.collect_from_rest`, delete `reportsplus/security_assessment.py`, retire the SA-specific normalizer / persister / adapter, delete existing SA artifact directories so subjects re-collect into the new canonical shape (no forward-migration script — see methodology entry below and ADR 0002 precedent).
4. **ADR 0003 phase 5 — LS migration**: same shape as phase 4 for License Summary (report 206, 7 tables, this is where `output_as: "card"` first gets seeded for the header datasets).
5. **AI import workstream — staging UI for proposal review, compliance rules.**
6. **CommCell-discovery flow for customer creation.** Auth plumbing overlaps with ADR 0003 phases 2/3.
7. **Report-provenance verification.** Check imported reports' embedded CommCell IDs against the active customer's stored CommCell ID. Catches "wrong customer's report" mistakes.
8. **Read-only per-finalization view.** Deferred from ADR 0002 phase 5 step 5.
9. **Customer panel on the right side of `quick_hc.html`.** Raised earlier, not acted on.
10. **`shared.py` split.** 413-line god-module; flagged in the 2026-05-20 review.
11. **`SecurityAssessmentArtifactRegistry` rename / generalize.** May be partially obsolete once phase 4 lands.
12. **Hardcoded URLs in `report_service.py`.** Audit whether any remain after the 2026-05-20 partial cleanup.
13. **Left-nav structural review.**
14. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL and `db/customers.py` helpers — pick one.
15. **Template inheritance cleanup.** Uneven `base.html` extends.
16. **`engagements` table cleanup.** Empty since migration 0001; pre-ADR-0002.
17. **Project-scope the legacy SA/LS stores** under `data/catalog/{security_assessment,license_summary}/`. Mostly obsolete once ADR 0003 phases 4/5 land — but the historical artifacts in those directories may still need a one-time cleanup pass.
18. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
19. **Audit Section 6 #2/#5/#6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.
20. **Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered.** Wipe and re-collect unless real customer data is at stake. The cost of a migration script is paid up front; the cost of "delete and recreate" is paid in five minutes of re-collection. ADR 0002 set the precedent; ADR 0003 follows it. Apply this rule to remaining ADR 0003 phases (no artifact forward-migration; delete existing SA/LS artifacts before seeding new catalog rows in phases 4 and 5). Revisit at the post-ADR-0003 retrospective to decide whether it becomes a tool-wide default.
21. **Review ADR workflow efficiency after ADR 0003 lands.** Are the survey-then-steer-then-draft-then-phased-implementation cycles worth the overhead, or are we over-engineering process? Deliberate retrospective marker — don't act on this until ADR 0003 phases 2–5 are complete.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section.

### Existing tooling worth surveying for ADR 0003

- `src/cvhealthcheck/auth/commvault_auth.py` — Flask session-backed CommCell token management.
- `src/cvhealthcheck/api_client.py` — Commvault API client.
- `src/cvhealthcheck/reportsplus/client.py` — Reports Plus client used by SA/LS collect paths.
- `src/cvhealthcheck/extractors/rest.py` — generic RESTExtractor used by `/quick-hc/<subject_id>/collect`.
- `src/cvhealthcheck/security_assessment/service.py::SecurityAssessmentService.collect_from_rest` and `license_summary/service.py::LicenseSummaryService.collect_from_rest` — dedicated REST collection per system subject.

ADR 0003 sits at the intersection of all of these. Its job is to design the unifying story — not implement it yet.

### Priority-ordered backlog

1. **ADR 0003 — REST extractor with credentials.** Design first, no implementation. Single recommended next action above repeats this; listed here as #1 for completeness. The data flow audit (`docs/data_flow_audit.md`) was refreshed this session as a prerequisite — the ADR 0003 design conversation now has a fresh post-ADR-0002 baseline to read against.
2. **AI import workstream — staging UI for proposal review, REST extractor with credentials, compliance rules.** Larger scope; ADR 0002's implementation likely surfaced architectural choices that simplify some of this. Auth/extractor design will overlap with ADR 0003.
3. **CommCell-discovery flow for customer creation.** Falls out of ADR 0003's auth design — same plumbing, different destination (customer record's identity fields vs project's working state).
4. **Report-provenance verification.** When an HTML/CSV report is imported, check the embedded CommCell identity matches the active customer's stored CommCell identity. Catches "wrong customer's report uploaded by accident" mistakes.
5. **Read-only per-finalization view.** Deferred from phase 5 step 5. `GET /customers/<c>/projects/<p>/finalizations/<n>` would let consultants see a delivered report's contents alongside the current working state. Needs either an ArtifactStore read-mode that points at `finalized/<n>/` paths, or a sibling helper. Architectural decision left to that session.
6. **Customer panel on the right side of `quick_hc.html`.** Raised previously, not acted on. A right-side panel surfacing the active customer's context (customer name, CommCell hostname/ID, active project metadata) alongside the existing subject workspace. Pairs with the active-project selector at the top.
7. **`shared.py` split.** `src/cvhealthcheck/web/routes/shared.py` is a 413-line god-module with 60+ imports spanning auth, ReportsPlus, metrics, license_summary, security_assessment. Flagged in the 2026-05-20 review; still open. Split by concern.
8. **`SecurityAssessmentArtifactRegistry` rename.** Class at `src/cvhealthcheck/security_assessment/registry.py` is SA-specific in name but the registry pattern is also used by License Summary. Decide: rename to a generic `ArtifactRegistry` and unify, or clarify the per-domain naming as intentional. Flagged in the 2026-05-20 review.
9. **Hardcoded URLs in `report_service.py`.** Partial work landed (CHANGELOG 2026-05-20 says detail URLs were replaced with `TileDefinition.detail_endpoint` resolution through `url_for()`). Audit whether any hardcoded URLs remain.
10. **Left-nav structural review.** The sidebar has accumulated items (Overview, Reports, Customers, Settings, Staging, plus SUBJECTS). Grouping or visual hierarchy will help at some point.
11. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL through `get_db()` AND `db/customers.py`'s module-level helpers — phase 3 surprise. Pick one, retire the other. Same review applies to projects.
12. **Template inheritance cleanup.** Some workspace templates extend `base.html`, others are self-contained — phase 4 surprise. Active-project selector is included in both ways, which is awkward. Consolidate.
13. **`engagements` table cleanup.** Empty since migration 0001; predates ADR 0002. No production writes. Retire if no future use surfaces (ADR 0002 explicitly replaced this concept with `projects`).
14. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). Globally scoped today (Option A read fallback). Needs a project-scoping story eventually.
15. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3 — 200+ raw extraction files accumulating with no retention policy.
16. **Audit Section 6 #2, #5, #6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section (still describes the pre-canonical artifact paths).

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **ADR 0002 is fully implemented.** Customers and projects are CRUD-managed through the UI under `/customers/...`. Each project has its own working state under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. Finalize captures an immutable snapshot under `.../finalized/<n>/<subject>/`. Reload restores the latest snapshot.
- **Finalize is the only code path that writes under `finalized/`.** `ArtifactStore` (the production write path used by every other artifact-saving code path) writes only to `working/`. This is the application-layer immutability invariant from ADR 0002.
- **Finalize/reload core logic lives in `src/cvhealthcheck/db/finalizations.py`.** Three functions: `finalize_project`, `reload_latest_finalization`, `diff_working_vs_latest`. Used by both the routes (`projects_finalize`, `projects_reload`) and by future automation (e.g. a CLI command if added later).
- **Finalize captures `ticket_reference` and `assigned_consultant` at the moment of finalization** and writes them into the `finalizations` row. Editing the project row later doesn't change earlier finalizations — this is the auditable history.
- **Diff is content-based on `latest.json`.** Timestamped snapshot files (the append-only history) are ignored. A no-op save (writing the same content) doesn't trigger a false "modified" signal.
- **Project deletion is blocked once any finalization exists.** Phase 4 introduced the guard with a direct-INSERT test fixture; phase 5 verified it still works with finalizations created via the new UI.
- **`init_db()` and `schema.sql` are gone.** `run_migrations()` is the sole bootstrap path.
- **ADR 0001 source-building fork is orthogonal.** `_legacy_builders` continue to serve their subjects globally; ADR 0002 changed *where* canonical artifacts live, not *how* legacy tile data is shaped.
- **Active-project session.** Lives in the Flask session as `session['active_project'] = {'customer_id': ..., 'project_id': ...}`. The active-project selector partial at `templates/partials/active_project_selector.html` is included on every workspace page (via `base.html` and the self-contained top-level templates).
- **ADR 0003 phase 1 landed.** `subject_section_sources.extraction_instructions` now carries `report_id` and `dataset_name` on all three REST rows (the new canonical reference under ADR 0003). `dataset_guid` persists in the JSON as an **optional cache hint**, not canonical.
- **`dataset_guid` in the JSON is untrusted.** Phase 1 surfaced one case where the stored value was wrong (backup_job_summary had the report-level GUID, not a dataset GUID — corrected in migration 0006). Phase 2's extractor MUST always resolve `dataset_name` against the live `reportBuilder.do` response and not rely on the catalog's stored `dataset_guid` value.
- **`output_as: "card"`** is documented in ADR 0003 but not yet consumed. Phase 4/5 (SA/LS seeding) introduce the first card-shaped rows; phase 2 needs to anticipate the third output mode but doesn't need to implement card rendering yet.
- **Same-report_id-per-subject rule is a runtime check, not a DB constraint.** Phase 2's extractor asserts at load time that all REST sections for a given subject share the same `report_id`. ADR 0003 explicitly left this as an open question with no preference; phase 1 chose runtime check (SQLite multi-row CHECK isn't expressible; a TRIGGER would be harder to debug than a Python assertion).

---

## Session workflow disciplines

These apply to **every session**, not just ADR implementations or
multi-step refactors. Treat them as project workflow rules, not
suggestions.

### Push to GitHub regularly

- **Push to `origin` after each major task completes.** A "major task"
  is: a phase of an ADR implementation, an interstitial cleanup, an
  ADR write-up, a multi-commit refactor, a documentation pass that
  produces multiple commits.
- **Push at the end of every session**, regardless of whether a major
  task just completed. The session-end push is the *last* action
  before stopping — after updating HANDOVER's last-commit pointer, the
  very next thing to do is `git push origin <branch>`.
- This is the final step of the "single recommended next action"
  pointer. Don't treat it as optional.

**Why:** local-only commits are one disk failure away from gone. This
discipline was added after a session discovered 59 local commits had
accumulated unpushed — the work was only on the dev machine and
couldn't be pulled to a second machine. Pushing regularly puts the
commits behind GitHub's durability guarantees and makes the branch
available to any other machine.

If a push fails (auth issue, network), report it and stop — don't
push-force or work around it. Pushes should be append-only and
no-rebase under normal conditions.

### Verify before write

See `docs/PATTERNS.md` — HANDOVER claims are starting points, not
contracts. Grep first, then act.

### STOP-and-report

Many session briefs say "if X happens, STOP and report." Take that
literally — when a step surfaces a design question not covered by
the brief, ask the user rather than fabricating an answer. Better to
leave a gap than to document the wrong thing.

---

## Where work happens — Claude Code vs Claude.ai

This project's sessions run in two different tools. Knowing which is
which saves a fresh chat from trying work it can't do.

### Claude Code (agentic CLI, filesystem access)

Runs every session that touches the codebase. Every implementation
session in this project's history has been Claude Code. Use it for:

- ADR implementation phases
- Audit refreshes and documentation passes that verify against code
- Schema migrations
- Refactors and cleanups
- Anything that needs to read source files, run tests, commit, or push

If the work involves the filesystem at all, it belongs here.

### Claude.ai (chat interface, no filesystem)

Handles work that is pure conversation and prose. Use it for:

- Design conversations and strategic decisions
- Prompt drafting for Claude Code sessions
- Meta-discussions about the project's direction
- ADR drafting *when* the ADR doesn't need verification against
  current code (if it does, Claude Code is faster — it can grep
  while drafting)

### The handoff pattern

The user is the bridge between the two tools:

1. Claude.ai conversation produces a session brief (prompt) and any
   strategic decisions
2. User runs the brief in Claude Code at the dev machine
3. Claude Code executes, commits, pushes, reports back
4. User pastes the report into the next Claude.ai conversation if
   the work continues strategically

### ADR design sessions: the survey-then-steer pattern

ADR drafting looks like prose work, but the prose's value depends
on accurate reading of the codebase. So ADR design sessions follow
this four-step pattern:

1. **Claude Code produces a survey report.** Reads the relevant
   files (existing services, schemas, related ADRs), summarizes
   findings, surfaces the design forks. No design work, no
   drafting — just grounding.
2. **User pastes the survey report into a fresh Claude.ai chat.**
3. **Claude.ai does the design conversation.** Surfaces forks
   from the survey, takes steers from the user, drafts the ADR.
4. **If the draft needs verification against code**, another
   Claude Code session handles that. Often this is the start of
   the implementation phases rather than a separate verification
   pass.

The survey is filesystem work even though it produces prose,
because guessing at file contents from a chat without filesystem
access produces unreliable design conversations. The pattern was
adopted after a Claude.ai chat drafted a Claude Code brief that
asserted "the diagrams are SVG embedded in the markdown" — the
file had no diagrams, and the wasted round trip motivated this
discipline.

### Signal that a session needs Claude Code

Any of these in the brief means filesystem access is required:

- "read `<file>`", "update `<file>`", "edit `<file>`"
- "run the tests", "run pytest", "confirm test count"
- "commit", "push", "update CHANGELOG", "update HANDOVER"
- "verify against current code", "grep for", "check whether"
- "the audit", "the schema", "the migrations"

A Claude.ai chat seeing these signals should respond: *"this work
needs Claude Code — here's the prompt"*, then draft the prompt rather
than attempting the work.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 554 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001, 0002, README
```
