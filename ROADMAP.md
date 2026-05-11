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

## Phase 2: Reports Plus Discovery and Cataloging

Status: started.

- Report inventory CLI and Flask views.
- Dataset inventory CLI and Flask views.
- Report and dataset JSON catalog generation.
- Report content inspection for dataset references, chart definitions, metrics references, query structures, and report composition metadata.
- Report/dataset mapping research.

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

## Later Phases

- Collector orchestration
- Health models and checks
- Output renderers
- Trend analytics
- Persistence layer
- Production dashboard
