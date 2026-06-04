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