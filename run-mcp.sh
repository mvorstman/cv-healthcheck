#!/usr/bin/env bash
source /home/michiel/.cv-healthcheck-env
export CV_LOGIN_TOKEN_FILE="/home/michiel/dev/cv-healthcheck/.login_token"
exec /home/michiel/dev/cv-healthcheck/venv/bin/cv-healthcheck-mcp "$@"
