# Development Log

## 2026-05-11

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
