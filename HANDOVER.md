# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-28 (bugfix: LS HTML workload-section detection for Commvault export markup)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `02722a4` — CHANGELOG + HANDOVER: LS HTML workload-section detection fix
**Test status:** 556 passing. `tests/test_unified_upload_route.py` has a pre-existing collection error (`from tests.test_security_assessment_import import HTML_SAMPLE` with no `tests/__init__.py`) — unrelated to this fix.

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

**Bugfix: LS HTML workload-section detection for Commvault export markup.** The prior numeric-extraction fix made values render correctly, but the user pointed out that workload summary sections (Capacity / Operating Instances / Virtualization / User / Data Insights / Air Gap Protect / Other) are the CORE of a License Summary report — and the artifact was reporting **0 workload sections** for real exports. Investigation surfaced two stacked bugs. (1) `_table_section_name` at `license_summary/import_html.py:128-133` walked `find_previous(["h1",...,"div"])`, landed on the table's own wrapper `<div class="exportTable">`, then `.get_text()` dumped the table's full contents as the "section name" — never matched `SUMMARY_SECTION_NAMES`. Commvault exports wrap titles in `<span class="component-title-text">` inside nested divs, with zero `<h2>`-`<h6>` headings in the entire file. (2) Two workload tables (Virtualization Licenses, Data Insights Licenses) use bare `Available Total`/`Used` headers without unit qualifiers, so the header-only classifier returns `"other"` and the rows pile into `other_licenses`. The user's "9 Other Licenses rows" was actually 2+7 from mis-bucketed Virtualization and Data Insights sections. Fix: `_table_section_name` walks `find_all_previous()` matching against direct text only (string children, not recursive `get_text()`) against `_KNOWN_SECTION_TITLES`; a claimed-titles guard prevents cross-wiring; the parse loop routes section_name-in-SUMMARY_SECTION_NAMES tables to workload-summary regardless of classifier output. Real-file verification confirms 7 sections / 23 rows (4/2/2/5/7/1/2), 0 standalone other_licenses, 0 agent_feature, no cross-wiring. Two new tests use the real markup shape and would have caught both bugs.

### Prior session: LS numeric value extraction

**Bugfix: LS numeric value extraction for combined value+unit cells.** After the prior two fixes wired up the inline-import path correctly, the LS HTML import landed an artifact whose `Other Licenses` table rendered blank `Available Total` and `Used` columns in the workspace — only the unit survived. Root cause: `parse_number` at `license_summary/normalize.py:64-72` float-parsed the whole cell, so combined cells like `"500 VMs"` / `"25 TB"` raised `ValueError` and returned `None`. The unit extractor (a separate regex) worked fine, which is why the Unit column was the only one populated. Fix: regex-extract the leading numeric prefix; also strip `\x00` from `clean_text` as belt-and-braces (the real export has 84 NUL bytes scattered between tags, none inside cells, but the cost is negligible). One fix covers all three normalize callsites by construction (Other Licenses HTML+CSV; Agent/Feature uses the same `parse_number` call shape — unverified against real data because the user's export had 0 agent/feature rows). Real-file verification confirmed: 9 Other Licenses rows parse correctly; the user's `Auto Recovery` row now shows `available_total=500, used=0`. New + extended tests proven to fail-against-old / pass-against-fix. 564 tests pass (was 563).

### Prior session: upload field-name mismatch

**Bugfix: upload field-name mismatch for already-collected system subjects.** Yesterday's inline-JSON fix (`130e28b`) unmasked a second latent bug. With the JSON-response path wired correctly, the JS now received an error JSON it could display — and that error read "No file selected." even though a file was clearly selected. Root cause: `_provenance_to_tile_sources` at `subject_data_service.py:226` hardcoded `import_field="file"`, but the SA/LS handlers read `request.files[handler.form_field]` where `form_field` is `"assessment_file"` / `"license_summary_file"`. The bug fires when a canonical artifact exists for the subject (the orchestration takes the provenance path instead of the nodata path, where the right field names ARE declared). Fix uses `get_handler(subject_id).form_field` as the source of truth. Contract test added that pins the action-dict-importField ↔ handler.form_field invariant — it fails against the pre-fix code, passes against the fix.

### Prior session: inline JSON response fix

**Bugfix: inline JSON response for system-subject uploads.** Image evidence showed CSV and HTML offline imports for `license_summary` failing in the UI with "Import failed: The string did not match the expected pattern." Investigation surfaced a latent server-side bug since 2026-05-25: `_handle_system_upload` ignored the JS's `X-Inline: 1` header and always replied with flash+redirect (302 → HTML body); the JS then failed `resp.json()` parsing and surfaced WebKit's SyntaxError. The underlying import was actually succeeding — the LS legacy store has 7 content-duplicate groups (2-10 artifacts each, tight time windows) from user retries. SA's legacy store has 29 unique artifacts (no retry pattern). The fix added X-Inline handling to `_handle_system_upload` and 4 inline-mode tests. ADR 0003 was unaffected by this bug — it predates the ADR and the upload path is unrelated. The duplicate artifacts in the LS legacy store were not cleaned up — backlog #14 (legacy SA/LS store retirement) is the right place for that.

### Prior session: ADR 0003 phase 5 cleanup

**Phase 5 cleanup pass; ADR 0003 implemented with LS caveat.** Step 1 investigation surfaced that LS's report 206 structurally doesn't fit the catalog model defined in ADR 0003 (47+ pages with name-ambiguous datasets, runtime parameter-substitution-from-prior-results, per-row value-formula transforms). Steering chat approved Path A: leave LS bespoke, do the safe cleanup half of phase 5, mark ADR 0003 implemented with the caveat documented. Deleted: `CommvaultSession.init_report` (dormant since the interstitial fix), `REPORT_DEFINITIONS` dict + its file (orphan since phase 2), `_read_commcell_provenance` (zero callers since phase 3). ADR 0003's Migration / Consequences / Out-of-scope sections amended to reflect the actual outcome. The ADR status is now "Implemented (with LS caveat)."

---

## What is in-flight

**ADR 0003 is implemented (with the documented LS caveat).** The catalog-driven REST extractor handles four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment); License Summary retains its bespoke `collect_from_rest` path. The methodology retrospective is the recommended next session. Working tree is clean.

---

## Single recommended next action

**Methodology retrospective for ADR 0003.**

ADR 0003's implementation produced four methodology lessons that the project hasn't reflected on yet. Conduct a retrospective conversation (Claude.ai is the right venue, not Claude Code — this is prose work, not filesystem work) covering:

1. **Wipe-and-recreate rule** (HANDOVER backlog item #17 / methodology marker from the 2026-05-27 ADR 0003 amendment). ADR 0002 set the precedent; ADR 0003 phases 1, 4, and 5 followed it. The retrospective decides whether it becomes a tool-wide default.
2. **ADR workflow efficiency review** (HANDOVER backlog item #18). The survey-then-steer-then-draft-then-phased-implementation cycle has now run end-to-end twice (ADR 0002, ADR 0003). Was the overhead worth it? Particular lens: phase 5's discovery that the design model didn't fit LS — could a deeper survey or a prototype-against-real-data step have surfaced this earlier?
3. **ADR-commit-alongside-first-phase pattern** (HANDOVER backlog item #19). ADR 0002 and ADR 0003 both landed this way (ADR doc committed in the same session as phase 1). Decide whether to document this in `docs/PATTERNS.md` or HANDOVER's "Where work happens" section.
4. **NEW: Catalog-model expressiveness limits.** Phase 4 surfaced that the original ADR 0003 catalog schema (just `dataset_name` + `dataset_guid` + post-processing) didn't fit SA's findings rendering — Approach A added `column_map` + `status_to_severity` + HTML stripping mid-implementation. Phase 5 surfaced that even the expanded schema didn't fit LS — required deferring LS migration. Twice the implementation surfaced model gaps that the design conversation didn't catch. Worth a deliberate examination of how to surface "the model isn't expressive enough" earlier — perhaps a "prototype against a real second subject before declaring the design done" step.

The retrospective produces decisions, not code. After the retrospective, the next concrete code work depends on what comes out — likely either a PATTERNS.md update + ADR workflow rule clarifications, or new backlog items for tool-wide rules.

### After the retrospective

Whatever surfaces. The current backlog is healthy (no urgent next code action); LS-migration future-work is documented; ADR 0003 is done.

### Priority-ordered backlog (everything else)

### Priority-ordered backlog (everything else)

1. **AI import workstream — staging UI for proposal review, compliance rules.**
2. **CommCell-discovery flow for customer creation.** Auth plumbing overlaps with ADR 0003 phase 3 (landed). The discovery flow can reuse `get_active_customer` and the customer-bound auth model directly.
3. **Report-provenance verification.** Check imported reports' embedded CommCell IDs against the active customer's stored CommCell ID. Catches "wrong customer's report" mistakes.
4. **Read-only per-finalization view.** Deferred from ADR 0002 phase 5 step 5.
5. **Customer panel on the right side of `quick_hc.html`.** Raised earlier, not acted on.
6. **`shared.py` split.** 413-line god-module; flagged in the 2026-05-20 review.
7. **`SecurityAssessmentArtifactRegistry` rename / generalize.** The registry pattern is used by both SA and LS but the class name is SA-specific. Decide: rename to a generic `ArtifactRegistry` and unify, or document the per-domain naming as intentional.
8. **LS catalog migration.** Phase 5 of ADR 0003 deliberately left `license_summary` bespoke after investigation showed the catalog model's expressiveness was insufficient. To migrate LS would require three extractor extensions: (1) runtime parameter substitution from prior dataset results (LS's organization dataset returns `OrgGUID`s that downstream datasets need as parameters); (2) page-aware GUID resolution (LS's report 206 has 47+ pages where the same dataset name appears multiple times with different GUIDs); (3) value-formula transforms (LS uses per-row unit suffixing via a `LicUsageType` integer code → unit string dispatcher). Defer until consultant demand justifies. Until then, LS uses its existing bespoke `collect_from_rest` path; new LS-shaped reports continue to require Python code rather than catalog rows.
9. **Hardcoded URLs in `report_service.py`.** Audit whether any remain after the 2026-05-20 partial cleanup.
10. **Left-nav structural review.**
11. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL and `db/customers.py` helpers — pick one.
12. **Template inheritance cleanup.** Uneven `base.html` extends.
13. **`engagements` table cleanup.** Empty since migration 0001; pre-ADR-0002.
14. **Project-scope the legacy SA/LS stores** under `data/catalog/{security_assessment,license_summary}/`. SA store still has its pre-ADR-0002 `latest_*.json` files (29 unique artifacts, no duplicates); LS store similarly with 42 `artifact_*.json` files — of which 41 belong to 7 content-duplicate groups from the 2026-05-25 → 2026-05-27 X-Inline bug's retry pattern (now fixed at commit 130e28b). Phases 4/5 didn't touch them — separate cleanup. The LS store remains in active use through the bespoke path. When this cleanup eventually lands, the duplicate-collapse is the natural first pass: keep the latest artifact per content-hash, delete the older retries.
15. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
16. **Audit Section 6 #2/#5/#6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.
17. **Methodology marker: wipe-and-recreate rule.** Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered. Wipe and re-collect unless real customer data is at stake. ADR 0002 set the precedent; ADR 0003 phases 1 and 4 followed it. Phase 5 didn't need it (LS not migrated). Up for retrospective decision: tool-wide default or ADR-by-ADR judgment.
18. **Methodology marker: ADR workflow efficiency.** The survey-then-steer-then-draft-then-phased-implementation cycle ran end-to-end twice (ADR 0002, ADR 0003). Was the overhead worth it? Particular lens for ADR 0003: phase 4 surfaced an extractor-schema gap mid-implementation (column_map / status_to_severity), and phase 5 surfaced a deeper gap that forced LS to stay bespoke. Could a deeper survey or a prototype-against-real-data step have caught these earlier? Retrospective decides.
19. **Methodology marker: ADR-commit-alongside-first-phase pattern.** ADR 0002 and ADR 0003 both landed this way (ADR doc committed in the same session as phase 1). Should `docs/PATTERNS.md` or HANDOVER's "Where work happens" section document this explicitly so future ADR sessions don't leave the doc uncommitted? Low-priority decision.
20. **Methodology marker (new): catalog-model expressiveness limits.** ADR 0003 surfaced its model gaps twice — Approach A in phase 4 (added column_map + status_to_severity + HTML stripping) and the LS escalation in phase 5 (would need parameter substitution + page-aware GUID resolution + value-formula transforms). Both surfaced during *implementation*, not during *design*. Worth a deliberate examination of when to surface "the model isn't expressive enough" earlier in the ADR process. Retrospective fodder.
21. **Cleanup: retire `reportsplus/checklist.py`** (dead since phase 4 — only callers were the deleted SA bespoke modules; LS doesn't use it). Small post-ADR-0003 cleanup.

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
- **ADR 0003 is implemented (with LS caveat).** Phase 1 extended catalog schema. Phase 2 built the GET-only `RESTExtractor`. Phase 3 made auth customer-aware. The interstitial fix and protocol amendment landed the GET-only protocol. **Phase 4 migrated Security Assessment** — extractor gained `column_map` + `status_to_severity` + HTML stripping; migration 0007 seeded six SA catalog rows. **Phase 5 was the cleanup pass; LS retained bespoke** because LS's report 206 requires runtime parameter-substitution-from-prior-results, page-aware GUID resolution, and value-formula transforms that the catalog model doesn't express. Four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment) use the generic catalog-driven path; LS continues through `LicenseSummaryService.collect_from_rest`.
- **REST extractor catalog keys honored**: `report_id`, `dataset_name`, `dataset_guid` (cache hint, used when the live name→guid map doesn't have the name), `fields`, `orderby`, `limit`, `parameters`, `timestamp_fields`, `timestamp_format`, `null_values`, **`column_map`** (rename source keys → canonical, drop the rest), **`status_to_severity`** (when output_as=="findings", set row.severity from status mapping), `output_as` (`"table"` / `"findings"` / `"card"`). Under `output_as: "findings"`, the extractor strips embedded HTML via `html.parser`. `fields` and `orderby` are only sent to the server when a cacheId is present — the lab's CacheDB rejects them without one.
- **Catalog-driven SA reference**: migration 0007 seeded six rows under `security_assessment.rest` with `report_id="336"` plus column_map renaming Parameter/Status/Remarks/Action to canonical lowercase + status_to_severity mapping `1_Good→good` / `2_Info→info` / `3_Warning→warning` / `4_Critical→critical` + `output_as: "findings"`. Use as a template for any future catalog-driven REST subjects.
- **Bespoke LS modules retained** (deliberately, per ADR 0003 amendment): `license_summary/collect_rest.py`, `license_summary/service.py::collect_from_rest`, `adapters/license_summary.py`, `normalize_license_summary_rest_extraction`, `persist_license_summary_artifact`, and `reportsplus/extract_report.py` (LS is its last caller). The LS UI continues to work through this path. Backlog item #8 records what extractor extensions would be needed to migrate LS in a future expansion.
- **`backup_job_summary` collects but produces 0 rows.** The lab's "Job details" dataset on report 194 is genuinely empty (probe: `GET /datasets/a30bd278-.../data?format=object` returns HTTP 200 with `totalRecordCount: 0, failures: {}`). Name resolution succeeds; the dataset just has no jobs.
- **Default customer's CommCell binding is configured.** `commcell_hostname = https://192.168.182.129:4433`, `commcell_id = SMOKE-TEST-CS` — set during phase 3 verification, useful for any future REST-path probing.
- **`set_current_token` signature.** Required positional arg `customer_id` after `token`. Two production callsites (`/login`, `/api/login`). Tests that wrote directly to `session[SESSION_TOKEN_KEY]` still work for the loose `is_authenticated()` gate; customer-aware routes use `is_authenticated_for(customer_id)`.
- **`is_authenticated()` vs `is_authenticated_for(customer_id)`** — the first is loose (any token in session); the second is strict (token AND bound customer matches). `login_required` decorator uses the loose check; the catalog-driven collect handler uses the strict check.
- **Dead code retired in phase 5**: `CommvaultSession.init_report` (no callers since the GET-only protocol amendment), `REPORT_DEFINITIONS` dict + `reportsplus/report_definitions.py` (orphan since phase 2), `_read_commcell_provenance` (zero callers since phase 3).
- **Still-dead code waiting on a cleanup pass**: `cvhealthcheck.reportsplus.checklist` (only callers were the SA bespoke modules; LS doesn't use it). Backlog item #21. Small post-ADR cleanup.
- **`output_as: "card"`** is implemented in the extractor (trims `rows[:1]`) but not exercised in production today (no catalog rows declare it). If a future subject needs card rendering, the workspace renderer needs either a `CardSection` artifact type or a template branch — neither shipped with ADR 0003.
- **Same-report_id-per-subject rule** is a runtime check in `_resolve_single_report_id`. Not a DB constraint. Reports offending section_ids in the error message on mismatch.

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
python -m pytest -q                                # expect 564 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001, 0002, README
```
