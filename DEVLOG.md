# Development Log

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
