# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-02 (ADR-0008 app-mediated auth / trust boundary — **COMPLETE end to end, proven live**)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `7214ea7` — Add Connections page: live status + connect/disconnect (ADR-0008 B, complete)
**Test status:** **862 passing** under `pytest` and `python -m pytest`.

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0008-app-mediated-auth-trust-boundary.md`** — the governing ADR for the auth model just built; *Accepted* and now fully implemented.
5. **`docs/adr/0007-declarative-single-object-source-and-environment-migration.md`** — the prior complete arc (environment on the uniform declarative path).
6. The most recent CHANGELOG entries (2026-06-02): the ADR-0008 build, components A–E + the Connections page.

---

## What was just completed

**ADR-0008 (app-mediated auth / trust boundary) is COMPLETE end to end.** cv-healthcheck is now the trust boundary between the AI/MCP layer and the CommServe:

- The AI/MCP layer **holds no CommServe token** and reaches the CommServe **only** via `POST /internal/commserve` (shared-secret + loopback-`127.0.0.1` guarded, fail-closed).
- The app holds the token **in memory only** (Flavour 1 — no credential at rest) and **out of the session cookie**; the auth gate is keyed off the in-process store (`cvhealthcheck.token_store`).
- Redaction is shared and **app-side** (`cvhealthcheck.redaction`) — the app-mediated path can't return raw `description`.
- The operator has a real **`/connections`** status/connect/disconnect surface (and a "Connections" sidebar nav link).

**Commit trail:** ADR accept `600c27e` · probe baseline (superseded) `e193e4b` · shared redaction `955db50` · token store `7fb87e4` · login→store wiring `65d7e2b` · loopback endpoint `9e189e3` · probe retired to the endpoint `9f8e205` · de-cookie + gate-on-store `270752a` · Connections page `7214ea7`.

---

## Operator setup that must persist (don't lose this)

- **`CV_INTERNAL_SECRET`** lives in **`~/.cv-healthcheck-env`** (sourced into the env by both `start.sh` and `run-mcp.sh`). The internal endpoint **fails closed (503) without it**, and the MCP probe can't authenticate to the app without it. Same value must be visible to both processes.
- The in-memory token store **empties on app restart** (single-process, by design) → the operator **re-logs-in via `/connections`** (or the connect modal) to refill it. A restart with no login reads as honestly *disconnected* (no false logged-in, no silent fail) — verified.
- The old direct-probe wiring is gone: `run-mcp.sh` no longer exports a `CV_LOGIN_TOKEN_FILE`; `.login_token` is no longer read by the MCP path (the CLI `scripts/probe_*_with_login_token.sh` Reports-Plus tools still use it — unrelated).

---

## Single recommended next action

ADR-0008 is done; there is **no forced next step**. Open items, all *named and deferred* (none are in ADR-0008) — pick per priority:

1. **Real-browser lock-out confirm (recommended, quick):** `./start.sh`, log in via `/connections` → confirm connected + collect works; restart without logging in → confirm the honest "disconnected — reconnect" (not a false logged-in / silent fail). Test-client simulation already passed; this is the human eyeball.
2. **Branch review/merge** — `feature/basic-healthcheck-report-output` is well ahead of `main`; consider a review + merge + tag now that ADR-0007 and ADR-0008 are both complete (operator's call).
3. **RBAC over the app/MCP interface** (future ADR) — whether "may author a report" is a Commvault permission (off the token's role) or a cv-healthcheck permission (app-side roles). The `/internal/commserve` contract already carries `principal` + `capability` so enforcement drops in at one site.
4. **Reactive expiry** — flip the store to `expired` on a CommServe 401 from the endpoint; needs the identity / auth-failure distinction so one unauthorized request can't nuke the connection.
5. **Flavour 2** (encrypted stored service-account credentials / multi-user) — layers onto `/connections` + the `get_active_token()` seam without redoing the store or endpoint.
6. **Oversized-response tiering / compute-at-the-data** — the parked >1MB lesson; only when a genuinely large dataset shows up.
7. **Connections-page polish** — auto-detect a stale/emptied store without a manual page refresh (small UX nicety).

---

## Other notes

- ADR-0008 is *Accepted* and fully implemented. Several earlier ADR Status lines (0004 parent, 0006) are *Proposed* / decision-blocked — code honors them; ratification is the operator's call.
- `~/.cv-healthcheck-env` also holds `CV_BASE_URL=https://192.168.182.129:4433` and `CV_VERIFY_SSL=false` for the lab (self-signed). The Connections page shows these read-only (env-configured; editing them is a separate future item).
