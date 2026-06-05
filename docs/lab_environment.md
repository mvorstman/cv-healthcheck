Development and Commvault Lab Environment Context

Development Workflow

Primary workstation:

* MacBook
* VS Code
* iTerm2
* AI assistant (chat) used for:
    * brainstorming
    * architecture
    * API research
    * reverse engineering
    * troubleshooting
    * coding-agent handover generation

Actual implementation work is performed by a coding agent running on the Rocky VM.

Workflow:

AI assistant (chat)
  ↓
research / architecture / curl analysis
Coding agent on Rocky
  ↓
implementation
Rocky terminal
  ↓
validation/testing
GitHub
  ↓
commit/push

Note on tooling:

* The AI assistant (chat) layer is tool-agnostic — any chat-based assistant may be used.
* The coding agent layer is tool-agnostic — any terminal/IDE-based coding agent may be used.

Principle:

curl first
code second

⸻

Development Environment

MacBook:

* used only as frontend/interface
* VS Code Remote SSH frontend
* iTerm2 SSH frontend
* local git clones are optional reference copies only
* no authoritative execution on Mac

Rocky Linux VM:

* hostname: dev
* authoritative development machine
* all real code lives here
* all execution/testing happens here
* the coding agent runs here
* Git repositories here are authoritative

Authoritative project paths on Rocky:

~/dev/cv-topology
~/dev/cv-healthcheck

Python:

* Python 3.12
* virtualenv-based

Typical startup:

source venv/bin/activate

⸻

Flask Environment

Projects run simultaneously on different ports:

Project	Port
cv-topology	5000
cv-healthcheck	5001

cv-healthcheck Flask UI is intended primarily as:

* engineering UI
* API exploration UI
* diagnostics UI
* dataset exploration UI

Not initially as a production dashboard.

⸻

Commvault Lab Environment

Primary Command Center / REST API endpoint:

https://192.168.182.129:4433/commandcenter/api

Known gateway/web server:

gw02
192.168.182.129

Commvault version:

* v11.40

SSL:

* self-signed certificate
* SSL verification disabled for lab use

Preferred connectivity:

* use direct IPs instead of hostnames when possible
* hostname resolution may fail from Rocky

⸻

Authentication

Two authentication header styles are known and should both be supported.

Style 1 — Authtoken

Used successfully with Reports Plus APIs:

Authtoken: <token>

Style 2 — Bearer Token

Used by existing cv-topology project:

Authorization: Bearer <token>

⸻

Token Management

Token files:

.token
.refresh_token

.token may contain either:

Plain token string

<token>

JSON structure

{
  "access_token": "...",
  "refresh_token": "..."
}

Behavior requirements:

* support both formats
* automatic parsing
* token files are never committed to git

Token generation:

* Command Center
* user profile
* Access Tokens
* Add
* expiry: 365 days
* scope: All

401 responses usually mean:

* token expired
* token revoked

⸻

Reports Plus Discovery

Known working internal Reports Plus API base:

/commandcenter/api/cr/reportsplusengine/

Known working dataset endpoints:

/datasets/<dataset-guid>
/datasets/<dataset-guid>/data

Known proven dataset:

979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4

Known working parameters:

showDeconfigClients=0
includePsuedoClients=0

Known behavior:

* metadata accessible
* fields exposed
* parameters exposed
* SQL/stored procedure metadata exposed
* JSON output works
* orderby works
* limits work
* dataset queries work directly over REST

⸻

Architecture Principles

Preferred architecture:

Collector Layer
    ↓
Normalization Layer
    ↓
Health/Compliance Evaluation Layer
    ↓
UI/Reporting Layer

Key rules:

* separate collection from evaluation
* separate API inventory from health logic
* Flask routes should call reusable services
* avoid direct API calls inside UI routes
* avoid overengineering early
* keep collectors reusable
* JSON-compatible outputs preferred

Documentation structure:

* API_MAPPING.md = technical capability inventory
* HEALTHCHECK_MATRIX.md = operational health evaluation inventory

⸻

Connection & Token Setup

User-local environment file:

cp env.example ~/.cv-healthcheck-env

Recommended ~/.cv-healthcheck-env contents:

export CV_BASE_URL="https://192.168.182.129:4433"
export CV_VERIFY_SSL="false"
export CV_TIMEOUT="60"
export CV_TOKEN_FILE="$HOME/dev/cv-healthcheck/.token"

Load it before CLI commands, scripts, or the Flask UI:

source ~/.cv-healthcheck-env

Project-local token file:

cd ~/dev/cv-healthcheck
printf '%s\n' 'plain-token-value' > .token
chmod 600 .token

Verify the token file is present:

test -n "$CV_TOKEN_FILE" && test -f "$CV_TOKEN_FILE" && ls -l "$CV_TOKEN_FILE"

Shared login helper (outside this repo) — retrieves a fresh CV_TOKEN into the current shell without printing it:

export CV_BASE_URL="https://example:4433"
export CV_USERNAME="admin"
export CV_PASSWORD_B64="$(printf '%s' 'password' | base64 -w 0)"
source ~/dev/scripts/cv-env.sh

Connectivity probe scripts:

scripts/probe_api.sh
scripts/probe_dataset_metadata.sh <dataset-guid>
scripts/probe_dataset_data.sh <dataset-guid>

⸻

Lab Realism & Health-Rule Readiness

The current lab is intentionally minimal.

Current limitations:

* few or no completed backup jobs
* limited operational history
* minimal alerting activity
* limited DDB activity
* minimal SLA data
* minimal MediaAgent activity

Because of this:

* discovery work is valid
* API validation is valid
* dataset execution validation is valid
* health-rule conclusions are NOT yet representative

Before health-rule development:

* improve lab realism
* generate operational activity
* create backup history
* generate alerts/failures
* create realistic storage usage
* generate SLA trends

⸻

Reports Plus inventory login token

Reports Plus discovery/catalog endpoints require an Authtoken issued by POST /commandcenter/api/Login. The plain .token value can work for /commandcenter/api while returning HTTP 401 Unauthenticated for Reports Plus inventory endpoints.

Safe manual login-token workflow:

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

The .login_token file is local-only and must not be committed.

Then test Reports Plus report and dataset inventory with the Login-issued token:

scripts/probe_reports_with_login_token.sh
scripts/probe_datasets_with_login_token.sh

Inventory CLI precedence: when CV_LOGIN_TOKEN is set, inventory commands use it; otherwise project-local .login_token when present; otherwise the configured .token (Reports Plus inventory calls then return HTTP 401).