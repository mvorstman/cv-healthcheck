#!/usr/bin/env bash
# ADR-0008 E: the probe is app-mediated — the MCP process holds NO CommServe token.
# It only needs CV_INTERNAL_SECRET (the loopback-endpoint shared secret), which comes
# from ~/.cv-healthcheck-env. The direct .login_token / CV_LOGIN_TOKEN_FILE wiring is
# removed; the .login_token file is simply no longer read.
source /home/michiel/.cv-healthcheck-env
exec /home/michiel/dev/cv-healthcheck/venv/bin/cv-healthcheck-mcp "$@"
