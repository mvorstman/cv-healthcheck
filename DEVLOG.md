# Development Log

## 2026-05-17

- Stabilized the new Security Assessment SQLite registry foundation after the initial refactor.
- Tightened active-artifact selection so it is no longer global by artifact type; it now scopes by customer, CommCell, artifact type, source type, and engagement/report-stream context where applicable.
- Verified that repeated imports create unique artifact files and preserve prior registry rows instead of overwriting historical runs.
- Added recovery logic for missing active artifact files: the service now attempts to promote the newest recoverable artifact in the same scope before falling back to `latest.json`.
- Added explicit fallback diagnostics by marking the path actually loaded when compatibility fallback is used.
- Added registry export support for audit/debugging as JSON without introducing restore or destructive cleanup features.
- Added SQLite hardening through idempotent schema creation plus `foreign_keys`, `busy_timeout`, and `WAL` pragmas.
- Added tests for:
  unique artifact lifecycle,
  scoped active selection,
  multi-customer isolation,
  multi-CommCell isolation,
  missing-artifact recovery,
  `latest.json` fallback,
  and registry export.
- Confirmed full validation still passes:
  `venv/bin/python -m compileall src tests`
  `venv/bin/python -m pytest`

## 2026-05-17

- Refactored the Security Assessment artifact foundation under the existing Flask UI without removing pages or changing the visible Development interface.
- Split the previous monolithic normalization path into:
  `models.py`, `normalize.py`, `validate.py`, `artifact.py`, `registry.py`, and `service.py`.
- Added strict schema models for customer/CommCell/engagement/report stream/report run/import run/artifact record/canonical finding/Security Assessment artifact.
- Added a SQLite artifact registry at `data/imports/security_assessment/artifact_registry.sqlite3`.
- Added unique persisted artifact files per import/refresh in addition to `latest.json` compatibility files.
- Kept temporary compatibility behavior by continuing to write:
  `latest.json`, `latest_rest.json`, `latest_html.json`, and `latest_csv.json`.
- Added service orchestration so Flask routes stay thin and call a backend layer that imports, normalizes, validates, stores, and registers artifacts.
- Moved source activation/selection responsibility out of `normalize.py`; active artifact selection now belongs to registry/service logic.
- Kept `normalize.py` limited to field cleanup and canonical mapping only.
- Moved invalid/noisy finding filtering and deduplication into a dedicated validation layer.
- Updated HTML/CSV import flow to register artifacts in SQLite while keeping existing UI behavior intact.
- Updated the REST refresh path to persist artifacts through the same registry-backed foundation.
- Added tests for canonical finding validation, post-normalization filtering, registry insert/read behavior, `latest.json` compatibility, and multiple same-day report runs.
- Confirmed validation passes after the refactor:
  `python -m compileall src tests`
  `python -m pytest`

## 2026-05-17

- Added Security Assessment HTML import support.
- Added Security Assessment CSV import support.
- Added a shared Security Assessment normalization pipeline so REST, HTML, and CSV sources now converge on one canonical artifact schema.
- Expanded the Security Assessment architecture into a multi-source evidence ingestion path:
  `collect -> normalize -> persist -> render`.
- Added persisted latest artifacts for source-specific and selected output states:
  `data/imports/security_assessment/latest.json`,
  `data/imports/security_assessment/latest_rest.json`,
  `data/imports/security_assessment/latest_html.json`,
  and `data/imports/security_assessment/latest_csv.json`.
- Added reusable upload/import service support for Security Assessment ingestion outside Flask route handlers.
- Added browser upload/import support in the Flask UI for HTML and CSV evidence.
- Added runtime import storage at `data/imports/security_assessment/`.
- Hardened normalization with canonical field enforcement, noise rejection, deduplication, and footer/header filtering.
- Hardened HTML ingestion with strict table parsing that validates `thead` and only extracts `tbody`/`tr`/`td` cell content.
- Added regression coverage for noisy HTML exports to protect the parser against presentation-heavy report markup.
- Added source-type rendering in the Flask UI so the active artifact/source can be surfaced during review.
- Added debug logging for Security Assessment artifact loading and selection to support source precedence debugging.
- Key finding: HTML exports are presentation-heavy and cannot be treated as simple text extraction inputs; strict table parsing is required.
- Key finding: CSV exports are materially cleaner than HTML exports and currently appear to be the more reliable offline import format.
- Key finding: the Security Assessment implementation has evolved from single-source report extraction into multi-source canonical evidence ingestion.
- Debugging result: imported HTML and CSV artifacts appear to load and render correctly when REST/live source is unavailable.
- Unresolved issue remains open: noisy text may still appear in the UI when REST source is active even though offline imports normalize correctly.
- Current best hypothesis is that the remaining defect is in REST/live source interaction, source precedence, stale artifact selection, or an alternate rendering/load path rather than HTML/CSV parsing itself.
- This issue is not resolved yet and should not be documented as closed.

## 2026-05-15

- Kept the Flask navigation intentionally simple: Login / Logout, Quick HC, and Development.
- Clarified the product split: Quick HC is customer-facing healthcheck output; Development is for raw/debug/API/report exploration, validation, lab readiness, and report/dataset inspection.
- Added the Chart.js metric visualization pattern for historical metrics. Routes build server-side chart payloads, `metric_detail.html` renders them, and Chart.js is loaded only when chart data is present.
- Added a Client Growth mixed chart with total clients as a line and monthly additions/removals as bars.
- Extended the reusable chart approach to current historical metric pages: Client Count, Client Growth, and Capacity License Usage.
- Added Reports Plus Security Assessment extraction for report 336 using the existing report extraction pattern.
- Security Assessment endpoint pattern: `/commandcenter/api/cr/reportsplusengine/reports/336`, `/commandcenter/api/cr/reportsplusengine/datasets/<guid>`, and `/commandcenter/api/cr/reportsplusengine/datasets/<guid>/data`.
- Added normalized Security Assessment artifact output at `data/catalog/reportsplus/report_336_security_assessment_normalized.json`.
- Discovered six Security Assessment datasets: Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, and Hardening.
- Added reusable checklist-style normalization in `src/cvhealthcheck/reportsplus/checklist.py`.
- Added `/reportsplus/security-assessment` as the Development/debug view for report 336.
- Added Security Assessment to Quick HC with `/quick-hc/security-assessment`.
- Current Security Assessment artifact summary: 32 total checks, 2 Critical, 0 Warning, 18 Info, and 12 Good.
- Confirmed `cv-topology` is reference-only. It should not be refactored or modernized as part of active cv-healthcheck work.

## 2026-05-14

- Started Phase 3.0 Quick HC Foundation.
- Added reusable Quick HC CommCell Identity / Version collector for `GET /commandcenter/api/CommServ`.
- Added normalized REST artifact output at `data/catalog/rest/commserv.json`.
- Added `cv-healthcheck quickhc commcell`.
- Added Flask Quick HC pages at `/quick-hc` and `/quick-hc/commcell`.
- Live validated `/commandcenter/api/CommServ` with a Login-issued Authtoken: HTTP 200 returned `hostName`, nested `csGUID`, `csVersionInfo`, `releaseId`, `osType`, and `timeZone`.
- Kept Quick HC read-only and acquisition-only; no health scoring, health rules, SQL, database, or S3 code was added.
- Added `PROMPT.txt` as a durable project and AI guidance handover for future sessions.
- Clarified the strategic operating model around Daily Reporting, Quick HealthCheck, and Full HealthCheck modes.
- Clarified Reports Plus / private Metrics as a primary strategic trend and reporting source.
- Documented the disconnected/customer-side collection model: customer-side REST collectors can gather snapshots and upload evidence artifacts, with S3 expected as a future transport/evidence store.
- Clarified that the central reporting platform must not assume direct reachability to customer CommServe systems.

## 2026-05-13

- Added focused metric extraction pipelines for the four high-value Report 318 datasets: Client Count, Client Growth Summary, Capacity License Usage, and ClientGrowthDetails.
- Added normalized local metric artifacts under `data/catalog/metrics/` with source report/dataset/widget metadata, extraction timestamps, record counts, history ranges, and stable metric-oriented records.
- Added `/metrics/client-count`, `/metrics/client-growth`, and `/metrics/capacity-license` pages that display focused metric acquisition results from the local ignored artifacts.
- Kept the focused metric layer limited to acquisition and normalization; no health findings, scores, recommendations, or good/bad interpretation were added.
- Added normalized Report 318 metric inventory generation from the live extraction artifacts.
- Created `data/catalog/reportsplus/report_318_metric_inventory.json` with 30 classified datasets, returned columns, record counts, sample values, time ranges where visible, usefulness labels, and operational questions.
- Added `/reportsplus/report/318/metrics` to review the normalized metric inventory without introducing health findings or scoring.
- Classified the Report 318 datasets as 10 capacity/growth, 3 client growth, 6 deduplication/compression, 5 storage usage, and 6 low-value/unclear selector-style datasets.
- Notable useful metrics include client count and client growth monthly history from May 2025 through May 2026, capacity license usage over the same period, and client growth detail rollups.
- Low-value or unclear datasets are input/selector sources such as entity-name and library-name datasets that executed but did not expose standalone operational measurements in the lab sample.
- Completed live Report 318 validation after GW02 network reachability was restored.
- Confirmed Command Center `/commandcenter/api` returns HTTP 200 from dev, Flask `/login` returns HTTP 200 locally, Flask login redirects to `/reportsplus/report/318`, and the Report 318 extraction page renders HTTP 200.
- Confirmed `/commandcenter/api/cr/reportsplusengine/reports/318` returns HTTP 200 with a Login-issued Authtoken and identifies Report 318 as `Growth and Trends`.
- Confirmed Report 318 extraction discovers 24 widgets and 30 backing datasets, fetches dataset metadata for the discovered datasets, and executes all 30 backing datasets with HTTP 200 where default/no parameters allow.
- Confirmed local ignored artifacts are populated for Report 318 metadata, definition, dataset map, execution summary, and 30 raw dataset execution outputs under `data/catalog/reportsplus/`.
- Normalized Report 318 summary naming for live responses that expose the report title through the nested `report.customReportName` shape.
- Earlier 2026-05-13 validation was blocked by temporary GW02 reachability failure; validation was rerun successfully after static lab networking was restored.
- Refined Report 318 parsing for the live response shape observed in local artifacts: report definitions can be stored in `pages[].body` JSON strings, and widgets/datasets reference nested `dataSet` objects rather than a direct top-level `content` field.
- Updated Reports Plus dataset metadata and execution calls to use the same Login-issued/session token path as report inventory.

## 2026-05-11

- Added focused Reports Plus extraction workflow for Report 318.
- Added local Report 318 artifacts for metadata, definition, dataset mapping, execution summary, and raw dataset execution results under `data/catalog/reportsplus/`.
- Added `/reportsplus/report/318` inspection page for report metadata, widgets, dataset mappings, execution status, sample rows, and artifact paths.
- Documented Report 318 backend endpoints and extraction artifacts in `API_MAPPING.md`.
- Added Flask login flow for Commvault authentication.
- Token expiry handling now clears the session token and redirects users to login.
- Kept Commvault login logic separated from Reports Plus report and dataset execution.
- Started Phase 2.4 lab readiness baseline assessment.
- Added readiness assessment output at `data/labreadiness/latest.json`.
- Added `cv-healthcheck lab readiness`, JSON output mode, and `/lab-readiness` Flask view.
- Kept readiness baseline file-based and limited to source availability and operational evidence; no health rules, database, or credential storage.
- Started Phase 2.3 candidate validation by dataset execution.
- Added local execution validation output for prioritized dataset candidates without creating health rules.
- Added CLI and Flask views for execution validation status review.
- Started Phase 2.2 Reports Plus catalog inspection and candidate prioritization.
- Added local catalog prioritization that writes `health_candidate_priority.json` from generated report and dataset summaries.
- Added CLI and Flask views for prioritized healthcheck candidates without implementing health rules.
- Started Phase 2.1 Reports Plus catalog persistence and analysis.
- Added catalog CLI commands for reports, datasets, and all inventory sources.
- Added summary JSON generation for report and dataset catalogs plus heuristic health candidate discovery tags.
- Enhanced Reports Plus Flask inventory pages with catalog status, summary fields, and simple relevance tags.
- Confirmed Reports Plus dataset inventory discovery with Login-issued Authtoken: `/commandcenter/api/cr/reportsplusengine/datasets` returned HTTP 200 and exposed rich dataset metadata including fields, GetOperation parameters, SQL text, database name, query plan, tenant visibility fields, and builtIn/systemDataSet flags.
- Updated Reports Plus inventory calls to prefer `CV_LOGIN_TOKEN` or project-local `.login_token` for report and dataset inventory while leaving existing dataset metadata and dataset data calls on the configured token path.
- Confirmed Reports Plus report inventory authentication behavior: current `.token` works for `/commandcenter/api` but fails with HTTP 401 on Reports Plus inventory endpoints, while a Login API token from `POST /commandcenter/api/Login` works as `Authtoken` for `/commandcenter/api/cr/reportsplusengine/reports`.
- Confirmed report inventory response with Login-issued Authtoken returned HTTP 200 and JSON containing `reports` and `userHistory`.
- Added `scripts/probe_auth_matrix.sh` to compare `Authtoken` and `Authorization: Bearer` across base API, known Reports Plus dataset metadata, report inventory, and dataset inventory endpoints.
- Auth matrix result with current `.token`: `/commandcenter/api` returned HTTP 200 for both header styles; Reports Plus dataset metadata, report inventory, and dataset inventory returned HTTP 401 `Unauthenticated` for both header styles. This suggests the current token is not accepted by Reports Plus and a Login-issued Authtoken should be tested before changing endpoint status.
- Started Phase 2 Reports Plus discovery and cataloging.
- Added reusable Reports Plus report and dataset inventory methods.
- Added CLI inventory commands with JSON output, summary output, and local JSON catalog persistence.
- Added lightweight Flask pages for report inventory, report detail inspection, and dataset inventory.
- Added initial report content clue extraction for dataset references, chart definitions, metrics references, and query structures while preserving raw content.
- Separated API collection mapping from the health evaluation matrix.
- Created `API_MAPPING.md` as the source-centric capability catalog.
- Refocused `HEALTHCHECK_MATRIX.md` on health questions, required data, rules, severity, and reporting status.
- Rationale: one source can support many health checks, and health logic should not be embedded in API inventory.
- Initialized standalone `cv-healthcheck` project.
- Added reusable Commvault API client.
- Added Reports Plus metadata and dataset query helpers.
- Added CLI and lightweight Flask exploration UI.
