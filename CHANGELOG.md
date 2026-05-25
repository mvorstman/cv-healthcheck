# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — sections for **Added / Changed / Fixed / Removed** where they apply, plus a short prose **Notes** section per entry for findings, root causes, architectural decisions, and gotchas worth preserving.

This file is append-only. Past entries are never deleted or rewritten — corrections are made by adding a new entry.

See `HANDOVER.md` for what to do next. See `README.md` for what the project is.

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
