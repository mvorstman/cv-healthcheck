# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (ADR 0003 interstitial fix: extractor switched to GET-only protocol)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `12db239` — CHANGELOG + HANDOVER: ADR 0003 interstitial fix
**Test status:** 582 passing

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

**ADR 0003 interstitial fix — RESTExtractor switched to GET-only protocol.** Phase 2's extractor POSTed `reportBuilder.do` to acquire a cacheId; phase 3's smoke surfaced HTTP 419 from the lab on that POST; the prior session amended ADR 0003 to GET-only. This session lands the code change: `extract()` drops the `session.init_report` call; `CommvaultSession.fetch_dataset` now performs a direct GET when no cacheId is set (and skips `fields`/`orderby` params in that path, which the lab's CacheDB rejects without a cacheId). Tests updated, full suite 582 passing. End-to-end verified against the real lab: `client_growth` produced 13 rows, `capacity_license` produced 13 rows, `backup_job_summary` produced 0 rows (the lab's "Job details" dataset on report 194 is genuinely empty — confirmed by a direct probe returning `totalRecordCount: 0, failures: {}`). Name resolution for "Job details" → `a30bd278-...` succeeded against the live report definition, matching phase 1's catalog GUID. No 419 errors anywhere; artifact provenance for all three came from the customer row.

---

## What is in-flight

**ADR 0003 implementation — phases 1, 2, 3, and the interstitial fix complete.** Phase 4 (SA migration) is the next ADR phase. Working tree is clean.

---

## Single recommended next action

**ADR 0003 phase 4 — Security Assessment migration to the catalog-driven extractor.**

Spec: `docs/adr/0003-rest-extractor-with-credentials.md`, particularly the "Migration" subsection. The generic REST extractor now works end-to-end (interstitial fix landed this session); SA can be the first subject migrated into it.

### What phase 4 needs to do

1. **Walk report 336's live definition** (use `CommvaultSession.get_report("336")` or the existing `extract_report.py` machinery) to enumerate its datasets. Pick the datasets that correspond to the tables consultants want to render for Security Assessment. From SA's current bespoke code (`security_assessment/service.py::collect_from_rest`, `reportsplus/security_assessment.py`, the normalizer), determine which datasets and how the existing extraction shape maps to `subject_section_sources` rows.
2. **Write a migration** (`0007_*.sql`) seeding rows in `subject_sections` and `subject_section_sources` for `security_assessment`, one section per table. Each section: `report_id="336"`, `dataset_name=<live dataset name>`, `output_as` matching the current rendering (most will be `"findings"` — SA is the canonical findings subject), with any timestamp/null-value post-processing the bespoke code does.
3. **Delete the bespoke SA code**:
   - `src/cvhealthcheck/security_assessment/service.py::collect_from_rest` (method)
   - `src/cvhealthcheck/reportsplus/security_assessment.py` (file)
   - `normalize_security_assessment`, `persist_security_assessment_artifact`, `adapt_reportsplus_rest` — anything that exists to produce the SA-shaped artifact and isn't shared with the generic path
   - `SecurityAssessmentService` keeps its non-REST methods (HTML extraction paths, UI helpers) — only `collect_from_rest` and the modules that exist solely to support it go away
4. **Update the SA collect route** (`POST /quick-hc/security-assessment/collect`) to delegate to the generic catalog-driven path, OR remove the dedicated route in favor of `POST /quick-hc/<subject_id>/collect` with `subject_id="security_assessment"`. The latter is cleaner since the catalog now drives the work. Check `quick_hc.py:254` (`quick_hc_security_assessment_collect`) and the corresponding template button.
5. **Wipe existing SA artifact directories** under `data/catalog/artifacts/<customer>/<project>/working/security_assessment/` and any global SA store. ADR 0002 precedent + HANDOVER backlog #19 — no forward-migration script. Subjects re-collect on first use of the new path.
6. **End-to-end verify**: clean session, sign in, hit collect on the Security Assessment tile in the Quick HC workspace, confirm the artifact has SA's expected findings tables (sample a row or two), confirm provenance came from the customer row.

### Constraints

- **Don't touch License Summary yet.** Phase 5 does that — same shape, but LS is where `output_as: "card"` first gets exercised, so it's bigger.
- **Don't delete `extract_report.py` yet.** ADR 0003's Migration section lists it for eventual deletion, but it has callers in `reportsplus/inventory.py` and other dev/audit tooling unrelated to SA's collect path. Deletion is a phase 5 (or post-phase-5 cleanup) concern.
- **Don't touch the new extractor or CommvaultSession.** They work; phase 4 is catalog + deletion + route wiring only.
- **Don't auto-delete artifact directories silently.** The wipe should happen during phase 4 implementation (manual `rm` or a one-shot script), not auto on first collect. Document the wipe in CHANGELOG.

### Useful pointers for phase 4

- `src/cvhealthcheck/security_assessment/service.py` — current SA service. `collect_from_rest` is what's being retired; other methods stay.
- `src/cvhealthcheck/reportsplus/security_assessment.py` — bespoke REST-collection helper (going away).
- `src/cvhealthcheck/reportsplus/extract_report.py::discover_widgets` + `discover_dataset_references` — same helpers the generic extractor uses to build the name→guid map. Useful for surveying report 336's datasets during phase 4 planning.
- `tests/test_security_assessment_*.py` — existing SA tests. Some will need updating (the ones that exercise `collect_from_rest`); others (the canonical-artifact tests, the HTML import tests) stay.
- For SA's `output_as`: SA renders findings tables. The existing bespoke code outputs `Finding` objects via `_build_finding` in `result_to_artifact.py`. The catalog rows for SA should use `output_as: "findings"`, which `result_to_artifact` already handles via the `_SEVERITY_MAP` branch.

### Priority-ordered backlog (everything else)

1. **ADR 0003 phase 4 — SA migration** (the single recommended next action above).
2. **ADR 0003 phase 5 — LS migration**: same shape as phase 4 for License Summary (report 206, 7 tables, this is where `output_as: "card"` first gets seeded for the header datasets). Phase 5 also deletes the now-orphaned `REPORT_DEFINITIONS` dict at `src/cvhealthcheck/reportsplus/report_definitions.py` (no callers in tree as of phase 2).
3. **AI import workstream — staging UI for proposal review, compliance rules.**
4. **CommCell-discovery flow for customer creation.** Auth plumbing overlaps with ADR 0003 phase 3 (now landed). The discovery flow can reuse `get_active_customer` and the customer-bound auth model directly.
5. **Report-provenance verification.** Check imported reports' embedded CommCell IDs against the active customer's stored CommCell ID. Catches "wrong customer's report" mistakes.
6. **Read-only per-finalization view.** Deferred from ADR 0002 phase 5 step 5.
7. **Customer panel on the right side of `quick_hc.html`.** Raised earlier, not acted on.
8. **`shared.py` split.** 413-line god-module; flagged in the 2026-05-20 review.
9. **`SecurityAssessmentArtifactRegistry` rename / generalize.** May be partially obsolete once phase 4 lands.
10. **Hardcoded URLs in `report_service.py`.** Audit whether any remain after the 2026-05-20 partial cleanup.
11. **Left-nav structural review.**
12. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL and `db/customers.py` helpers — pick one.
13. **Template inheritance cleanup.** Uneven `base.html` extends.
14. **`engagements` table cleanup.** Empty since migration 0001; pre-ADR-0002.
15. **Project-scope the legacy SA/LS stores** under `data/catalog/{security_assessment,license_summary}/`. Mostly obsolete once ADR 0003 phases 4/5 land — but the historical artifacts in those directories may still need a one-time cleanup pass.
16. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
17. **Audit Section 6 #2/#5/#6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.
18. **Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered.** Wipe and re-collect unless real customer data is at stake. The cost of a migration script is paid up front; the cost of "delete and recreate" is paid in five minutes of re-collection. ADR 0002 set the precedent; ADR 0003 follows it. Apply this rule to remaining ADR 0003 phases (no artifact forward-migration; delete existing SA/LS artifacts before seeding new catalog rows in phases 4 and 5). Revisit at the post-ADR-0003 retrospective to decide whether it becomes a tool-wide default.
19. **Review ADR workflow efficiency after ADR 0003 lands.** Are the survey-then-steer-then-draft-then-phased-implementation cycles worth the overhead, or are we over-engineering process? Deliberate retrospective marker — don't act on this until ADR 0003 phases 4–5 are complete.
20. **Document the "commit the ADR doc alongside its first implementation phase" pattern in PATTERNS.md or HANDOVER's "Where work happens" section.** ADR 0002 and ADR 0003 both landed this way (ADR doc commit immediately followed by phase 1 commits in the same session). Neither HANDOVER nor PATTERNS.md says this explicitly; future ADR drafting sessions might leave the ADR doc uncommitted unintentionally. Low priority — established by precedent.
21. **Cleanup: retire `CommvaultSession.init_report` and `_REPORTBUILDER_PATH`** if no in-tree caller is added before phase 5 wraps. Method is dormant after the interstitial fix; deleting it is YAGNI cleanup once ADR 0003 is fully implemented.

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
- **ADR 0003 phases 1, 2, 3, and the interstitial fix all landed.** Phase 1 extended `subject_section_sources.extraction_instructions` with `report_id` + `dataset_name`. Phase 2 built the new `RESTExtractor`. Phase 3 made auth customer-aware (`/login` binds the token to the active customer's id via `SESSION_CUSTOMER_ID_KEY`; the collect handler gates on `is_authenticated_for(customer_id)`). The interstitial fix switched the extractor to GET-only — `init_report` is no longer called from the generic path; `fetch_dataset` works with or without a cacheId. The generic REST collect route is the only customer-aware caller today; SA and LS still use their old direct-GET modules (phase 4/5 retires them).
- **`CommvaultSession.fetch_dataset` operates in two modes.** Without a cacheId (the default for the catalog-driven extractor), it does a direct GET to `/datasets/<guid>/data` and ignores any `fields`/`orderby` from the call — the lab's CacheDB rejects those without a cacheId. With a cacheId (passed explicitly or stored via `init_report`), `fields` and `orderby` are honored and the cacheId is included in the request params. Both modes share the same pagination loop, which now reads `totalRecordCount` alongside `total`.
- **`fields` and `orderby` from catalog rows are descriptive only in the GET-only path.** The catalog still declares them per section (`client_growth.monthly_table.fields = ["MonthStart","Total","Removed","Added"]`, etc.) — they document intent. But under the no-cacheId protocol the server returns all columns in natural order. Downstream code (extractor post-processing, `result_to_artifact`) doesn't depend on column subsets or sort order, so the divergence is invisible to consumers.
- **The 419 from phase 3 is resolved.** Not by fixing the POST — by not making the POST. The extractor no longer calls `init_report`. The HANDOVER's "diagnose the 419" item from the post-phase-3 backlog is gone.
- **`backup_job_summary` collects but produces 0 rows.** The lab's "Job details" dataset on report 194 is genuinely empty (probe: `GET /datasets/a30bd278-.../data?format=object` returns HTTP 200 with `totalRecordCount: 0, failures: {}`). Name resolution succeeds; the dataset just has no jobs. This is lab state, not a defect. If the lab gets backup jobs into that dataset, the next collect will pick them up.
- **`init_report` and the rest of the cacheId machinery stay in `CommvaultSession`** as dormant code. Anything that calls them still works. Listed in the backlog as YAGNI cleanup once ADR 0003 phases 4 and 5 are complete.
- **Default customer's CommCell binding is configured.** `commcell_hostname = https://192.168.182.129:4433`, `commcell_id = SMOKE-TEST-CS` — set during phase 3 verification, kept in place for follow-up testing of the 419.
- **`set_current_token` signature changed.** It now requires `customer_id` (positional after `token`). Two production callsites updated (`/login`, `/api/login`). Tests that wrote directly to `session[SESSION_TOKEN_KEY]` continue to work — they don't go through `set_current_token` and only the loose `is_authenticated()` decorator gate (`login_required`) cares about them. Tests that need customer binding should write `SESSION_CUSTOMER_ID_KEY` too.
- **`is_authenticated()` vs `is_authenticated_for(customer_id)`** — the first is loose (any token in session); the second is strict (token AND bound customer matches). `login_required` decorator still uses the loose check; new customer-aware routes use the strict check. Don't mix them up.
- **`_read_commcell_provenance` and `commserv.json` are not consulted by the generic REST collect path anymore.** The function still exists at `quick_hc.py:77-86` and the JSON file still lives at `data/catalog/rest/commserv.json` — `/quick-hc/commcell` (the dev tooling page) reads them. They go away when phases 4/5 retire any remaining SA/LS provenance reads.
- **`dataset_guid` in the JSON is an untrusted cache hint.** Phase 2's extractor resolves `dataset_name` against the live report definition first; the stored `dataset_guid` is used only as a fallback when the name isn't in the live definition (and emits a warning when used). Phase 1 surfaced one case where the stored value was wrong (backup_job_summary's was the report-level GUID, corrected in migration 0006).
- **`output_as: "card"`** is partially implemented. Phase 2's extractor trims `result.sections[section_id]` to `rows[0:1]` when `output_as="card"`; the rendering as a key-value block still needs a real CardSection artifact type and template support, which lands in phase 4/5 when SA/LS seeding introduces the first card-shaped rows.
- **Same-report_id-per-subject rule is a runtime check, not a DB constraint.** Phase 2's extractor asserts at load time that all REST sections for a given subject share the same `report_id` and reports the offending section_ids on mismatch. ADR 0003 explicitly left this as an open question with no preference.
- **`REPORT_DEFINITIONS` dict at `src/cvhealthcheck/reportsplus/report_definitions.py` is orphaned** after phase 2 (no callers in tree). Phase 5 deletes the file alongside the SA/LS-specific modules; left in place for now to keep phase 2's blast radius small.
- **Auth flow is still single-CommCell.** Phase 2 deliberately left the auth flow alone: `/quick-hc/<subject_id>/collect` still uses `settings.base_url` (env-driven `CV_BASE_URL`) and the un-bound Flask session token. Phase 3 makes the auth flow customer-aware (`commcell_hostname` from the active customer row, token bound to a customer, 401 → clear-and-redirect).

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
python -m pytest -q                                # expect 582 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001, 0002, README
```
