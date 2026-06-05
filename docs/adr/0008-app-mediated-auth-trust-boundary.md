# ADR-0008: cv-healthcheck is the trust boundary for AI/CommServe access (app-mediated auth, Flavour 1)

Status: Accepted
Supersedes: the AI-holds-token model (the direct MCP probe and the
  .login_token / CV_LOGIN_TOKEN_FILE token path)
Related: ADR-0007 (environment), future ADR — RBAC over the app/MCP interface (see Deferred)

## Context
The MCP/AI layer needs CommServe data to assemble reports. The question is how the
CommServe token reaches it. Two models were considered:

- AI holds a CommServe token and calls the CommServe directly (the current probe).
- The AI holds no token, calls the app, and the app calls the CommServe (app-mediated).

The driving concern is security, not convenience. An AI principal that holds a live
CommServe token and can call the CommServe directly is privileged to whatever that
token allows, with no enforceable boundary between it and the backup environment.

Current state on disk (confirmed read-only, branch
feature/basic-healthcheck-report-output):
- The token lives in the Flask **session** — single-slot, request-scoped cookie,
  read via get_current_token()/_current_token() (shared.py:86). There is no
  process-level token store and no get_active_token() seam today.
- The existing probe (mcp/server.py) is the AI-holds-token model: _probe_token()
  reads CV_LOGIN_TOKEN/.login_token/.token and calls the CommServe directly. It is
  currently uncommitted.
- The internal GET seam _api_client().get(path) (shared.py:89 → api_client.py:65)
  exists but is dormant — no route exposes it.
- There is no CSRF middleware; login_required 302-redirects a cookieless caller, so a
  sibling MCP process is anonymous to every existing route.
- Redaction (_redact_user_descriptions) lives only in the MCP probe.

## Decision
cv-healthcheck is the trust boundary between the AI/MCP layer and the CommServe.

1. The AI/MCP layer never holds a CommServe token and never calls the CommServe
   directly. It calls an internal endpoint on the app, authenticated by a shared
   secret both processes obtain from ~/.cv-healthcheck-env (the wrapper scripts source
   it into the environment; the app reads it via env, not the file directly). The
   endpoint additionally rejects any request whose request.remote_addr is not
   127.0.0.1 — defense-in-depth, not the primary control (see Consequences).
2. The app makes the CommServe call with its own held token, applies shared
   redaction, and returns the result. Redaction moves out of the MCP module into a
   shared module so the app-mediated path cannot return raw data.
3. The app holds **a live token in memory while connected** — Flavour 1. No CommServe
   credential (password or token) is stored at rest. The token is minted by a live
   Connect action (operator types the password); nothing about the CommServe identity
   is written to disk.
4. The token is read through a get_active_token() seam that **replaces** the existing
   _current_token() read (it does not sit beside it — there must be one read seam, not
   two). It is a single slot today, so a multi-user store can replace it later without
   disturbing the endpoint, MCP, or redaction.
5. Token expiry is **visible, not silent**: a dead held token surfaces as
   "disconnected — reconnect" on the connection UI, and the internal endpoint returns
   a clean "expired" signal rather than a bare 401. This lands on existing pieces —
   CommvaultApiClient.get already surfaces status_code, and /api/auth/status already
   carries connection state — so no new machinery is required to interpret a held-token
   401 as expired.
6. The internal endpoint contract carries an explicit **acting-principal** and
   **requested-capability** from day one. Today the principal is always the single
   operator and the capability is always read; the fields exist so authorization can
   be enforced later at one site without an interface redesign.

## Rationale
The security rationale is primary and ages well: deprivileging the AI to only what the
app's interface exposes makes the app — not the AI — the enforcement point for what can
reach the CommServe. Holding a live token in memory (rather than a CommServe credential
at rest) avoids any encryption-key-custody problem and preserves "no CommServe
credential on disk." The UX benefit (no terminal step) is a side effect, not the reason.

Two secrets, deliberately different in value: the **CommServe credential** stays off
disk entirely (Flavour 1's core claim); the **loopback shared secret** is a new on-disk
credential, but it gates only a loopback endpoint, not the CommServe, and is the lower-
value of the two. The principle "no CommServe credential at rest" is intact; the shared
secret on disk is not a contradiction of it.

Flavour 1 over Flavour 2 (encrypted per-user service accounts): Flavour 1 holds only a
short-lived token minted at Connect, never a password. Flavour 2 is deferred to if/when
this becomes multi-user and layers onto the same connection page later.

## Consequences
- **The token store is single-process-scoped.** An in-memory slot lives in one process;
  the session-cookie model it replaces was process-agnostic. Today's single `flask run`
  worker is fine, but the debug reloader (parent+child) and any future multi-worker
  deployment (e.g. gunicorn) reintroduce cross-process token-sharing — which
  get_active_token() alone does NOT solve. This is an accepted constraint of the current
  single-operator scope, not a solved problem; a multi-worker move must revisit it.
- The app must hold a token reachable **outside** a request context. This is a real
  change from today's session-cookie-only model and is the core of the build that
  follows this ADR.
- A live CommServe token sits in app memory while connected — a deliberate, accepted
  tradeoff, lighter than storing a password.
- **Loopback enforcement is a request-level check, not a kernel-level guarantee.** The
  app binds 0.0.0.0 (start.sh) and a single Flask app cannot socket-bind one route to
  127.0.0.1 while others stay on 0.0.0.0. Enforcement is therefore an in-request
  remote_addr == 127.0.0.1 check; the shared secret is the actual authenticator, and
  loopback is defense-in-depth. (Re-binding the whole app or a second listener were
  considered and judged disproportionate for single-operator dev use.)
- A new internal endpoint is introduced. Because CSRF is absent and login_required
  cannot be met by a cookieless caller, it authenticates the sibling process via the
  shared secret, not cookies.
- The AI-holds-token model is superseded. The uncommitted probe is then a
  commit-as-is-then-retire vs fold-into-supersede decision — which accepting this ADR
  triggers.
- Relocating redaction touches the probe's only call site.

## Deferred (future ADR)
RBAC over the app/MCP interface — whether "may author a report" is a **Commvault**
permission (read off the token's role) or a **cv-healthcheck** permission (an app-side
roles store), and the move to Flavour 2 / multi-user. Out of scope here. The
principal/capability fields on the endpoint and the get_active_token() seam are placed
specifically so this can be decided and built later without reopening this interface.
