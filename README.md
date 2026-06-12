# cv-healthcheck

Automated Commvault HealthCheck and analytics exploration tooling.

This project is standalone. It does not import from or integrate with `cv-topology` — a frozen reference/prototype platform that may be inspected for Commvault API, Flask, UI, database, topology, and compliance patterns, but where active development should not happen.

## Scope

Initial focus:

- Command Center API connectivity
- Reports Plus dataset metadata access
- Reports Plus dataset data querying
- Lightweight Flask exploration UI
- CLI access to the same reusable service layer

## Strategic Direction

cv-healthcheck is shaped around three operating modes:

- Daily Reporting: recurring operational reporting from Reports Plus / Metrics, email, and trend datasets.
- Quick HealthCheck: fast, minimally invasive assessment using Metrics trend data, REST collection, and uploaded snapshots.
- Full HealthCheck: comprehensive, evidence-driven analysis across Metrics, REST APIs, uploaded snapshots, and expanded collectors.

The platform must not assume direct access to customer CommServe systems: the expected model is central analysis over accessible Metrics / Reports Plus data plus customer-side REST collectors that upload structured snapshots or evidence artifacts.

Direction detail (operating-mode evolution, S3 evidence transport, distributed collection) lives in [ROADMAP.md](ROADMAP.md).

## Data Sources & Collection Strategy

Reports Plus / Metrics is a primary strategic data source — especially valuable for trends, historical reporting, SLA analysis, growth and capacity analysis, operational summaries, and multi-CommCell reporting. Private Metrics servers are expected to become major long-term sources. Because dataset GUIDs and report IDs vary across environments (report names are more stable than IDs), report-composition mapping and dataset-execution validation matter more than hardcoded IDs.

Preferred collection order:

1. REST APIs
2. Reports Plus datasets
3. Existing reports
4. Uploaded exports/artifacts
5. SQL only as a last resort

Avoid unsupported DB-access assumptions, hardcoded environment assumptions, tight coupling to one lab, and assuming reports are identical across environments.

## High-Level Architecture

Responsibilities are kept separate (full boundaries in [PROMPT.txt](PROMPT.txt) → ARCHITECTURE PRINCIPLES):

- **Collection** — REST / Reports Plus collectors produce structured artifacts and stay reusable and transportable.
- **Normalization** — sources normalize to a canonical artifact model shared across acquisition methods.
- **Evaluation** — row-scope rules score table subjects ([ADR 0010](docs/adr/0010-row-scope-evaluation-rules.md)); evaluation is separate from collection.
- **Reporting / UI** — Quick HC composes customer-facing reports; Flask routes stay thin.

Quick HC is the customer-facing report-composition surface. Its architecture — product areas, subjects, the registry/tile framework, routing, report composition, and business-state separation — is documented in [docs/architecture/quickhc.md](docs/architecture/quickhc.md). Two subjects have their own pipelines: [Security Assessment](docs/subjects/security_assessment.md) and [License Summary](docs/subjects/license_summary.md).

## Quick Start

```bash
python -m pip install -e .
source venv/bin/activate
source ~/.cv-healthcheck-env
./start.sh                       # Flask UI on http://127.0.0.1:5001
```

Then open `http://127.0.0.1:5001/quick-hc`. Lab connection and token setup are in [docs/lab_environment.md](docs/lab_environment.md).

## Configuration

Set the Commvault Command Center base URL:

```bash
export CV_BASE_URL=https://192.168.182.129:4433
```

**Web app / MCP auth does not use a token file.** Under ADR-0008 the app holds
a live token in memory, minted by the operator's Connect action (header pill);
the AI/MCP layer reaches the CommServe only through the app's loopback endpoint
(`CV_INTERNAL_SECRET`). No CommServe credential is stored at rest.

**CLI inventory commands only:** a `.token` file at the project root remains the
auth source for the standalone CLI (`cv-healthcheck reportsplus …`, lab probes),
either plain or JSON:

```text
plain-token-value
```

```json
{"access_token": "plain-token-value"}
```

It may also contain a JSON `refresh_token`; the CLI and lab probes use `access_token`.

SSL verification is enabled by default. Disable it only for isolated lab usage; the clients log a warning when it is off:

```bash
export CV_VERIFY_SSL=false
```

Lab connection, SSL, token-file, environment-file, the shared login helper, and the connectivity probe scripts are documented in [docs/lab_environment.md](docs/lab_environment.md) — the lab is Commvault v11.40 at `https://192.168.182.129:4433` (self-signed).

## CLI

Install for local development and load the lab settings:

```bash
python -m pip install -e .
source venv/bin/activate
source ~/.cv-healthcheck-env
```

Core commands:

```bash
cv-healthcheck api ping                 # ping the API
cv-healthcheck quickhc commcell         # CommCell identity / version (Quick HC CommCell subject)
cv-healthcheck reportsplus metadata --dataset-guid <guid>

cv-healthcheck reportsplus data \
  --dataset-guid <guid> \
  --fields "[MonthStart],[Added],[Removed],[Total]" \
  --limit 100 \
  --parameter showDeconfigClients=0 \
  --parameter includePsuedoClients=0
```

### Reports Plus inventory & catalog

Reports Plus inventory endpoints require a Login-issued `Authtoken` — see [docs/lab_environment.md](docs/lab_environment.md) (Reports Plus inventory login token). When `CV_LOGIN_TOKEN` is set, inventory commands use it; otherwise project-local `.login_token`; otherwise the configured `.token`, which returns HTTP 401 for inventory endpoints.

List reports/datasets (JSON or `--summary`):

```bash
cv-healthcheck reportsplus reports
cv-healthcheck reportsplus reports --summary
cv-healthcheck reportsplus datasets
cv-healthcheck reportsplus datasets --summary
```

Summary columns: `reportId`, `reportName`, `guid`, `deployed`, `viewable`, `editable`, `isMetrics`.

Build local catalog files:

```bash
cv-healthcheck reportsplus catalog reports
cv-healthcheck reportsplus catalog datasets
cv-healthcheck reportsplus catalog all
```

Writes `data/catalog/{reports,datasets,reports_summary,datasets_summary,health_candidates}.json`. Summary files add a heuristic `relevance` tag (a discovery aid, not a health rule).

Prioritize and validate healthcheck candidates:

```bash
cv-healthcheck reportsplus catalog prioritize
cv-healthcheck reportsplus catalog show-priority
cv-healthcheck reportsplus catalog validate-candidates --priority HIGH --limit 5   # --all for every priority
cv-healthcheck reportsplus catalog show-validation
```

Writes `data/catalog/health_candidate_priority.json` and `data/catalog/execution_validation.json`. Validation statuses: `EXECUTABLE` (HTTP 200 with a valid record set, including empty), `NEEDS_PARAMS` (required params lacked safe defaults), `FAILS` (error / invalid response), `SKIPPED` (not a dataset / no GUID). Generated catalog files are local runtime artifacts and are not committed.

### Lab readiness

```bash
cv-healthcheck lab readiness
cv-healthcheck lab readiness --json
```

Writes `data/labreadiness/latest.json`. Readiness states: `NOT_READY` (base API / inventory unreachable), `READY_FOR_DISCOVERY` (APIs reachable, no dataset-execution validation), `READY_FOR_DATA_EXECUTION` (discovery + execution work, operational activity incomplete), `READY_FOR_HEALTH_RULE_TESTING` (enough operational evidence to begin). It is a baseline assessment only: it implements no health rules, creates no database, and stores no credentials.

## Web UI

Start the operational-style Flask UI:

```bash
./start.sh
./start.sh DEBUG
```

`start.sh` loads `~/.cv-healthcheck-env` when present, stops previous `python run.py` / `flask run` instances, generates a fresh `CV_SECRET_KEY`, sets `CV_LOG_LEVEL`, activates `venv`, ensures runtime directories exist, and runs `flask run --host="${CV_WEB_HOST}" --port="${CV_WEB_PORT}"`. Defaults: `CV_WEB_HOST=0.0.0.0`, `CV_WEB_PORT=5001`, log level `INFO`.

For manual development (cv-topology may use port 5000, so cv-healthcheck uses 5001):

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
flask --app cvhealthcheck.web.app run --debug --port 5001
```

Customer-facing pages:

- `/` — redirects to `/quick-hc`
- `/quick-hc` — Quick HC workspace (subject tiles, source selection, report composition)
- `/quick-hc/commcell` — CommCell identity detail
- `/quick-hc/report` — composed customer-facing report

## Documentation Index

- **README.md** — what the project is and how to run it (this file).
- [ROADMAP.md](ROADMAP.md) — strategic direction: vision, and initiatives Now / Next / Later.
- [PROMPT.txt](PROMPT.txt) — how we operate: decision hierarchy, decision-making, engineering & validation rules, the documentation model, and the session workflow.
- [HANDOVER.md](HANDOVER.md) — current working state and the single recommended next action (overwritten each session).
- [CHANGELOG.md](CHANGELOG.md) — append-only history.
- [docs/architecture/quickhc.md](docs/architecture/quickhc.md) — Quick HC architecture (product surface, registry/tile framework, routing, report composition, business state).
- [docs/subjects/security_assessment.md](docs/subjects/security_assessment.md) — Security Assessment subject (report 336; multi-source canonical pipeline).
- [docs/subjects/license_summary.md](docs/subjects/license_summary.md) — License Summary subject (CSV / HTML / XLSX / REST-206 pipeline).
- [API_MAPPING.md](API_MAPPING.md) — validated collection/source catalog: what can be collected, from where, with which auth/params, and whether proven.
- [DATA_SOURCE_MAPPING.md](DATA_SOURCE_MAPPING.md) — operating-mode source strategy: which datasource per subject across Quick HC / Daily / Full.
- [docs/PATTERNS.md](docs/PATTERNS.md) — project-wide patterns and standing conventions to know before adding code.
- [docs/lab_environment.md](docs/lab_environment.md) — lab setup, connection, token, and realism.
- [docs/data_flow_audit.md](docs/data_flow_audit.md) — on-disk data-flow audit.
- [docs/adr/](docs/adr/) — Architecture Decision Records (0001–0014). Required reading before touching the areas they govern.
