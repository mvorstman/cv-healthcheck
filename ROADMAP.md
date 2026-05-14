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
