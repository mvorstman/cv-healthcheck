# cv-healthcheck

Automated Commvault HealthCheck and analytics exploration tooling.

This project is standalone. It does not import from or integrate with `cv-topology`.

`cv-topology` is now treated as a frozen reference/prototype platform. It can be inspected for Commvault API, Flask, UI, database, topology, and compliance patterns, but active development should happen in this repository.

## Scope

Initial focus:

- Command Center API connectivity
- Reports Plus dataset metadata access
- Reports Plus dataset data querying
- Lightweight Flask exploration UI
- CLI access to the same reusable service layer

## Strategic Direction

cv-healthcheck is being shaped around three operating modes:

- Daily Reporting: recurring operational reporting from Reports Plus / Metrics, email, and existing trend datasets.
- Quick HealthCheck: fast, minimally invasive assessment using Metrics trend data, REST API collection, and uploaded snapshots.
- Full HealthCheck: comprehensive, evidence-driven analysis using Metrics, REST APIs, uploaded operational snapshots, and expanded collectors.

Private Metrics / Reports Plus servers are a primary strategic trend and reporting source, especially for historical growth, SLA visibility, capacity analysis, operational summaries, and multi-CommCell reporting.

The central cv-healthcheck/reporting platform must not assume direct access to customer CommServe systems. The expected real-world model is central analysis over accessible Metrics / Reports Plus data plus customer-side REST collectors that gather live configuration/state and upload structured snapshots or evidence artifacts, potentially through S3. S3 is planned as a transport and evidence store; S3 collection code is not implemented yet.

## Quick HC Foundation

Quick HC is now the main customer-facing report-composition surface for cv-healthcheck.

The product split is intentional:

- Quick HC is the customer-facing composition layer.
- Development holds raw/debug/API/report exploration pages, including lab readiness, Reports Plus inventory, report extraction, dataset execution, registry views, and validation tools.

Current Quick HC subjects:

- CommCell Details
- Security Assessment
- License Summary
- Client Growth
- Capacity Licenses

Each subject now supports:

- an expandable tile on `/quick-hc`
- customer-facing preview content in the tile body
- a parent include/exclude control
- nested section or table selection for report composition
- composition into `/quick-hc/report`

The Quick HC overview is the place where the user decides which subjects and sections appear in the customer-facing report. Selections are currently remembered in the browser with `localStorage`; there is no server-side saved profile or database persistence for report layouts yet.

Phase 3.0 started with CommCell Identity / Version from:

```text
GET /commandcenter/api/CommServ
```

The collector normalizes `hostName`, `csGUID`, `csVersionInfo`, `releaseId`, `osType`, and `timeZone`, then writes the latest local artifact:

```text
data/catalog/rest/commserv.json
```

CLI:

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
cv-healthcheck quickhc commcell
```

Flask UI:

```text
http://127.0.0.1:5001/quick-hc
http://127.0.0.1:5001/quick-hc/commcell
http://127.0.0.1:5001/quick-hc/security-assessment
http://127.0.0.1:5001/quick-hc/license-summary
http://127.0.0.1:5001/quick-hc/report
```

### Customer-Facing Report Composition

`/quick-hc/report` now renders only the selected subjects and selected nested sections. The composition pipeline is assembled through `QuickHcReportService` and keeps the core filtering logic out of Jinja templates.

Current report output capabilities include:

- CommCell Details environment metadata
- Security Assessment summary counters
- Security Assessment critical or warning highlight output
- Security Assessment optional all-findings section
- License Summary workload sections
- License Summary other-license detail tables with compact usage summaries
- License Summary agent or feature detail tables without progress bars
- Client Growth summary metrics
- Client Growth Chart.js history visualization
- Client Growth monthly summary table
- Capacity Licenses summary and latest table inclusion

Customer-facing report rules:

- no artifact paths
- no dataset GUIDs
- no HTTP status values
- no raw/debug extraction fields
- evidence and source metadata stay internal only

### UI Foundation

The current UI foundation work is moving the Flask surface from isolated pages to a cleaner product shell:

- app shell layout with sidebar and topbar
- active navigation states
- global design tokens
- global light/dark theme toggle with persisted preference
- responsive shell behavior
- visual separation between customer-facing Quick HC pages and internal/development pages

Quick HC itself now uses full-width expandable subject tiles, per-section cards, nested include/exclude controls, and theme-aware customer-facing previews.

### Current Limitations

- no PDF export yet
- no persisted report profiles yet
- no scoring or recommendations yet
- localStorage is currently used for UI selection persistence
- runtime artifacts remain outside git
- evidence provenance is intentionally kept out of the customer-facing report output

## Reports Plus Security Assessment

Security Assessment is integrated from Reports Plus report 336.

Security Assessment now supports multi-source ingestion with a shared canonical artifact model. Supported sources are:

- REST
- HTML export import
- CSV export import

All three sources feed the same collect -> normalize -> persist -> render path. The canonical artifact is the normalized evidence contract shared across REST, HTML, and CSV so the UI and downstream health logic can render one consistent structure regardless of acquisition method.

Endpoint pattern:

```text
/commandcenter/api/cr/reportsplusengine/reports/336
/commandcenter/api/cr/reportsplusengine/datasets/<guid>
/commandcenter/api/cr/reportsplusengine/datasets/<guid>/data
```

The normalized local artifact is:

```text
data/catalog/reportsplus/report_336_security_assessment_normalized.json
```

Latest persisted multi-source artifacts are now stored as:

```text
data/imports/security_assessment/latest.json
data/imports/security_assessment/latest_rest.json
data/imports/security_assessment/latest_html.json
data/imports/security_assessment/latest_csv.json
```

Imported HTML and CSV sources are intended to support offline evidence ingestion and browser-driven upload workflows when live REST access is unavailable or unsuitable.

Under the current UI, the Security Assessment backend has been refactored into a persistent artifact foundation:

- `models.py`: strict schema layer for customer/CommCell/import/artifact/finding models
- `normalize.py`: field cleanup and canonical mapping only
- `validate.py`: noise rejection, validity checks, and deduplication
- `artifact.py`: canonical artifact building, unique artifact persistence, and `latest.json` compatibility writes
- `registry.py`: SQLite artifact registry
- `service.py`: orchestration used by Flask routes and future non-UI collectors

Compatibility is intentionally preserved during this phase. The current UI still works through `latest.json`, but each import/refresh now also writes a unique artifact JSON file and registers it in SQLite so the long-term read path can shift to:

```text
registry -> active artifact -> artifact file
```

Current registry/compatibility outputs include:

```text
data/imports/security_assessment/artifact_registry.sqlite3
data/catalog/security_assessment/<artifact_id>.json
data/catalog/security_assessment/latest.json
data/catalog/security_assessment/latest_<source_type>.json
```

Registry stabilization notes:

- The registry database path is deterministic: `data/imports/security_assessment/artifact_registry.sqlite3`.
- SQLite schema creation is idempotent and runs on demand.
- Registry reads now prefer scoped active-artifact selection first, then load the referenced artifact file.
- Compatibility fallback only uses `latest.json` when the scoped registry entry or artifact file is unavailable.
- Active selection is scoped so different customers and CommCells do not overwrite or select each other’s artifacts.
- The registry layer uses simple SQLite hardening (`foreign_keys`, `busy_timeout`, `WAL`) but does not yet introduce a migration framework.
- A registry export utility exists for audit/debugging; destructive cleanup is not implemented.

Historical/read-path foundation added on top of the registry layer:

- Registry helpers now support listing artifacts, fetching the latest artifact within scope, fetching the active artifact within scope, and listing report/import runs.
- Service-layer reads now prefer registry-backed artifact loading over `latest.json`.
- A lightweight `SecurityAssessmentService` exposes current-state, history, and artifact-by-id/run retrieval methods for future UI and reporting use.
- Hidden internal/debug history tooling exists without changing the visible page flow:
  the JSON endpoints require an authenticated session and remain read-only.
  `/security-assessment/history`
  `/security-assessment/registry-export`
- A simple internal viewer is available from the Development page at
  `/development/security-assessment-registry`.

Additional metadata now tracked for artifacts/import runs:

- `created_at`
- `last_accessed_at`
- `retention_policy`
- `imported_by`
- `import_method`
- `source_metadata`

Retention intent for this phase:

- Keep all artifact files by default.
- Treat `latest.json` only as a compatibility pointer, not the system of record.
- Future cleanup must not delete active artifacts without explicit operator action.

Discovered sections:

- Access Security
- Auditing
- Platform Security
- Company and Owners Security
- Capabilities
- Hardening

The reusable checklist normalizer lives in `src/cvhealthcheck/reportsplus/checklist.py`. It normalizes status values, strips unsafe HTML from remarks, extracts safe action links, and groups checks for Quick HC display.

Recent ingestion hardening added canonical field enforcement, noise rejection, deduplication, header/footer filtering, and strict HTML table parsing limited to validated `thead` headers plus `tbody`/`tr`/`td` extraction.

Current artifact summary:

- Total checks: 32
- Critical: 2
- Warning: 0
- Info: 18
- Good: 12

Development/debug page:

```text
http://127.0.0.1:5001/reportsplus/security-assessment
```

Current unresolved issue: imported HTML and CSV artifacts appear to render correctly when REST is unavailable, but noisy text may still appear when the REST source is active. The remaining defect is believed to be in REST/live source interaction, source precedence, stale artifact selection, or an alternate render/load path rather than the offline import normalization pipeline itself.

## License Summary Artifact Pipeline

License Summary now has a separate artifact pipeline built on the same registry-backed persistence pattern used by Security Assessment.

Supported sources are:

- CSV export import
- HTML export import
- XLSX API viewer recording import
- REST dataset extraction through Reports Plus report 206

The current implementation is now exposed through the existing Quick HC License Summary page without redesigning the broader application. It preserves the existing detail tables and also supports workload/category summary sections when they are present in imports or returned by live REST collection.

Observed detail-table sections:

- Other Licenses - current usage details
- Agent and Feature Licenses - current usage details

Observed workload/category summary sections:

- Capacity Licenses
- Operating Instance Licenses
- Virtualization Licenses
- User Licenses
- Data Insights Licenses
- Air Gap Protect Licenses
- Other Licenses

Current package layout:

- `models.py`: canonical `LicenseSummaryArtifact`, `OtherLicense`, `AgentFeatureLicense`, and workload-summary models
- `import_csv.py`: multi-section CSV parsing
- `import_html.py`: HTML table extraction by validated header shape
- `collect_rest.py`: REST report 206 normalization plus XLSX recording import
- `validate.py`: canonical row validity filters
- `artifact.py`: artifact construction and compatibility writes
- `service.py`: upload orchestration and registry-backed read path

Current outputs include:

```text
data/imports/license_summary/artifact_registry.sqlite3
data/catalog/license_summary/<artifact_id>.json
data/catalog/license_summary/latest.json
data/catalog/license_summary/latest_<source_type>.json
```

Current Quick HC behavior:

- The page renders workload summary sections separately from the existing detail tables.
- Live REST collection discovers summary/category datasets dynamically from report 206 and renders only sections with real returned rows.
- Some summary datasets may be unavailable or fail in a given CommCell; the UI intentionally omits those sections instead of fabricating them.
- In the current lab CommCell, sections such as `Operating Instance Licenses`, `Data Insights Licenses`, and `Other Licenses` render from live REST collection, while `Capacity Licenses` may be absent because the upstream dataset fails there.
- `license_expiry` remains `N/A` in the UI when report 206 does not return a value.

The License Summary canonical artifact currently focuses on acquisition, normalization, provenance, and persistence only. No scoring, compliance rules, recommendations, or trend analytics are implemented yet.

## Metric Charts

Historical metric pages use Chart.js through a reusable server-side payload pattern:

```text
route -> server-side chart payload -> metric_detail.html -> Chart.js render
```

`/metrics/client-growth` renders a mixed chart with a line for total clients and bars for monthly additions/removals. Future historical metrics should reuse this pattern by passing chart payloads into `metric_detail.html`; do not add page-specific JavaScript unless the shared pattern is insufficient.

## Architecture Documents

- [DATA_SOURCE_MAPPING.md](DATA_SOURCE_MAPPING.md) is the operating-mode source strategy. It documents which datasource should be used per healthcheck subject across Quick HC, Daily Reporting, and Full Healthcheck, including REST, Reports Plus / Metrics, and import/manual fallbacks.
- [API_MAPPING.md](API_MAPPING.md) is the technical collection and source catalog. It tracks what data can be collected, where it comes from, required authentication and parameters, and whether the source is proven.
- [HEALTHCHECK_MATRIX.md](HEALTHCHECK_MATRIX.md) is the health evaluation and rule catalog. It tracks the health questions, required collected data, evaluation rules, severities, and reporting categories.

The API mapping feeds the collector capability layer. The health matrix consumes collected data and feeds the health rule engine, reports, and UI.

## Configuration

Set the Commvault Command Center base URL:

```bash
export CV_BASE_URL=https://192.168.182.129:4433
```

Place an authentication token in `.token` at the project root. The file can contain either:

```text
plain-token-value
```

or:

```json
{"access_token": "plain-token-value"}
```

It may also contain a JSON `refresh_token`; current lab probes and Reports Plus calls use `access_token`.

SSL verification is enabled by default. Disable it only for isolated lab usage:

```bash
export CV_VERIFY_SSL=false
```

When `CV_VERIFY_SSL=false`, the clients now log a warning so insecure lab behavior is not silent.

## Lab Environment Connection Setup

The lab Command Center and Web Server are available at:

```text
https://192.168.182.129:4433
```

Use the direct IP for Rocky VM testing. The gateway name is `gw02`, but DNS resolution for `gw02` may fail from Rocky. The lab uses a self-signed certificate, so local lab work may require explicitly setting `CV_VERIFY_SSL=false`. The known lab version is Commvault v11.40.

Create a user-local environment file:

```bash
cp env.example ~/.cv-healthcheck-env
```

Recommended `~/.cv-healthcheck-env` contents:

```bash
export CV_BASE_URL="https://192.168.182.129:4433"
export CV_VERIFY_SSL="false"
export CV_TIMEOUT="60"
export CV_TOKEN_FILE="$HOME/dev/cv-healthcheck/.token"
```

Load it before running CLI commands, scripts, or the Flask UI:

```bash
source ~/.cv-healthcheck-env
```

Create the project-local token file:

```bash
cd ~/dev/cv-healthcheck
printf '%s\n' 'plain-token-value' > .token
chmod 600 .token
```

The `.token` file may contain plain text or JSON:

```json
{"access_token": "plain-token-value", "refresh_token": "optional-refresh-token"}
```

Verify the token file is configured and present:

```bash
test -n "$CV_TOKEN_FILE" && test -f "$CV_TOKEN_FILE" && ls -l "$CV_TOKEN_FILE"
```

Authentication currently uses the `Authtoken` header for known Reports Plus and API ping tests. The existing `cv-topology` project uses `Authorization: Bearer`; cv-healthcheck is structured so a future auth-header option can be added if needed.

A shared login helper exists outside this repository:

```bash
export CV_BASE_URL="https://example:4433"
export CV_USERNAME="admin"
export CV_PASSWORD_B64="$(printf '%s' 'password' | base64 -w 0)"
source ~/dev/scripts/cv-env.sh
```

This retrieves a fresh `CV_TOKEN` into the current shell and does not print the token.

Verify API connectivity:

```bash
scripts/probe_api.sh
```

Verify the proven Reports Plus metadata endpoint:

```bash
scripts/probe_dataset_metadata.sh 979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4
```

Verify the proven Reports Plus dataset data endpoint:

```bash
scripts/probe_dataset_data.sh 979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4
```

## Phase 2: Reports Plus Discovery

Reports Plus discovery moves cv-healthcheck from a single known dataset toward a local inventory of Reports Plus reports and datasets.

Reports Plus discovery and catalog endpoints require an `Authtoken` issued by `POST /commandcenter/api/Login`. The current `.token` value can work for `/commandcenter/api` while returning HTTP 401 `Unauthenticated` for Reports Plus inventory endpoints.

Safe manual login-token workflow:

```bash
source ~/.cv-healthcheck-env
cd ~/dev/cv-healthcheck

export CV_USERNAME="your-username"
export CV_PASSWORD_B64="$(printf '%s' 'your-password' | base64 -w 0)"

curl -k -sS \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "{\"username\":\"${CV_USERNAME}\",\"password\":\"${CV_PASSWORD_B64}\"}" \
  "${CV_BASE_URL%/}/commandcenter/api/Login" > /tmp/cv-healthcheck-login.json

python - <<'PY'
import json
from pathlib import Path

body = json.loads(Path("/tmp/cv-healthcheck-login.json").read_text())
token = body.get("token")
if not token:
    raise SystemExit("Login response did not include token")
Path(".login_token").write_text(token + "\n")
PY

chmod 600 .login_token
export CV_LOGIN_TOKEN="$(cat .login_token)"
unset CV_USERNAME CV_PASSWORD_B64
rm -f /tmp/cv-healthcheck-login.json
```

Then test Reports Plus report and dataset inventory with the Login-issued token:

```bash
scripts/probe_reports_with_login_token.sh
scripts/probe_datasets_with_login_token.sh
```

The `.login_token` file is local-only and must not be committed.

List Reports Plus reports as formatted JSON:

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
cv-healthcheck reportsplus reports
```

Show a compact report inventory summary:

```bash
cv-healthcheck reportsplus reports --summary
```

Summary columns:

- `reportId`
- `reportName`
- `guid`
- `deployed`
- `viewable`
- `editable`
- `isMetrics`

List Reports Plus datasets as formatted JSON:

```bash
cv-healthcheck reportsplus datasets
```

Show a compact dataset inventory summary:

```bash
cv-healthcheck reportsplus datasets --summary
```

When `CV_LOGIN_TOKEN` is set, inventory commands use it. Otherwise they use project-local `.login_token` when present. If neither exists, they fall back to the configured `.token`; Reports Plus inventory calls are expected to fail with HTTP 401 in that mode.

Build local Reports Plus catalog files:

```bash
cv-healthcheck reportsplus catalog reports
cv-healthcheck reportsplus catalog datasets
cv-healthcheck reportsplus catalog all
```

Successful catalog calls write local JSON catalogs and summaries:

```text
data/catalog/reports.json
data/catalog/datasets.json
data/catalog/reports_summary.json
data/catalog/datasets_summary.json
data/catalog/health_candidates.json
```

Raw catalog files contain:

- `collected_at`
- `source_endpoint`
- `record_count`
- `records`

Summary files extract stable fields from the raw Reports Plus inventory and add a simple heuristic `relevance` tag such as `Storage`, `Jobs`, `SLA`, `Audit`, `Security`, `Infrastructure`, `Tenant`, `Metrics`, or `Unknown`. These tags are only discovery aids for future healthcheck design; they are not health rules.

Prioritize local healthcheck candidates from generated catalog summaries:

```bash
cv-healthcheck reportsplus catalog prioritize
cv-healthcheck reportsplus catalog show-priority
```

This writes:

```text
data/catalog/health_candidate_priority.json
```

Priority is heuristic and transparent. It favors SLA, failed or backup jobs, storage capacity, infrastructure utilization, readiness, MediaAgent/library/DDB signals, and audit/security candidates. It does not implement health rules.

Validate whether prioritized dataset candidates can execute safely:

```bash
cv-healthcheck reportsplus catalog validate-candidates --priority HIGH --limit 5
cv-healthcheck reportsplus catalog show-validation
```

Use `--all` to include all priorities. Validation writes:

```text
data/catalog/execution_validation.json
```

Validation statuses:

- `EXECUTABLE`: dataset data endpoint returned HTTP 200 with fields and a valid record set, including an empty set.
- `NEEDS_PARAMS`: required dataset parameters were present but missing safe literal/default values.
- `FAILS`: endpoint returned an error or an invalid response.
- `SKIPPED`: candidate is not a dataset or has no dataset GUID.

Generated catalog JSON files are local runtime artifacts and are not committed.

## Phase 2.4: Lab Readiness Baseline

Lab readiness summarizes whether the current lab has enough discovered and executable data to continue toward healthcheck rule development. It is a baseline assessment only: it does not implement health rules, does not create a database, and does not store credentials.

Run the readiness assessment:

```bash
cv-healthcheck lab readiness
cv-healthcheck lab readiness --json
```

The assessment writes the latest local result to:

```text
data/labreadiness/latest.json
```

Readiness states:

- `NOT_READY`: base API or Reports Plus inventory is not reachable.
- `READY_FOR_DISCOVERY`: APIs are reachable, but dataset execution validation is not available.
- `READY_FOR_DATA_EXECUTION`: discovery and dataset execution work, but operational lab activity is incomplete.
- `READY_FOR_HEALTH_RULE_TESTING`: enough operational evidence exists to begin health-rule testing.

The baseline currently uses live API reachability, existing Reports Plus catalog files, existing execution validation output, and conservative operational activity indicators. Unknown object counts remain explicit until a proven source is mapped.

## CLI

Install for local development:

```bash
python -m pip install -e .
```

Activate the development environment and load the lab settings:

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
```

Ping the API:

```bash
cv-healthcheck api ping
```

Fetch Reports Plus dataset metadata:

```bash
cv-healthcheck reportsplus metadata --dataset-guid 979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4
```

Fetch Reports Plus dataset data:

```bash
cv-healthcheck reportsplus data \
  --dataset-guid 979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4 \
  --fields "[MonthStart],[Added],[Removed],[Total]" \
  --limit 100 \
  --parameter showDeconfigClients=0 \
  --parameter includePsuedoClients=0
```

## Flask UI

Start the operational-style Flask UI:

```bash
./start.sh
./start.sh DEBUG
```

`start.sh` loads `~/.cv-healthcheck-env` when present, stops previous `python run.py` or `flask run` instances, generates a fresh `CV_SECRET_KEY`, sets `CV_LOG_LEVEL`, activates `venv`, ensures runtime directories exist, and starts the app with:

```bash
flask run --host="${CV_WEB_HOST}" --port="${CV_WEB_PORT}"
```

Defaults are `CV_WEB_HOST=0.0.0.0`, `CV_WEB_PORT=5001`, and log level `INFO`. Override the host or port by exporting `CV_WEB_HOST` or `CV_WEB_PORT` before running the script.

For manual development, run the UI on port 5001. The `cv-topology` project may use port 5000, so cv-healthcheck can use 5001 during lab work:

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
flask --app cvhealthcheck.web.app run --debug --port 5001
```

Pages:

- `/`
- `/api/test`
- `/reportsplus/reports`
- `/reportsplus/reports/<report_id_or_guid>`
- `/reportsplus/datasets`
- `/reportsplus/dataset/<dataset_guid>`
- `/reportsplus/data/<dataset_guid>`
- `/reportsplus/health-candidates`
- `/reportsplus/execution-validation`
- `/lab-readiness`
