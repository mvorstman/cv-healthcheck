#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CV_BASE_URL:-}" ]]; then
  echo "ERROR: CV_BASE_URL is not set. Source ~/.cv-healthcheck-env first." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOKEN_FILE="${CV_TOKEN_FILE:-${CV_TOKEN_PATH:-${PROJECT_ROOT}/.token}}"
TIMEOUT="${CV_TIMEOUT:-${CV_TIMEOUT_SECONDS:-60}}"

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

ENDPOINTS=(
  "/commandcenter/api"
  "/commandcenter/api/cr/reportsplusengine/datasets/979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4"
  "/commandcenter/api/cr/reportsplusengine/reports"
  "/commandcenter/api/cr/reportsplusengine/datasets"
)

AUTH_MODES=("Authtoken" "Bearer")

printf 'endpoint,auth_mode,http_status,snippet\n'
for endpoint in "${ENDPOINTS[@]}"; do
  url="${CV_BASE_URL%/}${endpoint}"
  for auth_mode in "${AUTH_MODES[@]}"; do
    if [[ "${auth_mode}" == "Authtoken" ]]; then
      header=("Authtoken: ${TOKEN}")
    else
      header=("Authorization: Bearer ${TOKEN}")
    fi

    if response="$(curl "${CURL_OPTS[@]}" \
      -H "${header[0]}" \
      -H "Accept: application/json" \
      -w $'\nHTTP_STATUS:%{http_code}' \
      "${url}")"; then
      status="${response##*HTTP_STATUS:}"
      body="${response%HTTP_STATUS:*}"
    else
      status="curl_failed"
      body="curl could not reach endpoint"
    fi

    snippet="$(printf '%s' "${body}" | tr '\r\n' '  ' | cut -c 1-160)"
    printf '%s,%s,%s,"%s"\n' "${endpoint}" "${auth_mode}" "${status}" "${snippet//\"/\"\"}"
  done
done
