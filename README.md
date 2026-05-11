# cv-healthcheck

Automated Commvault HealthCheck and analytics exploration tooling.

This project is standalone. It does not import from or integrate with `cv-topology`.

## Scope

Initial focus:

- Command Center API connectivity
- Reports Plus dataset metadata access
- Reports Plus dataset data querying
- Lightweight Flask exploration UI
- CLI access to the same reusable service layer

## Architecture Documents

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

SSL verification is disabled by default for lab usage. Enable it with:

```bash
export CV_VERIFY_SSL=true
```

## Lab Environment Connection Setup

The lab Command Center and Web Server are available at:

```text
https://192.168.182.129:4433
```

Use the direct IP for Rocky VM testing. The gateway name is `gw02`, but DNS resolution for `gw02` may fail from Rocky. The lab uses a self-signed certificate, so SSL verification is disabled for local lab work. The known lab version is Commvault v11.40.

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
