# Roadmap

## Phase 1: Connectivity and Exploration

- Command Center API ping
- Reports Plus dataset metadata retrieval
- Reports Plus dataset data retrieval
- CLI commands over reusable services
- Lightweight Flask exploration UI

## Near-Term Milestone: Source Mapping Before Rules

- Build the API mapping catalog.
- Expand Reports Plus dataset discovery.
- Use the API mapping as the foundation for collectors.
- Implement health rules only after source capabilities are mapped.

## Future Architecture: Operating Modes and Collection Model

cv-healthcheck should support three operating modes:

- Daily Reporting: recurring operational reports, trends, exceptions, SLA visibility, and concise operational insight.
- Quick HealthCheck: fast, low-impact assessment focused on major operational risks from Metrics data, REST API snapshots, and uploaded artifacts.
- Full HealthCheck: comprehensive evidence-driven analysis with expanded collectors, deeper configuration validation, and long-form reporting.

Reports Plus / private Metrics servers are a primary strategic source for trends, historical reporting, SLA analysis, growth analysis, capacity analysis, operational summaries, and multi-CommCell reporting.

The central reporting platform must not assume direct access to customer CommServe systems. Future collection should support customer-side REST snapshot collectors that run near the customer environment, produce structured artifacts, and upload snapshots/evidence to S3 or equivalent transport. Central analysis and reporting should consume accessible Metrics data plus uploaded artifacts.

No S3 collector code is planned until the source inventory and focused collector contracts are stable.

## Phase 2: Reports Plus Discovery and Cataloging

Status: live proven for inventory and focused Report 318 metric extraction.

- Report inventory CLI and Flask views.
- Dataset inventory CLI and Flask views.
- Report and dataset JSON catalog generation.
- Report content inspection for dataset references, chart definitions, metrics references, query structures, and report composition metadata.
- Report/dataset mapping research.
- Report 318 / Growth and Trends extraction and focused metric acquisition pipelines.

## Phase 2.1: Catalog Persistence and Analysis

Status: started.

- Persist Reports Plus report and dataset inventory to local JSON catalog files.
- Generate report and dataset summary JSON files from catalog records.
- Add lightweight heuristic relevance tags for future healthcheck candidate discovery.
- Keep catalog persistence file-based; no database.

## Phase 2.2: Catalog Inspection and Candidate Prioritization

Status: started.

- Prioritize local Reports Plus catalog candidates for future healthcheck coverage.
- Map candidates to known API mapping subjects when confidence is reasonable.
- Keep prioritization heuristic and adjustable; no health rules.

## Phase 2.3: Candidate Validation by Dataset Execution

Status: started.

- Execute safe, prioritized dataset candidates with bounded result limits.
- Record EXECUTABLE, NEEDS_PARAMS, FAILS, and SKIPPED validation outcomes.
- Keep validation file-based and exploratory; no health rules.

## Phase 2.4: Lab Readiness Baseline

Status: started.

- Summarize whether the lab is ready for discovery, dataset execution, or future health-rule testing.
- Write the latest readiness result to `data/labreadiness/latest.json`.
- Expose readiness through `cv-healthcheck lab readiness`, `cv-healthcheck lab readiness --json`, and `/lab-readiness`.
- Keep readiness file-based and credential-free; no database and no health rules.

## Phase 3.0: Quick HC Foundation

Status: active.

- Add a Quick HC section to the Flask UI.
- Keep Quick HC fast, read-only, low impact, and API-first.
- Implement reusable Quick HC collectors outside Flask route handlers.
- Persist latest REST collection artifacts under `data/catalog/rest/`.
- First subject: CommCell Identity / Version from `GET /commandcenter/api/CommServ`.
- Normalize CommCell identity fields for later rule-engine consumption without adding health scoring.
- Add a basic assembled HTML HealthCheck report page over existing artifacts before introducing scoring, recommendations, charts, or PDF generation.

Current Phase 3 capabilities:

- Quick HC now acts as the main customer-facing report-composition surface.
- Supported Quick HC subjects are CommCell Details, Security Assessment, License Summary, Client Growth, and Capacity Licenses.
- Each subject supports expandable overview tiles, customer-facing previews, include/exclude controls, and nested section/table selection.
- `/quick-hc/report` now renders selected subjects and selected sections only.
- Customer-facing output intentionally strips artifact paths, dataset GUIDs, HTTP status fields, and raw/debug extraction metadata.
- Client Growth now includes a professional Chart.js visualization in the customer-facing report.
- License Summary now includes workload/category sections plus compact usage visualization where that presentation fits the data.
- The shell navigation direction is now stabilized around a sidebar-first flow with `Connect to CS`, `Status`, `Quick HC`, and `Development`, plus a lightweight Back action in the topbar.
- Quick HC metadata extraction has started through shared tile/section dataclasses and a registry-first architecture so future subjects can be added incrementally without a full route/template rewrite.
- Quick HC overview rendering now also uses a shared subject-tile shell partial so template duplication can be reduced before any preview-renderer abstraction or report-service rewrite.
- Quick HC section cards now also use a shared wrapper partial, completing the structural shell extraction before preview-renderer abstraction work.
- Preview decomposition has started with explicit CommCell, Security Assessment, License Summary, and Client Growth preview partials, proving the extraction pattern before applying it to the remaining subject previews.

Current known limitations:

- no PDF export yet
- no persisted report profiles yet
- no scoring or recommendations yet
- UI selection persistence currently uses localStorage only
- runtime artifacts remain outside git and are not part of the repository state

## Current Foundation Hardening

Status: started.

- Keep the current user-facing URLs and templates stable while improving internal maintainability.
- Split the Flask route layer into focused modules instead of growing one monolithic route file.
- Standardize artifact version metadata across canonical artifact types.
- Keep existing persisted artifacts readable without forcing a migration yet.
- Make SSL verification default to enabled and require explicit opt-out for self-signed lab environments.
- Emit clear warnings when insecure SSL mode is used.
- Add focused regression coverage around route registration, key page availability, artifact version fields, and SSL behavior.

## Near-Term Follow-Up: Security Assessment Multi-Source Stabilization

Status: active.

- Complete the transition from compatibility-first `latest.json` reads to registry-driven active artifact reads everywhere.
- Resolve the remaining REST/source precedence issue affecting Security Assessment rendering.
- Finalize the canonical artifact render path so REST, HTML, and CSV all load through one consistent selection path.
- Complete end-to-end ingestion validation across live REST collection, HTML import, CSV import, persistence, and Flask rendering.
- Strengthen artifact provenance and debugging so selected source, artifact path, and normalization history are explicit.
- Validate REST normalization parity against HTML and CSV canonical artifacts to confirm equivalent field-level output.
- Install and standardize `pytest` plus required runtime/development dependencies in the local environment so regression coverage can run consistently.
- Continue expanding regression coverage for noisy exports and source-selection edge cases.
- Preserve all artifact files by default and design future retention/cleanup as an explicit, non-destructive operator action.
- Keep export/audit tooling lightweight while the registry model settles; no heavy migration framework yet.

## Near-Term Follow-Up: License Summary Artifact Foundation

Status: started.

- Keep License Summary minimal in Quick HC; no scoring, recommendations, charts, or broader dashboard redesign.
- Normalize CSV export, HTML export, XLSX API viewer recordings, and live Reports Plus report 206 extraction into one canonical artifact.
- Reuse the artifact registry/read-path pattern already established for Security Assessment.
- Preserve customer and CommCell scoping in registry selection and persistence.
- Treat `latest.json` as compatibility/cache only; prefer registry-backed reads internally.
- Keep raw dataset evidence and source metadata attached for later provenance and parity checks.
- Support both logical License Summary data families in the canonical artifact:
  detail/current-usage tables and workload/category summary sections.
- Preserve the missing-values policy:
  do not fabricate absent sections,
  do not guess `license_expiry`,
  and render only sections that return real rows in the current CommCell.
- Continue using page context plus field/header shape for report 206 discovery; do not hardcode environment-specific dataset GUIDs.
- Defer scoring, compliance rules, recommendations, and trend analytics.

## Future Research: Commvault Report Definitions

- Treat raw Commvault report-definition exports such as `Licensesummary.xml` as sensitive research inputs.
- Do not commit customer or environment-specific XML unless it has been explicitly sanitized and approved.
- Analyze XML report definitions on a separate research branch when needed.
- Investigate whether XML exports can become the basis for a generic Commvault report-definition parser covering pages, widgets, datasets, parameters, GUID relationships, and section layout.

## Foundation Milestone: Persistent Artifact Registry

Status: started.

- Keep the existing Flask Development interface stable while replacing the backend artifact foundation underneath it.
- Treat `latest.json` as a temporary compatibility layer, not the long-term source of truth.
- Persist each Security Assessment artifact as a uniquely addressable file plus a SQLite registry record.
- Support customer, CommCell, engagement, report stream, report run, and import-run identity in the artifact model even before the reporting/evaluation engine exists.
- Support multiple recurring report runs on the same day through `report_run_id`, `executed_at`, and optional `run_sequence`.
- Keep active-artifact selection scoped so customers and CommCells cannot select each other’s artifacts.

## Foundation Milestone: Read-Path Migration and Historical Retrieval

Status: started.

- Prefer registry-backed reads internally and treat `latest.json` as compatibility/cache only.
- Expose service-layer methods for current artifact, artifact history, and artifact lookup by artifact/run identifiers.
- Support historical browsing by customer, CommCell, import run, and report run.
- Keep any history UI additive and debug-oriented until the backend contracts settle.
- Track retention/provenance metadata now, but defer destructive cleanup and retention enforcement.

## Future Architecture: Evidence Provenance and Confidence

- Add explicit provenance metadata to canonical artifacts so downstream health logic can distinguish live REST evidence from imported offline evidence.
- Add evidence confidence concepts so future health scoring can account for source quality, completeness, and collection freshness.

## Later Phases

- Collector orchestration
- Customer-side REST snapshot collectors
- S3 artifact upload and evidence store
- Central analysis over Metrics data plus uploaded snapshots
- Health models and checks
- Output renderers
- Trend analytics
- Persistence layer
- Production dashboard
