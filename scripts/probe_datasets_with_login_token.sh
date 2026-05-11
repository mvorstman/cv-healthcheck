#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CV_BASE_URL:-}" ]]; then
  echo "ERROR: CV_BASE_URL is not set. Source ~/.cv-healthcheck-env first." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOGIN_TOKEN_FILE="${CV_LOGIN_TOKEN_FILE:-${PROJECT_ROOT}/.login_token}"
TIMEOUT="${CV_TIMEOUT:-${CV_TIMEOUT_SECONDS:-60}}"
ENDPOINT="/commandcenter/api/cr/reportsplusengine/datasets"
URL="${CV_BASE_URL%/}${ENDPOINT}"

if [[ -n "${CV_LOGIN_TOKEN:-}" ]]; then
  LOGIN_TOKEN="${CV_LOGIN_TOKEN}"
elif [[ -f "${LOGIN_TOKEN_FILE}" ]]; then
  LOGIN_TOKEN="$(tr -d '\r\n' < "${LOGIN_TOKEN_FILE}")"
else
  echo "ERROR: set CV_LOGIN_TOKEN or create ${LOGIN_TOKEN_FILE}" >&2
  exit 2
fi

if [[ -z "${LOGIN_TOKEN}" ]]; then
  echo "ERROR: login token is empty" >&2
  exit 2
fi

CURL_OPTS=(-sS --connect-timeout "${TIMEOUT}" --max-time "${TIMEOUT}")
if [[ "${CV_VERIFY_SSL:-false}" != "true" ]]; then
  CURL_OPTS+=(-k)
fi

echo "Testing endpoint: ${URL}"
if ! RESPONSE="$(curl "${CURL_OPTS[@]}" \
  -H "Authtoken: ${LOGIN_TOKEN}" \
  -H "Accept: application/json" \
  -w $'\nHTTP_STATUS:%{http_code}' \
  "${URL}")"; then
  echo "ERROR: curl could not reach Reports Plus dataset inventory endpoint" >&2
  exit 1
fi

STATUS="${RESPONSE##*HTTP_STATUS:}"
BODY="${RESPONSE%HTTP_STATUS:*}"

echo "HTTP status: ${STATUS}"
PYTHON_BODY="${BODY}" python - <<'PY'
import json
import os

raw = os.environ.get("PYTHON_BODY", "")
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("Response snippet:", raw.replace("\n", " ")[:240])
    raise SystemExit(0)

datasets = []
if isinstance(data, dict):
    value = data.get("dataSet") or data.get("datasets") or data.get("data")
    if isinstance(value, list):
        datasets = value
elif isinstance(data, list):
    datasets = data

print(f"datasets: {len(datasets)} records")
for dataset in datasets[:5]:
    if not isinstance(dataset, dict):
        continue
    nested = dataset.get("dataSet")
    if not isinstance(nested, dict):
        nested = {}
    dataset_id = dataset.get("dataSetId") or nested.get("dataSetId") or dataset.get("id") or ""
    name = dataset.get("dataSetName") or nested.get("dataSetName") or dataset.get("name") or ""
    guid = dataset.get("dataSetGuid") or nested.get("dataSetGuid") or dataset.get("guid") or ""
    print(f"- {dataset_id} {name} {guid}".rstrip())
PY

if [[ "${STATUS}" != 2* ]]; then
  exit 1
fi
