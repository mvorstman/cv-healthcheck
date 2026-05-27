# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (ADR 0003 phase 3: customer-bound CommCell auth)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *the phase 3 CHANGELOG+HANDOVER commit; pointer-update commit follows.*
**Test status:** 581 passing

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

**ADR 0003 phase 3 — customer-bound CommCell auth.** Repurposes `/login` (and `/api/login`) as the customer-aware credentials prompt: it authenticates against the active customer's `commcell_hostname` (not `CV_BASE_URL`) and binds the issued token to that customer's id in the Flask session. Switching customer (or hitting a route whose active customer doesn't match the bound one) clears the token and bounces to `/login`. The generic REST collect handler resolves the active customer, gates on `is_authenticated_for(customer_id)`, uses `customer.commcell_hostname` as the CommvaultSession base_url, and pulls provenance fields (`commcell_id`, `commcell_name`) from the customer row instead of `data/catalog/rest/commserv.json`. New session key `SESSION_CUSTOMER_ID_KEY`; new helpers `is_authenticated_for` and `get_active_customer`; `set_current_token` now requires `customer_id`. Two commits this session (implementation + wrap-up) plus the pointer-update commit. 18 new tests, 581 total (was 563). Step 1 surfaced that `/login` had always been CommCell auth (never separate "app auth") — Path A (repurpose `/login`) was chosen over Path B (parallel `/connect-commcell` route).

---

## What is in-flight

**ADR 0003 implementation — phase 3 complete, blocker before phase 4.** Phase 3 committed; phase 4 (SA migration) is the next ADR phase but is gated on resolving the `reportBuilder.do` HTTP 419 surfaced during phase 3's end-to-end smoke (see "Single recommended next action" below). Working tree is clean.

---

## Single recommended next action

**Diagnose the `reportBuilder.do` HTTP 419** before starting phase 4.

Phase 3's end-to-end smoke confirmed the auth flow lands correctly, but the **first call inside the new extractor that requires the cacheId pattern fails**: `session.init_report({"reportId": 318})` returns HTTP 419 against the lab CommCell at `https://192.168.182.129:4433`. This was reproduced with a bare CommvaultSession (no Flask, no test_client) and with multiple token variants:

- Fresh `/Login`-issued token, no `QSDK ` prefix → 419
- Fresh token with `QSDK ` prefix → 419
- Pre-existing `.token` file value → 419
- Minimal `{"reportId": 318}` body → 419
- Phase 2's `{"reportId": 318, "datasets": [...]}` shape → 419
- The full report dict echoed back from `GET /reports/318` → 419
- `application/x-www-form-urlencoded` body → 419

The 419 response body is the generic Commvault Command Center HTML error page (`<h1>An error has occurred.</h1>`), not a JSON API error. In contrast, the **direct `GET /datasets/<guid>/data` (the pre-cacheId path) returns 200 cleanly AND includes a generated `cacheId` field in its response body** — the CommCell is auto-creating cacheIds for dataset GETs.

This blocks real-world collection through the new extractor and will block SA/LS migration (phases 4/5) since they're meant to inherit the cacheId pattern.

### What to investigate (priority order)

1. **Capture a working browser POST.** Open the Command Center in a browser, log in, open DevTools' Network tab, navigate to a report that triggers a `reportBuilder.do` POST. Capture the full request — headers, cookies, body. Compare to what `CommvaultSession.init_report` sends. Suspect candidates: a CSRF token header (`X-CSRF-Token`, `X-XSRF-TOKEN`, or similar), a `Referer` requirement, a cookie that needs to round-trip from the login response.
2. **Check whether the cacheId pattern is still necessary.** The direct dataset GET returns a cacheId in its body. If subsequent paginated GETs with that body-supplied cacheId work, the `reportBuilder.do` step might be redundant. This would be an **ADR 0003 design re-examination** — the ADR currently calls out `reportBuilder.do` as the canonical cacheId acquisition. Re-validating the "writes converge / reads stay diverse" claim against current CommCell behavior is appropriate before committing to a code change.
3. **Verify the lab itself hasn't changed.** Phase 2's "end-to-end verified" report was made before this session. If the CommCell was upgraded, reconfigured, or had reportBuilder.do disabled, that's the explanation. Check the CommCell admin interface for service / version state.

Default's `commcell_hostname` is already set to `https://192.168.182.129:4433` and `commcell_id` to `SMOKE-TEST-CS` (left in place from the phase 3 smoke). Use those for further probes.

### After the 419 is resolved

Phase 4 — SA migration — becomes the next single recommended action: seed `subject_section_sources` for Security Assessment (report 336, the 6+ tables it renders), delete `SecurityAssessmentService.collect_from_rest`, delete `reportsplus/security_assessment.py`, retire the SA-specific normalizer/persister/adapter, delete existing SA artifact directories so subjects re-collect into the new canonical shape (no forward-migration script — see methodology entry #19 below and ADR 0002 precedent). Spec: `docs/adr/0003-rest-extractor-with-credentials.md` "Migration" section.

### Priority-ordered backlog (everything else)

1. **Diagnose the `reportBuilder.do` HTTP 419** (the single recommended next action above). Blocking phase 4 because the cacheId pattern is the canonical collect path SA/LS will inherit.
2. **ADR 0003 phase 4 — SA migration**: seed `subject_section_sources` for Security Assessment (report 336, the 6+ tables it renders), delete `SecurityAssessmentService.collect_from_rest`, delete `reportsplus/security_assessment.py`, retire the SA-specific normalizer / persister / adapter, delete existing SA artifact directories so subjects re-collect into the new canonical shape (no forward-migration script — see methodology entry below and ADR 0002 precedent). **Gated on #1.**
3. **ADR 0003 phase 5 — LS migration**: same shape as phase 4 for License Summary (report 206, 7 tables, this is where `output_as: "card"` first gets seeded for the header datasets). Phase 5 also deletes the now-orphaned `REPORT_DEFINITIONS` dict at `src/cvhealthcheck/reportsplus/report_definitions.py` (no callers in tree as of phase 2). **Gated on #1.**
4. **AI import workstream — staging UI for proposal review, compliance rules.**
5. **CommCell-discovery flow for customer creation.** Auth plumbing overlaps with ADR 0003 phase 3 (now landed). The discovery flow can reuse `get_active_customer` and the customer-bound auth model directly.
6. **Report-provenance verification.** Check imported reports' embedded CommCell IDs against the active customer's stored CommCell ID. Catches "wrong customer's report" mistakes.
7. **Read-only per-finalization view.** Deferred from ADR 0002 phase 5 step 5.
8. **Customer panel on the right side of `quick_hc.html`.** Raised earlier, not acted on.
9. **`shared.py` split.** 413-line god-module; flagged in the 2026-05-20 review.
10. **`SecurityAssessmentArtifactRegistry` rename / generalize.** May be partially obsolete once phase 4 lands.
11. **Hardcoded URLs in `report_service.py`.** Audit whether any remain after the 2026-05-20 partial cleanup.
12. **Left-nav structural review.**
13. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL and `db/customers.py` helpers — pick one.
14. **Template inheritance cleanup.** Uneven `base.html` extends.
15. **`engagements` table cleanup.** Empty since migration 0001; pre-ADR-0002.
16. **Project-scope the legacy SA/LS stores** under `data/catalog/{security_assessment,license_summary}/`. Mostly obsolete once ADR 0003 phases 4/5 land — but the historical artifacts in those directories may still need a one-time cleanup pass.
17. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
18. **Audit Section 6 #2/#5/#6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.
19. **Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered.** Wipe and re-collect unless real customer data is at stake. The cost of a migration script is paid up front; the cost of "delete and recreate" is paid in five minutes of re-collection. ADR 0002 set the precedent; ADR 0003 follows it. Apply this rule to remaining ADR 0003 phases (no artifact forward-migration; delete existing SA/LS artifacts before seeding new catalog rows in phases 4 and 5). Revisit at the post-ADR-0003 retrospective to decide whether it becomes a tool-wide default.
20. **Review ADR workflow efficiency after ADR 0003 lands.** Are the survey-then-steer-then-draft-then-phased-implementation cycles worth the overhead, or are we over-engineering process? Deliberate retrospective marker — don't act on this until ADR 0003 phases 3–5 are complete.
21. **Document the "commit the ADR doc alongside its first implementation phase" pattern in PATTERNS.md or HANDOVER's "Where work happens" section.** ADR 0002 and ADR 0003 both landed this way (ADR doc commit immediately followed by phase 1 commits in the same session). Neither HANDOVER nor PATTERNS.md says this explicitly; future ADR drafting sessions might leave the ADR doc uncommitted unintentionally. Low priority — established by precedent.

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
- **ADR 0003 phases 1, 2, and 3 landed.** Phase 1 extended `subject_section_sources.extraction_instructions` with `report_id` + `dataset_name` (the new canonical reference). Phase 2 built the new `RESTExtractor` that consumes those fields. Phase 3 made auth customer-aware: `/login` authenticates against the active customer's `commcell_hostname` (not `CV_BASE_URL`); the token is bound to `customer_id` in the Flask session via `SESSION_CUSTOMER_ID_KEY`; the collect handler gates on `is_authenticated_for(customer_id)` and falls back to `/login` on mismatch (clearing wrong-customer tokens first). The generic REST collect route is the only customer-aware caller today; SA and LS still use their old direct-GET modules (phases 4/5).
- **`reportBuilder.do` returns HTTP 419 against the current lab CommCell.** Surfaced during phase 3's smoke test. Independent of phase 3's code — reproduces with a bare CommvaultSession and any token format. Blocks real-world collection through the new extractor. **The single recommended next action.** The direct dataset GET still returns 200 and now includes its own auto-generated cacheId — that's the fallback / pivot avenue.
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
python -m pytest -q                                # expect 581 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001, 0002, README
```
