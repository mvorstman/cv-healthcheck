#!/usr/bin/env bash
set -euo pipefail

: "${CV_BASE_URL:?Set CV_BASE_URL first}"
: "${1:?Usage: probe_dataset_metadata.sh DATASET_GUID}"

TOKEN_FILE="${CV_TOKEN_PATH:-.token}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOKEN="$(PYTHONPATH="${PROJECT_ROOT}/src" python -c 'from cvhealthcheck.auth import load_token; print(load_token("'"${TOKEN_FILE}"'") or "")')"

curl -k -sS \
  -H "Authtoken: ${TOKEN}" \
  -H "Accept: application/json" \
  "${CV_BASE_URL%/}/commandcenter/api/cr/reportsplusengine/datasets/$1"
