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

Run the development UI on port 5001. The `cv-topology` project may use port 5000, so cv-healthcheck should use 5001 during lab work:

```bash
source venv/bin/activate
source ~/.cv-healthcheck-env
flask --app cvhealthcheck.web.app run --debug --port 5001
```

Pages:

- `/`
- `/api/test`
- `/reportsplus/dataset/<dataset_guid>`
- `/reportsplus/data/<dataset_guid>`
