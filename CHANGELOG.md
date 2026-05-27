# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — sections for **Added / Changed / Fixed / Removed** where they apply, plus a short prose **Notes** section per entry for findings, root causes, architectural decisions, and gotchas worth preserving.

This file is append-only. Past entries are never deleted or rewritten — corrections are made by adding a new entry.

See `HANDOVER.md` for what to do next. See `README.md` for what the project is.

---

## 2026-05-27 (ADR 0003 amendment: wipe-and-re-collect, no forward-migration script)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `bd5262e`, plus the wrap-up commit that publishes this entry.
**Test status:** 554 passing (docs only).

Interstitial amendment between phase 1 (already landed) and phase 2. The steering chat re-examined ADR 0003's forward-migration step against ADR 0002's precedent ("existing canonical-store data on disk is not preserved during the migration; the current layout is throwaway dev state") and concluded the forward-migration is over-engineered for proof-of-concept stage. New rule: phases 4 and 5 delete existing SA/LS artifact directories rather than migrating them; subjects re-collect into the new canonical shape on first use of the new extractor.

### Changed

- **ADR 0003 "Decision → Migration"** paragraph rewritten to describe wipe-and-re-collect and cite ADR 0002's precedent. The "No forward-migration script, no dual-read compatibility, no shape-translation code" sentence states the rule plainly; the ADR reads as if this were the decision from the start (no changelog-of-itself).
- **ADR 0003 "Consequences → Negative"** sentence rewritten: SA/LS shapes still change, dev artifacts get deleted rather than migrated, consultants re-collect after phases 4 and 5.
- **HANDOVER backlog #3 (phase 4 — SA migration)** updated to drop the forward-migration substep in favor of "delete existing SA artifact directories so subjects re-collect."

### Added

- **HANDOVER backlog #20** — methodology marker: "Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered. Wipe and re-collect unless real customer data is at stake." Includes the directive to apply this rule to remaining ADR 0003 phases (4 and 5), and a retrospective trigger to decide whether it becomes a tool-wide default after ADR 0003 fully lands.

### Notes

- No code changes. No phase-count correction needed in HANDOVER — the forward-migration was a substep of phase 4, not a separate phase 6.

---

## 2026-05-27 (ADR 0003 phase 1: extraction_instructions extended for catalog-driven REST)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `40e8f3f` (ADR 0003 doc), `71a9c8f` (migration 0006 + test count update), plus the wrap-up commit publishing this entry.
**Test status:** 554 passing (unchanged — phase 1 is additive schema; the test-count assertion in `test_migration_status_reports_all_applied` updated 5→6 to match).

Phase 1 of the ADR 0003 implementation. The catalog now carries the new canonical reference for REST collection (report_id + dataset_name), and a wrong cache-hint value from migration 0004 is corrected.

### Added

- **ADR 0003 itself** at `docs/adr/0003-rest-extractor-with-credentials.md`. Status: Proposed. Designs a single catalog-driven, customer-scoped REST extractor that replaces the three current REST paths; introduces the `report_id` + `dataset_name` canonical reference with `dataset_guid` demoted to optional cache hint; adopts the cacheId-aware `CommvaultSession` pattern (production Commvault uses this) and migrates SA/LS away from their direct-GET path. Survey at `docs/adr/0003-survey.md` (committed earlier in the day) was the grounding doc.
- **Migration `0006_rest_extraction_instructions_report_id_and_dataset_name.sql`** — backfills the three existing REST rows under the new canonical reference.

### Changed

- **`client_growth.monthly_table`** extraction_instructions gains `report_id="318"`, `dataset_name="Client Count"`.
- **`capacity_license.table`** gains `report_id="318"`, `dataset_name="Capacity License Usage"`.
- **`backup_job_summary.recent_jobs`** gains `report_id="194"`, `dataset_name="Job details"`, AND has its `dataset_guid` corrected from `2638c3d3-...` (the report-level GUID for report 194, stored under the wrong key in migration 0004) to `a30bd278-c7d9-470f-9ae9-8b4922743330` (the real dataset GUID, captured manually from a `reportBuilder.do` trace). Justification for the inline correction: the migration was already rewriting this row; leaving a known-wrong cache hint in place could mask bugs in phase 2's runtime resolution.

### Notes

- **Migration style.** Pure SQL with `json_set` + WHERE guards. Each UPDATE filters on the field the first run sets (e.g. `report_id IS NULL` for the additive rows) or changes (the wrong dataset_guid value for backup_job_summary), so a second run matches zero rows. Idempotency verified by deleting the migration row from `schema_migrations`, re-running, and confirming JSON + `updated_at` are unchanged.
- **Runtime check chosen for "same report_id per subject" rule** rather than a DB constraint. Reasoning: SQLite can't express a multi-row CHECK; a TRIGGER would JOIN across siblings and be harder to debug than a one-line Python assertion in phase 2's extractor load path. ADR 0003 explicitly left this as an open question with no preference.
- **`output_as: "card"`** is documented in ADR 0003 but not consumed yet. Phase 4/5 (SA/LS seeding) introduce the first card-shaped rows.
- **No application code reads the new fields yet.** Phase 2 builds the new extractor. The backfill is invisible to current code paths; the only test churn was a count-pin in `test_migration_status_reports_all_applied`.
- **Surprise from step 1, confirmed.** The `2638c3d3-...` value migration 0004 stored as a "dataset_guid" for `backup_job_summary.recent_jobs` is actually the report-level GUID for report 194 — not a dataset GUID. No data-flow had been broken because the existing `RESTExtractor` never went through dataset discovery; it submitted the GUID directly. Under ADR 0003 the runtime resolver will look up datasets by name from the live report definition, so the corrected GUID is just a cache hint that may or may not be honored (phase 2 design decision).

### Carry-forward for phase 2

Phase 2 builds the new generic REST extractor: a `CommvaultSession`-based collector that takes `(customer_id, project_id, subject_id, token, base_url)` as explicit constructor args, POSTs `reportBuilder.do` once per subject collection, resolves each section's `dataset_name` to a runtime `dataset_guid` from the report definition, then paginates `fetch_dataset` with the obtained `cacheId`. Stored `dataset_guid` in the JSON is treated as untrusted (it may have been wrong, as backup_job_summary's case demonstrated).

---

## 2026-05-27 (tool-selection guidance)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** the two commits that publish this entry (the section addition and the last-commit pointer).
**Test status:** 554 passing (docs only).

Added a "Where work happens — Claude Code vs Claude.ai" section to HANDOVER, documenting which tool runs which kind of session and the handoff pattern between them. Prompted by a fresh Claude.ai chat correctly identifying that filesystem work can't happen there.

### Added

- **HANDOVER.md "Where work happens" section** sits between "Session workflow disciplines" and "Quick verification commands". Names Claude Code as the filesystem-aware tool (every implementation session in this project's history) and Claude.ai as the chat interface for design conversations and prompt drafting. Lists the explicit signal phrases ("read", "update", "run pytest", "the audit", "the schema", etc.) that mean a brief needs Claude Code.

### Notes

- No code changes. Docs only.
- The user remains the bridge between the two tools: Claude.ai drafts the brief, Claude Code executes, the user pastes the report back into Claude.ai if work continues strategically.

---

## 2026-05-27 (workflow discipline: push to GitHub regularly)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `c872b62`, plus this wrap-up.
**Test status:** 554 passing (docs only).

Motivating incident: a session discovered 59 local commits had accumulated without ever being pushed to GitHub. The work was only on the dev machine, couldn't be pulled to a second machine, and would have been lost if the machine had failed. Adding the push discipline as an explicit project workflow rule so future sessions can't drift the same way.

### Added

- **HANDOVER.md "Session workflow disciplines" section.** Sits between "Context" and "Quick verification commands". First subsection is "Push to GitHub regularly" — push after each major task, push at the end of every session, the session-end push is the final step of the single-recommended-next-action pointer. Cross-references the existing verify-before-write and STOP-and-report disciplines.
- **`docs/PATTERNS.md` third pattern: "Push to GitHub regularly".** Same shape as the existing two — brief description, why it matters (the 59-commit incident), when it applies (every session, not just ADR implementations).

### Notes

- Applies to every session going forward, including docs-only sessions and single-commit fixes.
- No force-push, no rebasing pushed branches — append-only.
- If a push fails, stop and report the failure rather than working around it.

---

## 2026-05-27 (housekeeping pass)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `7baa4a9` (HANDOVER backlog sweep), `cd23be3` (docs/PATTERNS.md + README links), plus this wrap-up commit.
**Test status:** 554 passing (unchanged — docs-only).

Small post-ADR-0002 housekeeping. No functional changes.

### Changed

- **HANDOVER backlog sweep.** Promoted ADR 0003 to explicit #1 (was only in the "single recommended next action" header). Added six items that had been raised across recent phases but not surfaced in the backlog list: refresh data flow audit, customer panel on quick_hc.html right side, shared.py split, SecurityAssessmentArtifactRegistry rename, hardcoded URLs in report_service.py audit, engagements table cleanup. Promoted two-CRUD-APIs investigation and template-inheritance cleanup from the smaller-cleanups list into the main backlog. Reordered: AI import workstream moved to #3 ("near top"), CommCell-discovery dropped from #1 to #4 (downstream of ADR 0003).

### Added

- **`docs/PATTERNS.md`** — two project-wide patterns documented as a single short doc:
  1. *Writes converge to canonical; reads stay diverse.* Cites Option A, ADR 0001, ADR 0002, and phase 5 finalize as four instances of the same shape.
  2. *Verify before write.* HANDOVER/CHANGELOG are starting points, not contracts. Cites two real cases where verification caught a mistake before code changed (the audit's `client_growth_summary.json` false-positive, and the init_db/schema.sql footgun).
- **README's "Architecture Documents" section** now links `docs/PATTERNS.md`, `docs/data_flow_audit.md`, and `docs/adr/`. The audit and the ADR directory were in the repo but not findable from the README's documents index.

---

## 2026-05-27 (ADR 0002 phase 5: finalize + reload — ADR 0002 IMPLEMENTATION COMPLETE)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `e4c582d` (core logic + unit tests), `8dfb0a3` (finalize UI), `e86ce90` (reload UI), `33c96fb` (finalizations placeholder refresh), `158841c` (route tests), plus the wrap-up commit that publishes this entry.
**Test status:** 554 passing (was 527 after phase 4; +15 from `tests/test_finalizations.py` + +12 from `tests/test_finalize_reload_routes.py`).

**ADR 0002 implementation is complete.** Five phases over 2026-05-26→27 took cv-healthcheck from "one customer, one project" to a full customer/project lifecycle with an audit-trail-safe finalize/reload workflow. The architecture's promise is now delivered.

### Added

- **`src/cvhealthcheck/db/finalizations.py`** — three operations plus one exception:
  - `finalize_project(db, customer, project) -> int` copies every subject directory under `working/` into `finalized/<n+1>/<subject>/`, inserts a `finalizations` row (capturing the project's current `ticket_reference` and `assigned_consultant` at finalize time so they're stable in the audit trail), and returns `n+1`. Raises `FinalizationError` if working has no subjects or the project is unknown.
  - `reload_latest_finalization(db, customer, project) -> int` clears `working/`, copies every subject from `finalized/<max>/` back in, bumps `working_state_modified_at`. Raises `FinalizationError` if no finalizations exist.
  - `diff_working_vs_latest(db, customer, project) -> list[str]` — content-based diff on `latest.json` per subject. Returns subject_ids that differ; uses symmetric-difference for subjects present in one side but not the other.
- **Finalize UI** at `GET|POST /customers/<c>/projects/<p>/finalize` (`templates/project_finalize.html`). GET shows the next finalization_number, the subjects in working state, the project's current ticket_reference/assigned_consultant (which will be captured), and a Confirm button. When working is empty the page renders in blocked mode. POST runs the finalize, flashes "Finalized as #N", redirects to project detail.
- **Reload UI** at `GET|POST /customers/<c>/projects/<p>/reload` (`templates/project_reload.html`). Three branches: blocked (no finalizations), soft info ("working matches latest"), firm warning ("discard N modifications") with the list of differing subjects. POST runs the reload, flashes "Reloaded finalization #N", redirects to project detail.
- **Finalize and "Reload latest" actions on the project detail page.** The Reload button only renders when at least one finalization exists.
- **27 new tests.** 15 in `test_finalizations.py` for the core logic (finalize success, twice produces 1 then 2, empty raises, finalized_by NULL vs set, ticket_reference captured at finalize-time, reload restores, reload removes added subjects, diff returns empty/symmetric-difference cases). 12 in `test_finalize_reload_routes.py` for the UI surfaces (GET/POST happy paths, blocked paths, finalizations list ordering, regression check on phase 4's delete-blocked-after-finalization invariant).

### Notes

- **Application-layer immutability.** No filesystem chmod, no read-only flags. The contract is that `finalize_project` is the only code path that writes under `finalized/<n>/`. ArtifactStore — the production write path used by every other artifact-saving code path — writes only to `working/`.
- **`shutil.copytree` for the snapshot copy.** `dirs_exist_ok=False` since `next_number` is always new. The copy isn't a transaction with the DB INSERT, but if the copy raises, no DB row is written — the next finalize attempt will get the same `next_number` and a clean slate. The window between "copy succeeded" and "DB row written" is very small; if a crash happened there, the orphan directory would be visible on disk but not in the DB, and the next finalize would write to a new `<n>` slot.
- **`ticket_reference` and `assigned_consultant` captured at finalize-time.** Editing the project's `ticket_reference` later doesn't bleed into earlier finalization rows. Verified by `test_finalize_captures_ticket_reference_at_finalize_time`.
- **Diff is content-based on `latest.json`.** Timestamped snapshot files (the append-only history) are ignored by the diff; only `latest.json` per subject is compared byte-for-byte. A touched-but-identical save doesn't trigger a false "modified" signal because `latest.json` is byte-identical after a no-op save.
- **Read-only per-finalization view (`GET /customers/<c>/projects/<p>/finalizations/<n>`) is deferred.** Listed in the HANDOVER backlog. Rendering a finalization's contents would need ArtifactStore (or equivalent) to read from a `finalized/<n>/` path, which is an architectural change beyond phase 5's scope.
- **End-to-end smoke test verified manually.** Create project → drop artifact → finalize #1 → see #1 on detail page → modify working → reload → verify restored → finalize #2 → see #2 above #1 on detail page (DESC order). All assertions passed.

### Carry-forward

ADR 0002 is now production-complete. The next focus shifts to ADR 0003 (REST extractor with credentials), which will use the active project's storage path for the artifacts it collects. The customer/project foundation is in place.

---

## 2026-05-27 (ADR 0002 phase 4: project page UI + active-project switcher)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `34a0f61` (customer detail), `ee28eb4` (project create), `aad4015` (project detail), `b08794b` (project edit), `5cad2ed` (project delete), `29c3666` (selector + API), `d3bcc55` (tests), plus the wrap-up commit that publishes this entry.
**Test status:** 527 passing (was 503 after the init_db retirement; +24 from `tests/test_projects_routes.py`).

Phase 4 of ADR 0002. Projects are now manageable through the web UI under their parent customer; the active-project session can be switched from any workspace page via the selector pinned to the top-right.

### Added

- **Customer detail page** at `GET /customers/<customer_id>` (`templates/customer_detail.html`). Shows customer metadata, an edit link, and a projects table sorted by created_at desc. Each project row links to its detail page; the active project's row is highlighted with an "Active" badge in place of the "Set as active" button. Empty-state when no projects exist. The Customers list now links each customer name to its detail page.
- **`src/cvhealthcheck/web/routes/projects.py`** — eight routes covering the full project CRUD lifecycle plus the active-project JSON API. Routes are nested under `/customers/<c>/projects/...` so they always carry the customer context in the URL.
- **Project create form** (`templates/project_form.html` shared with edit). Required field: project_number (free-form, will eventually come from an external ticket system). Optional: ticket_reference, assigned_consultant. `UNIQUE(customer_id, project_number)` collisions surface as a friendly form error. project_id is server-side slugified from project_number with global-uniqueness collision disambiguation. On successful create, the new project is auto-set as active and the user lands on its detail page.
- **Project detail page** at `GET /customers/<c>/projects/<p>` (`templates/project_detail.html`). Project metadata, Active badge or "Set as active" button, Edit/Delete actions, and a "Finalizations" section that's a placeholder for phase 5 ("No finalizations yet. The finalize action lands in a future phase."). Breadcrumb back to the customer.
- **Project edit form** — shares the create template. project_number is editable; URL stays stable (project_id is fixed at create time).
- **Project delete with strict-and-then-some guard** (`templates/project_delete.html`). The GET side renders a confirmation when finalizations is empty; when finalizations exist, the page renders in blocked mode ("Cannot delete: this project has N finalizations. Removal of finalized projects requires direct database access."). The POST side server-side re-checks finalization count and returns 400 on a bypass attempt. When the deleted project is the active one, the handler falls back to the migration-seeded Default project via `resolve_default_project()` + `set_active_project()`.
- **Active-project JSON API** at `/api/active-project`. GET returns the current `(customer_id, project_id)` plus customer_name, project_number, and the full list of customers and their projects for the selector dropdown. POST takes customer_id + project_id (form-encoded), validates that the project belongs to the customer, and updates the session. Optional `redirect_to` form field switches the response from JSON to a 302 redirect — used by form-driven "Set as active" buttons.
- **Active-project selector partial** (`templates/partials/active_project_selector.html`). Fixed to the top-right of every workspace page (`base.html` + the self-contained top-level templates). Renders as "Active <Customer> / <Project>" → click expands a panel grouped by customer with all projects. Clicking a project posts to `/api/active-project` with a redirect back to the current URL so the workspace reloads against the new active state. Click-outside closes the panel. No new localStorage keys — active project lives in the Flask session per phase 2.
- **`tests/test_projects_routes.py`** — 24 tests covering customer detail (2), project create (5), detail (4), edit (3), delete (5), and the active-project API (5).

### Notes

- **Project ID slug uniqueness.** A test ("DUP" for two different customers) caught a bug in `_slugify_project_id`: the collision check was scoped to the same customer, but `project_id` is the global PK on `projects`. Two customers slugifying the same project_number to the same project_id would have hit an `IntegrityError`. Fixed by checking project_id collisions across all projects, not just within the customer. The user-facing `UNIQUE(customer_id, project_number)` constraint is unaffected — it's still per-customer.
- **Auto-activate on create.** ADR 0002's "starting work for a customer, create a project, start working" workflow is the common case, so the new project becomes active without an extra click. The user can switch back via the selector if needed.
- **Strict-and-then-some delete.** ADR 0002's audit-trail safety: finalized projects cannot be deleted via the UI. Removal requires direct DB access (deliberate, per the ADR's "removal of finalizations requires direct database access" decision).
- **Selector visibility.** Added the partial to `base.html` (which `quick_hc_backup_job_summary`, `quick_hc_commcell`, `quick_hc_report`, `quick_hc_staging` all extend) and to the self-contained top-level templates (`quick_hc.html`, `quick_hc_settings.html`, customers/projects pages). End-to-end verified: create a new project, see workspace re-render against it via the selector, switch back to Default, workspace re-renders again.

### Carry-forward for phase 5

Phase 5 implements the finalize action and reload-latest-finalization. The Finalizations placeholder on the project detail page becomes a real history list once rows can be written. Closes out ADR 0002.

---

## 2026-05-27 (interstitial: retire init_db and schema.sql)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `bd7b4a0`, plus the wrap-up commit that publishes this entry.
**Test status:** 503 passing (was 508 after phase 3; -5 from the deleted `test_init_db_*` tests).

Small interstitial cleanup between phase 3 and phase 4. Phase 2 and phase 3 both flagged the same recurring footgun: tests using `init_db()` got a schema frozen at migration 0001 (the state `schema.sql` covered), and broke in surprising ways whenever a later migration added columns or tables. Phase 3's response was to switch two test fixtures to `run_migrations()`. This entry finishes the job — `init_db()` and `schema.sql` are gone, `run_migrations()` is the sole database-bootstrap path.

### Removed

- **`src/cvhealthcheck/db/schema.sql`** — only ever covered migration 0001's tables (`customers`, `engagements`, `staged_artifacts`). Stale; deleted.
- **`init_db()`** in `src/cvhealthcheck/db/database.py` + the `_SCHEMA_PATH` constant. No production callers.
- **`init_db` export** from `src/cvhealthcheck/db/__init__.py`.
- **Five `test_init_db_*` tests** in `tests/test_db_customers_engagements.py` that exercised `init_db` itself. Superseded by `tests/test_migrations.py` which covers `run_migrations`.

### Changed

- **`tests/test_staging_routes.py`** — `db_path` fixture switched from `init_db` to `run_migrations` + delete the migration-seeded default rows so the empty-table behaviour assumed by the tests still holds.
- **`tests/test_db_staging.py`** and **`tests/test_db_customers_engagements.py`** — drop the stale `init_db` import. Their fixtures were already on `run_migrations` from phase 3.
- **`src/cvhealthcheck/db/migrations/__init__.py`** — docstring updated to drop the historical "Replaces init_db()" framing now that init_db no longer exists.

### Notes

- The footgun the HANDOVER's priority-ordered backlog called out ("bring schema.sql in sync with migrations, or retire it") is resolved by the "retire" path. The next time a migration adds tables, no test fixture will silently miss them.

---

## 2026-05-27 (ADR 0002 phase 3: customer page UI)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `226c1ab` (nav), `9858bcc` (list), `b8877f4` (create form), `e22da6f` (delete), `ae8bc27` (tests), plus the wrap-up commit that publishes this entry.
**Test status:** 508 passing (was 493 after phase 2; +15 from `tests/test_customers_routes.py`).

Phase 3 of ADR 0002. The customers table is now fully manageable through the web UI — list, create, edit, delete. Manual entry is the primary path; CommCell-discovery (auto-populating identity fields from a CommCell login) is deferred to a future phase and shares plumbing with ADR 0003's REST extractor.

### Added

- **`Customers` nav item** in the left sidebar of `templates/quick_hc.html`, between Reports and Settings. Points at `main.customers_list`.
- **`src/cvhealthcheck/web/routes/customers.py`** — seven routes covering the full CRUD lifecycle (`GET /customers`, `GET|POST /customers/new`, `GET|POST /customers/<id>/edit`, `GET|POST /customers/<id>/delete`). The route file uses inline SQL through `get_db()` (matching the staging-route pattern) and owns its own slugify helper. Registered in `routes/main.py`.
- **`templates/customers_list.html`** — heading, "New customer" CTA, table sorted by name with Name / CommCell ID / Projects / Edit-Delete columns, empty-state fallback.
- **`templates/customer_form.html`** — shared between create (mode=new) and edit (mode=edit). Required field is customer_name; all others optional. Hints clarify when to set `company_guid` ("only if the CommCell hosts multiple companies") to discourage speculative filling.
- **`templates/customer_delete.html`** — confirmation page with customer summary card + project count. Renders in `blocked=True` mode when the customer has projects: red block message, disabled delete button. The server-side POST handler re-checks project count and returns 400 on a race or stale-form bypass.
- **`tests/test_customers_routes.py`** — 15 tests across list view, create form (including slugify collision disambiguation), edit form (including 404 on unknown), and delete (including the strict project-count guard on both GET render and POST defence-in-depth).
- **`src/cvhealthcheck/db/customers.py`** extended with the new fields, a `slugify_customer_id` helper, `list_customers_with_project_counts`, and `count_customer_projects`. The route layer doesn't depend on these (it uses inline SQL), but the module remains the canonical CRUD API for non-Flask callers (CLI, tests).

### Notes

- **Customer ID slug convention.** Matches the migration-seeded `default` style: lowercase, alphanumeric runs joined with underscores, leading/trailing underscores stripped. On collision, append `_2`, `_3`, etc.
- **No CommCell network calls anywhere in this phase.** Discovery is deferred — when implemented, it will be an addition to the existing customer form, not a replacement.
- **No authentication required on customer routes.** Consistent with the existing settings and staging pages.
- **Default customer is not specially protected.** It can be deleted like any other if it has no projects. Phase 1 + phase 2 step 1 seeded a Default project under it, so attempting to delete Default goes through the blocked path until that project is removed (phase 4 will handle project deletion).
- **Migration-seeded data and test fixtures.** `test_db_customers_engagements.py` and `test_db_staging.py` previously used `init_db()` which applies the legacy `schema.sql` (no `projects`/`finalizations` tables, no new customer columns). Both were switched to `run_migrations()` and the seeded `default` rows are deleted in the fixture so existing empty-table assertions still hold. `test_create_customer_returns_all_fields` updated to expect the extended column set.
- **Step 4 ('edit form')** had no new files — the route handler landed in step 2, the template is shared with the create form from step 3. Documented here for the audit trail; no commit was made.

### Carry-forward for phase 4

Phase 4 builds the project page UI: list projects per customer, create, switch the active project (the customer-level half landed here gives nav context; project-level needs the projects table). Phase 5 follows with finalize + reload.

---

## 2026-05-27 (ADR 0002 phase 2: project-scoped storage + active project session)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `d78e47c` (Default project), `119e360` (active-project helper), `f5c5946` (ArtifactStore project-scoping), `a16942c` (acceptance tests), plus the wrap-up commit that publishes this entry.
**Test status:** 493 passing (was 482 after phase 1; +11 = +6 active-project + +5 project-scoping acceptance).

Phase 2 of ADR 0002. The workspace now reads and writes artifacts from customer/project-scoped paths instead of the global path. The active project lives in the Flask session (namespaced `session['active_project']`); the migration-seeded Default customer + Default project is the fallback when no active project is set. **Existing dev artifacts at `data/catalog/artifacts/*` were already deleted in phase 1; phase 2 doesn't touch any new data on disk** — the new on-disk layout will populate organically as collections/imports run.

### Added

- **`src/cvhealthcheck/web/active_project.py`** — `get_active_project`, `set_active_project`, `clear_active_project`, `resolve_default_project`, plus the constructor helpers `make_active_project_store` (request-context callers) and `make_default_project_store` (non-request callers like MCP staging and CLI). Session key is namespaced; `clear_*` restores the Default fallback.
- **Migration 0005 extended** with an `INSERT OR IGNORE` for the Default project under the Default customer (`project_id='default'`, `project_number='DEFAULT'`). Idempotent; the dev DB was brought into sync by re-applying the INSERT directly since 0005 was already marked applied from phase 1.
- **`tests/test_active_project.py`** — 6 tests covering the helper.
- **`tests/test_project_scoped_artifacts.py`** — 5 acceptance tests pinning project isolation, active-project switching, the path structure, and defensive constructor checks.

### Changed

- **`ArtifactStore.__init__`** now requires positional `customer_id` and `project_id`. Path becomes `<base_dir>/<customer_id>/<project_id>/working/<artifact_type>/{latest.json, <timestamp>.json}`. The `finalized/<N>/` sibling directory is reserved for phase 5; the store exposes no write path for it (application-layer immutability per ADR 0002).
- **Module-level singletons retired** in four places. Each module now constructs the store on demand via `make_active_project_store()` so each call resolves the current session's active project:
  - `security_assessment/service.py` (`_artifact_store` → `_active_project_store()`)
  - `license_summary/service.py` (`_artifact_store` → `_active_project_store()`)
  - `quickhc/subject_data_service.py` (`_canonical_store` → `_canonical_store()`)
  - `registry/execution.py` (`_store` → `_active_project_store()`)
- **Route handlers** in `web/routes/quick_hc.py` migrated from bare `ArtifactStore()` to `make_active_project_store()` at three sites (delete_subject, generic collect, unified dispatcher upload).
- **`execute_approval` in `db/staging.py`** falls back to `make_default_project_store(db)` when no `store` is injected — non-request contexts (MCP) hit the Default project.
- **`mcp/server.py` delete tool** constructs its store via `make_default_project_store(db)` while the db connection is open.
- **Test infrastructure** updated to match. The autouse `_isolate_canonical_stores` fixture now monkeypatches `_DEFAULT_BASE_DIR` (matching the production `data/catalog/artifacts` directory name so path-structure assertions still pass), instead of monkeypatching the now-defunct module-level singletons. Tests that previously monkeypatched `ArtifactStore` as a module attribute now monkeypatch `make_active_project_store` / `make_default_project_store` returning fakes. One test (`test_dispatched_subjects_rest_source_shows_validated_with_collect_action`) that monkeypatched `sds._canonical_store` as an instance now monkeypatches it as a callable.

### Notes

- **Source-building fork unaffected.** ADR 0001's `_legacy_builders` / `_legacy_loaders` continue to read globally-scoped legacy on-disk files (`commserv.json`, `metrics/*.json`, `backup_job_summary_latest.json`, the legacy SA/LS stores). These remain customer-agnostic for v1 — the step-4 read-site audit explicitly preserved them. Project-scoped reads are only the canonical-store reads.
- **The legacy SA/LS Option A read-fallback paths** (`data/catalog/{security_assessment,license_summary}/latest.json`) also stay globally scoped. Their consumers will need a project-scoping story eventually; not phase 2.
- **Provenance builders' file-path strings** (`source_provenance.py:87, 125, 224, 274`) are informational display values, not actual reads. Left as-is for now; future iterations can teach them the project-scoped layout when the UI surfaces customer/project context.
- **Workspace verified rendering** in a request context: Default project, empty canonical artifacts directory. The six system subjects render through the legacy-builder fallback (reading legacy on-disk files); the two AI subjects show "Not collected" because their project-scoped paths are empty. This matches the expected post-phase-2 state.

### Carry-forward for phase 3

Phase 3 builds the customer page UI: list customers, create (manual + CommCell-discovery), edit. The schema and storage are ready; the missing piece is the surface for managing customers (and choosing which CommCell to connect to). Phase 4 follows with the project page (list per customer, create, switch active, view finalization history). Phase 5 implements finalize + reload.

---

## 2026-05-26 (ADR 0002 phase 1: schema and storage foundation)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `4c69034` (migration), `75ba4b9` (snapshot test deletion), plus the wrap-up commit that publishes this entry.
**Test status:** 482 passing (was 483; -1 from the deleted snapshot test).

Phase 1 of the 5-session ADR 0002 implementation. The database now knows about customers, projects, and finalizations; no application code uses any of it yet — phase 2 plumbs the active project through `ArtifactStore`.

### Added

- **Migration `0005_customer_project_finalization.sql`.** Three changes to the schema, all idempotent via `IF NOT EXISTS` / `INSERT OR IGNORE`:
  - `customers` extended with `commcell_id`, `commcell_hostname`, `company_guid`, `contact_info` (JSON-as-TEXT), `notes`. Existing `customer_id` PK and `customer_name` preserved so the `staged_artifacts.customer_id` FK from migration 0002 stays valid.
  - New `projects` table: `project_id` PK, `customer_id` FK CASCADE NOT NULL, `project_number` NOT NULL, `ticket_reference`/`assigned_consultant` nullable, timestamps. `UNIQUE(customer_id, project_number)`. No status column — history is the sequence of finalizations per the ADR.
  - New `finalizations` table: `finalization_id` PK, `project_id` FK CASCADE NOT NULL, `finalization_number` (CHECK >= 1), `finalized_at`, `finalized_by` nullable, `ticket_reference` nullable (the ticket that triggered *this* finalization, distinct from the project's), `notes` nullable. `UNIQUE(project_id, finalization_number)`.
  - Auto-seeds a `customer_id='default'` / `customer_name='Default'` row via `INSERT OR IGNORE`. ADR 0002's first-run experience: the empty-state is hidden behind a pre-created customer.

### Removed

- **`tests/test_subject_initial_data_snapshot.py`** and its fixture `tests/fixtures/subject_initial_data_snapshot.json` deleted. The snapshot pinned the behavior of `build_subject_initial_data()` against the single-customer architecture that ADR 0002 replaces. Phases 2-5 exercise the new customer/project-scoped paths through targeted tests as those paths come online.
- **`data/catalog/artifacts/{license_summary,security_assessment,storage_utilization}/`** contents deleted on the dev machine. Throwaway dev data per ADR 0002's "existing data not preserved" decision. The directory itself stays in place; the gitignored content is regenerated on first artifact write.

### Notes

- **`engagements` table is left alone.** Predates ADR 0002, empty, no code path inserts into it via app.db. Future cleanup can retire it; phase 1 keeps the migration tightly scoped.
- **Idempotency.** The migration runner already guarantees single-application via `schema_migrations` tracking. The ALTER statements (which SQLite doesn't support `IF NOT EXISTS` on) are protected by that mechanism rather than per-statement guards. Verified by simulating a fresh DB then running migrations twice.
- **Application code is unchanged.** No reads against the new tables, no writes to the new storage paths. Phase 2 (`ArtifactStore` project-scoping) is the next session.

### Carry-forward for phase 2

Phase 2 adds a `project_context` parameter (or equivalent) to `ArtifactStore.save_artifact` and `load_latest_artifact`, threading the active project through the route → service → store path. The new on-disk layout is `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject_id>/...` for mutable state and `.../finalized/<N>/<subject_id>/...` for immutable snapshots. The canonical schema and source-building paths do not move.

---

## 2026-05-26 (ADR 0002: Customer and Project entities)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `0cff36c` (ADR), plus the wrap-up commit that publishes this entry.
**Test status:** 483 passing (unchanged — ADR session, no code).

ADR-only session. Records the design for first-class Customer and Project entities to support real consulting work — see `docs/adr/0002-customer-and-project-entities.md`. The architectural shape: customer is a first-class entity with rich configuration including CommCell details; project belongs to a customer; finalization is the data-retention unit (immutable per-project snapshots, kept forever); finalize is not a one-way trapdoor (a finalized project reloads its latest finalization for editing, and re-finalizing produces the next immutable snapshot); immutability is enforced at the application layer, not the file system. Multi-CommCell and multi-company-within-CommCell are explicitly out of scope for v1; existing dev artifacts are deleted by the migration rather than preserved.

The ADR is orthogonal to ADR 0001's source-building fork — system subjects still flow through `_legacy_builders`, the customer/project work changes *where* artifacts are stored and *which* artifact a builder reads, not *how* tile data is shaped.

### Carry-forward

Implementation is the next session. ADR 0003 (REST extractor with credentials) follows that one and builds on ADR 0002's storage paths.

---

## 2026-05-26 (housekeeping: gitignore app.db, README refresh)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `e58adca` (gitignore), `6d2daed` (README refresh).
**Test status:** 483 passing (unchanged).

Two priority-ordered backlog items cleared in one session — both as small as expected.

### Changed

- **`data/app.db` is now gitignored.** `git rm --cached data/app.db` untracks the file; the local copy stays on disk. Added entries for the WAL/SHM/journal sidecars too. On a fresh clone, `run_migrations()` (`src/cvhealthcheck/db/migrations/__init__.py:69`) runs at app startup (`web/app.py:13`, `mcp/server.py:59`) and produces the working schema from the four migration files. Migration `0003_report_inventory.sql` seeds the six system subjects plus their sources and section-instruction rows via `INSERT OR IGNORE`, so the Quick HC workspace renders correctly out of the box — no separate bootstrap mechanism needed. Verified by simulating a fresh DB; the `subjects` table comes back populated with `environment`, `license_summary`, `backup_job_summary`, `capacity_license`, `client_growth`, `security_assessment`.
- **README refresh.** Three edits, no new sections:
  - Test count line `298` → `483` (the "Session Validation" line had been stale across many sessions).
  - "Legacy detail-route behavior" block replaced — it still described the hyphenated `POST /quick-hc/<subject>/import` routes that session 4 deleted. Now correctly describes the unified `POST /quick-hc/<subject_id>/import` dispatch (with `upload_dispatch.py` wiring), the two surviving hyphenated `/collect` endpoints for SA/LS, and the GET redirects carrying `#subject=<id>` fragments.
  - Bottom "Pages:" list split into "Customer-facing" (`/`, `/quick-hc`, `/quick-hc/commcell`, `/quick-hc/report`) and "Internal / development" (everything else). The previous list mixed the two — `/` is customer-facing (redirects to `/quick-hc`), everything else is dev.

### Notes

- **AI-subject state is dev-machine.** The two `ai`-created subjects in current `data/app.db` (`cloud_storage_egress_ingress`, `storage_utilization`) are user-created via MCP `propose_new_subject` or AI import flows; they're not load-bearing for a fresh clone. Losing them on a wipe is acceptable behavior.
- **Tests are unaffected.** `tests/conftest.py:32` `migrated_db_path` fixture creates tmp-path DBs for every test; the real `data/app.db` is never touched by the test suite.
- **Deeper README staleness flagged but not fixed.** The Security Assessment section (around L270-278) lists "Latest persisted multi-source artifacts" paths under `data/imports/security_assessment/latest*.json` that no longer match the canonical-store layout. Out of scope for this refresh — separate session.

---

## 2026-05-26 (post-5b — server-side half of the Collect-position fix)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** the redirect-fragment commit that publishes this entry.
**Test status:** 483 passing (was 482; +1 new pin).

Server-side complement to `fecf68c` ("Preserve active subject across Collect's full-page reload via URL fragment"). The earlier client-side fix wrote `#subject=<id>` to the URL on every `openConfig()` — but Collect's full-page reload comes from a server-issued `Location: /quick-hc` redirect that doesn't carry the fragment, so on reload `_readSubjectFromHash` found nothing and the JS init defaulted to `environment` (CommCell Details). Confirmed by user after force-reload.

### Fixed

- **`src/cvhealthcheck/web/routes/quick_hc.py`** — added `_workspace_redirect(subject_id=None)` helper that returns `redirect(url_for("main.quick_hc") + "#subject=<subject_id>")` when `subject_id` is supplied, plain `redirect(url_for("main.quick_hc"))` otherwise. Wired into every subject-specific redirect site:
  - `quick_hc_security_assessment` (legacy GET) and `quick_hc_license_summary` (legacy GET) — the indirection through which the SA/LS collect handlers chain to the workspace. One line each.
  - `quick_hc_generic_collect` — all four redirect sites (no base URL, exception, errors, success) now carry the subject fragment. The "subject not found" site stays bare (the subject doesn't exist; preserving its id would be nonsensical).
  - `_unified_dispatcher_upload` — both redirect sites (no file selected, completion) carry the subject fragment so AI-subject uploads also land on the right tile.
  - The `_handle_system_upload` path (SA/LS uploads via the unified import route) inherits the fragment through the legacy GET chain — no direct change needed.
- **`quick_hc_delete_subject`** intentionally left unchanged. After delete, the subject doesn't exist; preserving the fragment for a non-existent subject would be incorrect — the JS would fall back to the default anyway.

### Added

- **`tests/test_core_solidity.py::test_subject_specific_redirects_carry_subject_fragment`** — pins the legacy GETs (which all subject-specific upload/collect chains route through). Asserts both legacy GETs redirect to `/quick-hc#subject=<id>`.

### Notes

- **Existing test assertions safe.** All test redirect-location checks use `"/quick-hc" in response.headers["Location"]` (substring match) — the fragment doesn't break them. The one `endswith("/quick-hc")` check is on the `quick_hc_delete_subject` redirect, which intentionally stays bare. No test updates needed.
- **Subject ID form.** Fragments use the underscored DB form (`security_assessment`, `license_summary`), matching the subject IDs `build_subject_initial_data` produces and the JS regex `/^#subject=(.+)$/` compares against. Not the hyphenated route form.

---

## 2026-05-26 (post-5b regression fix — source-provenance dispatch)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** the regression-fix commit that publishes this entry. (An earlier attempt at the same fix landed in `8dda62a` as a registry-level URL map; reverted in favor of this dispatch approach.)
**Test status:** 482 passing (was 477; +5 new tests across `test_source_provenance_dispatch.py` and `test_core_solidity.py`).

Fix for a workspace-tile regression introduced by `db87676` ("Retire legacy Quick HC detail pages"). The License Summary and Security Assessment tiles were rendering REST / Reports Plus as "○ Not implemented" — REST collection was correctly implemented, but the source-building path that runs when a canonical artifact exists had no signal about it.

**This is the second seam between data-driven and hardcoded paths in this codebase — same architectural shape as session 5b's `upload_dispatch`.** Both subjects have behavior that doesn't fit the catalog-table model (upload has subject-specific import functions; collection has subject-specific REST services). Both seams are now resolved by a small `dict[str, callable]` keyed by `subject_id` in a dedicated dispatch module. If a third seam shows up, it should use the same pattern.

### Added

- **`src/cvhealthcheck/quickhc/source_provenance_dispatch.py`** — sibling to `upload_dispatch.py`. Contains `PROVENANCE_DISPATCH: dict[str, ProvenanceBuilder]` with two entries (`security_assessment`, `license_summary`) pointing at the existing `build_security_assessment_provenance` / `build_license_summary_provenance` functions in `source_provenance.py`. The `get_provenance_builder(subject_id)` helper is the consumption interface for `_build_generic_sources`.
- **`tests/test_source_provenance_dispatch.py`** — 4 tests: SA wiring, LS wiring, unknown-subject returns None, keys-pin asserting exactly 2 entries.
- **`tests/test_core_solidity.py::test_dispatched_subjects_rest_source_shows_validated_with_collect_action`** — integration pin. Saves canonical artifacts for SA and LS to a tmp store, runs `build_subject_initial_data`, asserts both subjects' REST source has status="v" and a Collect action pointing at the expected hyphenated route.

### Changed

- **`src/cvhealthcheck/quickhc/subject_data_service.py::_build_generic_sources`** — consults the dispatch before falling through to the catalog-table logic. If a builder is registered, it's called with the subject's canonical-artifact dict (passed via the new `artifact_payload` parameter), and the resulting provenance items are adapted to the tile-source schema by `_provenance_to_tile_sources`. The adapter maps provenance source types (`rest_reports_plus`/`csv`/`html`) to tile source IDs, maps long-form status strings (`validated`/`available`/...) to the short codes the frontend consumes (`v`/`a`/...), and builds the action list (upload for CSV/HTML, collect for REST with the dedicated hyphenated route URL from `_DISPATCH_REST_COLLECT_URLS`).
- **`_build_generic_subject`** — calls `artifact.model_dump(mode="json")` on the canonical artifact (when present) and threads it through to `_build_generic_sources` as `artifact_payload`. Provenance builders tolerate the canonical-shape dict (they use `.get()` with defaults; their status strings are hardcoded), so no shape adapter is needed at this boundary.

### Notes

- **Root cause was the retirement of dedicated detail pages.** Before commit `db87676`, the `quick_hc_security_assessment` and `quick_hc_license_summary` GET handlers called `build_security_assessment_provenance()` / `build_license_summary_provenance()` directly to produce their source lists. Those handlers became redirects to `/quick-hc`; the provenance builders went dead, and the workspace tile path took over with no equivalent wiring. This fix restores the connection through a dispatch module rather than a re-coupled call site.
- **Collect URL hyphenation.** The dedicated SA/LS routes use hyphenated paths (`/quick-hc/security-assessment/collect`, `/quick-hc/license-summary/collect`) — these are the canonical names; tests, route decorators, and the new `_DISPATCH_REST_COLLECT_URLS` constant all agree. The frontend (`quick_hc.js:371`) consumes whatever `collectUrl` the server emits, so there's no URL mismatch in the UI.
- **Snapshot test passes unchanged.** The `_isolate_canonical_stores` fixture in `conftest.py` redirects the canonical store to a tmp dir, so the snapshot's render path never reaches `_build_generic_subject` for SA/LS — it goes through the legacy builders (`_build_security_assessment_subject` / `_build_license_summary_subject`), which set their own source statuses and aren't touched by this fix. The bug only manifests when a canonical artifact exists (the production state).
- **Legacy builder paths unchanged.** `_build_security_assessment_subject` / `_build_license_summary_subject` still own the no-canonical-artifact paths and continue producing their own source lists. Bringing them onto the dispatch would be a refactor, not a wiring fix; out of scope here.
- **δ → β migration path stays clean.** Same rationale as `upload_dispatch.py`: if the set of dispatched subjects grows enough that the in-Python dict becomes painful, the migration unit is the builder function, not the dispatch shape. See `docs/refactor_unified_upload_session_5a_design.md` Section 6.

---

## 2026-05-26 (session 5b)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `d04640d` (step 1 — dispatch module + tests), `ae58c21` (step 2 — route handler reads from the module, FIXME tags retired), plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (up from 472; +5 dispatch tests added in step 1, ±0 in step 2).

Session 5b — implements Option δ from the session 5a design. **The unified-upload refactor is now complete.** All three `FIXME(refactor-unified-upload-session-5)` tags are retired.

### Added

- **`src/cvhealthcheck/web/routes/upload_dispatch.py`** — data-only module containing the `UploadHandler` frozen dataclass and the `UPLOAD_HANDLERS: dict[str, UploadHandler]` lookup table. Two entries today: `security_assessment` and `license_summary`. Each handler bundles the five subject-specific behaviors the route needs (form field name, import function reference, error class, success-message format function, redirect endpoint). No Flask imports — the route handler is the only consumer.
- **`tests/test_upload_dispatch.py`** — 5 tests covering the SA handler wiring, the LS handler wiring, AI subjects returning `None` from `get_handler`, unknown subjects returning `None`, and a keys-pin asserting `UPLOAD_HANDLERS` has exactly the two known entries.

### Changed

- **`quick_hc_subject_import`** rewritten as a four-line dispatch: look up the subject in the db (404 if unknown), look up the subject_id in `UPLOAD_HANDLERS`, run `_handle_system_upload(handler)` if a handler exists, otherwise either 404 (system subjects with no handler entry) or fall through to `_unified_dispatcher_upload` (AI/user subjects). The hard-coded `if subject_id == "security_assessment"` / `if subject_id == "license_summary"` branches are gone.
- **`_handle_system_upload(handler: UploadHandler)`** — single new function consuming a handler. Reads the form file under the handler's form-field name, calls the handler's import function, catches the handler's error class for known failures (flashes `str(exc)`), catches `Exception` for unexpected failures (flashes `"Import failed: {exc}"` — note: the subject-specific prefix "Security Assessment import failed" / "License Summary import failed" is replaced by the generic phrasing, since the subject is already implied by the redirect destination and no test asserted on the old prefix), flashes the handler's success-format text on success, and redirects to the handler's endpoint.

### Removed

- **`_unified_security_assessment_upload`** in `quick_hc.py` — its job is now done by `_handle_system_upload` reading the SA handler.
- **`_unified_license_summary_upload`** in `quick_hc.py` — same. Note: the explicit extension pre-check (`if suffix not in LICENSE_SUMMARY_UPLOAD_EXTENSIONS`) is dropped; the importer itself already raises `LicenseSummaryImportError("Unsupported file type. Upload a License Summary CSV or HTML export.")` for the same case, which the handler's `error_class` catch translates into the same flash text.
- **All 3 `FIXME(refactor-unified-upload-session-5)` tags** in `quick_hc.py` — the data-driven dispatch they pointed at now exists.
- **Dead imports in `quick_hc.py`:** `LICENSE_SUMMARY_UPLOAD_EXTENSIONS`, `import_security_assessment_upload`, `import_license_summary_upload`. `SecurityAssessmentImportError` and `LicenseSummaryImportError` stay — the REST collect routes still raise them.

### Notes

- **The refactor is complete.** Sessions 1 (template wiring), 2 (unified-route shim with FIXMEs in place), 3 (dispatcher hardening), 3b (stop-and-report inventory), 3c (ADR 0001), 4 (old-route deletion), 5a (design proposal), 5b (data-driven dispatch). The dispatch smell that the FIXMEs marked is resolved. `POST /quick-hc/<subject_id>/import` is the sole upload path; the route handler is a four-line dispatch; subject-specific behavior lives in the dispatch module's data and in the importer functions themselves.
- **Option δ vs the alternatives.** The dict-based approach added 5 tests and ~120 lines of well-named data; a schema migration (Option β) would have added ~50 lines of SQL + Python plus a `propose_new_subject` change for two subjects with three differing fields each. The δ → β migration path stays clean — `UploadHandler` fields are typed scalars that map naturally to SQL columns if the set of upload-special subjects grows.
- **No behavior change from the user's perspective.** The route accepts the same form-field names, redirects to the same endpoints, returns the same 404s, and produces the same artifacts. The flash for unexpected exceptions reads "Import failed: ..." instead of "Security Assessment import failed: ..." / "License Summary import failed: ..." — no test exercised that exact prefix.
- **Snapshot test passes.** No source-building code was touched.
- **3 FIXME tags retired.** `grep -rn "FIXME(refactor-unified-upload-session-5)" src/ tests/` returns zero hits.

### Carry-forward

The refactor is done. `HANDOVER.md` is rewritten to drop the refactor-state tracking and to promote the next backlog item — moving `data/app.db` out of git — as the single recommended next action. Earlier session-6 candidates (the `TileDefinition.import_url=` dead data at `registry.py:131, 205`, the legacy `/security-assessment` dev page, the README test-count refresh) stay as smaller follow-ups.

---

## 2026-05-26 (session 5a)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `062ebcf`, plus the wrap-up commit that publishes this entry.
**Test status:** 472 passing (unchanged — investigation only).

Session 5a — investigation session for the dispatch smell that the three `FIXME(refactor-unified-upload-session-5)` tags mark.

### Added

- **`docs/refactor_unified_upload_session_5a_design.md`** — 7-section design proposal. Section 1 inventories the dispatch sites and the contract table. Section 2 narrows the "data the dispatch needs" set from the FIXME's six speculative dimensions down to three actual ones. Sections 3-6 evaluate four data-model options (α JSON column / β typed columns / γ separate table / δ Python lookup) against the dispatch contract, the AI-proposal workflow, and migration mechanics. Section 7 makes the recommendation.

### Notes

- **Headline recommendation:** Option δ (Python lookup table). The smell is smaller than the FIXMEs implied — only three fields differ between the SA and LS branches, and a `dict[str, _UploadHandler]` resolves both the duplication and the dispatch branching in one move. No schema migration, no `propose_new_subject` change, no new column.
- **The FIXME tag text said "likely a new column on `subjects`"** — that was suggestive when the tags were written in session 2, not prescriptive. The actual smell (subject-specific branching in route-handler code) is fully resolved by δ; database-stored alternatives are over-engineered for two subjects with three fields each. If a future AI subject needs custom upload behavior that can't be expressed in a code-side dict, δ → β is a one-session migration.
- **No code changes this session.** Test count 472 unchanged. 3 FIXME tags still in place (they remain until session 5b implements the recommendation).
- **ADR 0001 stays untouched.** The upload-special subjects (SA, LS) are a strict subset of the source-building-special subjects (the six in `_legacy_builders`), but unifying them would re-open the question ADR 0001 closed. Session 5b's data model is upload-only.

### Carry-forward for session 5b

Session 5b implements Option δ (or whichever option the user picks after review). Estimated work: define `_UploadHandler` dataclass, populate `_SYSTEM_UPLOAD_HANDLERS` dict with the 2 entries, write one `_handle_system_upload` function that consumes a handler, rewrite `quick_hc_subject_import` to use the lookup, delete `_unified_security_assessment_upload` / `_unified_license_summary_upload`, remove the 3 FIXME tags, add a parametrised test, update docstrings. One session, modest test-count delta (+1).

---

## 2026-06-05

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `c06309d`, `b873431` (step 2 split — the first commit landed only the template deletion because a `git add` invocation died silently on the already-deleted path; the second commit landed the route bodies and comment updates). `6e0b1ed` (step 3 test cleanup). Plus the wrap-up commit that publishes this entry.
**Test status:** 472 passing (down from 477; -5 route-coupled tests deleted).

Session 4 of the unified-upload refactor — **the old upload routes are deleted.** Only the unified route `POST /quick-hc/<subject_id>/import` remains.

### Removed

- **`POST /quick-hc/security-assessment/import`** — handler `quick_hc_security_assessment_import` deleted from `src/cvhealthcheck/web/routes/quick_hc.py`.
- **`POST /quick-hc/license-summary/import`** — handler `quick_hc_license_summary_import` deleted.
- **`GET, POST /quick-hc/import`** — handler `quick_hc_generic_import` deleted (the multi-purpose old generic route, including its `?subject_id=`, `?stage=1`, and `X-Inline: 1` features).
- **`src/cvhealthcheck/web/templates/quick_hc_import.html`** — template only used by the GET branch of the deleted generic route.
- **5 route-coupled tests deleted** (per investigation report Section 5 categorisation):
  - `tests/test_recognition.py::test_import_route_{direct_save,staged,unrecognized,not_extractable}` — exercised behavior specific to the deleted generic route (recognition-from-payload without an explicit subject_id in the URL). The dispatcher's recognition + extractability mechanics remain covered by the unit tests in `test_recognition.py` (`test_recognize_*`, `test_dispatcher_*`) which exercise `extract_file` directly without going through any HTTP route.
  - `tests/test_import_flow.py::test_import_route_passes_subject_id` — exercised the deleted generic route's `?subject_id=` query-string handling. The unified route always has `subject_id` in the URL path; no equivalent test needed.

### Changed

- **`_unified_dispatcher_upload` redirect target.** Previously `url_for("main.quick_hc_generic_import")` (the deleted route) to be byte-equivalent with the old generic route's "redirect to self after upload" pattern. Now `url_for("main.quick_hc")` — the natural landing after a Quick HC upload. The docstring on `_unified_dispatcher_upload` documents this behavior change.
- **3 URL-coupled tests updated** to point at the unified URL (was the deleted hyphenated form):
  - `tests/test_security_assessment_import.py::test_quick_hc_security_assessment_upload_imports_html_and_redirects`
  - `tests/test_license_summary_web.py::test_quick_hc_license_summary_upload_imports_csv_and_redirects`
  - `tests/test_license_summary_web.py::test_quick_hc_license_summary_upload_rejects_unsupported_type`
- **3 parity tests in `tests/test_unified_upload_route.py` updated** to drop the OLD-route POST half (the OLD route no longer exists to compare against). Each test now POSTs only to the unified route and asserts directly on the outcome. `test_unified_route_ai_branch_produces_same_artifact_as_old_route` renamed to `test_unified_route_ai_branch_saves_artifact` since it no longer tests parity.
- **Module docstring** in `test_unified_upload_route.py` updated to reflect session-4 state.
- **Docstrings on `quick_hc_subject_import`, `_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`** rewritten to describe behavior directly instead of as "mirror of <deleted route>".
- **`subject_data_service.py:170` comment** about "legacy aliases until session 4 deletes them" updated. `_SA_IMPORT_URL` / `_LS_IMPORT_URL` header comment also updated.

### Notes

- **Step 1 pre-deletion grep surfaced one critical not-quite-production issue:** the `_unified_dispatcher_upload` helper had two `url_for("main.quick_hc_generic_import")` calls (inside the no-file-selected branch and the after-completion fallthrough). These would have failed at request time once the generic route was deleted, but they weren't user-facing references — they were inside the unified route's helper that was specifically designed to be byte-equivalent with the old generic route in session 2. Fixed both to redirect to `main.quick_hc`.
- **Two dead-data sites NOT touched (out of session 4 scope):** `src/cvhealthcheck/quickhc/registry.py:131, 205` hold `TileDefinition.import_url=` with the OLD hyphenated URLs. The field has been unread since session 2 deleted `canonical_view._build_sources` (its sole consumer). These can be removed in a future cleanup pass; not session 4's scope.
- **`src/cv_healthcheck.egg-info/PKG-INFO`** mentions the deleted URLs ("POST /quick-hc/security-assessment/import remains active"). Built artifact; regenerated on next build. Not edited.
- **Historical references in `docs/refactor_unified_upload_2026-05-31.md`, `docs/refactor_unified_upload_session_3b_inventory.md`, and `docs/adr/0001-source-building-fork.md`** — left untouched. These are records of what was once true and should remain accurate to the moment they were written.
- **Source-building fork still in place** per ADR 0001. Not reopened. `_legacy_builders` and the AI/system dispatch in `build_subject_initial_data` continue to function as documented.
- **Snapshot test passes** (frontend was already on the unified URLs since session 3 step 3; this session only deleted route handlers, no source-building change).
- **3 `FIXME(refactor-unified-upload-session-5)` tags** unchanged at the dispatch sites in `quick_hc.py`. They mark the branch-dispatch smell — session 5's target, not session 4's.

### Carry-forward for session 5

The unified route is now the sole upload path. Session 5 replaces the branch dispatch (which currently hard-codes `security_assessment` and `license_summary` sub-branches in `quick_hc_subject_import`) with data-driven dispatch — likely a new column or JSON field on the `subjects` table describing each subject's upload behavior (form-field name, allowed extensions, success-message format, persist function reference).

---

## 2026-06-04

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `c7a1a12`, plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (unchanged from session 3b).

Session 3c — short wrap-up session that closes out the source-building unification question. No code changes beyond comments.

### Added

- **`docs/adr/0001-source-building-fork.md`** — Architecture decision record for the γ4 outcome. The upload routing path is unified (`POST /quick-hc/<subject_id>/import` handles all subjects); the source-building path is intentionally not unified (`_legacy_builders` continues to serve the six system subjects whose view shapes the canonical schema can't represent). Full reasoning: alternatives considered (γ1/γ2/γ3 rejected), consequences (both preserved goals and accepted tradeoffs), references to the session 3 + 3b CHANGELOG entries and investigation reports, and revisit triggers (when to reopen).
- **`docs/adr/README.md`** — Sets up the ADR directory. Documents what an ADR is, when to add one, the required sections, and how to read existing ADRs from code annotations.

### Changed

- **In-code annotations in `src/cvhealthcheck/quickhc/subject_data_service.py`** at three sites pointing at ADR 0001:
  - The dispatch block inside `build_subject_initial_data` (around line 94 — comment above the `_load_from_canonical_store` call).
  - The `_legacy_loaders` function definition (around line 299).
  - The `_legacy_builders` function definition (around line 324).

  Each annotation is short (4-6 lines): a one-line pointer to the ADR plus the minimum context to understand why the fork is intentional. The detail lives in the ADR.

### Notes

- **γ4 decision rationale**: the canonical schema is frozen, and the legacy tile data uses section shapes (`counters`, `findings_grid`, `workload`, `chart_growth`) the schema can't carry. Sessions 3 and 3b both hit this wall. γ4 accepts the fork as honest reflection of two genuinely different shapes of tile data, not technical debt.
- **The annotations short-circuit re-derivation.** Without them, the next session that wonders why `_legacy_builders` still exists would repeat sessions 3 and 3b's investigation from scratch. The pattern is: comment in code → ADR → done.
- **Sessions 4 and 5 are unblocked.** Session 4 deletes the old upload routes. Session 5 replaces the unified route's branch-dispatch shim with data-driven dispatch. Both are independent of the source-building fork.

---

## 2026-06-03

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `11df86c`, plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (unchanged from session 3).

Session 3b of the unified-upload refactor — **STOP-and-report at the architectural assessment stage.** No code changes. One docs commit. The brief's Option γ plan cannot land cleanly without a companion architectural decision that the user needs to make.

### What happened

The session-3b brief was Option γ from the 2026-06-02 HANDOVER: move legacy on-disk reads into a fallback inside `_load_from_canonical_store`, return `CanonicalArtifact`, let `_build_generic_subject` render. Then delete `_legacy_builders` cleanly.

Before writing the adapter, I traced the legacy builder output vs. what `_build_generic_subject` + `artifact_to_view` would produce given a `CanonicalArtifact`. They diverge significantly:

- Legacy SA produces `counters` and `findings_grid` section types. The generic view producer doesn't.
- Legacy LS produces a `workload` section type. The generic view producer doesn't.
- Legacy CG produces a `chart_growth` section type. The generic view producer doesn't.
- Even simple subjects (environment) diff on subject-level fields the generic path doesn't synthesise: subtitle, fullUrl, per-source meta/status.
- The canonical schema is frozen, so we can't add these section types.

Per the brief's STOP-and-report rule, this session stopped at the inventory + architectural finding stage rather than writing an adapter that would produce the same proof 200 lines later.

### Inventory of legacy on-disk reads

Full inventory in `docs/refactor_unified_upload_session_3b_inventory.md` (Section A). Six file-based reads:

- `environment` → `data/catalog/rest/commserv.json`
- `security_assessment` → `data/catalog/security_assessment/latest.json` (via the SA service)
- `license_summary` → `data/catalog/license_summary/latest.json` (via the LS service)
- `client_growth` → `data/catalog/metrics/{client_count_history,client_growth_summary,client_growth_details}.json`
- `capacity_license` → `data/catalog/metrics/capacity_license_usage.json`
- `backup_job_summary` → `data/catalog/quickhc/backup_job_summary_latest.json`

### Four options forward

Documented in detail in the docs commit. Summary:

- **γ1** — Restore per-subject view producers in `canonical_view.py` (`security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view`). Make `artifact_to_view` dispatch by `artifact_type`. Then delete `_legacy_builders`. Largest scope; cleanest end state with the canonical schema intact.
- **γ2** — Accept the regression: delete `_legacy_builders`, all subjects render via the generic view producer, lose `counters`/`findings_grid`/`workload`/`chart_growth` shapes. Smallest end state; meaningful visible UX change.
- **γ3** — Extend the canonical schema with new section types. Violates "schema is frozen" rule, large blast radius.
- **γ4** — Hold position. Don't unify source-building further. Sessions 4-5 (route deletion + data-driven dispatch) proceed independently. The source-building stays split (`_legacy_builders` lives, alongside `_build_generic_subject`).

### Notes

- **No code changes this session.** Test count unchanged at 477.
- **FIXME tags intact.** `grep -rn "FIXME(refactor-unified-upload-session-5)" src/` returns the same 3 hits in `quick_hc.py`.
- **The unified upload route is still live and tested** (from session 2). The frontend uses the new URLs (from session 3). The architectural blocker is specifically the source-building unification half of the refactor, not the route half.
- **This is the second time the source-building unification has hit an architectural wall.** Session 3 hit "deleting `_legacy_builders` loses access to legacy on-disk file data." Session 3b hit "the canonical schema can't carry subject-specific view shapes." Both walls are real; both reflect the legacy builders doing two distinct jobs (file reading + view synthesis) that the architecture has implicitly bundled together for years.
- **Sessions 4 and 5 can still proceed if option γ4 is picked.** The unified upload route exists, the URL flip happened, the FIXME branch dispatch can be replaced with data-driven dispatch independently of how source-building resolves.

---

## 2026-06-02

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `81ee0a8` (step 1 snapshot baseline), `389bc4d` (step 3 narrowed URL flip), plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (up from 476; +1 new snapshot test in step 1, 0 net in step 3).

Session 3 of the unified-upload refactor — **landed partially.** Steps 1 and 3 (narrowed) committed; steps 4, 5, and 6 deferred pending user decision on the architectural conflict surfaced in step 3.

### Added

- **`tests/test_subject_initial_data_snapshot.py`** + `tests/fixtures/subject_initial_data_snapshot.json` — pins `build_subject_initial_data()` output against the migrated test DB. Diffs print a readable unified-diff message and fail the test. Future sessions regenerate the fixture only when changes are confirmed intentional.

### Changed

- **Frontend now points at the unified `POST /quick-hc/<subject_id>/import` route.** Three places updated:
  - `_build_generic_sources` in `subject_data_service.py` now produces `f"/quick-hc/{subject_id}/import"` (was: `f"/quick-hc/import?subject_id={subject_id}"`).
  - `_SA_IMPORT_URL` in `subject_data_service.py` is now `/quick-hc/security_assessment/import` (was: `/quick-hc/security-assessment/import`).
  - `_LS_IMPORT_URL` in `subject_data_service.py` is now `/quick-hc/license_summary/import` (was: `/quick-hc/license-summary/import`).
- Three URL-coupled tests updated to match: `test_quick_hc_report.py:893-896` (assertions), `test_license_summary_web.py:100` (substring assertion broadened to accept either form), `test_import_flow.py:219` (assertion updated to path-component shape).

### Notes (step 2 finding — load-bearing)

**The investigation report's Section 3.3 prediction is confirmed by code reading.** Control flow in `build_subject_initial_data:91-103`:

```
artifact = _load_from_canonical_store(subject_id)
if artifact is not None:                       ← canonical hit:  _build_generic_subject
else:
    if legacy_builder is not None:             ← canonical miss + system: legacy_builder
    elif db is not None:                       ← canonical miss + AI:     _build_generic_subject(tile, None)
```

`_build_generic_subject` is the production path for two of three cases (canonical-hit and AI-subject-no-data). The legacy builders run ONLY for system subjects in the pre-first-import state. Once any successful import populates the canonical store for a subject, all subsequent page loads route through `_build_generic_subject`.

### Notes — the step-3 architectural conflict (STOP-and-report)

The brief's two constraints proved mutually exclusive:

1. **Delete `_legacy_builders`, route everything through `_build_generic_subject`.**
2. **Snapshot diff must be URL changes only — any other diff is a regression.**

Constraint (1) would produce sparse "nodata" tiles for all 6 system subjects in the pre-canonical-bootstrap state. The legacy builders' job is precisely to bridge from the file-based legacy artifacts (`data/catalog/rest/commserv.json`, `data/imports/security_assessment/latest.json`, `data/catalog/metrics/*.json`, `data/catalog/quickhc/backup_job_summary_latest.json`) into the view model. The canonical-store path through `_build_generic_subject(tile, None)` has no access to those file paths and produces empty `sections=[]`, `state="nodata"`, `subtitle="Not collected"`.

In production this matters less because after the first REST collect or upload, the canonical store has data. But:
  - The test environment was capturing rich output because dev-machine state in `data/` was leaking into tests.
  - More importantly, real deployments WITH stale legacy files (e.g. dev machines, anyone who upgraded from before the canonical store existed) would see the rich → sparse degradation immediately.

Per the brief's explicit STOP-and-report rule when conflicts surface, **session 3 was narrowed**: URL changes landed; legacy builders kept alive. Steps 4 (retire `write_legacy`), 5 (verify FIXME tags), and 6 (full wrap-up) were not executed.

### What still needs to happen (carried to next session)

The path forward depends on a user decision. The three options:

1. **Accept the pre-canonical-import regression.** Sunset the legacy file-based bootstrap. Update the snapshot to reflect the sparse output. Continue with full `_legacy_builders` deletion and steps 4-6 of the original session-3 brief.
2. **Write a one-way migration on startup.** Read each legacy file-based artifact, synthesise an equivalent `CanonicalArtifact`, write it to the canonical store. After the migration runs once, the canonical path produces rich output and the legacy builders genuinely become dead code that can be deleted without behavioral change.
3. **Keep a small bootstrap fallback inside `_load_from_canonical_store`.** For each system subject, if the canonical store is empty, fall back to the legacy file-based loader and synthesise an artifact in-memory. This preserves the rich pre-import view without changing on-disk state. Subject-specific knowledge stays in one place (the fallback function); future sessions can incrementally migrate each subject's bootstrap to a real canonical write.

The next HANDOVER recommends option 3 as the lowest-blast-radius path, but the choice is the user's.

### Carried forward unchanged

- The unified `POST /quick-hc/<subject_id>/import` route (landed in session 2 / commit `dff43f1`) is still alive and tested. Its three `FIXME(refactor-unified-upload-session-5)` tags are still in place.
- The old per-subject and generic upload routes are still alive. Session 4 deletes them — but only after step 3 / steps 4 are completed properly.
- The `write_legacy=True` default on both persist functions remains in place. Option A's regression tests still pin the post-refactor contract.

---

## 2026-06-01

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `dff43f1`, plus the wrap-up commit that publishes this entry.
**Test status:** 476 passing (up from 469; +7 new tests in `tests/test_unified_upload_route.py`).

Session 2 of the unified-upload-route refactor (see `docs/refactor_unified_upload_2026-05-31.md` for the full plan).

### Added

- **`POST /quick-hc/<subject_id>/import`** — the unified upload route. Lives alongside the existing per-subject (`/quick-hc/security-assessment/import`, `/quick-hc/license-summary/import`) and generic (`/quick-hc/import?subject_id=…`) routes. Dispatches by `subjects.created_by`:
  - Unknown subject_id → 404.
  - `created_by == 'system'`: sub-branches by subject_id. `'security_assessment'` and `'license_summary'` mirror their existing per-subject route bodies; any other system subject → 404 (the other four are REST/metrics-only).
  - `created_by == 'ai'` / `'user'` / other → mirrors the existing generic route, including X-Inline JSON mode, ?stage=1 staging routing, and three-way error reporting.
- **Three private helpers** in `quick_hc.py` — `_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`. Each is a deliberate body-duplicate of the matching old route. Docstrings call out the duplication and point at the session-5/6 collapse.
- **`tests/test_unified_upload_route.py`** — 7 new tests covering every dispatch branch (see commit `dff43f1` for the per-test breakdown). Includes the License Summary Option A regression test that the 2026-05-27 HANDOVER flagged as missing.

### Removed

- **`canonical_view._build_sources`** — confirmed unreachable from production. Its only callers were `security_assessment_to_view` and `license_summary_to_view`, both only reached via dead try-blocks inside the legacy builders in `subject_data_service.py:480-486` and `:735-741`. The dead try-blocks themselves are NOT touched here — that's session 3 work alongside the rest of the source-building unification.
- **`canonical_view._IMPORT_FIELDS`, `_IMPORT_ACCEPT`, `_SOURCE_DEFAULT_STATUS`** — private constants used only by the deleted `_build_sources`.

### Changed

- `security_assessment_to_view` and `license_summary_to_view` now return `"sources": []` instead of calling `_build_sources(...)`. Reachability of these view functions themselves is also dead in production; their `sources` field was never asserted on by any test.

### Notes

- **The dispatch in the new route is an architectural smell.** Branching by `subjects.created_by` and sub-branching by hard-coded subject IDs (security_assessment / license_summary) embeds subject-specific knowledge in route-handler code — which is exactly what the refactor exists to eliminate. The choice was deliberate: keep session 2 small and obvious, defer the data-model question. Every dispatch line carries a `# FIXME(refactor-unified-upload-session-5)` tag so future grep finds them. Session 5/6 replaces the branch dispatch with data-driven dispatch — likely a new column on `subjects` describing import behavior (form-field name, allowed extensions, success-message format, persist function). **Do NOT** add an intermediate abstraction (registry of hooks, plugin system, etc.) before session 5/6 — that would lock in the data-model choice prematurely.
- **The three handler bodies (`_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`) are byte-equivalent to their old counterparts.** Edits to one must be mirrored to the other until session 5/6 collapses them. The docstrings say this.
- **Old routes still work, frontend still uses them.** This was the safety boundary for session 2. The frontend flip happens in session 3.
- **License Summary now has an Option A regression test.** The 2026-05-27 HANDOVER's "Context the next session needs" flagged its absence; landing it via the new route was a natural side-quest because session 2 touches the LS import path anyway.
- **The verification report's "production-vs-test divergence" concern (Section 3 of `docs/refactor_unified_upload_2026-05-31.md`) is still open.** I did NOT run an actual end-to-end import through the running server this session. The new route exists and tests pass, but the old generic-route-via-canonical-artifact path that the report flagged has not been exercised against a real running app. Session 3 will need to verify this before session 4 deletes the old URLs.

---

## 2026-05-30

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `20be561`, plus the wrap-up commit that publishes this entry.
**Test status:** 469 passing (up from 468; +1 new test).

### Added

- **`GET /quick-hc/settings` route** in `src/cvhealthcheck/web/routes/quick_hc.py`. Anonymous-reachable (no `@login_required`) so signed-out users can still reset their preferences.
- **`templates/quick_hc_settings.html`** — placeholder Settings page. Standalone (does not extend `base.html`); reuses `quick_hc.css` for design tokens. Inline JS inspects the two localStorage keys and the "Reset local preferences" button clears them and reloads.
- **"Settings" sidebar nav link** in `templates/quick_hc.html` between Reports and Staging, using the existing `lnav-item` class.
- `tests/test_settings_route.py` — one smoke test asserting 200 + presence of "Settings" heading + both localStorage key names in the response body.

### Notes

- **The Quick HC UX queue now has one item remaining**: remove the old `/quick-hc/import` generic upload route. That is the next session's single recommended next action.
- **`lnav-item` is the correct nav class name**, not `left-nav-item` as the 2026-05-29 HANDOVER sketch suggested. Verified before writing. The earlier HANDOVER was approximate — the verify-before-write step in the workflow paid off again.
- **The Settings page does not extend a base template** because `quick_hc.html` itself is standalone (it pre-dates the consolidation around `base.html` for the older Flask surfaces). For consistency with the dark UI, the settings page mirrors quick_hc.html's `<head>` (theme bootstrap + `quick_hc.css` import) and adds page-specific layout in an inline `<style>` block. If a future change introduces a Quick-HC-level base template, the settings page should adopt it.
- **localStorage key inventory** is currently exactly two keys: `quickhc-theme-v1` (theme toggle, written by `base.html` and `quick_hc.html`) and `quickhc-state-v1` (report-composition state, written by `quick_hc.js`). No variants, no versioned siblings, no per-subject keys. If a future change adds a key, update `quick_hc_settings.html` so the Reset button clears it too — the inline comment in the template names every other file that touches these keys to make this easy.
- **No server-side preferences storage was added.** The Settings page is a placeholder so a future session has somewhere obvious to land things like default report sections, display density, or persisted report profiles.

---

## 2026-05-29

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `2a57cdf`, plus the wrap-up commit that publishes this entry.
**Test status:** 468 passing (up from 466; +2 new tests in `tests/test_api_auth_status.py`).

### Added

- **Connect modal sign-out branch** (`templates/quick_hc.html`). Modal body is now split into `#connect-modal-signin` (existing username/password form) and `#connect-modal-signout` (new). Sign-out branch shows "Signed in as `<user>`. Sign out?" plus a `#signout-error` div and a `#signout-submit` button. Modal title switches between "Connect to Commvault" and "Sign out of Commvault".
- **`SESSION_USERNAME_KEY`** in `auth/commvault_auth.py`. New `get_current_username()` helper. `set_current_token()` now accepts an optional `username=` kwarg.
- **`username` field on `/api/auth/status`** — `{"authenticated": <bool>, "username": <str | null>}`. Null for anonymous sessions and for legacy authenticated sessions created before this field existed.
- **`window.CURRENT_USERNAME`** in the page template alongside `window.IS_AUTHENTICATED`. Kept in sync by the polling fetch.
- **`submitSignOut()` in `quick_hc.js`** — POSTs to `/logout` with `redirect: 'manual'`, treats 2xx/3xx/opaqueredirect as success, clears `window.IS_AUTHENTICATED` + `window.CURRENT_USERNAME`, calls `_updateConnBadge()`, closes the modal. On failure, shows an inline error and leaves the modal open. Mirrors `submitConnect()`'s busy-state and error-display pattern exactly.
- New tests in `tests/test_api_auth_status.py`: authenticated-without-username (pins the legacy-session contract) and end-to-end sign-out (seeds session, POSTs `/logout`, asserts 302 → `/login`, asserts the status endpoint flips, asserts both session keys are gone).

### Changed

- `openConnectModal()` branches on `window.IS_AUTHENTICATED`. Sign-in branch focuses the username input as before; sign-out branch populates `#signout-username` from `window.CURRENT_USERNAME` and falls back to "this Commvault session" when unknown.
- `submitConnect()` now caches `window.CURRENT_USERNAME` on successful login so the next open of the modal shows the right name without waiting for the next polling fetch.
- `_updateConnBadge()`'s polling fetch updates `window.CURRENT_USERNAME` from the response. Network failure still leaves both `IS_AUTHENTICATED` and `CURRENT_USERNAME` in their last-known state.
- Both login call sites (`basic.py::login`, `quick_hc_api.py::api_login`) pass the username through to `set_current_token()`.
- `clear_current_token()` now also drops `SESSION_USERNAME_KEY`.

### Notes

- **`/logout` POST support was NOT added — it already existed.** `basic.py` declares `methods=["POST"]` and `base.html` already POSTs to it from the sidebar's user menu. The handover's worry about it being GET-only turned out to be unfounded; verified before changing anything.
- **No CSRF middleware in this app**, and no existing POST route uses a CSRF token (`/api/login` and the sidebar logout form both POST without one). `submitSignOut()` follows the same pattern. If CSRF protection is added in a future session, `/logout`, `/api/login`, the sidebar logout form, and the new sign-out fetch all need updating together.
- **`username` is gated on `authenticated` in `/api/auth/status`.** Even if a stale `SESSION_USERNAME_KEY` survives a half-cleared session, the endpoint surfaces `username: null` until the token is also valid. This avoids exposing a username for an effectively-anonymous session.
- **The signout branch shows "this Commvault session"** when `window.CURRENT_USERNAME` is null. This covers two real cases: legacy sessions created before `SESSION_USERNAME_KEY` existed, and sessions where the polling fetch has not yet populated the cache (rare — the template seeds it).
- **No CSRF tokens, no PDF export, no scoring engine** — all carried forward unchanged.

---

## 2026-05-28

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `489c970`, plus the wrap-up commit that publishes this entry.
**Test status:** 466 passing (up from 463; +3 new tests in a new file).

### Added

- **`GET /api/auth/status` endpoint** (`src/cvhealthcheck/web/routes/quick_hc_api.py`). Returns `{"authenticated": <bool>}`. Session read only — no Commvault round-trip. Used by the Quick HC connection badge to refresh state without reloading.
- **`_paintConnBadge(isAuth)`** — extracted from the old `_updateConnBadge()` to keep the DOM-write logic pure and testable.
- **`_startConnBadgePolling()`** in `quick_hc.js` — sets up a 60s `setInterval` plus a `window.focus` listener, both calling `_updateConnBadge`. Guarded by a module-level `_connBadgeIntervalId` so the interval cannot stack on repeated calls. Invoked once from the `// ── INIT ──` block.
- `tests/test_api_auth_status.py` — three tests covering unauthenticated, authenticated, and empty-token-treated-as-unauthenticated states.

### Changed

- **`_updateConnBadge()`** in `quick_hc.js` now (1) repaints synchronously from `window.IS_AUTHENTICATED` so the first paint is immediate, then (2) fetches `/api/auth/status` and updates both `window.IS_AUTHENTICATED` and the badge from the JSON. On fetch failure, the badge is left in its last-known state — a flaky network must not flip the user to "disconnected".
- The dead `avail = allSubjs().filter(s => s.state !== 'nodata').length` line in the old `_updateConnBadge()` was removed during the refactor; it was unused.

### Notes

- **Badge state precedence**: synchronous server-rendered initial value → asynchronous refresh from `/api/auth/status` → preserve last-known on network error. Documented inline at the top of the connection-badge section in `quick_hc.js`.
- **Sign-out flow is not yet wired up.** The badge `title` still says "click to sign out" when authenticated, but clicking the badge opens the connect modal in its sign-in form regardless of state. The modal sign-out branch is item 2 of the Quick HC UX queue and is the next recommended action — see `HANDOVER.md`.
- **No new endpoints invoked during tests.** The three new tests hit `/api/auth/status` directly via `client.test_client()`; they do not touch Commvault. Total run time for the new file is under 200ms.

---

## 2026-05-27

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `96c1281`, plus the wrap-up commit that publishes this entry.
**Test status:** 463 passing (up from 462; +1 regression test).

### Changed

- **Option A landed**: Security Assessment and License Summary imports no longer write to the legacy per-domain store (`data/catalog/<subject>/`). The canonical store (`data/catalog/artifacts/<subject>/`) is now the sole writer for new imports. Reads from the legacy store are intentionally preserved as fallback for any pre-existing on-disk artifacts.
- `persist_security_assessment_artifact()` and `persist_license_summary_artifact()` gained a `write_legacy: bool = True` parameter. When False, both the legacy file writes and the legacy SQLite registry insertion are skipped, and the function returns the in-memory artifact payload only. Default stays True so existing legacy-store-behavior tests continue to exercise their original path without modification.
- Production callers all pass `write_legacy=False`:
  - `security_assessment.service.import_security_assessment_upload`
  - `license_summary.service.LicenseSummaryService.collect_from_rest`
  - `license_summary.service.import_license_summary_upload`
  - `reportsplus.security_assessment.extract_security_assessment` (also stops depending on `artifact_paths` from the persist call and on the `load_active_security_assessment_artifact()` round-trip)
- `test_license_summary_service_collect_from_rest_persists_registry_artifact` renamed to `..._writes_canonical_only` and rewritten to assert canonical-only persistence plus a successful canonical load.
- `test_flask_upload_imports_html_and_redirects` / `test_flask_upload_imports_csv_and_redirects` now assert the **absence** of legacy `latest.json` / `latest_<source>.json` files after an upload. The legacy `/security-assessment` development page (which reads only legacy) can no longer render fresh-import data; Quick HC is the authoritative fresh-import read surface.

### Added

- `tests/test_security_assessment_import.py::test_fresh_security_assessment_import_creates_no_legacy_artifact_files` — pins the Option A contract end-to-end. A future change that reintroduces a legacy write will break this test on a fresh import.

### Notes

- **Why Option A and not Option B?** Option B would have one-way migrated existing legacy artifacts into the canonical store, then deleted the legacy code path. We picked A because it is reversible (revert this commit and writes resume), bounded (single focused commit, no startup-time migration to debug), and has no data loss. Option B remains available as a future cleanup if the legacy directories ever need to be purged automatically.
- **`ensure_schema()` may still create the legacy SQLite registry file on first read.** The fallback lookup path (`load_active_security_assessment_artifact`, `load_active_license_summary_artifact`) calls `registry.ensure_schema()` before checking for an active artifact, and that creates the empty `registry.sqlite3` file as a side effect. This is metadata, not an artifact, and the registry tables remain empty unless something explicitly writes — which production code no longer does. The regression test is narrowed to assert no new JSON artifact files, not no SQLite files, to reflect this contract precisely.
- **Legacy `/security-assessment` development page is now effectively read-only history.** It loads via `load_security_assessment_artifact()` → `SecurityAssessmentService.get_current()` → `load_active_security_assessment_artifact()` (legacy). Fresh imports no longer populate that path. The page will show "No Security Assessment artifact exists yet" after the first fresh import unless legacy `latest.json` already existed. This is acceptable; the page was a development/debug surface and Quick HC is the customer-facing one.
- **No SQL or schema changes.** This is purely a code-path change; no migrations were needed.

---

## 2026-05-26

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `b7d2f67`, plus the wrap-up commit that publishes this entry.
**Test status:** 462 passing (up from 461; +1 regression test).

### Fixed

- **Section ID double-prefix in `canonical_view`** (`src/cvhealthcheck/quickhc/canonical_view.py:116` and `:213`). The HTML extractor stores fully-qualified section IDs like `security_assessment.access_security`, and the view builders were rebuilding them as `f"{subject_id}.{sec.id}"` — producing `security_assessment.security_assessment.access_security`. Display titles were correct, but the doubled IDs leaked into the JS state, rendered DOM, and the `localStorage` key (`quickhc-state-v1`), silently breaking per-section include/exclude persistence and the report-composition round-trip. Both prefix sites now guard with `startswith(...)`.

### Added

- `test_sa_section_id_no_double_prefix_when_already_qualified` in `tests/test_quickhc_canonical_view.py` — pins the contract for both `artifact_to_view()` and `security_assessment_to_view()`. A future "normalise the extractor's section IDs to short form" change cannot silently reintroduce the bug.

### Removed

- `0003_report_inventory.sql` and `migrations.py` at project root — stale design-session leftovers, never tracked by git. `0003_report_inventory.sql` was byte-identical to `src/cvhealthcheck/db/migrations/0003_report_inventory.sql`. `migrations.py` differed only in stale ways (docstring referenced old filenames `0001_initial_schema.sql`/`0002_...`, and the path resolution assumed the file would live at `src/cvhealthcheck/db/migrations.py` rather than as the package `__init__.py`). Deleted from the working tree; no git commit needed since they were never tracked.

### Notes

- **Cleanup that produces no commit is still cleanup.** The two stale root files were never tracked by git — verified via `git log --all -- <file>` and `git ls-files <file>`, both returned empty. Deleting them is a working-tree-only operation. Future sessions cloning the repo would never have seen them; this benefited only the local working tree. A `.gitignore` entry to prevent recurrence felt arbitrary for two specific filenames; if the pattern recurs, consider a broader rule like "no `.sql` or top-level `.py` files at project root."

---

## 2026-05-25

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `9073f06`, `9edb2a8`, plus the wrap-up commit that publishes this consolidation.
**Test status:** 461 passing.

### Added

- Versioned SQL migration runner at `src/cvhealthcheck/db/migrations/__init__.py`. Migrations: `0001_initial`, `0002_staged_artifacts`, `0003_report_inventory`, `0004_rest_instructions_and_constraints`.
- `subjects` / `subject_sections` / `subject_sources` / `subject_section_sources` / `collector_schemas` tables seeded with the six system tiles.
- `src/cvhealthcheck/db/subjects.py` — CRUD for the subject catalog plus `create_subject_from_proposal()`.
- Generic extractor pipeline under `src/cvhealthcheck/extractors/` (`dispatcher`, `html`, `csv`, `rest`, `recognition`, `result_to_artifact`), driven by `subject_section_sources` instructions.
- `/quick-hc/import` generic upload endpoint routing through `extract_file()`.
- MCP staging workflow: `propose_new_subject` and `list_proposed_subjects` tools, plus subject-proposal handling in `execute_approval()`.
- Staging review UI at `/quick-hc/staging`.
- Quick HC standalone dark UI (`quick_hc.html` no longer extends `base.html`).
- `subject_data_service.build_subject_initial_data()` returning `{commcell, cats, report_url}`.
- ~14 new test modules: `core_solidity`, `db_staging`, `db_subjects`, `delete`, `extractor_csv`, `extractor_html`, `import_flow`, `mcp_tools`, `migrations`, `recognition`, `rest_extractor`, `staging_routes`.
- `CHANGELOG.md` (this file) — consolidated append-only history.
- `HANDOVER.md` (project root) — single forward-looking handover file, always overwritten.

### Changed

- `create_app()` runs `run_migrations()` instead of the deprecated `init_db()`.
- Quick HC sidebar reads subjects from the DB via `get_tiles(db)` instead of the static `QUICK_HC_TILES` tuple; AI-proposed subjects appear alongside system tiles.
- Quick HC connection badge: always shows `Connect` when unauthenticated and `Connected` when authenticated.
- Quick HC report action bar moved from the top of the main panel to the bottom; visible only when at least one subject is included.
- `canonical_view.artifact_to_view()` now uses `tile["title"]` from the registry for the sidebar display name, so stale `artifact.subject.title` provenance (e.g. "Test Subject") no longer leaks into the UI.
- HTML extractor section-title matching accepts both exact match and `"<title> -"` / `"<title>:"` prefix forms, so `"Other Licenses - current usage details"` matches the `"Other Licenses"` instruction.
- Documentation model consolidated to three files: `README.md` (what + how), `CHANGELOG.md` (backward-looking), `HANDOVER.md` (forward-looking). `DEVLOG.md` and `docs/handover/` retired.
- Test count rose from 343 to 461.

### Fixed

- **Test pollution.** `execute_approval()` was instantiating `ArtifactStore()` with the default base_dir, so `test_execute_approval_artifact` was overwriting the real `data/catalog/artifacts/security_assessment/latest.json` with its `_make_artifact()` fixture data (`title="Test Subject"`, section `id="test_section"`, finding `title="Test finding"`) on every `pytest` run. Added an optional `store` parameter to `execute_approval()`; the test now injects its `tmp_path` store. The user-visible symptom was a sidebar that kept reverting to "Test Subject" no matter how many times Security Assessment was imported.
- **License Summary "No data".** `canonical_view.license_summary_to_view` now accepts both short (`other_licenses`) and fully-qualified (`license_summary.other_licenses`) section IDs. Cause: the extractor was prefixing section IDs with the subject ID but the view was still looking up the short form.
- **Sidebar "ok"/"nodata" mismatch.** Table-only canonical artifacts with non-empty rows now resolve to `ArtifactStatus.good` instead of `unknown`. Previously a healthy License Summary import showed as "nodata".
- **Security Assessment HTML extractor.** Section title "Other Licenses" failed to match HTML titled "Other Licenses - current usage details". Added prefix-with-delimiter matching.
- **Connection badge "6 available".** Removed the dead `else if (avail > 0)` branch in `_updateConnBadge()` that was showing a misleading availability count instead of "Connect".

### Removed

- `DEVLOG.md` — content consolidated into this file under earlier dated entries.
- `docs/handover/` — `HANDOVER_2026-05-25.md` content folded into this entry; `report_inventory_context.md` content summarised in the 2026-05-24 entry.

### Notes

- **Section ID double-prefix is a known bug**, not yet fixed: `canonical_view.artifact_to_view()` builds `sec_id = f"{subject_id}.{sec.id}"` but the HTML extractor already stores fully-qualified IDs. Result: `security_assessment.security_assessment.access_security`. Display titles are correct; the mangled IDs leak into localStorage keys and break per-section include/exclude state across reloads. Fix lives in `canonical_view.py:116` and `:213` — guard with `if not sec.id.startswith(...)`. This is the single recommended next action — see `HANDOVER.md`.
- **Two artifact stores of truth.** Legacy `data/catalog/<subject>/latest.json` and canonical `data/catalog/artifacts/<subject>/latest.json` both exist; imports write both. The UI reads canonical. Decide whether to deprecate the legacy path or migrate it on startup.
- **Quick HC subject naming rule (load-bearing).** The sidebar/display name must come from the registry tile title (`tile["title"]`), not from `artifact.subject.title`. The override lives at `subject_data_service.py:213`. Do not remove it — it protects against stale provenance from prior imports.
- **`execute_approval()` requires an injected store in tests.** Pattern in `tests/test_core_solidity.py::test_execute_approval_artifact`. Without it, the test pollutes the real catalog.
- **Stale 955-byte test-pollution artifacts** in `data/catalog/artifacts/security_assessment/` from before the `execute_approval` fix. Inert (only `latest.json` is loaded). Clean with `find data/catalog/artifacts/security_assessment -size 955c -delete`.
- **Two root-level stale files**: `0003_report_inventory.sql` and `migrations.py` at the project root are leftover duplicates of the canonical copies under `src/cvhealthcheck/db/migrations/`. Safe to delete.
- **`data/app.db` is committed.** Should move to `.gitignore`; migrations recreate the schema on first run.

---

## 2026-05-24

**Test status:** 298 passing.

### Added

- `TileDefinition.category`, `category_label`, `import_url`, `collect_url` — category structure and action URLs are now first-class registry metadata.
- `quickhc/canonical_view.py` — translation layer from canonical artifacts into the Quick HC JS view-model contract.
- Canonical JSON API endpoints: `GET /api/security-assessment/canonical`, `GET /api/license-summary/canonical`.
- License Summary canonical adapter and canonical side-write support for both REST collection and file import.
- `data/app.db` — business/application state DB, separate from import registries and canonical artifact files.
- New raw-SQL `db/` package for customers and engagements.

### Changed

- Quick HC initial subject assembly moved to a registry-driven path via `quickhc.registry.list_tiles()` with explicit tile-id loader/builder dispatch in `subject_data_service.py`.
- Legacy Quick HC GET detail pages now redirect to `/quick-hc`; POST import/collect handlers remain active.

### Notes

- **Product structure direction** locked in: HealthCheck → Customers → Advanced → Development.
- **Legacy detail-route GET vs POST split**: `GET /quick-hc/security-assessment` and `GET /quick-hc/license-summary` redirect to `/quick-hc`; the corresponding `POST .../import` and `POST .../collect` endpoints remain active. This split is intentional — keeps the user-facing surface unified while preserving the existing automation contracts.
- **Five-layer architecture, settled this date**: (1) `subjects` + `subject_sections` = catalog/definition; (2) `subject_sources` + `subject_section_sources` = acquisition/extraction; (3) `staged_artifacts` = review/verification; (4) `ArtifactStore` / `latest.json` = approved canonical outputs; (5) compliance rules = future evaluation layer. `staged_artifacts` is the single staging mechanism for both AI subject proposals (`artifact_type='subject_proposal'`) and ingested artifacts (`artifact_type='artifact'`).
- **Constraints captured for the design brief that produced 2026-05-25's work**: Raw SQL only — no ORM. No Flask dependencies in adapter/registry/db layers. Additive-only schema changes. Pydantic v2 canonical schema v1 is frozen — do not change `artifacts/models.py`.

---

## 2026-05-23

### Changed

- Retired `/quick-hc/security-assessment` and `/quick-hc/license-summary` GET detail pages; both now redirect to `/quick-hc`.
- Updated `detail_endpoint` in the Quick HC registry and `_try_url` calls in `subject_data_service.py` to point at `main.quick_hc` directly.

### Removed

- `quick_hc_security_assessment.html` template.
- `license_summary.html` template.

---

## 2026-05-22

### Added

- Cross-tile regression guard that seeds all current Quick HC subjects and fails if the workspace-emitted section IDs diverge from the authoritative registry section IDs.

### Changed

- Registry made authoritative for the Security Assessment detail-view section set: summary, highlights, Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, Hardening.

### Removed

- `security_assessment.all_findings` from the user-facing registry contract. Kept as a compatibility alias inside the report service for older selection payloads.

### Notes

- **Section contract drift was the root cause.** Detail-view sections and customer-report sections had been edited independently and silently diverged. The new regression guard prevents this from happening again without a test change.

---

## 2026-05-20

### Added

- Quick HC source-provenance block, applied consistently to Backup Job Summary, License Summary, Security Assessment, CommCell, and metric-backed detail views. Unavailable / unimplemented / not-tested / not-applicable sources render as muted instead of being hidden.
- Backup Job Summary Quick HC tile, using the existing registry-driven tile platform and the Phase 1 normalized Reports Plus artifact (dataset GUID `2638c3d3-adc7-4b61-bb24-2ba509229bf5` + related GUID `ce01fc88-d2bd-46cc-ba41-1d967c7fa4a2`).
- Backup Job Summary collector foundation at `reportsplus/backup_job_summary.py` with normalization for total jobs, status buckets, protected client count, recent failures, and recent jobs. Persisted at `data/catalog/quickhc/backup_job_summary_latest.json`.
- `@login_required` on the three `/metrics/*` routes and two previously unprotected Reports Plus routes.
- Tile-contract helpers on `TileDefinition` so description and section/default-selection access stay registry-derived.
- Explicit preview-builder mapping in `quickhc/overview_service.py` keyed by each tile's `preview_renderer`.
- Explicit report-builder mapping in `quickhc/report_service.py` keyed by each tile's `report_renderer`.
- Quick HC overview preview orchestration moved out of `web/routes/shared.py` into `quickhc/overview_service.py`.
- Reusable Quick HC partials: `partials/quickhc_tile.html` (subject-card shell), `partials/quickhc_section_card.html` (section wrapper), and per-subject preview partials under `partials/quickhc/previews/`.
- Shared Quick HC dataclasses in `quickhc/models.py` and central tile registry in `quickhc/registry.py`.
- `tests/test_quickhc_registry.py` — locks down unique tile/section IDs, tile metadata completeness, per-tile section ownership, and alignment between registry-derived selection metadata and report-service constants.

### Changed

- `extract_security_assessment()` no longer persists unauthorized or failed report responses; validates auth/status before normalization.
- Replaced hardcoded Quick HC report detail URLs in `quickhc/report_service.py` with registry-authoritative `TileDefinition.detail_endpoint` resolution through `url_for()`.
- License Summary service's direct import of the Security Assessment registry replaced with a generic artifact-registry helper.

### Fixed

- Stale `message: "Not collected yet"` value in the available Client Growth report branch.

### Notes

- **Architectural boundary captured this date**: registry owns metadata, report service owns filtering/composition, routes stay thin, templates remain presentation-only. The Quick HC framework extraction milestone closes here for the current subject set.
- **Next phase**: controlled renderer orchestration through an explicit mapping layer — not direct dynamic Jinja template resolution.
- **Longer-term direction**: the Quick HC registry is intended to align with future MCP-driven and scheduled report orchestration. Same metadata, different surfaces.
- **Companion codebase review** captured in `docs/review_2026-05-20.md` — flagged `shared.py` god-module, `SecurityAssessmentArtifactRegistry` naming collision with License Summary, hardcoded detail URLs in `report_service.py`, CWD-relative catalog paths. Several items still open as of 2026-05-25.

---

## 2026-05-19

### Added

- `QuickHcReportService` assembling CommCell Details, Security Assessment, License Summary, Client Growth, and Capacity Licenses into one filtered report view model.
- Subject-level and section-level selection IDs so `/quick-hc/report` can render only the selected subjects and nested sections.
- Browser-side selection persistence with `localStorage` (key `quickhc-state-v1`). No server-side profiles.
- Customer-facing report rendering for Security Assessment counters/highlights, License Summary workload + detail sections, Client Growth summary/chart/table, and Capacity Licenses summary/table.
- License Summary compact usage visualization for workload and other-license rows, with `License not purchased` handling where capacity is zero.
- REST collection support on the Quick HC Security Assessment page and the Quick HC License Summary page (preserves upload/CSV/HTML import).
- Broad regression coverage for Quick HC overview rendering, section selection, default report rendering, Security Assessment import/collect flows, Client Growth chart output, License Summary usage rendering.

### Changed

- Quick HC promoted from a simple summary page into the main customer-facing report-composition surface.
- `/quick-hc` redesigned around expandable full-width subject tiles with previews, nested section cards, and parent include/exclude cascade.
- `start.sh` now stops any process already listening on port 5001 before starting Flask again.

### Notes

- **Customer-facing report exclusions, locked in**: no artifact paths, no dataset GUIDs, no HTTP status values, no raw/debug extraction metadata. Evidence and source metadata stay internal only.
- **Agent / Feature Licenses kept without progress-bar visuals** after validating that usage bars made that section noisier rather than clearer.

---

## 2026-05-18

### Added

- Basic Quick HC HTML report at `/quick-hc/report`. Assembly-only — loads current Security Assessment and License Summary artifacts through their service layers (no direct artifact-file reads in the route).
- `quickhc/report_service.py` building a combined report view model: environment identifiers, source metadata, timestamps, Security Assessment counters, License Summary summary counts.
- Explicit artifact version fields on Security Assessment and License Summary canonical models: `schema_version`, `artifact_version`, `collector_version`. Backward-compatible (defaults applied on load).
- License Summary canonical artifact extension: `workload_summary_sections[]` for category/workload summary tables (`Capacity Licenses`, `Operating Instance Licenses`, `Virtualization Licenses`, `User Licenses`, `Data Insights Licenses`, `Air Gap Protect Licenses`, summary-page `Other Licenses`).
- CSV multi-section parsing for License Summary (report title + generated timestamp metadata + independent section tables).
- HTML table parsing for License Summary by validated header shape.
- REST normalization for Reports Plus report 206 (License Summary) on top of the generic report extraction helper.
- XLSX API viewer recording import for offline REST-recorded evidence — no new dependency.
- Registry-backed artifact persistence and registry-first active artifact loading for `artifact_type=license_summary`.
- Masked registration-code handling in License Summary metadata (unmasked codes are never persisted).
- New `src/cvhealthcheck/license_summary/` package.

### Changed

- Flask route surface split into focused modules under `src/cvhealthcheck/web/routes/` (Quick HC, Security Assessment, development, metrics, Reports Plus). Organisational only; URLs and templates unchanged.
- `CV_VERIFY_SSL` now defaults to enabled (was disabled). Explicit warning logged when disabled.
- Quick HC License Summary page renders workload summary sections separately from detail tables.

### Notes

- **Missing-values policy for License Summary**: do not fabricate absent sections, do not guess `license_expiry`, render only sections that return real rows in the current CommCell.
- **Lab CommCell observation**: `Operating Instance Licenses`, `Data Insights Licenses`, and `Other Licenses` render from live REST. `Capacity Licenses` may be absent because the upstream dataset fails in this CommCell. `license_expiry` remains unset when report 206 does not return it.

---

## 2026-05-17

(Multiple consolidated entries from this date — see DEVLOG history before the consolidation if needed.)

### Added

- `src/cvhealthcheck/security_assessment/` package: `models.py`, `normalize.py`, `validate.py`, `artifact.py`, `registry.py`, `service.py`.
- Strict schema models for customer / CommCell / engagement / report stream / report run / import run / artifact record / canonical finding / Security Assessment artifact.
- SQLite artifact registry at `data/imports/security_assessment/artifact_registry.sqlite3`. Idempotent schema; `foreign_keys`, `busy_timeout`, `WAL` pragmas.
- Unique persisted artifact files per import/refresh, plus `latest.json` compatibility writes (`latest_rest.json`, `latest_html.json`, `latest_csv.json`).
- Service-layer read API: `SecurityAssessmentService.get_current()`, `get_history()`, `get_artifact()`.
- Historical retrieval by `artifact_id`, `import_run_id`, `report_run_id`, and latest-within-scope.
- Hidden/debug history and registry-export endpoints, login-gated.
- Internal registry viewer linked from the Development page.
- Retention/provenance metadata: `created_at`, `last_accessed_at`, `retention_policy`, `imported_by`, `import_method`, `source_metadata`.
- Browser HTML/CSV upload support in the Flask UI.
- Multi-source Security Assessment ingestion path: `collect → normalize → persist → render`.
- Source-specific persisted latest artifacts (`latest_rest.json`, `latest_html.json`, `latest_csv.json`) at `data/imports/security_assessment/`.

### Changed

- Active-artifact selection scoped by customer, CommCell, artifact type, source type, and engagement/report-stream context (was global by artifact type).
- Source activation/selection moved out of `normalize.py` into the registry/service layer.
- Invalid/noisy-finding filtering and deduplication moved to a dedicated validation layer.
- HTML/CSV import and REST refresh flows updated to register artifacts in SQLite while preserving existing UI behavior.

### Fixed

- HTML ingestion hardened against presentation-heavy report markup: strict table parsing validates `thead` and only extracts `tbody`/`tr`/`td`.
- Missing-active-artifact recovery: service now attempts to promote the newest recoverable artifact in the same scope before falling back to `latest.json`.
- Explicit fallback diagnostics — marks the path actually loaded when compatibility fallback is used.

### Notes

- **HTML exports are presentation-heavy** and cannot be treated as simple text-extraction inputs. Strict table parsing is required.
- **CSV exports are materially cleaner than HTML exports** and currently appear to be the more reliable offline import format.
- **Security Assessment has evolved** from single-source report extraction into multi-source canonical evidence ingestion. Multiple same-day report runs are now supported (`report_run_id`, `executed_at`, optional `run_sequence`).
- **Open question (still open as of 2026-05-25)**: imported HTML and CSV artifacts render correctly when REST is unavailable, but noisy text may still appear when the REST source is active. The remaining defect is most likely in REST/live source interaction, source precedence, or stale artifact selection — not in HTML/CSV parsing itself. Track this if you see it recur.

---

## 2026-05-15

### Added

- Reports Plus Security Assessment extraction for report 336. Endpoint pattern: `/commandcenter/api/cr/reportsplusengine/reports/336`, `/datasets/<guid>`, `/datasets/<guid>/data`.
- Normalized Security Assessment artifact at `data/catalog/reportsplus/report_336_security_assessment_normalized.json`.
- Reusable checklist-style normalization in `src/cvhealthcheck/reportsplus/checklist.py` — status values, unsafe-HTML stripping from remarks, safe action-link extraction.
- `/reportsplus/security-assessment` Development/debug view.
- Security Assessment tile in Quick HC at `/quick-hc/security-assessment`.
- Chart.js metric visualization pattern: route → server-side chart payload → `metric_detail.html` → Chart.js render. Applied to Client Count, Client Growth, Capacity License Usage.

### Notes

- **Discovered Security Assessment sections** (six): Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, Hardening.
- **Current artifact summary** at this date: 32 total checks, 2 Critical, 0 Warning, 18 Info, 12 Good.
- **`cv-topology` is reference-only** — confirmed. Do not refactor or modernize it as part of active cv-healthcheck work.

---

## 2026-05-14

### Added

- Phase 3.0 Quick HC Foundation begins.
- Reusable Quick HC CommCell Identity / Version collector for `GET /commandcenter/api/CommServ`.
- Normalized REST artifact at `data/catalog/rest/commserv.json`.
- `cv-healthcheck quickhc commcell` CLI command.
- Flask Quick HC pages at `/quick-hc` and `/quick-hc/commcell`.
- `PROMPT.txt` — durable project and AI guidance for future sessions.

### Notes

- **Live validation**: `/commandcenter/api/CommServ` with a Login-issued Authtoken returned HTTP 200 with `hostName`, nested `csGUID`, `csVersionInfo`, `releaseId`, `osType`, `timeZone`.
- **Quick HC kept read-only and acquisition-only** at this stage — no health scoring, rules, SQL, database, or S3 code.
- **Strategic operating model clarified**: Daily Reporting, Quick HealthCheck, Full HealthCheck. The central reporting platform must not assume direct reachability to customer CommServe systems; customer-side REST collectors will gather snapshots and upload evidence artifacts (S3 expected as future transport).

---

## 2026-05-13

### Added

- Focused metric extraction pipelines for the four high-value Report 318 datasets: Client Count, Client Growth Summary, Capacity License Usage, ClientGrowthDetails.
- Normalized local metric artifacts under `data/catalog/metrics/`.
- `/metrics/client-count`, `/metrics/client-growth`, `/metrics/capacity-license` pages.
- Normalized Report 318 metric inventory at `data/catalog/reportsplus/report_318_metric_inventory.json` — 30 classified datasets, returned columns, record counts, sample values, time ranges, usefulness labels, operational questions.
- `/reportsplus/report/318/metrics` review page.

### Notes

- **Report 318 dataset classification**: 10 capacity/growth, 3 client growth, 6 deduplication/compression, 5 storage usage, 6 low-value/unclear selector-style.
- **Useful metrics discovered**: client count + client growth monthly history (May 2025–May 2026), capacity license usage over the same period, client growth detail rollups.
- **Report 318 live extraction shape**: report definitions can live in `pages[].body` as JSON strings; widgets/datasets reference nested `dataSet` objects rather than a top-level `content` field. Adjust parsing accordingly.

---

## 2026-05-11

### Added

- Focused Reports Plus extraction workflow for Report 318.
- Local Report 318 artifacts under `data/catalog/reportsplus/`: metadata, definition, dataset mapping, execution summary, raw dataset execution results.
- `/reportsplus/report/318` inspection page (metadata, widgets, dataset mappings, execution status, sample rows).
- Flask login flow for Commvault authentication. Token-expiry handling clears session and redirects to login.
- Phase 2.4 lab readiness baseline. Readiness output at `data/labreadiness/latest.json`. `cv-healthcheck lab readiness`, JSON mode, `/lab-readiness` view.
- Phase 2.3 candidate validation by dataset execution. CLI + Flask views.
- Phase 2.2 Reports Plus catalog inspection and candidate prioritization. `health_candidate_priority.json` from generated report/dataset summaries.
- Phase 2.1 Reports Plus catalog persistence and analysis. Catalog CLI for reports, datasets, all-inventory.
- Reusable Reports Plus report and dataset inventory methods.
- CLI inventory commands with JSON, summary, and local catalog persistence.
- Flask pages for report inventory, report detail inspection, dataset inventory.
- `API_MAPPING.md` — source-centric capability catalog (separate from `HEALTHCHECK_MATRIX.md` which is the health-rule catalog).
- `scripts/probe_auth_matrix.sh` to compare `Authtoken` vs `Authorization: Bearer` across base API + Reports Plus endpoints.
- Initial standalone `cv-healthcheck` project — reusable Commvault API client, Reports Plus metadata + dataset query helpers, CLI, lightweight Flask UI.

### Notes

- **Reports Plus auth**: current `.token` works for `/commandcenter/api` but returns HTTP 401 on Reports Plus inventory endpoints. A Login-issued Authtoken (from `POST /commandcenter/api/Login`) works as `Authtoken` for `/commandcenter/api/cr/reportsplusengine/reports`. Auth-matrix script confirmed both header styles fail with the current `.token` for Reports Plus.
- **Dataset metadata payload is rich**: includes fields, `GetOperation` parameters, SQL text, database name, query plan, tenant visibility, and `builtIn`/`systemDataSet` flags.
- **Rationale for splitting `API_MAPPING.md` from `HEALTHCHECK_MATRIX.md`**: one source can support many health checks; health logic should not be embedded in the API inventory.

---

*Earlier history is not consolidated here. See `git log` for granular detail before this file existed.*
