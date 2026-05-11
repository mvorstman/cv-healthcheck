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

SSL verification is disabled by default for lab usage. Enable it with:

```bash
export CV_VERIFY_SSL=true
```

## CLI

Install for local development:

```bash
python -m pip install -e .
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

Run the development UI:

```bash
flask --app cvhealthcheck.web.app run --debug
```

Pages:

- `/`
- `/api/test`
- `/reportsplus/dataset/<dataset_guid>`
- `/reportsplus/data/<dataset_guid>`

