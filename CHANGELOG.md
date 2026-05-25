# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — sections for **Added / Changed / Fixed / Removed** where they apply, plus a short prose **Notes** section per entry for findings, root causes, architectural decisions, and gotchas worth preserving.

This file is append-only. Past entries are never deleted or rewritten — corrections are made by adding a new entry.

See `HANDOVER.md` for what to do next. See `README.md` for what the project is.

---

## 2026-06-04

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `c7a1a12`, plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (unchanged from session 3b).

Session 3c — short wrap-up session that closes out the source-building unification question. No code changes beyond comments.

### Added

- **`docs/adr/0001-source-building-fork.md`** — Architecture decision record for the γ4 outcome. The upload routing path is unified (`POST /quick-hc/<subject_id>/import` handles all subjects); the source-building path is intentionally not unified (`_legacy_builders` continues to serve the six system subjects whose view shapes the canonical schema can't represent). Full reasoning: alternatives considered (γ1/γ2/γ3 rejected), consequences (both preserved goals and accepted tradeoffs), references to the session 3 + 3b CHANGELOG entries and investigation reports, and revisit triggers (when to reopen).
- **`docs/adr/README.md`** — Sets up the ADR directory. Documents what an ADR is, when to add one, the required sections, and how to read existing ADRs from code annotations.

### Changed

- **In-code annotations in `src/cvhealthcheck/quickhc/subject_data_service.py`** at three sites pointing at ADR 0001:
  - The dispatch block inside `build_subject_initial_data` (around line 94 — comment above the `_load_from_canonical_store` call).
  - The `_legacy_loaders` function definition (around line 299).
  - The `_legacy_builders` function definition (around line 324).

  Each annotation is short (4-6 lines): a one-line pointer to the ADR plus the minimum context to understand why the fork is intentional. The detail lives in the ADR.

### Notes

- **γ4 decision rationale**: the canonical schema is frozen, and the legacy tile data uses section shapes (`counters`, `findings_grid`, `workload`, `chart_growth`) the schema can't carry. Sessions 3 and 3b both hit this wall. γ4 accepts the fork as honest reflection of two genuinely different shapes of tile data, not technical debt.
- **The annotations short-circuit re-derivation.** Without them, the next session that wonders why `_legacy_builders` still exists would repeat sessions 3 and 3b's investigation from scratch. The pattern is: comment in code → ADR → done.
- **Sessions 4 and 5 are unblocked.** Session 4 deletes the old upload routes. Session 5 replaces the unified route's branch-dispatch shim with data-driven dispatch. Both are independent of the source-building fork.

---

## 2026-06-03

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `11df86c`, plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (unchanged from session 3).

Session 3b of the unified-upload refactor — **STOP-and-report at the architectural assessment stage.** No code changes. One docs commit. The brief's Option γ plan cannot land cleanly without a companion architectural decision that the user needs to make.

### What happened

The session-3b brief was Option γ from the 2026-06-02 HANDOVER: move legacy on-disk reads into a fallback inside `_load_from_canonical_store`, return `CanonicalArtifact`, let `_build_generic_subject` render. Then delete `_legacy_builders` cleanly.

Before writing the adapter, I traced the legacy builder output vs. what `_build_generic_subject` + `artifact_to_view` would produce given a `CanonicalArtifact`. They diverge significantly:

- Legacy SA produces `counters` and `findings_grid` section types. The generic view producer doesn't.
- Legacy LS produces a `workload` section type. The generic view producer doesn't.
- Legacy CG produces a `chart_growth` section type. The generic view producer doesn't.
- Even simple subjects (environment) diff on subject-level fields the generic path doesn't synthesise: subtitle, fullUrl, per-source meta/status.
- The canonical schema is frozen, so we can't add these section types.

Per the brief's STOP-and-report rule, this session stopped at the inventory + architectural finding stage rather than writing an adapter that would produce the same proof 200 lines later.

### Inventory of legacy on-disk reads

Full inventory in `docs/refactor_unified_upload_session_3b_inventory.md` (Section A). Six file-based reads:

- `environment` → `data/catalog/rest/commserv.json`
- `security_assessment` → `data/catalog/security_assessment/latest.json` (via the SA service)
- `license_summary` → `data/catalog/license_summary/latest.json` (via the LS service)
- `client_growth` → `data/catalog/metrics/{client_count_history,client_growth_summary,client_growth_details}.json`
- `capacity_license` → `data/catalog/metrics/capacity_license_usage.json`
- `backup_job_summary` → `data/catalog/quickhc/backup_job_summary_latest.json`

### Four options forward

Documented in detail in the docs commit. Summary:

- **γ1** — Restore per-subject view producers in `canonical_view.py` (`security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view`). Make `artifact_to_view` dispatch by `artifact_type`. Then delete `_legacy_builders`. Largest scope; cleanest end state with the canonical schema intact.
- **γ2** — Accept the regression: delete `_legacy_builders`, all subjects render via the generic view producer, lose `counters`/`findings_grid`/`workload`/`chart_growth` shapes. Smallest end state; meaningful visible UX change.
- **γ3** — Extend the canonical schema with new section types. Violates "schema is frozen" rule, large blast radius.
- **γ4** — Hold position. Don't unify source-building further. Sessions 4-5 (route deletion + data-driven dispatch) proceed independently. The source-building stays split (`_legacy_builders` lives, alongside `_build_generic_subject`).

### Notes

- **No code changes this session.** Test count unchanged at 477.
- **FIXME tags intact.** `grep -rn "FIXME(refactor-unified-upload-session-5)" src/` returns the same 3 hits in `quick_hc.py`.
- **The unified upload route is still live and tested** (from session 2). The frontend uses the new URLs (from session 3). The architectural blocker is specifically the source-building unification half of the refactor, not the route half.
- **This is the second time the source-building unification has hit an architectural wall.** Session 3 hit "deleting `_legacy_builders` loses access to legacy on-disk file data." Session 3b hit "the canonical schema can't carry subject-specific view shapes." Both walls are real; both reflect the legacy builders doing two distinct jobs (file reading + view synthesis) that the architecture has implicitly bundled together for years.
- **Sessions 4 and 5 can still proceed if option γ4 is picked.** The unified upload route exists, the URL flip happened, the FIXME branch dispatch can be replaced with data-driven dispatch independently of how source-building resolves.

---

## 2026-06-02

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `81ee0a8` (step 1 snapshot baseline), `389bc4d` (step 3 narrowed URL flip), plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (up from 476; +1 new snapshot test in step 1, 0 net in step 3).

Session 3 of the unified-upload refactor — **landed partially.** Steps 1 and 3 (narrowed) committed; steps 4, 5, and 6 deferred pending user decision on the architectural conflict surfaced in step 3.

### Added

- **`tests/test_subject_initial_data_snapshot.py`** + `tests/fixtures/subject_initial_data_snapshot.json` — pins `build_subject_initial_data()` output against the migrated test DB. Diffs print a readable unified-diff message and fail the test. Future sessions regenerate the fixture only when changes are confirmed intentional.

### Changed

- **Frontend now points at the unified `POST /quick-hc/<subject_id>/import` route.** Three places updated:
  - `_build_generic_sources` in `subject_data_service.py` now produces `f"/quick-hc/{subject_id}/import"` (was: `f"/quick-hc/import?subject_id={subject_id}"`).
  - `_SA_IMPORT_URL` in `subject_data_service.py` is now `/quick-hc/security_assessment/import` (was: `/quick-hc/security-assessment/import`).
  - `_LS_IMPORT_URL` in `subject_data_service.py` is now `/quick-hc/license_summary/import` (was: `/quick-hc/license-summary/import`).
- Three URL-coupled tests updated to match: `test_quick_hc_report.py:893-896` (assertions), `test_license_summary_web.py:100` (substring assertion broadened to accept either form), `test_import_flow.py:219` (assertion updated to path-component shape).

### Notes (step 2 finding — load-bearing)

**The investigation report's Section 3.3 prediction is confirmed by code reading.** Control flow in `build_subject_initial_data:91-103`:

```
artifact = _load_from_canonical_store(subject_id)
if artifact is not None:                       ← canonical hit:  _build_generic_subject
else:
    if legacy_builder is not None:             ← canonical miss + system: legacy_builder
    elif db is not None:                       ← canonical miss + AI:     _build_generic_subject(tile, None)
```

`_build_generic_subject` is the production path for two of three cases (canonical-hit and AI-subject-no-data). The legacy builders run ONLY for system subjects in the pre-first-import state. Once any successful import populates the canonical store for a subject, all subsequent page loads route through `_build_generic_subject`.

### Notes — the step-3 architectural conflict (STOP-and-report)

The brief's two constraints proved mutually exclusive:

1. **Delete `_legacy_builders`, route everything through `_build_generic_subject`.**
2. **Snapshot diff must be URL changes only — any other diff is a regression.**

Constraint (1) would produce sparse "nodata" tiles for all 6 system subjects in the pre-canonical-bootstrap state. The legacy builders' job is precisely to bridge from the file-based legacy artifacts (`data/catalog/rest/commserv.json`, `data/imports/security_assessment/latest.json`, `data/catalog/metrics/*.json`, `data/catalog/quickhc/backup_job_summary_latest.json`) into the view model. The canonical-store path through `_build_generic_subject(tile, None)` has no access to those file paths and produces empty `sections=[]`, `state="nodata"`, `subtitle="Not collected"`.

In production this matters less because after the first REST collect or upload, the canonical store has data. But:
  - The test environment was capturing rich output because dev-machine state in `data/` was leaking into tests.
  - More importantly, real deployments WITH stale legacy files (e.g. dev machines, anyone who upgraded from before the canonical store existed) would see the rich → sparse degradation immediately.

Per the brief's explicit STOP-and-report rule when conflicts surface, **session 3 was narrowed**: URL changes landed; legacy builders kept alive. Steps 4 (retire `write_legacy`), 5 (verify FIXME tags), and 6 (full wrap-up) were not executed.

### What still needs to happen (carried to next session)

The path forward depends on a user decision. The three options:

1. **Accept the pre-canonical-import regression.** Sunset the legacy file-based bootstrap. Update the snapshot to reflect the sparse output. Continue with full `_legacy_builders` deletion and steps 4-6 of the original session-3 brief.
2. **Write a one-way migration on startup.** Read each legacy file-based artifact, synthesise an equivalent `CanonicalArtifact`, write it to the canonical store. After the migration runs once, the canonical path produces rich output and the legacy builders genuinely become dead code that can be deleted without behavioral change.
3. **Keep a small bootstrap fallback inside `_load_from_canonical_store`.** For each system subject, if the canonical store is empty, fall back to the legacy file-based loader and synthesise an artifact in-memory. This preserves the rich pre-import view without changing on-disk state. Subject-specific knowledge stays in one place (the fallback function); future sessions can incrementally migrate each subject's bootstrap to a real canonical write.

The next HANDOVER recommends option 3 as the lowest-blast-radius path, but the choice is the user's.

### Carried forward unchanged

- The unified `POST /quick-hc/<subject_id>/import` route (landed in session 2 / commit `dff43f1`) is still alive and tested. Its three `FIXME(refactor-unified-upload-session-5)` tags are still in place.
- The old per-subject and generic upload routes are still alive. Session 4 deletes them — but only after step 3 / steps 4 are completed properly.
- The `write_legacy=True` default on both persist functions remains in place. Option A's regression tests still pin the post-refactor contract.

---

## 2026-06-01

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `dff43f1`, plus the wrap-up commit that publishes this entry.
**Test status:** 476 passing (up from 469; +7 new tests in `tests/test_unified_upload_route.py`).

Session 2 of the unified-upload-route refactor (see `docs/refactor_unified_upload_2026-05-31.md` for the full plan).

### Added

- **`POST /quick-hc/<subject_id>/import`** — the unified upload route. Lives alongside the existing per-subject (`/quick-hc/security-assessment/import`, `/quick-hc/license-summary/import`) and generic (`/quick-hc/import?subject_id=…`) routes. Dispatches by `subjects.created_by`:
  - Unknown subject_id → 404.
  - `created_by == 'system'`: sub-branches by subject_id. `'security_assessment'` and `'license_summary'` mirror their existing per-subject route bodies; any other system subject → 404 (the other four are REST/metrics-only).
  - `created_by == 'ai'` / `'user'` / other → mirrors the existing generic route, including X-Inline JSON mode, ?stage=1 staging routing, and three-way error reporting.
- **Three private helpers** in `quick_hc.py` — `_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`. Each is a deliberate body-duplicate of the matching old route. Docstrings call out the duplication and point at the session-5/6 collapse.
- **`tests/test_unified_upload_route.py`** — 7 new tests covering every dispatch branch (see commit `dff43f1` for the per-test breakdown). Includes the License Summary Option A regression test that the 2026-05-27 HANDOVER flagged as missing.

### Removed

- **`canonical_view._build_sources`** — confirmed unreachable from production. Its only callers were `security_assessment_to_view` and `license_summary_to_view`, both only reached via dead try-blocks inside the legacy builders in `subject_data_service.py:480-486` and `:735-741`. The dead try-blocks themselves are NOT touched here — that's session 3 work alongside the rest of the source-building unification.
- **`canonical_view._IMPORT_FIELDS`, `_IMPORT_ACCEPT`, `_SOURCE_DEFAULT_STATUS`** — private constants used only by the deleted `_build_sources`.

### Changed

- `security_assessment_to_view` and `license_summary_to_view` now return `"sources": []` instead of calling `_build_sources(...)`. Reachability of these view functions themselves is also dead in production; their `sources` field was never asserted on by any test.

### Notes

- **The dispatch in the new route is an architectural smell.** Branching by `subjects.created_by` and sub-branching by hard-coded subject IDs (security_assessment / license_summary) embeds subject-specific knowledge in route-handler code — which is exactly what the refactor exists to eliminate. The choice was deliberate: keep session 2 small and obvious, defer the data-model question. Every dispatch line carries a `# FIXME(refactor-unified-upload-session-5)` tag so future grep finds them. Session 5/6 replaces the branch dispatch with data-driven dispatch — likely a new column on `subjects` describing import behavior (form-field name, allowed extensions, success-message format, persist function). **Do NOT** add an intermediate abstraction (registry of hooks, plugin system, etc.) before session 5/6 — that would lock in the data-model choice prematurely.
- **The three handler bodies (`_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`) are byte-equivalent to their old counterparts.** Edits to one must be mirrored to the other until session 5/6 collapses them. The docstrings say this.
- **Old routes still work, frontend still uses them.** This was the safety boundary for session 2. The frontend flip happens in session 3.
- **License Summary now has an Option A regression test.** The 2026-05-27 HANDOVER's "Context the next session needs" flagged its absence; landing it via the new route was a natural side-quest because session 2 touches the LS import path anyway.
- **The verification report's "production-vs-test divergence" concern (Section 3 of `docs/refactor_unified_upload_2026-05-31.md`) is still open.** I did NOT run an actual end-to-end import through the running server this session. The new route exists and tests pass, but the old generic-route-via-canonical-artifact path that the report flagged has not been exercised against a real running app. Session 3 will need to verify this before session 4 deletes the old URLs.

---

## 2026-05-30

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `20be561`, plus the wrap-up commit that publishes this entry.
**Test status:** 469 passing (up from 468; +1 new test).

### Added

- **`GET /quick-hc/settings` route** in `src/cvhealthcheck/web/routes/quick_hc.py`. Anonymous-reachable (no `@login_required`) so signed-out users can still reset their preferences.
- **`templates/quick_hc_settings.html`** — placeholder Settings page. Standalone (does not extend `base.html`); reuses `quick_hc.css` for design tokens. Inline JS inspects the two localStorage keys and the "Reset local preferences" button clears them and reloads.
- **"Settings" sidebar nav link** in `templates/quick_hc.html` between Reports and Staging, using the existing `lnav-item` class.
- `tests/test_settings_route.py` — one smoke test asserting 200 + presence of "Settings" heading + both localStorage key names in the response body.

### Notes

- **The Quick HC UX queue now has one item remaining**: remove the old `/quick-hc/import` generic upload route. That is the next session's single recommended next action.
- **`lnav-item` is the correct nav class name**, not `left-nav-item` as the 2026-05-29 HANDOVER sketch suggested. Verified before writing. The earlier HANDOVER was approximate — the verify-before-write step in the workflow paid off again.
- **The Settings page does not extend a base template** because `quick_hc.html` itself is standalone (it pre-dates the consolidation around `base.html` for the older Flask surfaces). For consistency with the dark UI, the settings page mirrors quick_hc.html's `<head>` (theme bootstrap + `quick_hc.css` import) and adds page-specific layout in an inline `<style>` block. If a future change introduces a Quick-HC-level base template, the settings page should adopt it.
- **localStorage key inventory** is currently exactly two keys: `quickhc-theme-v1` (theme toggle, written by `base.html` and `quick_hc.html`) and `quickhc-state-v1` (report-composition state, written by `quick_hc.js`). No variants, no versioned siblings, no per-subject keys. If a future change adds a key, update `quick_hc_settings.html` so the Reset button clears it too — the inline comment in the template names every other file that touches these keys to make this easy.
- **No server-side preferences storage was added.** The Settings page is a placeholder so a future session has somewhere obvious to land things like default report sections, display density, or persisted report profiles.

---

## 2026-05-29

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `2a57cdf`, plus the wrap-up commit that publishes this entry.
**Test status:** 468 passing (up from 466; +2 new tests in `tests/test_api_auth_status.py`).

### Added

- **Connect modal sign-out branch** (`templates/quick_hc.html`). Modal body is now split into `#connect-modal-signin` (existing username/password form) and `#connect-modal-signout` (new). Sign-out branch shows "Signed in as `<user>`. Sign out?" plus a `#signout-error` div and a `#signout-submit` button. Modal title switches between "Connect to Commvault" and "Sign out of Commvault".
- **`SESSION_USERNAME_KEY`** in `auth/commvault_auth.py`. New `get_current_username()` helper. `set_current_token()` now accepts an optional `username=` kwarg.
- **`username` field on `/api/auth/status`** — `{"authenticated": <bool>, "username": <str | null>}`. Null for anonymous sessions and for legacy authenticated sessions created before this field existed.
- **`window.CURRENT_USERNAME`** in the page template alongside `window.IS_AUTHENTICATED`. Kept in sync by the polling fetch.
- **`submitSignOut()` in `quick_hc.js`** — POSTs to `/logout` with `redirect: 'manual'`, treats 2xx/3xx/opaqueredirect as success, clears `window.IS_AUTHENTICATED` + `window.CURRENT_USERNAME`, calls `_updateConnBadge()`, closes the modal. On failure, shows an inline error and leaves the modal open. Mirrors `submitConnect()`'s busy-state and error-display pattern exactly.
- New tests in `tests/test_api_auth_status.py`: authenticated-without-username (pins the legacy-session contract) and end-to-end sign-out (seeds session, POSTs `/logout`, asserts 302 → `/login`, asserts the status endpoint flips, asserts both session keys are gone).

### Changed

- `openConnectModal()` branches on `window.IS_AUTHENTICATED`. Sign-in branch focuses the username input as before; sign-out branch populates `#signout-username` from `window.CURRENT_USERNAME` and falls back to "this Commvault session" when unknown.
- `submitConnect()` now caches `window.CURRENT_USERNAME` on successful login so the next open of the modal shows the right name without waiting for the next polling fetch.
- `_updateConnBadge()`'s polling fetch updates `window.CURRENT_USERNAME` from the response. Network failure still leaves both `IS_AUTHENTICATED` and `CURRENT_USERNAME` in their last-known state.
- Both login call sites (`basic.py::login`, `quick_hc_api.py::api_login`) pass the username through to `set_current_token()`.
- `clear_current_token()` now also drops `SESSION_USERNAME_KEY`.

### Notes

- **`/logout` POST support was NOT added — it already existed.** `basic.py` declares `methods=["POST"]` and `base.html` already POSTs to it from the sidebar's user menu. The handover's worry about it being GET-only turned out to be unfounded; verified before changing anything.
- **No CSRF middleware in this app**, and no existing POST route uses a CSRF token (`/api/login` and the sidebar logout form both POST without one). `submitSignOut()` follows the same pattern. If CSRF protection is added in a future session, `/logout`, `/api/login`, the sidebar logout form, and the new sign-out fetch all need updating together.
- **`username` is gated on `authenticated` in `/api/auth/status`.** Even if a stale `SESSION_USERNAME_KEY` survives a half-cleared session, the endpoint surfaces `username: null` until the token is also valid. This avoids exposing a username for an effectively-anonymous session.
- **The signout branch shows "this Commvault session"** when `window.CURRENT_USERNAME` is null. This covers two real cases: legacy sessions created before `SESSION_USERNAME_KEY` existed, and sessions where the polling fetch has not yet populated the cache (rare — the template seeds it).
- **No CSRF tokens, no PDF export, no scoring engine** — all carried forward unchanged.

---

## 2026-05-28

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `489c970`, plus the wrap-up commit that publishes this entry.
**Test status:** 466 passing (up from 463; +3 new tests in a new file).

### Added

- **`GET /api/auth/status` endpoint** (`src/cvhealthcheck/web/routes/quick_hc_api.py`). Returns `{"authenticated": <bool>}`. Session read only — no Commvault round-trip. Used by the Quick HC connection badge to refresh state without reloading.
- **`_paintConnBadge(isAuth)`** — extracted from the old `_updateConnBadge()` to keep the DOM-write logic pure and testable.
- **`_startConnBadgePolling()`** in `quick_hc.js` — sets up a 60s `setInterval` plus a `window.focus` listener, both calling `_updateConnBadge`. Guarded by a module-level `_connBadgeIntervalId` so the interval cannot stack on repeated calls. Invoked once from the `// ── INIT ──` block.
- `tests/test_api_auth_status.py` — three tests covering unauthenticated, authenticated, and empty-token-treated-as-unauthenticated states.

### Changed

- **`_updateConnBadge()`** in `quick_hc.js` now (1) repaints synchronously from `window.IS_AUTHENTICATED` so the first paint is immediate, then (2) fetches `/api/auth/status` and updates both `window.IS_AUTHENTICATED` and the badge from the JSON. On fetch failure, the badge is left in its last-known state — a flaky network must not flip the user to "disconnected".
- The dead `avail = allSubjs().filter(s => s.state !== 'nodata').length` line in the old `_updateConnBadge()` was removed during the refactor; it was unused.

### Notes

- **Badge state precedence**: synchronous server-rendered initial value → asynchronous refresh from `/api/auth/status` → preserve last-known on network error. Documented inline at the top of the connection-badge section in `quick_hc.js`.
- **Sign-out flow is not yet wired up.** The badge `title` still says "click to sign out" when authenticated, but clicking the badge opens the connect modal in its sign-in form regardless of state. The modal sign-out branch is item 2 of the Quick HC UX queue and is the next recommended action — see `HANDOVER.md`.
- **No new endpoints invoked during tests.** The three new tests hit `/api/auth/status` directly via `client.test_client()`; they do not touch Commvault. Total run time for the new file is under 200ms.

---

## 2026-05-27

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `96c1281`, plus the wrap-up commit that publishes this entry.
**Test status:** 463 passing (up from 462; +1 regression test).

### Changed

- **Option A landed**: Security Assessment and License Summary imports no longer write to the legacy per-domain store (`data/catalog/<subject>/`). The canonical store (`data/catalog/artifacts/<subject>/`) is now the sole writer for new imports. Reads from the legacy store are intentionally preserved as fallback for any pre-existing on-disk artifacts.
- `persist_security_assessment_artifact()` and `persist_license_summary_artifact()` gained a `write_legacy: bool = True` parameter. When False, both the legacy file writes and the legacy SQLite registry insertion are skipped, and the function returns the in-memory artifact payload only. Default stays True so existing legacy-store-behavior tests continue to exercise their original path without modification.
- Production callers all pass `write_legacy=False`:
  - `security_assessment.service.import_security_assessment_upload`
  - `license_summary.service.LicenseSummaryService.collect_from_rest`
  - `license_summary.service.import_license_summary_upload`
  - `reportsplus.security_assessment.extract_security_assessment` (also stops depending on `artifact_paths` from the persist call and on the `load_active_security_assessment_artifact()` round-trip)
- `test_license_summary_service_collect_from_rest_persists_registry_artifact` renamed to `..._writes_canonical_only` and rewritten to assert canonical-only persistence plus a successful canonical load.
- `test_flask_upload_imports_html_and_redirects` / `test_flask_upload_imports_csv_and_redirects` now assert the **absence** of legacy `latest.json` / `latest_<source>.json` files after an upload. The legacy `/security-assessment` development page (which reads only legacy) can no longer render fresh-import data; Quick HC is the authoritative fresh-import read surface.

### Added

- `tests/test_security_assessment_import.py::test_fresh_security_assessment_import_creates_no_legacy_artifact_files` — pins the Option A contract end-to-end. A future change that reintroduces a legacy write will break this test on a fresh import.

### Notes

- **Why Option A and not Option B?** Option B would have one-way migrated existing legacy artifacts into the canonical store, then deleted the legacy code path. We picked A because it is reversible (revert this commit and writes resume), bounded (single focused commit, no startup-time migration to debug), and has no data loss. Option B remains available as a future cleanup if the legacy directories ever need to be purged automatically.
- **`ensure_schema()` may still create the legacy SQLite registry file on first read.** The fallback lookup path (`load_active_security_assessment_artifact`, `load_active_license_summary_artifact`) calls `registry.ensure_schema()` before checking for an active artifact, and that creates the empty `registry.sqlite3` file as a side effect. This is metadata, not an artifact, and the registry tables remain empty unless something explicitly writes — which production code no longer does. The regression test is narrowed to assert no new JSON artifact files, not no SQLite files, to reflect this contract precisely.
- **Legacy `/security-assessment` development page is now effectively read-only history.** It loads via `load_security_assessment_artifact()` → `SecurityAssessmentService.get_current()` → `load_active_security_assessment_artifact()` (legacy). Fresh imports no longer populate that path. The page will show "No Security Assessment artifact exists yet" after the first fresh import unless legacy `latest.json` already existed. This is acceptable; the page was a development/debug surface and Quick HC is the customer-facing one.
- **No SQL or schema changes.** This is purely a code-path change; no migrations were needed.

---

## 2026-05-26

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `b7d2f67`, plus the wrap-up commit that publishes this entry.
**Test status:** 462 passing (up from 461; +1 regression test).

### Fixed

- **Section ID double-prefix in `canonical_view`** (`src/cvhealthcheck/quickhc/canonical_view.py:116` and `:213`). The HTML extractor stores fully-qualified section IDs like `security_assessment.access_security`, and the view builders were rebuilding them as `f"{subject_id}.{sec.id}"` — producing `security_assessment.security_assessment.access_security`. Display titles were correct, but the doubled IDs leaked into the JS state, rendered DOM, and the `localStorage` key (`quickhc-state-v1`), silently breaking per-section include/exclude persistence and the report-composition round-trip. Both prefix sites now guard with `startswith(...)`.

### Added

- `test_sa_section_id_no_double_prefix_when_already_qualified` in `tests/test_quickhc_canonical_view.py` — pins the contract for both `artifact_to_view()` and `security_assessment_to_view()`. A future "normalise the extractor's section IDs to short form" change cannot silently reintroduce the bug.

### Removed

- `0003_report_inventory.sql` and `migrations.py` at project root — stale design-session leftovers, never tracked by git. `0003_report_inventory.sql` was byte-identical to `src/cvhealthcheck/db/migrations/0003_report_inventory.sql`. `migrations.py` differed only in stale ways (docstring referenced old filenames `0001_initial_schema.sql`/`0002_...`, and the path resolution assumed the file would live at `src/cvhealthcheck/db/migrations.py` rather than as the package `__init__.py`). Deleted from the working tree; no git commit needed since they were never tracked.

### Notes

- **Cleanup that produces no commit is still cleanup.** The two stale root files were never tracked by git — verified via `git log --all -- <file>` and `git ls-files <file>`, both returned empty. Deleting them is a working-tree-only operation. Future sessions cloning the repo would never have seen them; this benefited only the local working tree. A `.gitignore` entry to prevent recurrence felt arbitrary for two specific filenames; if the pattern recurs, consider a broader rule like "no `.sql` or top-level `.py` files at project root."

---

## 2026-05-25

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `9073f06`, `9edb2a8`, plus the wrap-up commit that publishes this consolidation.
**Test status:** 461 passing.

### Added

- Versioned SQL migration runner at `src/cvhealthcheck/db/migrations/__init__.py`. Migrations: `0001_initial`, `0002_staged_artifacts`, `0003_report_inventory`, `0004_rest_instructions_and_constraints`.
- `subjects` / `subject_sections` / `subject_sources` / `subject_section_sources` / `collector_schemas` tables seeded with the six system tiles.
- `src/cvhealthcheck/db/subjects.py` — CRUD for the subject catalog plus `create_subject_from_proposal()`.
- Generic extractor pipeline under `src/cvhealthcheck/extractors/` (`dispatcher`, `html`, `csv`, `rest`, `recognition`, `result_to_artifact`), driven by `subject_section_sources` instructions.
- `/quick-hc/import` generic upload endpoint routing through `extract_file()`.
- MCP staging workflow: `propose_new_subject` and `list_proposed_subjects` tools, plus subject-proposal handling in `execute_approval()`.
- Staging review UI at `/quick-hc/staging`.
- Quick HC standalone dark UI (`quick_hc.html` no longer extends `base.html`).
- `subject_data_service.build_subject_initial_data()` returning `{commcell, cats, report_url}`.
- ~14 new test modules: `core_solidity`, `db_staging`, `db_subjects`, `delete`, `extractor_csv`, `extractor_html`, `import_flow`, `mcp_tools`, `migrations`, `recognition`, `rest_extractor`, `staging_routes`.
- `CHANGELOG.md` (this file) — consolidated append-only history.
- `HANDOVER.md` (project root) — single forward-looking handover file, always overwritten.

### Changed

- `create_app()` runs `run_migrations()` instead of the deprecated `init_db()`.
- Quick HC sidebar reads subjects from the DB via `get_tiles(db)` instead of the static `QUICK_HC_TILES` tuple; AI-proposed subjects appear alongside system tiles.
- Quick HC connection badge: always shows `Connect` when unauthenticated and `Connected` when authenticated.
- Quick HC report action bar moved from the top of the main panel to the bottom; visible only when at least one subject is included.
- `canonical_view.artifact_to_view()` now uses `tile["title"]` from the registry for the sidebar display name, so stale `artifact.subject.title` provenance (e.g. "Test Subject") no longer leaks into the UI.
- HTML extractor section-title matching accepts both exact match and `"<title> -"` / `"<title>:"` prefix forms, so `"Other Licenses - current usage details"` matches the `"Other Licenses"` instruction.
- Documentation model consolidated to three files: `README.md` (what + how), `CHANGELOG.md` (backward-looking), `HANDOVER.md` (forward-looking). `DEVLOG.md` and `docs/handover/` retired.
- Test count rose from 343 to 461.

### Fixed

- **Test pollution.** `execute_approval()` was instantiating `ArtifactStore()` with the default base_dir, so `test_execute_approval_artifact` was overwriting the real `data/catalog/artifacts/security_assessment/latest.json` with its `_make_artifact()` fixture data (`title="Test Subject"`, section `id="test_section"`, finding `title="Test finding"`) on every `pytest` run. Added an optional `store` parameter to `execute_approval()`; the test now injects its `tmp_path` store. The user-visible symptom was a sidebar that kept reverting to "Test Subject" no matter how many times Security Assessment was imported.
- **License Summary "No data".** `canonical_view.license_summary_to_view` now accepts both short (`other_licenses`) and fully-qualified (`license_summary.other_licenses`) section IDs. Cause: the extractor was prefixing section IDs with the subject ID but the view was still looking up the short form.
- **Sidebar "ok"/"nodata" mismatch.** Table-only canonical artifacts with non-empty rows now resolve to `ArtifactStatus.good` instead of `unknown`. Previously a healthy License Summary import showed as "nodata".
- **Security Assessment HTML extractor.** Section title "Other Licenses" failed to match HTML titled "Other Licenses - current usage details". Added prefix-with-delimiter matching.
- **Connection badge "6 available".** Removed the dead `else if (avail > 0)` branch in `_updateConnBadge()` that was showing a misleading availability count instead of "Connect".

### Removed

- `DEVLOG.md` — content consolidated into this file under earlier dated entries.
- `docs/handover/` — `HANDOVER_2026-05-25.md` content folded into this entry; `report_inventory_context.md` content summarised in the 2026-05-24 entry.

### Notes

- **Section ID double-prefix is a known bug**, not yet fixed: `canonical_view.artifact_to_view()` builds `sec_id = f"{subject_id}.{sec.id}"` but the HTML extractor already stores fully-qualified IDs. Result: `security_assessment.security_assessment.access_security`. Display titles are correct; the mangled IDs leak into localStorage keys and break per-section include/exclude state across reloads. Fix lives in `canonical_view.py:116` and `:213` — guard with `if not sec.id.startswith(...)`. This is the single recommended next action — see `HANDOVER.md`.
- **Two artifact stores of truth.** Legacy `data/catalog/<subject>/latest.json` and canonical `data/catalog/artifacts/<subject>/latest.json` both exist; imports write both. The UI reads canonical. Decide whether to deprecate the legacy path or migrate it on startup.
- **Quick HC subject naming rule (load-bearing).** The sidebar/display name must come from the registry tile title (`tile["title"]`), not from `artifact.subject.title`. The override lives at `subject_data_service.py:213`. Do not remove it — it protects against stale provenance from prior imports.
- **`execute_approval()` requires an injected store in tests.** Pattern in `tests/test_core_solidity.py::test_execute_approval_artifact`. Without it, the test pollutes the real catalog.
- **Stale 955-byte test-pollution artifacts** in `data/catalog/artifacts/security_assessment/` from before the `execute_approval` fix. Inert (only `latest.json` is loaded). Clean with `find data/catalog/artifacts/security_assessment -size 955c -delete`.
- **Two root-level stale files**: `0003_report_inventory.sql` and `migrations.py` at the project root are leftover duplicates of the canonical copies under `src/cvhealthcheck/db/migrations/`. Safe to delete.
- **`data/app.db` is committed.** Should move to `.gitignore`; migrations recreate the schema on first run.

---

## 2026-05-24

**Test status:** 298 passing.

### Added

- `TileDefinition.category`, `category_label`, `import_url`, `collect_url` — category structure and action URLs are now first-class registry metadata.
- `quickhc/canonical_view.py` — translation layer from canonical artifacts into the Quick HC JS view-model contract.
- Canonical JSON API endpoints: `GET /api/security-assessment/canonical`, `GET /api/license-summary/canonical`.
- License Summary canonical adapter and canonical side-write support for both REST collection and file import.
- `data/app.db` — business/application state DB, separate from import registries and canonical artifact files.
- New raw-SQL `db/` package for customers and engagements.

### Changed

- Quick HC initial subject assembly moved to a registry-driven path via `quickhc.registry.list_tiles()` with explicit tile-id loader/builder dispatch in `subject_data_service.py`.
- Legacy Quick HC GET detail pages now redirect to `/quick-hc`; POST import/collect handlers remain active.

### Notes

- **Product structure direction** locked in: HealthCheck → Customers → Advanced → Development.
- **Legacy detail-route GET vs POST split**: `GET /quick-hc/security-assessment` and `GET /quick-hc/license-summary` redirect to `/quick-hc`; the corresponding `POST .../import` and `POST .../collect` endpoints remain active. This split is intentional — keeps the user-facing surface unified while preserving the existing automation contracts.
- **Five-layer architecture, settled this date**: (1) `subjects` + `subject_sections` = catalog/definition; (2) `subject_sources` + `subject_section_sources` = acquisition/extraction; (3) `staged_artifacts` = review/verification; (4) `ArtifactStore` / `latest.json` = approved canonical outputs; (5) compliance rules = future evaluation layer. `staged_artifacts` is the single staging mechanism for both AI subject proposals (`artifact_type='subject_proposal'`) and ingested artifacts (`artifact_type='artifact'`).
- **Constraints captured for the design brief that produced 2026-05-25's work**: Raw SQL only — no ORM. No Flask dependencies in adapter/registry/db layers. Additive-only schema changes. Pydantic v2 canonical schema v1 is frozen — do not change `artifacts/models.py`.

---

## 2026-05-23

### Changed

- Retired `/quick-hc/security-assessment` and `/quick-hc/license-summary` GET detail pages; both now redirect to `/quick-hc`.
- Updated `detail_endpoint` in the Quick HC registry and `_try_url` calls in `subject_data_service.py` to point at `main.quick_hc` directly.

### Removed

- `quick_hc_security_assessment.html` template.
- `license_summary.html` template.

---

## 2026-05-22

### Added

- Cross-tile regression guard that seeds all current Quick HC subjects and fails if the workspace-emitted section IDs diverge from the authoritative registry section IDs.

### Changed

- Registry made authoritative for the Security Assessment detail-view section set: summary, highlights, Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, Hardening.

### Removed

- `security_assessment.all_findings` from the user-facing registry contract. Kept as a compatibility alias inside the report service for older selection payloads.

### Notes

- **Section contract drift was the root cause.** Detail-view sections and customer-report sections had been edited independently and silently diverged. The new regression guard prevents this from happening again without a test change.

---

## 2026-05-20

### Added

- Quick HC source-provenance block, applied consistently to Backup Job Summary, License Summary, Security Assessment, CommCell, and metric-backed detail views. Unavailable / unimplemented / not-tested / not-applicable sources render as muted instead of being hidden.
- Backup Job Summary Quick HC tile, using the existing registry-driven tile platform and the Phase 1 normalized Reports Plus artifact (dataset GUID `2638c3d3-adc7-4b61-bb24-2ba509229bf5` + related GUID `ce01fc88-d2bd-46cc-ba41-1d967c7fa4a2`).
- Backup Job Summary collector foundation at `reportsplus/backup_job_summary.py` with normalization for total jobs, status buckets, protected client count, recent failures, and recent jobs. Persisted at `data/catalog/quickhc/backup_job_summary_latest.json`.
- `@login_required` on the three `/metrics/*` routes and two previously unprotected Reports Plus routes.
- Tile-contract helpers on `TileDefinition` so description and section/default-selection access stay registry-derived.
- Explicit preview-builder mapping in `quickhc/overview_service.py` keyed by each tile's `preview_renderer`.
- Explicit report-builder mapping in `quickhc/report_service.py` keyed by each tile's `report_renderer`.
- Quick HC overview preview orchestration moved out of `web/routes/shared.py` into `quickhc/overview_service.py`.
- Reusable Quick HC partials: `partials/quickhc_tile.html` (subject-card shell), `partials/quickhc_section_card.html` (section wrapper), and per-subject preview partials under `partials/quickhc/previews/`.
- Shared Quick HC dataclasses in `quickhc/models.py` and central tile registry in `quickhc/registry.py`.
- `tests/test_quickhc_registry.py` — locks down unique tile/section IDs, tile metadata completeness, per-tile section ownership, and alignment between registry-derived selection metadata and report-service constants.

### Changed

- `extract_security_assessment()` no longer persists unauthorized or failed report responses; validates auth/status before normalization.
- Replaced hardcoded Quick HC report detail URLs in `quickhc/report_service.py` with registry-authoritative `TileDefinition.detail_endpoint` resolution through `url_for()`.
- License Summary service's direct import of the Security Assessment registry replaced with a generic artifact-registry helper.

### Fixed

- Stale `message: "Not collected yet"` value in the available Client Growth report branch.

### Notes

- **Architectural boundary captured this date**: registry owns metadata, report service owns filtering/composition, routes stay thin, templates remain presentation-only. The Quick HC framework extraction milestone closes here for the current subject set.
- **Next phase**: controlled renderer orchestration through an explicit mapping layer — not direct dynamic Jinja template resolution.
- **Longer-term direction**: the Quick HC registry is intended to align with future MCP-driven and scheduled report orchestration. Same metadata, different surfaces.
- **Companion codebase review** captured in `docs/review_2026-05-20.md` — flagged `shared.py` god-module, `SecurityAssessmentArtifactRegistry` naming collision with License Summary, hardcoded detail URLs in `report_service.py`, CWD-relative catalog paths. Several items still open as of 2026-05-25.

---

## 2026-05-19

### Added

- `QuickHcReportService` assembling CommCell Details, Security Assessment, License Summary, Client Growth, and Capacity Licenses into one filtered report view model.
- Subject-level and section-level selection IDs so `/quick-hc/report` can render only the selected subjects and nested sections.
- Browser-side selection persistence with `localStorage` (key `quickhc-state-v1`). No server-side profiles.
- Customer-facing report rendering for Security Assessment counters/highlights, License Summary workload + detail sections, Client Growth summary/chart/table, and Capacity Licenses summary/table.
- License Summary compact usage visualization for workload and other-license rows, with `License not purchased` handling where capacity is zero.
- REST collection support on the Quick HC Security Assessment page and the Quick HC License Summary page (preserves upload/CSV/HTML import).
- Broad regression coverage for Quick HC overview rendering, section selection, default report rendering, Security Assessment import/collect flows, Client Growth chart output, License Summary usage rendering.

### Changed

- Quick HC promoted from a simple summary page into the main customer-facing report-composition surface.
- `/quick-hc` redesigned around expandable full-width subject tiles with previews, nested section cards, and parent include/exclude cascade.
- `start.sh` now stops any process already listening on port 5001 before starting Flask again.

### Notes

- **Customer-facing report exclusions, locked in**: no artifact paths, no dataset GUIDs, no HTTP status values, no raw/debug extraction metadata. Evidence and source metadata stay internal only.
- **Agent / Feature Licenses kept without progress-bar visuals** after validating that usage bars made that section noisier rather than clearer.

---

## 2026-05-18

### Added

- Basic Quick HC HTML report at `/quick-hc/report`. Assembly-only — loads current Security Assessment and License Summary artifacts through their service layers (no direct artifact-file reads in the route).
- `quickhc/report_service.py` building a combined report view model: environment identifiers, source metadata, timestamps, Security Assessment counters, License Summary summary counts.
- Explicit artifact version fields on Security Assessment and License Summary canonical models: `schema_version`, `artifact_version`, `collector_version`. Backward-compatible (defaults applied on load).
- License Summary canonical artifact extension: `workload_summary_sections[]` for category/workload summary tables (`Capacity Licenses`, `Operating Instance Licenses`, `Virtualization Licenses`, `User Licenses`, `Data Insights Licenses`, `Air Gap Protect Licenses`, summary-page `Other Licenses`).
- CSV multi-section parsing for License Summary (report title + generated timestamp metadata + independent section tables).
- HTML table parsing for License Summary by validated header shape.
- REST normalization for Reports Plus report 206 (License Summary) on top of the generic report extraction helper.
- XLSX API viewer recording import for offline REST-recorded evidence — no new dependency.
- Registry-backed artifact persistence and registry-first active artifact loading for `artifact_type=license_summary`.
- Masked registration-code handling in License Summary metadata (unmasked codes are never persisted).
- New `src/cvhealthcheck/license_summary/` package.

### Changed

- Flask route surface split into focused modules under `src/cvhealthcheck/web/routes/` (Quick HC, Security Assessment, development, metrics, Reports Plus). Organisational only; URLs and templates unchanged.
- `CV_VERIFY_SSL` now defaults to enabled (was disabled). Explicit warning logged when disabled.
- Quick HC License Summary page renders workload summary sections separately from detail tables.

### Notes

- **Missing-values policy for License Summary**: do not fabricate absent sections, do not guess `license_expiry`, render only sections that return real rows in the current CommCell.
- **Lab CommCell observation**: `Operating Instance Licenses`, `Data Insights Licenses`, and `Other Licenses` render from live REST. `Capacity Licenses` may be absent because the upstream dataset fails in this CommCell. `license_expiry` remains unset when report 206 does not return it.

---

## 2026-05-17

(Multiple consolidated entries from this date — see DEVLOG history before the consolidation if needed.)

### Added

- `src/cvhealthcheck/security_assessment/` package: `models.py`, `normalize.py`, `validate.py`, `artifact.py`, `registry.py`, `service.py`.
- Strict schema models for customer / CommCell / engagement / report stream / report run / import run / artifact record / canonical finding / Security Assessment artifact.
- SQLite artifact registry at `data/imports/security_assessment/artifact_registry.sqlite3`. Idempotent schema; `foreign_keys`, `busy_timeout`, `WAL` pragmas.
- Unique persisted artifact files per import/refresh, plus `latest.json` compatibility writes (`latest_rest.json`, `latest_html.json`, `latest_csv.json`).
- Service-layer read API: `SecurityAssessmentService.get_current()`, `get_history()`, `get_artifact()`.
- Historical retrieval by `artifact_id`, `import_run_id`, `report_run_id`, and latest-within-scope.
- Hidden/debug history and registry-export endpoints, login-gated.
- Internal registry viewer linked from the Development page.
- Retention/provenance metadata: `created_at`, `last_accessed_at`, `retention_policy`, `imported_by`, `import_method`, `source_metadata`.
- Browser HTML/CSV upload support in the Flask UI.
- Multi-source Security Assessment ingestion path: `collect → normalize → persist → render`.
- Source-specific persisted latest artifacts (`latest_rest.json`, `latest_html.json`, `latest_csv.json`) at `data/imports/security_assessment/`.

### Changed

- Active-artifact selection scoped by customer, CommCell, artifact type, source type, and engagement/report-stream context (was global by artifact type).
- Source activation/selection moved out of `normalize.py` into the registry/service layer.
- Invalid/noisy-finding filtering and deduplication moved to a dedicated validation layer.
- HTML/CSV import and REST refresh flows updated to register artifacts in SQLite while preserving existing UI behavior.

### Fixed

- HTML ingestion hardened against presentation-heavy report markup: strict table parsing validates `thead` and only extracts `tbody`/`tr`/`td`.
- Missing-active-artifact recovery: service now attempts to promote the newest recoverable artifact in the same scope before falling back to `latest.json`.
- Explicit fallback diagnostics — marks the path actually loaded when compatibility fallback is used.

### Notes

- **HTML exports are presentation-heavy** and cannot be treated as simple text-extraction inputs. Strict table parsing is required.
- **CSV exports are materially cleaner than HTML exports** and currently appear to be the more reliable offline import format.
- **Security Assessment has evolved** from single-source report extraction into multi-source canonical evidence ingestion. Multiple same-day report runs are now supported (`report_run_id`, `executed_at`, optional `run_sequence`).
- **Open question (still open as of 2026-05-25)**: imported HTML and CSV artifacts render correctly when REST is unavailable, but noisy text may still appear when the REST source is active. The remaining defect is most likely in REST/live source interaction, source precedence, or stale artifact selection — not in HTML/CSV parsing itself. Track this if you see it recur.

---

## 2026-05-15

### Added

- Reports Plus Security Assessment extraction for report 336. Endpoint pattern: `/commandcenter/api/cr/reportsplusengine/reports/336`, `/datasets/<guid>`, `/datasets/<guid>/data`.
- Normalized Security Assessment artifact at `data/catalog/reportsplus/report_336_security_assessment_normalized.json`.
- Reusable checklist-style normalization in `src/cvhealthcheck/reportsplus/checklist.py` — status values, unsafe-HTML stripping from remarks, safe action-link extraction.
- `/reportsplus/security-assessment` Development/debug view.
- Security Assessment tile in Quick HC at `/quick-hc/security-assessment`.
- Chart.js metric visualization pattern: route → server-side chart payload → `metric_detail.html` → Chart.js render. Applied to Client Count, Client Growth, Capacity License Usage.

### Notes

- **Discovered Security Assessment sections** (six): Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, Hardening.
- **Current artifact summary** at this date: 32 total checks, 2 Critical, 0 Warning, 18 Info, 12 Good.
- **`cv-topology` is reference-only** — confirmed. Do not refactor or modernize it as part of active cv-healthcheck work.

---

## 2026-05-14

### Added

- Phase 3.0 Quick HC Foundation begins.
- Reusable Quick HC CommCell Identity / Version collector for `GET /commandcenter/api/CommServ`.
- Normalized REST artifact at `data/catalog/rest/commserv.json`.
- `cv-healthcheck quickhc commcell` CLI command.
- Flask Quick HC pages at `/quick-hc` and `/quick-hc/commcell`.
- `PROMPT.txt` — durable project and AI guidance for future sessions.

### Notes

- **Live validation**: `/commandcenter/api/CommServ` with a Login-issued Authtoken returned HTTP 200 with `hostName`, nested `csGUID`, `csVersionInfo`, `releaseId`, `osType`, `timeZone`.
- **Quick HC kept read-only and acquisition-only** at this stage — no health scoring, rules, SQL, database, or S3 code.
- **Strategic operating model clarified**: Daily Reporting, Quick HealthCheck, Full HealthCheck. The central reporting platform must not assume direct reachability to customer CommServe systems; customer-side REST collectors will gather snapshots and upload evidence artifacts (S3 expected as future transport).

---

## 2026-05-13

### Added

- Focused metric extraction pipelines for the four high-value Report 318 datasets: Client Count, Client Growth Summary, Capacity License Usage, ClientGrowthDetails.
- Normalized local metric artifacts under `data/catalog/metrics/`.
- `/metrics/client-count`, `/metrics/client-growth`, `/metrics/capacity-license` pages.
- Normalized Report 318 metric inventory at `data/catalog/reportsplus/report_318_metric_inventory.json` — 30 classified datasets, returned columns, record counts, sample values, time ranges, usefulness labels, operational questions.
- `/reportsplus/report/318/metrics` review page.

### Notes

- **Report 318 dataset classification**: 10 capacity/growth, 3 client growth, 6 deduplication/compression, 5 storage usage, 6 low-value/unclear selector-style.
- **Useful metrics discovered**: client count + client growth monthly history (May 2025–May 2026), capacity license usage over the same period, client growth detail rollups.
- **Report 318 live extraction shape**: report definitions can live in `pages[].body` as JSON strings; widgets/datasets reference nested `dataSet` objects rather than a top-level `content` field. Adjust parsing accordingly.

---

## 2026-05-11

### Added

- Focused Reports Plus extraction workflow for Report 318.
- Local Report 318 artifacts under `data/catalog/reportsplus/`: metadata, definition, dataset mapping, execution summary, raw dataset execution results.
- `/reportsplus/report/318` inspection page (metadata, widgets, dataset mappings, execution status, sample rows).
- Flask login flow for Commvault authentication. Token-expiry handling clears session and redirects to login.
- Phase 2.4 lab readiness baseline. Readiness output at `data/labreadiness/latest.json`. `cv-healthcheck lab readiness`, JSON mode, `/lab-readiness` view.
- Phase 2.3 candidate validation by dataset execution. CLI + Flask views.
- Phase 2.2 Reports Plus catalog inspection and candidate prioritization. `health_candidate_priority.json` from generated report/dataset summaries.
- Phase 2.1 Reports Plus catalog persistence and analysis. Catalog CLI for reports, datasets, all-inventory.
- Reusable Reports Plus report and dataset inventory methods.
- CLI inventory commands with JSON, summary, and local catalog persistence.
- Flask pages for report inventory, report detail inspection, dataset inventory.
- `API_MAPPING.md` — source-centric capability catalog (separate from `HEALTHCHECK_MATRIX.md` which is the health-rule catalog).
- `scripts/probe_auth_matrix.sh` to compare `Authtoken` vs `Authorization: Bearer` across base API + Reports Plus endpoints.
- Initial standalone `cv-healthcheck` project — reusable Commvault API client, Reports Plus metadata + dataset query helpers, CLI, lightweight Flask UI.

### Notes

- **Reports Plus auth**: current `.token` works for `/commandcenter/api` but returns HTTP 401 on Reports Plus inventory endpoints. A Login-issued Authtoken (from `POST /commandcenter/api/Login`) works as `Authtoken` for `/commandcenter/api/cr/reportsplusengine/reports`. Auth-matrix script confirmed both header styles fail with the current `.token` for Reports Plus.
- **Dataset metadata payload is rich**: includes fields, `GetOperation` parameters, SQL text, database name, query plan, tenant visibility, and `builtIn`/`systemDataSet` flags.
- **Rationale for splitting `API_MAPPING.md` from `HEALTHCHECK_MATRIX.md`**: one source can support many health checks; health logic should not be embedded in the API inventory.

---

*Earlier history is not consolidated here. See `git log` for granular detail before this file existed.*
