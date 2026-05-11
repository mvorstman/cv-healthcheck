#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CV_BASE_URL:-}" ]]; then
  echo "ERROR: CV_BASE_URL is not set. Source ~/.cv-healthcheck-env first." >&2
  exit 2
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 DATASET_GUID" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOKEN_FILE="${CV_TOKEN_FILE:-${CV_TOKEN_PATH:-${PROJECT_ROOT}/.token}}"
TIMEOUT="${CV_TIMEOUT:-${CV_TIMEOUT_SECONDS:-60}}"
DATASET_GUID="$1"
ENDPOINT="${CV_BASE_URL%/}/commandcenter/api/cr/reportsplusengine/datasets/${DATASET_GUID}/data"

if [[ ! -f "${TOKEN_FILE}" ]]; then
  echo "ERROR: token file not found: ${TOKEN_FILE}" >&2
  exit 2
fi

TOKEN="$(PYTHONPATH="${PROJECT_ROOT}/src" python -c 'from cvhealthcheck.auth import load_token; print(load_token("'"${TOKEN_FILE}"'") or "")')"
if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: token file did not contain a usable access token: ${TOKEN_FILE}" >&2
  exit 2
fi

CURL_OPTS=(-sS --connect-timeout "${TIMEOUT}" --max-time "${TIMEOUT}")
if [[ "${CV_VERIFY_SSL:-false}" != "true" ]]; then
  CURL_OPTS+=(-k)
fi

echo "Testing endpoint: ${ENDPOINT}"
if ! RESPONSE="$(curl "${CURL_OPTS[@]}" \
  -G \
  -H "Authtoken: ${TOKEN}" \
  -H "Accept: application/json" \
  --data-urlencode "format=object" \
  --data-urlencode "includeOther=false" \
  --data-urlencode "fields=[MonthStart],[Added],[Removed],[Total]" \
  --data-urlencode "orderby=[MonthStart] Asc" \
  --data-urlencode "limit=15" \
  --data-urlencode "parameter.showDeconfigClients=0" \
  --data-urlencode "parameter.includePsuedoClients=0" \
  -w $'\nHTTP_STATUS:%{http_code}' \
  "${ENDPOINT}")"; then
  echo "ERROR: curl could not reach Reports Plus dataset data endpoint" >&2
  exit 1
fi
STATUS="${RESPONSE##*HTTP_STATUS:}"
BODY="${RESPONSE%HTTP_STATUS:*}"

if [[ "${STATUS}" == 2* ]]; then
  echo "SUCCESS: Reports Plus dataset data responded with HTTP ${STATUS}"
  printf '%s\n' "${BODY}"
else
  echo "ERROR: Reports Plus dataset data probe failed with HTTP ${STATUS}" >&2
  printf '%s\n' "${BODY}" >&2
  exit 1
fi
