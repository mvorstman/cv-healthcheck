# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — sections for **Added / Changed / Fixed / Removed** where they apply, plus a short prose **Notes** section per entry for findings, root causes, architectural decisions, and gotchas worth preserving.

This file is append-only. Past entries are never deleted or rewritten — corrections are made by adding a new entry.

See `HANDOVER.md` for what to do next. See `README.md` for what the project is.

---

## 2026-06-01 (UI fix — load localtime.js on the standalone workspace page; completes the browser-local timestamp slice)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `7f2dc0e`. **832 passing** (was 831; +1).

### Fixed
- **The workspace "Last collected" still rendered raw UTC** after `58b0079`. Root cause: `quick_hc.html`
  is a **standalone** document (no `{% extends "base.html" %}`), so the `localtime.js` include `58b0079`
  added to `base.html` never reached it — `window.fmtLocalTime` was undefined on the workspace, so
  `fmtUtc` silently took its raw-UTC fallback. Added the `localtime.js` `<script>` to `quick_hc.html`
  itself, **before** `quick_hc.js` (fmtUtc delegates to `window.fmtLocalTime`, so the helper must be
  defined first), with the page's `v=asset_version` cache-bust.

### Notes
- **`base.html:19` left as-is (reported, not expanded):** `asset_version` is passed only to
  `quick_hc.py`'s two `render_template` calls — it is **not** a global context processor — so it isn't in
  `base.html`'s scope. Adding `v=asset_version` there would raise `Undefined` on the other routes that
  extend base. base.html's include works on those pages (first-load); only the standalone workspace was
  missing one.
- **Guard test** (`test_platform_foundation.py::test_workspace_loads_localtime_helper_before_quick_hc_js`):
  the rendered `/quick-hc` references `static/localtime.js` **before** `static/quick_hc.js`, so this
  standalone-page miss can't silently recur. (It matches the `static/` src paths, not bare filenames,
  which also appear in on-page comments.)
- **Reviewer browser check (needs `./start.sh` + cache-busted reload):** the workspace "Last collected"
  now shows local time + zone label (e.g. `2026-06-01 21:49 CEST`), not `… UTC`.

---

## 2026-06-01 (UI — render UTC timestamps in browser-local time with a zone label; display-only)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `58b0079` (code + tests). **831 passing** (was 827; +4).

### Changed
- **Every user-facing timestamp now renders in the browser's LOCAL timezone with an explicit zone
  label** (e.g. `2026-06-01 21:30 CEST`) instead of UTC, fixing the UTC-vs-local misread (a stored
  `19:30 UTC` looked wrong to a viewer at 21:30 CEST). Correct-by-default; no setting/picker (the
  picker was deliberately deferred — browser-local is the chosen scope).
- **One helper each side, routing all 20 call sites:**
  - `web/static/localtime.js` (new) — `window.fmtLocalTime(iso)` (UTC ISO → local + zone label, via
    `Intl.DateTimeFormat`, numeric-offset fallback) plus a `data-localtime` DOM sweep on load. Loaded
    globally via `base.html` (+ the standalone `project_detail.html`).
  - `localtime_span(value, fallback)` Jinja global (`web/app.py`) — emits a `data-localtime` span
    carrying the machine-readable UTC, with the raw value as fallback text (no-JS / bad value) and a
    plain placeholder for empty values.
  - `quick_hc.js` `fmtUtc` now delegates to `window.fmtLocalTime` (the workspace "Last collected" line).

### Notes
- **HARD CONSTRAINT held — storage stays UTC.** `collected_at` / `generated_at` / `imported_at` are
  unchanged ISO-8601 `…Z`; no stamping/serialization/storage/extractor code was touched (verified by a
  guard test asserting a collect still stores `…Z`, and by `git diff --name-only` — changes are all in
  `web/`). This slice changes rendering only.
- **Call-site inventory (20):** 1 JS workspace render (`quick_hc.js` "Last collected") + 19
  server-rendered template timestamps across 9 templates — `quick_hc_report.html` (×6:
  generated_at/generated_on + license/client_growth/capacity imported_at + bjs generated_at),
  `quick_hc_staging.html` (created_at, reviewed_at), `project_detail.html` (created_at,
  working_state_modified_at, finalized_at), `security_assessment.html` (collected_at, generated_on,
  imported_at), `quick_hc_commcell.html` (collected_at), `quick_hc_backup_job_summary.html`
  (generated_at), `security_assessment_registry_history.html` (imported_at, executed_at), and the
  license_summary / backup_job_summary preview partials + the source_provenance partial. All values
  were confirmed machine-readable ISO-UTC at source (`collected_at()` / `_now()` / artifact
  `.isoformat()`), so none needed raw-value threading.
- **STOP-AND-STEER evaluated, did not trigger:** the report page (`quick_hc_report.html`) is a live
  on-screen render (route `render_template`), not a baked/exported customer document — `finalize_project`
  snapshots the JSON artifacts (UTC preserved), it does not bake the HTML — so browser-local is correct.
  No timestamp consumed for sorting/comparison was touched (SQL `ORDER BY created_at` uses the stored
  UTC value, unaffected).
- **Reviewer browser check (requires `./start.sh` — JS/template — + cache-busted reload):** every
  inventoried timestamp now shows local time with a zone label; "Last collected" in the workspace is the
  headline fix. Tests prove the server seam + the storage guard; the browser is the final confirmation.

---

## 2026-06-01 (ADR 0007 Phase 3 follow-on, slice A — surface the command-center source tab + Collect by default, thread card view_mode, flash auth-failed collects)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `afecdc2` (code + tests). **827 passing** (was 821; +6).

### Fixed
- **BUG 1 — command-center source tab dropped in the generic path.** Once a stored artifact wins
  precedence, environment renders via `_build_generic_subject` → `get_tiles` → `_build_db_source_entries`,
  whose `_SOURCE_TYPE_TO_CANONICAL_ID`/`_SOURCE_TYPE_TO_LABEL` (`registry.py`) only knew `{html,csv,rest,json}`
  — so the `rest_command_center_api` row mapped to `src_id=None` and was dropped. Added the mapping →
  a **"REST / Command Center API"** tab with its `/quick-hc/<id>/collect` url; `_build_generic_sources`
  (`subject_data_service.py`) now emits the collect action (`requiresSession=True`) for it.
- **BUG 2 — activeSource pointed at the dropped tab.** `artifact_to_view` maps `rest_commserve` →
  `REST_COMMAND_CENTER_API_SOURCE_ID` — the **same id string** the now-mapped tab renders with — so
  `quick_hc.js:501` resolves `activeSrc` and `:503` shows the panel + Collect button **by default**
  (previously reachable only by manually clicking the mislabeled Reports-Plus tab). Resolved by BUG 1's
  mapping; the stored artifact's `source.type` was **not** changed.
- **BUG 3 — silent auth-failed collect.** The customer-bound auth gate (`quick_hc.py`) did a bare
  redirect with no flash, so an auth-failed collect looked identical to a stale success (cost multiple
  diagnosis cycles). It now flashes **"Collection failed: sign in to Commvault for customer '…'…"**
  before redirecting. The `result.errors` flash and success flash are unchanged.

### Changed
- **Card `view_mode` now rides on the artifact (render-only).** `CardSection` gained an optional
  `view_mode` (`models.py`, additive-absent serializer — existing card artifacts stay byte-identical);
  `build_card_section` captures the binding's `card.view_mode`; `artifact_to_view` threads it to
  `_card_section_view` so a card authored `view_mode="table"` renders as the **Field/Value table**
  (matching the live card). Source-agnostic; unset → tiles (unchanged). The stored environment artifact
  was regenerated so it carries `view_mode="table"`.
- **Stale plain-`rest` source tab suppressed for command-center subjects.** When a subject has a
  `rest_command_center_api` source, `_build_db_source_entries` hides the legacy plain-`rest` tab so the
  user sees ONE correct source. Generic (keyed on source_type, not subject id) and reversible; the
  `rest` row itself is untouched. environment is the only command-center subject today.

### Notes
- **This slice is UI plumbing only — the live builder `_build_environment_subject` was NOT retired**
  (still in `legacy_builders`). Retiring it is the **next slice**.
- Non-goals held: the "canonical store wins" precedence, the collect/extractor/auth *logic* (beyond the
  BUG-3 flash), and CEL/`html.py`/`csv.py` are all unchanged.
- **Reviewer browser check (requires `./start.sh` — Python/template/JS state — + a cache-busted reload):**
  at `localhost:5001#subject=environment`, by default (no manual tab click) the **Command Center API**
  tab is selected, the **Collect button is visible**, and the card renders as a **TABLE**. Tests prove
  the data contract; final confirmation is the reviewer's browser.

---

## 2026-06-01 (ADR 0007 Phase 3 — environment full 9-field parity card spec + rules on the command-center artifact)

**Branch:** `feature/basic-healthcheck-report-output`

### Added
- **Migration 0028** (`0028_environment_full_parity_card_spec.sql`): replaces the provisional
  3-field spec migration 0026/0027 put on environment's `rest_command_center_api` binding with the
  **full 9-field parity spec** mapped to the real GET CommServ dot-paths — CommCell Name
  (`commcell.commCellName`), CommCell ID (`commcell.commCellId`, `type:hex` → "2"), CommCell GUID
  (`commcell.csGUID`), Version (`csVersionInfo`), OS Type (`osType`), Current/Installed SP Version,
  Timezone (`csTimeZone.TimeZoneName`), Hostname (`hostName`) — plus the **3 per-field rules**
  retargeted from row-7's flat keys (`version`/`timezone`/`name`) to row-22's dot-path field ids.
  Pure idempotent + FK-safe `UPDATE` of one binding row.

### Notes
- **Parity verified (the gate):** the STORED command-center artifact now resolves all 9 fields from
  the real nested `.raw` dict (no resolver changes — D2 dot-paths + D3 hex carry it), and the 3 rules
  fire **good / good / good** with a **good** roll-up — matching the live-served identity card.
- **The live builder `_build_environment_subject` is NOT retired this slice (steered).** Removing it
  is not a clean "remove from `legacy_builders`": the live builder also *authors* environment's
  `rest_command_center_api` SOURCE tile + Collect button + `Endpoint/Host` meta, which `get_tiles()`
  (surfaces only a `rest_reports_plus` source for environment) and `_build_generic_sources` (no
  command-center collect branch) do not yet produce for the generic path. A clean retire needs that
  source-tile/Collect plumbing first — a separate follow-on.
- **view_mode parity gap (presentational, deferred):** the spec carries `"view_mode":"table"` as
  declared intent, but the stored-artifact render path (`canonical_view.artifact_to_view` →
  `_card_section_view`) hardcodes `tiles` and does not thread a section view_mode, so the stored card
  renders as tiles today. Outside the hard parity gate (9 fields + 3 firing rules); a follow-on
  threads view_mode through the artifact render path.
- **821 passing** (was 820; +1 net: parity-rules-fire test added, provisional-3-field tests retargeted).

---

## 2026-06-01 (ADR 0007 Phase 2 fix — migration 0027 lands the command-center source on live DBs)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `ce8e8d4` (migration 0027 + tests).

**Root cause:** the broken first migration 0026 ran a plain `INSERT OR IGNORE` against the old
4-value `subject_sources.source_type` CHECK — the CHECK silently rejected the
`rest_command_center_api` row, but 0026 was stamped applied, so run-once keying meant the
corrected 0026 could never re-run on `data/app.db` (stuck: 4-value CHECK, no command-center
source → environment `/collect` fell to RESTExtractor and errored "missing report_id"). **0027**
lands 0026's intended effect under a new migration id: an idempotent + FK-safe `subject_sources`
rebuild (widen the CHECK) + `INSERT OR IGNORE` source/binding — no-op on fresh DBs, corrective on
the live DB (existing `rest` row id 7 + live-card binding preserved). Data/migration fix only, no
code changed. **820 passing** (was 818; +2 migration tests).

---

## 2026-06-01 (ADR 0007 Phase 2 — command_center_api source + pluggable /collect + environment Collect button)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `db39758` (implementation + tests + migration 0026).

Makes `environment` collectable through a single-object Command Center API extractor that
STORES a canonical artifact in `working/environment/`, proving the seam end to end (Collect
button → `/collect` → extract → `result_to_artifact` → `save_artifact`). **818 passing**
(was 813; +5). Additive — the live-served environment card is unchanged. CommCell ID is **not**
authored (gated on a live capture, Phase 3).

### Added

- **`extractors/command_center.py`** — `CommandCenterExtractor`: wraps the existing
  `get_commcell_identity` (unchanged; still writes `commserv.json` as raw provenance), feeds
  the CommServ `raw` object as ONE record to the generic card path, and reads the card spec
  from the subject's `rest_command_center_api` binding. Nested fields resolve via Phase-1's
  dot-path selector. Injectable `identity_provider` for offline tests.
- **Pluggable `/collect` dispatch** (`quick_hc.py`): `_has_command_center_source` selects the
  extractor by the subject's source type — Reports-Plus → `RESTExtractor` (unchanged),
  command-center → the new extractor. Auth checks + `result_to_artifact`/`save_artifact` tail
  identical.
- **environment Collect button** — the Command Center SOURCE tile emits a collect action
  (`collectUrl` + `requiresSession=True`); the card section is untouched.
- **Migration 0026** — widens the `subject_sources.source_type` CHECK to admit
  `rest_command_center_api` (FK-safe table rebuild, FK integrity verified) + adds environment's
  command-center source and a PROVISIONAL 3-field card spec (CommCell Name / Version / Timezone;
  two nested reads). No CommCell ID this slice.

### Changed

- `result_to_artifact._SOURCE_TYPE_MAP` maps `rest_command_center_api` → the existing
  `SourceType.rest_commserve` (the stored artifact's `source.type` is the CommServe type, not
  `rest`); `collected_at` is stamped for it (live collection).

### Notes (deviations from the brief, flagged)

- **SourceType reused, not added.** The brief asked for a `command_center_api` SourceType, but
  the canonical model already has `SourceType.rest_commserve` (used by the env adapter,
  `commcell_details.py:38`). Reused it rather than add a redundant third name alongside
  `rest_commserve` (enum) + `rest_command_center_api` (source-id). `source.type` = `rest_commserve`.
- **Collect-button gate point differed.** The brief's gate (`:269`, `_provenance_to_tile_sources`)
  is NOT on environment's bespoke path — environment builds sources via `_build_tile_sources` in
  `_build_environment_subject`. The button was surfaced by passing a collect action there (SOURCE
  only; the card section, rules, view_mode, and live-serve model are untouched).
- **CHECK ripple.** `subject_sources.source_type` had a closed CHECK — adding a new source type
  required a table rebuild (the ripple the STOP-AND-STEER list anticipated).

---

## 2026-06-01 (ADR 0007 Phase 1 — nested-path field selector + hex coercion capability fixture)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `70850bd` (implementation + tests + migration 0025 + fixture).

Proves ADR 0007's two new EXTRACT-stage capabilities in isolation on a dedicated test
subject, before any real subject depends on them — mirroring how `_metric_test` /
`_card_test` de-risked ADR 0004. Test-subject-first, additive only. **813 passing** (was
807; +6 new tests). environment, the HTML/CSV extractors, and CEL were NOT touched.

### Added

- **D2 — nested-path field selector.** New `_resolve_field_path(record, path)` in
  `metric_section.py` (the shared field-resolution module). A card/metric item `field` may
  now be a dot-path (`commcell.commCellId`, `csTimeZone.TimeZoneName`); it traverses nested
  dicts, and a missing/non-dict segment resolves to `None` (consistent with `.get()`). Used
  once, by both the metric/card path via `_aggregate` and the card no-agg path — not CEL.
- **D3 — `hex` coercion.** New `_coerce_item_value` in `card_section.py` adds `type: "hex"`
  to the card item path (a closed sibling of the HTML extractor's string/int/float): formats
  an integer as lowercase hex, no `0x` (`13183 -> "337f"`). `CardItem` gains an optional
  `raw_value` (the pre-coercion integer), omitted from JSON when absent.
- **`_nested_test` subject** (migration 0025, `created_by=system`) + nested JSON fixture
  `data/test_fixtures/nested_test.json` + `test_nested_test_subject.py` — one card section
  with `commcell.commCellName`, `commcell.commCellId` (hex), `csTimeZone.TimeZoneName`,
  deliberately mirroring environment's two hard fields.

### Notes

- **Step-1 finding:** `_aggregate` is the shared field helper (metric always; card-with-agg);
  the card no-agg path (`row.get(field)`) was the one outlier — both now route through the
  single `_resolve_field_path`, matching ADR 0007 D2's "implemented once, shared." No
  semantic change to flat fields (single-segment path is byte-identical to `row.get`).
- **Step-2 finding:** there was NO `type`-coercion step in the card/metric item value path
  (`_coerce` is HTML-local; `_coerce_number` is evaluate-stage). D3 therefore *added* a
  coercion step to card item resolution — it did not extend `html.py`.
- `_card_test` stays the flat-path oracle (untouched). Existing card artifacts are
  byte-identical (the new `raw_value` is omitted when absent).

---

## 2026-05-31 (ADR 0004 phase-8 follow-on — per-field evaluation, enum/format kinds, environment table)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `8f3910d` (per-field cards), `a06df57` (per-field card render), `cd4a777` (enum/format kinds), `49053a9` (environment rules as data), `9c3299c` (environment GET CommServ field set), `c61502d` (Field/Value table + `view_mode`), `98b0700` (info-dot fallback + legend), `46ef200` (right-aligned Status column). Plus terminology/doc commits (`d59141d`, `5e55d22`, ADR record `4ead582`) and a dev-workflow commit (`c2a9d87`, `start.sh` auto-reload).

Phase 8's evaluative face moved from base machinery to per-field judging on both metric and card sections, two new rule kinds, and a full rebuild of the bespoke environment / CommCell Details subject onto the shared path. **807 passing** under both `pytest` and `python -m pytest`.

### Added

- **Per-field card judging.** `CardItem` carries optional `severity` / `verdict_chain` / `recommendation_intent` (serializer omits them when absent, so existing card artifacts stay byte-identical). `card_section.py::_apply_per_field_rules` resolves each field's rule through the single `engine.evaluate` locus; section severity rolls up most-severe-surviving. Per-field render (badge in tiles; dot in table).
- **`enum` and `format` rule kinds** (`evaluative/enum_rule.py`, `evaluative/format_rule.py`), dispatched in `engine.evaluate` alongside threshold/presence. enum checks membership in `allowed_values`; format matches a `pattern` via `re.fullmatch`. "No spec configured → good, never raise," so an unconfigured rule renders safe.
- **environment per-field rules as catalog data** (migration 0023) and **`view_mode` on the section** (migration 0024) — both ride the `subject_section_sources` binding, mirroring how `evaluative.rules` already attach. `view_mode` ("tiles" | "table") is read by the renderer, not hardcoded per subject.
- **Field/Value table view for CommCell Details** — Field | Value | Status (3 columns, uppercase headers), reusing the `wl-table` styling, with a verdict dot on every row and a good/info/warning/critical legend beneath.

### Changed

- **environment / CommCell Details reads the real GET CommServ response.** `_load_legacy_commcell` now returns the real `.raw` block; the card reads `commcell.commCellName`, `hex(commcell.commCellId)`, `commcell.csGUID`, `csTimeZone.TimeZoneName` (clean, no `"0:0:"`), SP versions, etc. directly. CommCell ID is now the numeric id as hex (was the GUID); Release Name omitted (absent from the response).
- **Verdict dot fallback.** Every table row shows a dot: `effState = it.sev ?? it.state ?? 'info'` resolved in one spot — informational fields fall back to the info (blue) dot at render time, **not** via authored rules.
- **`start.sh`** enables dev auto-reload (`flask run --debug --no-debugger`); dropped the dead `FLASK_ENV`.

### Removed

- The duplicate header-CC identity grid in `quick_hc.js` (it duplicated the environment card and showed the dirty `"0:0:"` timezone + GUID-as-ID).

### Notes

- **No ID/GUID synthesis ever existed.** The "CommCell ID synthesized from Serial+RegCode" premise was false — the GUID is read directly; the bug was the card labeling the GUID as "CommCell ID." Serial/RegCode == the GUID split is a License-UI relationship, not collector code.
- **License fields are not in GET CommServ** (Edition / Mode / Serial / Reg Code / expiry / IPs); License Summary report 206 carries only Registration Code + License Expiry. Live capture of the rest was blocked by an expired lab token — recorded for a later slice.
- The recommend **seam** is built and ratified (`recommendation_intent` on verdicts); the recommend **stage** is not (future ADR). Phase-8 **Shapes** (StatusRow / inline-threshold) remain unbuilt.

---

## 2026-05-30 (ADR 0004 phase 7 — migrate backup_job_summary)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `2dce378` (2a card agg+CEL), `bb95a54` (2b table empty_message), `aad74f1` (2c migration 0016 + e2e), plus wrap-up + pointer.

The **third and last regressed-subject migration — ADR 0004's regression-recovery arc is complete** (capacity_license, client_growth, backup_job_summary all now render canonically). The **first real `build_card_section` consumer** (as phase 5 was first for chart, phase 6 first for the informational meta-metric). Browser-verified PASS. **727 passing** under both `pytest` and `python -m pytest` (was 713).

backup_job_summary now collects four canonical faces from the "Job details" dataset: a `metric` (Total Jobs, informational), a `card` (the six classify_job_status buckets), `findings` (recent failures), and a `table` (recent jobs). The lab returns **0 rows by design**, so the phase's deliverable was **"empty renders cleanly and informatively"** (empty-state A) — not populated jobs.

### Added

- **`build_card_section` aggregated / CEL item sources** (`2dce378`) — items can now be `source:"field"` (with optional `agg`: sum/count/avg/min/max/latest/first) or `source:"cel"` (expr over `records`), mirroring `build_metric_section` and reusing `cvhealthcheck.cel`. The BJS status buckets bind as `count(records.filter(r, r.status == "…"))`; `count()` of an empty filter is **0**, which is the all-zero card (not blanks). The phase-4 identity-card default (no source/agg → first row's field) is unchanged.
- **`TableSection.empty_message`** (`bb95a54`) — a presentational, subject-specific empty-state string ("No jobs in the selected window") shown instead of the generic "No data.". Threaded declaratively: `extraction_instructions["table"]["empty_message"]` → new `ExtractionResult.section_table_specs` (carried on the REST default `output_as=="table"`) → `TableSection.empty_message` → `artifact_to_view` → `quick_hc.js`. `None` → the generic message.
- **Migration 0016** (`aad74f1`) — flips `backup_job_summary.status_breakdown` from `table` to `card` (CHECK allows `card` since 0012) and binds all four sections. End-to-end test over a 0-row collect (all four faces build; all-zero no-verdict card; informational Total Jobs 0; empty table with the custom message; empty findings) plus a populated-rows case proving the counts are real wiring.

### Notes

- **No `required_fields` conformance on this subject — deliberate.** `check_conformance` fails `required_fields` on 0 rows (empty `present_fields` → every required field "missing"), which would drop every section. On an empty-by-design subject conformance is omitted; it's added when the subject collects real data (a phase-8 item).
- **Phase-8 correctness items** (deferred, agreed at the gate): the card's six buckets use **exact-match** CEL on the freetext `status` — `classify_job_status`'s substring bucketing is Python-only and outside the fixed CEL primitive set, so real-data bucket accuracy is phase 8 (moot on the 0-row lab). `recent_failures` is bound to the whole dataset; on real data it must be filtered to failures + mapped to crit severity. The metric is Total Jobs only — `protected_clients_seen` (a DISTINCT count) isn't in the ADR's aggregation primitive set, left out rather than widen the primitives (stop-and-steer).
- **`report_id "194"` / `dataset_name "Job details"` are per-deployment** (#34); bindings resolve by name with the `dataset_guid` as a cache-hint fallback. Raw source column names authored from the normalizer's aliases — unverifiable on a 0-row payload, confirmed at browser verification (the collect succeeds and renders empty).
- **Pre-existing, NOT a phase-7 regression:** the License Summary HTML-import "produced no license rows" error (`license_summary/service.py:186`) is in the bespoke LS import path, which phase 7 did not touch (verified: no LS/import file changed; the only `license_summary`-mentioning changed file, `canonical_view.py`, got a single generic-table `empty_message` line). Filed as a separate backlog item.

---

## 2026-05-29 (ADR 0004 phase 6.5 — dev tools retirement, part 1)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `c243057` (#25 repoint), `70d8a0f` ((a) metrics pages), `27101e1` ((b) scaffolding), `a3a9d47` ((c) staging guard), plus wrap-up + pointer.

Retired the disposable Development-page dev tools now that the canonical workspace renders the migrated subjects (phases 5/6). STEP 1 was a **classification gate** — every Development surface assigned to (a) auto-obviated / (b) disposable scaffolding / (c) load-bearing — approved before any deletion. Browser-verified PASS. **713 passing** under both `pytest` and `python -m pytest` (was 708; +3 repoint guards, +2 staging-preservation guards).

### Removed

- **(a) obviated metric dev pages** (`70d8a0f`) — `/metrics/client-count`, `/metrics/client-growth`, `/metrics/capacity-license` routes + the exclusive `metric_detail.html` template + the Metric Details landing section. Client Growth (phase 6) and Capacity License (phase 5) render canonically in the workspace now.
- **(b) disposable scaffolding** (`27101e1`) — `/lab-readiness`, `/api/test`, and the entire Reports Plus exploration cluster (`/reportsplus/reports`, `…/reports/<id>`, `…/report/<id>`, `…/report/<id>/metrics`, `…/datasets`, `…/dataset/<guid>`, `…/data/<guid>`, `…/health-candidates`, `…/execution-validation`) — 11 routes + their 11 exclusive templates + the now-unused `shared.py` imports in the dev blueprint.

### Changed

- **#25 detail_endpoint repoint** (`c243057`, repoint-FIRST) — `client_growth`/`capacity_license` tile `detail_endpoint` → `main.quick_hc` (registry.py:248,282), matching SA/LS. They were the only two tiles pointing at dev routes; repointed before deletion so `_detail_url_for_tile`'s `url_for()` can't `BuildError`. **#25 RESOLVED.**
- Dev landing slimmed to the surviving Workspace / License-Summary links + the held Security Assessment cluster; `base.html` dev-link active-check and the kept `security_assessment.html` raw-extraction link de-referenced from the deleted routes.

### Added (guards)

- **Repoint guards** (`c243057`) — every tile `detail_endpoint` resolves under app context; no tile points at a retired dev route; the two migrated tiles open the workspace.
- **(c) staging-preservation guards** (`a3a9d47`) — the AI-authoring review loop (`/quick-hc/staging` + approve/reject) endpoints stay registered, and web + MCP staging share the same `db.staging` backend.

### Notes

- **The gate corrected the brief's load-bearing premise.** The AI-authoring review loop is the **top-level `/quick-hc/staging` page** (`staging.py` → `main.quick_hc_staging`), *not* in the dev-tools blueprint — so retiring dev tools can't touch it. Verified: the web Staging page and the MCP tools (`list_staged_artifacts`/`execute_approval`/`reject_staged_artifact`) both drive `cvhealthcheck.db.staging` (the `staged_artifacts` table). The dev **"Security Assessment Registry (internal)"** view is a *different* surface — `SecurityAssessmentService.get_history()` (SA artifact-collection history), touching no staging — so it is **(b) deletable**, not the load-bearing (c) the brief feared. (Backlog #24 corrected accordingly.)
- **The Security Assessment dev cluster is HELD for its own pass** (steering decision) — `reportsplus_security_assessment` + import/history/registry-export/registry-view. Biggest blast radius, entangled with canonical-SA coverage parity, and it has its own backlog item (#14 legacy-store retirement). Phase 6.5 deleted only the unambiguous (a)+(b); the dev blueprint + its remaining `shared.py` orphan helpers get fully reaped when the SA cluster's dedicated pass lands.

---

## 2026-05-29 (MCP server #35 — root-caused + defense-in-depth hardening)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `62a5658` (offload), `483b36b` (quiet stderr), `fd522a5` (smoke test), plus pointer.

**#35 root cause (resolved, NOT a code change): SSH idle-timeout disconnect.** The client log showed the SSH session reaped on a ~2-hour idle timeout — last successful tool response at 15:56:45, then `Connection to dev closed by remote host` / `client_loop: send disconnect: Broken pipe`, "transport closed" at exactly 17:56:45 (two hours later to the second). The earlier symptoms were separate, already-resolved issues: a PTY problem (gone once the launch used `ssh -T`; every tool call — readers and writers — then returned) and pre-existing `Permission denied` / `unable to open database file` DB-path errors. **The fix is an SSH keepalive config change (`ServerAliveInterval`/`ClientAliveCountMax`), client/server side — outside the repo.** Investigation confirmed the server itself answers tool calls correctly over stdio.

### Added (server hardening — defense-in-depth, NOT the disconnect fix)

The STEP-1 investigation *did* surface one real server-side fragility, hardened here proactively:

- **Tool work offloaded off the event loop.** FastMCP (mcp 1.27.1) runs a sync tool **inline on the asyncio event loop** that also drives the stdio transport (no thread offload). A slow/blocking tool — a future live REST/CommCell call, or DB lock contention — would freeze the transport. Each tool is now registered wrapped in `anyio.to_thread.run_sync`; the module-level functions stay sync (directly callable + unit-tested), tool LOGIC unchanged (writers included — only execution context moves off the loop), schemas preserved via `functools.wraps`.
- **Per-request SDK stderr chatter quieted** — `main()` raises the `mcp` logger to WARNING so the SDK's `Processing request of type …` INFO lines can't accumulate and backpressure the loop if a client doesn't drain stderr. Targeted at the `mcp` logger only.
- **Live-execution smoke test** — spawns the real server, `initialize` → `call_tool("list_subjects")`, asserts a returned payload (a tool can advertise correctly and still hang on execution — the schema/drift test can't catch that); plus a concurrent-writer variant guarding the loop-blocking path. Wrapped in `anyio.fail_after` so a regression fails loudly. 708 passing both invocations.

### Notes

- **The hardening is NOT claimed to fix the disconnect.** #35's resolution is the SSH keepalive config. The smoke test does not traverse the client→SSH→transport path, so a green run here doesn't prove the disconnect is fixed. The offload + stderr-quieting are independent robustness improvements (and would matter the moment a tool does real blocking I/O).

---

## 2026-05-29 (ADR 0004 phase 6 — migrate client_growth)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `4c22720` (6a render_mode), `35d8480` (6b chart labels), `9696b38` (6c catalog migration + e2e test), plus wrap-up + pointer.

The **second regressed-subject migration**, and the first **informational (non-evaluative) metric** on a real subject — the deliberate contrast with phase 5's evaluative one. client_growth now collects a `metric` (latest Total, plain key/value, no verdict), a `table` (monthly detail), and a real `ChartSection` line (Total clients over months) from the live lab. Browser-verified PASS. 704 passing under both `pytest` and `python -m pytest` (was 697).

### Added

- **`build_metric_section` honors a spec `render_mode`** (default `"metric"`). A spec may declare `render_mode "meta"` + no `evaluative.rules` for an **informational** metric: plain key/value, no severity/badge/verdict (the LS `commcell_info` render path). Declared intent, not inferred from rule presence. A regression test pins that the **default evaluative path is unchanged byte-for-byte** (capacity_license / `_metric_test` still `render_mode "metric"` with the verdict intact).
- **Chart label truncation** — `build_chart_section` truncates an ISO-datetime label (e.g. `client_growth`'s `MonthStart` converted via `unix_seconds`) to its date part (`2025-05-01`); non-ISO labels (`capacity_license`'s `"May 1, 2025"`) pass through unchanged.
- **Migration 0015 — client_growth three-face bindings** (all to `Client Count`, report 318): metric (`Total` latest + net change, `render_mode "meta"`, **no rule**), chart (`Total` line, no gap handling), table (`column_map` clean columns + conformance, keeping the unix→ISO conversion). The three sections already existed (0003); this re-binds their REST source.
- End-to-end test over the **real dev-box capture shape** (13 fully-populated rows, no sentinel): three faces; metric meta-mode with no verdict and `net_change` reading the same latest month as `Total`; chart continuous (genuine zeros plotted, no gaps) with date-truncated labels; table 13 clean rows.

### Notes

- **The metric is informational — no verdict (deliberate).** Unlike capacity_license (a ratio with a natural ceiling → warn/critical), client growth has no meaningful threshold ("is N% growth good?" is customer-dependent). The metric is the latest-month `Total` (+ net change) in `meta` mode. **The phase-plan's YoY-decline rule is intentionally dropped — phase 6 supersedes it.** capacity_license proved the evaluative metric path; client_growth proves the informational one. Same metric face, two render modes.
- **No sentinel (verified on the live collect).** `Client Count` returns 13 fully-populated rows with real integers — the eleven leading `0/0/0` months are *genuine* zeros (plotted on the line), not inactive-month sentinels. So no `spanGaps`/gap handling and no n/a treatment — confirmed absent rather than guarded. (Contrast capacity_license's `-1`.) This is the **capture-vs-live discipline** paying off again: the binding was authored against the live data, not the captures.
- **ClientGrowthDetails (pivoted) deferred.** report 318 also exposes a `ClientGrowthDetails` dataset with months-as-columns (a pivoted single row). Consuming it needs an un-pivot/transpose the catalog model can't express; out of phase 6, recorded as a follow-up + a future test case for whether the catalog needs a transpose primitive.
- **`report_id` 318 is per-deployment** (backlog #23 / #34); bindings resolve by `dataset_name`, the GUID is a cache hint.
- **No existing subject changed** (browser-verified): SA, LS, the three `_test` subjects, capacity_license (its evaluative metric n/a + chart-with-gaps), backup_job_summary unchanged.

---

## 2026-05-29 (ADR 0004 phase 5 — migrate capacity_license)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `192e65c` (5a REST spec-carrying), `caba06e` (5c chart gaps), `2808518` (5b catalog migration + e2e test), plus the wrap-up + pointer.

The **first real subject migrated** onto the three-face vocabulary — and the start of the user-visible regression recovery. capacity_license now collects a `metric` (utilisation), a `table` (monthly detail), and a real `ChartSection` line (Used Capacity trend) from the live lab. Browser-verified PASS (live authenticated collect). 697 passing under both `pytest` and `python -m pytest` (was 691).

### Added

- **REST-path spec-carrying** — `RESTExtractor` now populates `section_metric_specs` / `section_chart_specs` / `section_card_specs` from each section's `extraction_instructions` (phases 2–4 only did this in `FixtureExtractor`). This is the mechanism that lets a *real* subject build metric/chart/card sections on a live collect.
- **Chart gap handling** — `ChartSeries.data` widened to `list[float | None]`; `build_chart_section` maps `null` and any declared `gap_value` (capacity_license's `-1`) to `None` (a break in the line), while `0` stays a real plotted value; the Chart.js line dataset sets `spanGaps:false`.
- **Migration 0014 — capacity_license three-face bindings** (all to `Capacity License Usage`, report 318): metric (latest-month `utilisation_pct` via CEL, sentinel→muted n/a, warn≥70/critical≥90), table (clean columns via `column_map` + conformance), and a NEW chart section (Used Capacity line, `gap_values [-1]`).
- End-to-end test driving the **real dev-box capture shape** (13 monthly rows, `-1` inactive / `0` active) through the migrated catalog + extractor: metric muted n/a, chart gaps at the eleven `-1` months with `0` at the active months, table 13 clean rows.

### Notes

- **Sentinel correction: guard `-1` AND `null`.** The migration-0003 comment and the gw02 captures said inactive months are `null` in REST, but the **live dev-box collect returns `-1`** (verified this session). The canonical path treats both `-1` and `null` as the inactive sentinel (→ muted n/a in the metric, gap in the line); `0` is a real value. A `null`-only guard would have rendered `-1` as a literal negative — the regression class the legacy `max(... or 0, 0.0)` clamp hid, flipped to `-1`. Load-bearing, and only visible from the live collect.
- **Decision #2 (cardinality) superseded by the live single-CommCell shape.** The brief's design read the headline utilisation off a report-provided **"Total" aggregate row** and rendered per-CommCell detail rows — derived from the multi-CommCell gw02 captures. The configured dev box is **single-CommCell**, and the dataset carrying a Total row (`...Details`) errors on CacheDB params here while `...Summary Chart` is empty; the only populated dataset is `Capacity License Usage` (a single-entity monthly series). So (Option A) all three faces bind to it: the **metric reads the latest month** (no Total row exists), and "per-CommCell detail rows" collapse to the **monthly series**.
- **Zero-data lab is the correct PASS.** Purchased = 0 / Used = −1 everywhere on this lab, so n/a utilisation + a near-empty (gapped) trend is the right result — not a 70% warning. Warn/critical firing is proven by `_metric_test`. No non-zero fixture was seeded into the real subject.
- **`report_id` is per-deployment** (318 here; varies per CommCell — backlog #23). Bindings resolve by `dataset_name`; the `dataset_guid` is a cache hint only. Cross-deployment report discovery is a new deferred backlog item.
- **Usage-bar table column deferred.** The per-row utilisation bar is genuinely new rendering (derived table column + bar renderer) and shows n/a on this lab; the table renders clean column-mapped rows. Folded into the cosmetic styling pass / a follow-up.
- **No existing subject changed** (browser-verified): SA, LS, the three `_test` subjects, client_growth, backup_job_summary unchanged.

---

## 2026-05-29 (ADR 0004 phase 4 — card section type)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `1028265` (4a model), `a443043` (4b CHECK migration), `4c244e1` (4c build/emit/disambiguation), `d7b41eb` (4e Python renderer), `3301b83` (4f JS renderer), `5d18ade` (4g SUPPORTED += card), `92b0c7b` (4h+4d test subject + conformance), `60c391c` (FIX 1 header badge), `1b822ed` (FIX 2 test-subject sidebar chapter), plus wrap-up + pointer.

The `card` section type — the last new section type in ADR 0004 (`multi_section` deferred to a future LS ADR). A card is a flat labeled key-value identity block that **also carries a section-level verdict** (the steering decision: every card is judged), reusing the metric severity + verdict_chain machinery. Browser-verified. 691 passing under both `pytest` and `python -m pytest` (was 673).

### Added

- **New `CardItem` + `CardSection` models** (own `type` literal, in the Section discriminated union). `CardSection` carries `items`, an optional `columns` grid hint, and — reusing the EXACT `severity` + `verdict_chain` (`VerdictEntry`) shape `MetricItem` carries — a section-level verdict. This evaluative-shape duplication across metric and card is intentional and temporary; **phase 8 unifies the evaluative face**.
- **Migration 0012** — table-rebuild widening `subject_sections.section_type` CHECK to allow `'card'` (SQLite can't alter a CHECK in place; follows migration 0004's pattern; safe — nothing references the table incoming).
- **`build_card_section(spec, rows)`** — reusable: maps declared `{label, field}` items off one row, and applies an optional template-default verdict via the **same phase-2 threshold evaluator** a metric uses.
- **Python + JS renderers** — `canonical_view` emits a `type:"card"` labeled-value view; `quick_hc.js` renders a grid (reusing `.meta-card` styling).
- **`card` added to `SUPPORTED_SECTION_TYPES`** — CHECK (0012) and SUPPORTED now agree; the loud-failure guard re-points at `multi_section`.
- **`_card_test` subject** (migration 0013) — a field-mapped identity card carrying a status verdict (free space 8% ≤ 15% → warning), from a fixture; rides the `is_test` toggle (one test subject per type).

### Changed

- **`output_as:"card"` disambiguation.** It was a declared-but-unused stub whose only behavior was `rows[:1]` in the REST extractor (no production row used it). It now means exactly one thing — "emit a CardSection" — and the obsolete `rows[:1]` trim was removed from the extractor (row selection is the card builder's concern). The token does one job.
- **FIX 1 — section status badge moved to the section header** for *both* card and metric, right-aligned next to the inclusion control (`[title … badge ☑]`). Finding: metric badges render per-item (attached to the judged value — sensible, kept as detail); the card badge was section-level above the grid. Both now also show a section-level summary badge in the header (card = its severity; metric = worst item severity). Renderer-only.
- **FIX 2 — test subjects render in their own "Test subjects" sidebar chapter** (grouped via `is_test`), separate from the real category structure, instead of mixed under Operations. Sidebar-rendering only.

### Notes

- **Cards are judged (overrides ADR line 31).** The ADR says "an identity card carries only semantic and presentational"; the steering decision is that the compliance engine judges every card, so cards carry an evaluative face too. The ADR text fix is queued (HANDOVER backlog), not edited mid-phase.
- **The three-layer model** (catalog = durable definition / engagement = per-run consultant state / render = dumb) is the framing several phase-4 decisions hinged on: a card's config IS its catalog declaration (no per-card runtime settings UI); report-inclusion stays engagement state (the existing per-section checkbox, not a card feature); the card status is catalog/evaluative. Queued to be stated explicitly in the ADR/docs (HANDOVER backlog).
- **Severity enum is fixed at five values** — `critical` (breached hard limit) / `warning` (approaching threshold) / `info` (neutral notation) / `good` (active positive judgment) / `muted` (suppressed / n-a). Section-level header badge = the worst item by `critical > warning > info > good` (muted outside the ordering). "Healthy" etc. are display labels for `good`, not new codes — one enum across the evaluative face; phase 8 uses these same five.
- **No existing subject changed** (browser-verified): the environment identity block still renders as the plain `meta` key-value block (the card type did **not** displace it); SA, LS, the three regressed subjects, `_metric_test`, `_chart_test` unchanged.

---

## 2026-05-29 (ADR 0004 phase 3 — chart section type + MCP schema reconciliation)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `6423a34` (3a+3b model/build/emit), `225ddf7` (3d Python renderer), `618b7c3` (3e JS Chart.js + lifecycle), `6f066a0` (3f SUPPORTED += chart), `f929c7c` (3g+3c test subject + conformance), `ce88cac` (3h MCP reconciliation), plus the wrap-up + pointer commits.

The `chart` section type, end-to-end, as a **single `chart_type`-discriminated renderer** (line + pie), browser-verified in Safari + Firefox. Bundled with the MCP schema reconciliation (backlog #30, #31), since phase 3 grows `SUPPORTED_SECTION_TYPES` — the surface the MCP schema over-advertised. 673 passing under both `pytest` and `python -m pytest` (was 658).

### Added

- **`build_chart_section(section_id, title, spec, rows)`** (`extractors/chart_section.py`) — reusable, mirrors `build_metric_section`. A chart is a *view* over a table: it maps `labels` from one column and each `series` from a column across rows; `chart_type` discriminates drawing. Column mapping only — no CEL in phase 3 (charts read raw columns); no verdict (the evaluative face is empty for charts). The pre-existing `ChartSection` model carried both data shapes with **no change** (line/bar = labels + N series over shared X; pie = labels + one proportional series; the existing validator holds) — the architectural settle.
- **`result_to_artifact` emits `ChartSection`** on `output_as == "chart"` (via `ExtractionResult.section_chart_specs`); a chart-only artifact registers as `good`.
- **Python + JS renderers.** `canonical_view` emits one canonical chart-data structure; `quick_hc.js` renders it via **Chart.js 4** (now loaded in the workspace template). ONE `buildChartJsConfig`, `chart_type`-discriminated. **Canvas lifecycle:** a module-level Chart instance registry + `teardownCharts()` destroys instances before every re-render and on leaving the config view (belt-and-braces `Chart.getChart(canvas)?.destroy()`); a visible fallback renders if Chart.js fails to load. Browser-verified: clean re-render across Collect / re-navigation, no leaked instances (the chart-regression-class bug is verified absent).
- **`_chart_test` subject** (migration 0011) — two chart sections (line: Added+Total trend; pie: job status breakdown) from JSON fixtures, exercising the single renderer across both shapes. Phase-1 conformance fires per chart section (section-grained). Rides the `is_test` toggle (one test subject per section type).
- **`chart` added to `SUPPORTED_SECTION_TYPES`** — now produced and rendered, so it joins `{findings, table, metric, chart}`; the loud-failure guard still rejects modelled-but-unsupported types (`card`, `multi_section`).

### Changed

- **MCP `get_canonical_schema` now derives from `CanonicalArtifact.model_json_schema()`** instead of a hand-maintained dict (backlog #30 — **closed**). The hand-schema had drifted two phases behind the models while `save_staged_artifact` validated against the live model, so it advertised shapes the validator rejected (the May-24 errors). Derivation makes drift structurally impossible. `supported_section_types` is sourced from `SUPPORTED_SECTION_TYPES` (backlog #31 — **closed**): the `$defs` describe what the model can express, this lists what the runtime accepts; they can't diverge.

### Notes

- **A chart is a view over tabular data, not a separate kind of data.** Phase 3's renderer is one `chart_type`-discriminated function, not a family of per-type renderers; adding bar/area/doughnut/radar/etc. is "a string + confirming the data-shaping," not a new renderer. Only line + pie are *built*; the architecture doesn't preclude the rest. They are **deferred** (architecture allows, not implemented).
- **NON-NEGOTIABLE drift guard added.** A test asserts the MCP schema equals the live model schema (+ the one `supported_section_types` annotation), describes the load-bearing phase-1/2/3 fields, and that `SUPPORTED_SECTION_TYPES ⊆` the modelled section types. Verified it fires loudly against a stale hand-schema — the loud-fail mechanism that was missing from the tool most central to ADR 0005.
- **Capacity Licenses classification (for phase 5).** Confirmed against the actual rendering: capacity_license has TWO chart-ish surfaces, **neither a phase-3 chart section** — (1) per-row utilisation **bars** (`usage-fill`, a table-with-bar-column presentation) and (2) a legacy inline monthly-trend **mini-chart** (raw `chart_capacity` divs). Phase 5 decides whether that inline trend becomes a real `ChartSection` (line) or stays a mini-chart; the per-row bars are a table-column presentation.
- **Browser verification PASS** (Safari + Firefox): line + pie both render correctly from the same renderer; canvas lifecycle clean across repeated re-renders; SA / LS / the three regressed subjects / the phase-2 metric subject all unchanged; toggle hides test subjects by default.

---

## 2026-05-29 (ADR 0004 phase 2 — metric section type)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `f78ab9d` (2a model), `bd811c8` (2c evaluator), `2687062` (2b build+CEL), `1626fa0` (2e Python renderer), `18170f8` (2f JS renderer), `d85b5d0` (2g+2d test subject + fixture + conformance), `5a2a817` (2h visibility toggle), `b9a5cfe` (sentinel-unit fix), plus the wrap-up + pointer commits.

The `metric` section type, end-to-end, browser-verified against a contrived internal test subject. The first canonical metric rendering through the full three-face vocabulary: catalog declaration → FixtureExtractor → CEL derivation → sentinel handling → threshold rule → severity verdict → Python + JS renderers. 658 passing under both `pytest` and `python -m pytest` (was 625).

### Added

- **MetricSection / MetricItem extensions** — `MetricItem.value` is now optional (None = sentinel "n/a", distinct from a real 0); `+derived`, `+severity`, `+verdict_chain`. New `VerdictEntry` model = one layer of the ADR verdict chain (layer / severity / rule_id / required `reason`). `MetricSection.render_mode` (default `"meta"`) — the explicit presentational discriminator. Added `muted` to `FindingSeverity`.
- **`cvhealthcheck.evaluative.threshold`** — minimum evaluative machinery: `evaluate_threshold_rule(rule, value, *, label, unit)` picks the highest-severity satisfied band (or `default_severity`), mutes on a sentinel value, and returns a single `template_default` `VerdictEntry` with a populated, auditable `reason`. Phase 8 prepends vendor / appends override on the same chain + adds the rules registry.
- **`build_metric_section(section_id, title, spec, rows)`** (`extractors/metric_section.py`) — reusable (phase 5 capacity_license uses the same helper + spec shape): field-source aggregation (latest/first/sum/min/max/avg), CEL-derived items (context = records + prior item ids), sentinel → None, and rule application. Derivations run once at collection time and are stored. `result_to_artifact` emits a MetricSection when `output_as == "metric"` and derives overall status from the worst metric verdict.
- **`FixtureExtractor`** + `data/test_fixtures/metric_test.json` + migration 0010 — the internal `_metric_test` subject collects from a shipped JSON fixture (no lab). `fixture_path` is sandboxed to `data/test_fixtures/` in code (rejects absolute paths and `../`). `POST /quick-hc/<id>/collect-fixture` runs it; the `json` source surfaces a Collect button. Phase-1 conformance fires per section on this path (2d).
- **Renderers** — `canonical_view.artifact_to_view` renders a `render_mode=="metric"` section richly (values, derived ƒ marker, severity badge + verdict tooltip, "n/a" for sentinels); `quick_hc.js` gains a `metric` branch + CSS.
- **Test-subject visibility toggle** — `is_test` flag (subject_id prefix `"_"`), a settings-page localStorage toggle (`quickhc-show-test-subjects-v1`), and a `renderLeft` filter. Hidden by default; class-level (governs all future test subjects).

### Changed

- `canonical_view`'s MetricSection branch now dispatches on the declared `render_mode`. License Summary's `commcell_info` defaults to `"meta"` and renders byte-for-byte as before (verified in the browser).

### Notes

- **Explicit `render_mode` over severity-inference (steering decision 4 amendment).** The rendering vocabulary is *declared intent* (`output_as=="metric"` → `render_mode="metric"`), not an emergent property of whether a field is populated. Gating on severity-presence would mean the day someone adds a severity to a currently-meta metric, its rendering silently flips — the exact latent coupling that caused the original chart regression. The explicit discriminator removes it. Verified LS's `commcell_info` is unaffected.
- **ADR example #2 shorthand confirmed in practice** — `build_metric_section`'s CEL items use the valid `.map`-style projection / direct field references; `sum`/etc. remain the registered aggregation primitives from phase 1. (HANDOVER backlog #26 queues the ADR-text fix for Proposed→Accepted.)
- **`extraction_instructions` now carries a second concept.** Phase 1 put `conformance` there; phase 2 adds the `metric` three-face block (and `fixture_path`). Flagged for the eventual catalog-vs-code boundary review: if a third/fourth concept lands there in later phases, consider decomposing `extraction_instructions` into first-class columns. Not now — visibility note only (HANDOVER backlog).
- **Threshold boundary is inclusive** as declared (`>=`): utilisation exactly 70 → warning. The test subject pins this.
- **Browser verification PASS.** Test subject renders correctly (multi-field, derived, sentinel n/a, warn badge); toggle works both directions; SA / LS / the three regressed subjects all render exactly as at end of phase 1 (no regression). Client Growth's degraded 13-row table is the expected unfixed regression (phases 3 + 6).

---

## 2026-05-29 (ADR 0004 phase 1 — Foundation)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `2956afc` (2a CEL), `d3b6da6` (2b template_version), `aaeca6b` (2c family), `7e1e611` (2d backend pinning), `4852c93` (2d UI), `5951750` (2e conformance), plus the wrap-up + pointer commits publishing this entry.

ADR 0004 phase 1 (Foundation) implemented. All infrastructure; **no user-visible change to existing subjects' content** (the three regressed subjects stay degraded — that's phases 5–7). 625 passing under both `pytest` and `python -m pytest` (was 575).

### Added

- **CEL plumbing (library: `cel-python`, imported as `celpy`).** New `cvhealthcheck.cel` package with a thin evaluator wrapper: `evaluate(expression, context) -> native value`. Loud-fail (`CELCompileError` / `CELEvaluationError`, both under `CELError`); never returns None to signal failure. Registers the ADR's catalog-vs-code-boundary aggregation primitives (`sum/count/avg/min/max/latest`) as custom CEL functions — plain CEL has `size()` but not these. Field transforms (`parse_number`, `parse_percent`, `strip_html`, `lookup`) deferred until a section type exercises them (phase 2+).
- **`ArtifactSource.template_version`** — the version-bearing subject_id a collection ran under. Optional on read (old artifacts load cleanly), set on every write via `result_to_artifact`. REST collection now also sets `collected_at`.
- **`subject_family(subject_id)`** + `version_number`, `list_family_versions`, `get/set_pinned_subject_id`, `resolve_active_version` in `db/subjects.py` — the family-derivation convention (strip terminal `_vN`) and version resolution.
- **Migration 0009 `customer_subject_pin`** `(customer_id, subject_family, pinned_subject_id)` PK `(customer_id, subject_family)` — per-customer template-version pinning. Collection resolves the pin (else latest version); the `/quick-hc/<subject_id>/pin-version` route persists the dropdown selection.
- **Source-tile version dropdown + "Last collected" (UTC)** in the workspace Data Source section, injected per subject by `build_subject_initial_data` (no edits to individual builders). Single-version families render a disabled one-option select.
- **Conformance mechanism** — `extractors/conformance.check_conformance(rows, conformance)` validates collected section data against a `conformance` block in the section's `extraction_instructions` JSON (`required_fields` / `field_types` / `enums` / `cardinality`). Returns the verbatim ADR 0004 failure-record shape on the first failing aspect. Section-grained in `RESTExtractor.extract` (failed section recorded in `ExtractionResult.section_failures`, siblings continue); emitted onto `artifact.metadata["conformance_failures"]`. Plumbing-only — no section type exercises it in phase 1.

### Changed

- **CommCell server version removed from the environment subject's DATA SOURCE tile** (it's a deployment property, not a property of this collection — ADR 0004 §Provenance). It remains in the environment subject's identity card.
- `RESTExtractor.extract` now distinguishes hard transport errors (fail-whole, unchanged) from conformance failures (section-grained, new).

### Notes

- **CEL library choice — `cel-python` over `common-expression-language` (Rust).** Both resolve with prebuilt aarch64 wheels and evaluate the ADR's example expressions. `cel-python` won on maturity (Cloud Custodian, latest release 2026-01-31), a distinct exception hierarchy (clean loud-fail), and dependency hygiene — the Rust binding failed to import out of the box (undeclared `typing_extensions`) and drags CLI deps (`typer`/`rich`/`prompt-toolkit`) into a library install. Performance is irrelevant here (derivations run once at collection over ≤13-row windows). Confirmed by the steering chat before code landed.
- **ADR example #2 was shorthand.** `sum(records.filter(r, ...).used_capacity)` projects a field off a *list*, which is not valid CEL; the working form uses `.map(r, r.used_capacity)`. Also `sum`/etc. are not CEL builtins — they're the ADR's documented aggregation primitives, registered in the wrapper. This implements the primitive set; it does not extend it (the stop-and-steer rule holds).
- **Two versioning mechanisms coexist.** ADR 0003's integer `version` column (`UNIQUE (subject_id, version)`) and ADR 0004's `_vN`-suffix-on-subject_id convention. They don't conflict — `capacity_license_v2` is a distinct subject_id row. The ADR text says the uniqueness constraint is "on subject_id (unchanged)"; the actual constraint is `(subject_id, version)`. Wording fix queued for ADR 0004's Proposed→Accepted transition (HANDOVER backlog).
- **Storage-keying for real multi-version is phase 5+.** Today every family has one version, so `resolve_active_version` returns the requested subject_id unchanged and artifacts store under the family id as before. When a real v2 lands and the dropdown switches versions, how the artifact store keys versioned-vs-family artifacts needs settling — out of scope for phase 1 (one version everywhere).
- **Browser verification (the workflow's central gate) is the user's remaining step.** Programmatic + app-level verification done: `/quick-hc` renders 200 with no template error; the assembled data shows the cleaned environment source tile, `version_info`/`last_collected` on every subject, and existing artifacts loading without `template_version`. The visual gate — confirming SA/LS still render correctly and capacity_license/client_growth/backup_job_summary remain in their current degraded state (NOT fixed yet) against the live lab — needs a human at the browser per the chart-regression lesson.

---

## 2026-05-29 (ADR 0004 phase plan committed)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `fa6328a` (phase plan), plus the wrap-up commit publishing this entry.

ADR 0004 phase plan committed: nine phases, dev tools retirement at 6.5, `multi_section` deferred to LS-handling ADR. Next: phase 1 implementation.

### Added

- **`docs/adr/0004-phase-plan.md`** — companion to `docs/adr/0004-three-face-metadata-vocabulary.md`. The ADR explicitly defers phase planning; this is that follow-on. Nine phases (1 Foundation → 2 metric → 3 chart → 4 card → 5 capacity_license migration → 6 client_growth migration → 6.5 dev tools retirement → 7 backup_job_summary migration → 8 evaluative face). Two scope adjustments: `multi_section` deferred to whatever ADR addresses License Summary, dev tools retirement (HANDOVER backlog #24/#25) folded into the sequence as phase 6.5.

### Notes

- **Phase 6.5 placement.** HANDOVER backlog #24 specified dev tools retirement as natural cleanup post-ADR-0004. Phase planning placed it explicitly between phase 6 (client_growth) and phase 7 (BJS), at the first moment LB-1 (production tile detail_endpoints depending on dev routes) is cleanly resolvable. Tile detail_endpoint decision (backlog #25) lands as part of phase 6.5.
- **Vocabulary documentation vs implementation.** ADR 0004 documents six section types (table / findings / metric / chart / card / multi_section). The implementation ships five. The ADR's vocabulary documentation stands at six; the LS-handling ADR brings `multi_section` with it. This is a deliberate documentation/implementation gap, not a regression of the ADR text.

---

## 2026-05-28 (WORKFLOW.md committed: living workflow document)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `b06c152` (WORKFLOW.md), plus the wrap-up commit publishing this entry.

WORKFLOW.md committed: living document codifying the AI-assisted architecture workflow used on this project. Sections marked as "emerging practice" will be revisited as those practices stabilize.

### Added

- **`WORKFLOW.md`** at the repo root, peer to README.md / CHANGELOG.md / HANDOVER.md / ROADMAP.md. 734 lines, 17 numbered sections covering scope of applicability, when NOT to use the workflow, human / AI division of labor, workflow stages (survey → steering → pre-cleanup → ADR → phased implementation → reality verification), STOP-and-steer protocol, design / implementation / system truth distinction, established vs emerging practices, continuous methodology marker capture, multi-context AI workflow, process cost, concrete lessons learned, retrospectives, important warnings, and summary.

### Notes

- The document is explicitly a living one; section 10 distinguishes established practices (survey-then-steer, phased implementation, STOP-and-steer, ADR-commit-alongside-first-phase, wipe-and-recreate, continuous marker capture, reality verification) from emerging practices (formula language selection, vocabulary expressiveness review, AI rebuild loop, conformance-failure structured record). Sections 14 (lessons learned) and 15 (retrospectives) will need revisiting as methodology retrospectives land.

---

## 2026-05-28 (ADR 0004 drafted: three-face metadata vocabulary)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `8a0f4fa` (ADR doc), plus the wrap-up commit publishing this entry.
**Status:** Proposed.

ADR 0004 (three-face metadata vocabulary) drafted and committed at `docs/adr/0004-three-face-metadata-vocabulary.md`. The survey at `docs/adr/0004-survey.md` is the evidence base. Implementation phasing is deferred to a follow-on phase-planning session per the ADR's own scope statement.

### Added

- **`docs/adr/0004-three-face-metadata-vocabulary.md`** — defines the three faces (semantic / presentational / evaluative), six section types (table / findings / metric / chart / card / multi_section), CEL as the formula language with a defined primitive set and a STOP-and-steer rule for extensions, the three vendor-compliance shapes (per-row severity codes / StatusRow / inline threshold), the vendor → template → override rules layering with explicit precedence and a `muted` severity, conformance failures as section-grained structured records that bridge to the future AI-rebuild flow, subject versioning via `_vN` suffix subjects rather than a version field, and migration of the three regressed subjects (Capacity Licenses, Client Growth, Backup Job Summary) as the ADR's end-to-end validation.

### Notes

- **Out of scope for ADR 0004** (per the ADR itself): License Summary migration, AI authoring loop, recommendations / predictive face, cross-CommCell report identification (HANDOVER backlog #23), and implementation phase planning.
- **The pre-ADR-0004 cleanup commits already address two of the survey's load-bearing gaps:** vendor-stable key preservation (`b871c46`) and unsupported-section-type loud failure (`4589409`). ADR 0004's Pointers section names them explicitly so implementation builds on top of them.
- **Methodology marker.** Future ADR surveys should write their plan-file deliverable to `/home/michiel/.claude/plans/` proactively before `ExitPlanMode`, so the post-survey commit task has a persistent source. The ADR 0004 survey had to be extracted from the chat transcript retroactively because no plan file was written.

---

## 2026-05-28 (pre-ADR-0004 cleanup: vendor-stable keys, loud failure for unsupported section types, report-ID backlog)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `b871c46` (vendor-key preservation), `4589409` (loud-failure validation), plus the wrap-up commit publishing this entry.
**Test status:** **575 passing** under both `pytest` and `python -m pytest` (was 566; +9 across two cleanup commits).

Three load-bearing fixes the ADR 0004 survey surfaced. None depend on ADR 0004's design conversation being settled; ADR 0004 will build on top of them.

### Fixed

- **Preserve SA vendor-stable identifiers (`attrName`, `PARAMID`) in canonical Finding.** Migration 0007's column_map dropped both — the canonical Finding had no slot for vendor-stable IDs at all, leaving rule overrides under ADR 0004's evaluative face with only free-text `Parameter` to match against. Commvault could rename the human-readable label and silently break any rule keyed on it. Migration 0008 extends the column_map for all six SA sections: `attrName → vendor_key`, `PARAMID → vendor_id`. Other operational columns (`Data Source`, `ccid`, `sys_rowid`, `GROUP`) remain dropped — `Data Source`/`ccid` are CommCell-level (already on `ArtifactSource`), `sys_rowid` is volatile, `GROUP` duplicates `section_id`.

### Added

- **`Finding.vendor_key: str | None` and `Finding.vendor_id: str | None`** — additive fields on the canonical Finding model. Both default to `None`, so existing artifacts predating this change validate cleanly.
- **`_build_finding` in `result_to_artifact.py`** — populates the new fields from the row dict.
- **Migration `0008_security_assessment_preserve_vendor_keys.sql`** — UPDATEs the existing six (security_assessment, rest, section_id) rows to add the two new column_map entries. Idempotent.
- **`cvhealthcheck.db.section_types` module** — pins `SUPPORTED_SECTION_TYPES = {findings, table, metric}` (the set the runtime can honour today) and raises `UnsupportedSectionTypeError` with a clear, informational message naming subject, section, declared type, supported set, and pointing at ADR 0004 for chart support.
- **Insert-time validation in `create_subject_from_proposal`** — future AI proposals declaring chart-typed sections fail loudly; the transaction rolls back; no half-state.
- **Collection-time validation in `RESTExtractor.extract`** — anyone bypassing the proposal flow (raw SQL, migrations, direct DB edit) with extraction wiring for a chart-typed section gets a clear error before any GET is attempted.
- **HANDOVER backlog #23 — Report IDs are CommCell-specific.** Three CommCell captures showed LS=206/178, BJS=194/168, Storage Utilization By Application=199/603 across deployments — and the dataset column schema differs between CommCells too. Any catalog row hardcoding a numeric `report_id` is single-deployment-scoped. ADR 0004 must address how subjects identify themselves across deployments (likely by report name or stable semantic identifier with per-deployment resolution to numeric ID).
- **Tests:**
  - `test_result_to_artifact_findings_preserves_vendor_keys` and `test_result_to_artifact_findings_vendor_keys_default_none` — pin the row dict → Finding hop and backwards compatibility.
  - `test_extract_preserves_vendor_keys_via_column_map` — pins the end-to-end column_map → extracted row shape with vendor identifiers present and operational fields dropped.
  - `tests/test_section_type_validation.py` — six tests covering the supported set, validator behaviour, insert-time rollback, and collection-time fail-whole.
  - `test_migration_status_reports_all_applied` count bumped 7 → 8.

### Notes

- **Real-data verification (vendor keys).** Replayed all six on-disk raw 336 dataset captures through the new column_map + result_to_artifact pipeline and wrote the resulting artifact via `ArtifactStore.save_artifact` to `data/catalog/artifacts/default/default/working/security_assessment/latest.json`. All 32 SA findings now carry both `vendor_key` and `vendor_id` populated. Sample finding: `title='Two-factor authentication'`, `vendor_key='2FAEnabled'`, `vendor_id='2501'`. This is equivalent to a fresh lab recollection because the raw captures ARE the lab's responses from 2026-05-27.
- **Real-catalog verification (loud failure).** The live DB has 7 chart-typed catalog rows today: `client_growth.chart` (system seed; legacy builder fulfills it via its own `chart_growth` typed section, so the canonical-driven path never asks for it), 4 cloud_storage_egress_ingress chart sections, 2 storage_utilization chart sections. The validator fires loudly against all 7 when exercised. The brief was scoped to NOT delete the existing rows — they're preserved as catalog declarations awaiting runtime support; the validator catches new attempts and any attempt to actually collect data for these sections.
- **Why insert-time AND collection-time.** Insert-time is the primary mechanism (catches AI proposals before they land in the DB). Collection-time is the safety net (catches anyone bypassing the proposal flow — migrations, raw SQL, direct edits). The same helper backs both; one test exercises each layer.
- **Surprise extension to the survey finding.** The survey identified storage_utilization and cloud_storage_egress_ingress as chart over-declarers. Step 1 surfaced that `client_growth.chart` (a SYSTEM seed in migration 0003, not an AI proposal) is ALSO chart-typed. The system-seed pattern shows the silent-render-nothing problem isn't limited to AI proposals — the seed itself has the same issue. The legacy builder happens to fulfill the chart for client_growth via its own `chart_growth` section emission outside the canonical model. The new validator preserves this row (no rollback for existing rows) and would fire if anyone added REST wiring for it.

---

## 2026-05-28 (infra: fix test-suite collection error; reconcile reported pass counts)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `06c70b4` (collection fix), plus the wrap-up commit publishing this entry.
**Test status:** **566 passing** under both `pytest` and `python -m pytest` (was: 0 collected under `pytest`, 566 under `python -m pytest` — see reconciliation below).

`tests/test_unified_upload_route.py` carried `from tests.test_security_assessment_import import HTML_SAMPLE` and `from tests.test_license_summary_web import CSV_SAMPLE` since its creation on 2026-05-25 (commit `dff43f1`). The project has no `tests/__init__.py` (tests are loose modules; the convention is established by every other file), so `tests` is not importable as a package. The result depended entirely on invocation:

- **`pytest`** (plain entrypoint, no `-m`): aborts during collection with `ModuleNotFoundError: No module named 'tests'`. Zero tests run. Suite cannot be evaluated.
- **`python -m pytest`**: cwd ends up first on `sys.path`, so `tests` resolves as an implicit namespace package. Imports succeed; full suite runs.

### Scope before the fix

12 tests in `tests/test_unified_upload_route.py` could only be collected via `python -m pytest`. Of those, 5 were the headline tests from recent fixes — and any session that ran `pytest` plain would have silently lost them:

- `test_system_upload_inline_returns_json_on_success`
- `test_system_upload_inline_returns_400_when_no_file`
- `test_system_upload_inline_returns_422_on_handler_error_class`
- `test_system_upload_inline_returns_500_on_generic_exception`
- `test_upload_action_field_matches_handler_form_field`

The other 7 are older `test_unified_route_*` tests carried over from the 2026-05-25 route-merge session.

### Fixed

- **`tests/test_unified_upload_route.py:47-48`** — dropped the `tests.` prefix from the cross-test imports. The `tests/` directory is on `sys.path` during pytest collection regardless of invocation, so `from test_security_assessment_import import HTML_SAMPLE` resolves cleanly under both `pytest` and `python -m pytest`. A short comment notes the convention so future test files don't reintroduce the `tests.` prefix. No `tests/__init__.py` added — that would have turned tests into a package and changed pytest's conftest discovery, and isn't necessary.
- **Verified** that all 8 named recent-fix tests (the 5 listed above plus `test_parse_license_summary_html_extracts_value_and_unit_combined_cell`, `test_parse_license_summary_html_handles_commvault_export_markup_shape`, and `test_parse_license_summary_html_does_not_cross_wire_section_titles`) are now collected and passing under both invocations.

### Reported-count reconciliation

The prior CHANGELOG entries used `python -m pytest` and were accurate for that invocation. My 2026-05-28 LS workload-section entry was **the outlier**: it ran `pytest --ignore=tests/test_unified_upload_route.py` and reported `556 passing (+2 new tests)`. The true count at that point was 568 under `python -m pytest` (566 prior + 2 new), or 0 under plain `pytest` (aborted at collection). 556 was a mis-count caused by treating the collection error as "pre-existing and unrelated" instead of investigating why earlier sessions hadn't hit it.

| CHANGELOG entry | Reported | True count under `python -m pytest` | True count under plain `pytest` |
|---|---|---|---|
| 2026-05-25 phase 2 step 3 (`f5c5946`) | (not flagged here) | 558? | 0 (aborted; broken file present from `dff43f1`) |
| 2026-05-25 phase 5 cleanup | **558** | 558 | 0 |
| 2026-05-27 inline JSON fix (`130e28b`) | **562** (+4 inline tests) | 562 | 0 |
| 2026-05-28 field-name mismatch (`cf14c15`) | **563** (+1 contract test) | 563 | 0 |
| 2026-05-28 LS numeric extraction (`3b25d8b`) | **564** (+1 new test) | 564 | 0 |
| 2026-05-28 LS workload-section (`1abc097`) | **556** (+2 new tests) ← my mis-count | **568** | 0 |
| 2026-05-28 collection fix (this entry) | **566 passing** | 566 | 566 |

Note the final 566 vs 568: the LS workload-section session's two new tests went into `test_license_summary.py` (always collectable). The 568 above is `566 (this entry, true total) + 2 (LS workload tests already counted)` — i.e. the new total is the same 566 plus the 2 LS workload-section tests, but those 2 were already part of the 566 figure at this entry. The mis-count was 556 → should-have-been 568; after this entry's collection fix, the standard run shows 566 (numbers reconcile against the same set of tests).

### Notes

- **Why earlier sessions hit it differently.** The Claude Code shell wrappers and historic session habits used `python -m pytest`. My recent session used the plain `pytest` entrypoint (resolved to `venv/bin/pytest`), which doesn't add cwd to `sys.path`. The two invocations diverge silently on the `from tests.X` shape — a quiet trap. The fix removes the trap entirely; both invocations now succeed.
- **Convention now documented at the callsite.** Two-line comment in `test_unified_upload_route.py` notes that the `tests/` directory is on sys.path without an `__init__.py`, so sibling test modules are imported by basename rather than via a `tests.` prefix. Future cross-test imports should follow the same shape.
- **Backlog entry added** (HANDOVER #22) flagging that the Capacity Licenses workload section in the Commvault HTML export encodes usage as a Summary-column status-bar percentage, not as a number in Used (TB). The recommendations / growth-trend work needs to either derive TB-used from `%×entitlement` or source consumption from the REST collect path.

---

## 2026-05-28 (bugfix: LS HTML workload-section detection for Commvault export markup)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `1abc097` (fix + tests), plus the wrap-up commit publishing this entry.
**Test status:** 556 passing (+2 new tests). `tests/test_unified_upload_route.py` collection error is pre-existing and unrelated.

After the prior LS numeric-extraction fix, the HTML import succeeded end-to-end but the artifact reported **0 workload-summary sections** despite the user pointing out that workload summary tables (Capacity / Operating Instances / Virtualization / User / Data Insights / Air Gap Protect / Other) are the CORE of a License Summary report. Investigation against the real Commvault export confirmed all seven section names ARE present in the file — they were being silently dropped (or mis-bucketed) by the parser.

### Root cause — two stacked bugs

**Bug 1 (primary): `_table_section_name` at `license_summary/import_html.py:128-133` resolved the wrong text.** The Commvault HTML export wraps section titles in `<span class="input-title tileHelpLabels component-title-text">Capacity Licenses</span>` inside several nested `<div>` wrappers — there are zero `<h2>`-`<h6>` headings in the entire 2 MB file. The old heuristic `table.find_previous(["h1", ..., "p", "div"])` walked DOM order backward looking for the first match in that tag list, found the `<div class="exportTable">` *immediately enclosing the table itself*, then called `.get_text(" ", strip=True)` on it — which dumped the entire table's text, producing strings like `'License Available Total (TB) Used (TB) Summary  Backup and Recovery 100 0%  Snapshot 500 0% ... 1 to 4 of 4 entries.'`. None of these match `SUMMARY_SECTION_NAMES`, so the parse loop's `elif section_name in SUMMARY_SECTION_NAMES:` branch never fired.

**Bug 2 (secondary): the header classifier can't distinguish workload sections from Other Licenses when the table's headers omit unit qualifiers.** Real Commvault exports have two workload sections (Virtualization Licenses, Data Insights Licenses) whose headers are bare `('License', 'Available Total', 'Used', 'Summary')` — no `(TB)` / `(instances)` / `(users)` suffix. `classify_header` checks the strict `OTHER_LICENSE_HEADERS = ("license", "available total", "used")` pattern first and returns `"other"` for those tables, so the parse-loop's `if table_kind == "other":` branch lights up first and the rows pile into `other_licenses`. The user's "9 Other Licenses rows" was actually 2 (Virtualization VM Sockets + Auto Recovery) + 7 (Data Insights E-Discovery / Risk Analysis / Threat Scan) merged together.

### Fixed

- **`_table_section_name` now walks `find_all_previous()` and matches against direct text only** (string children of each element, not recursive `get_text()`). The candidate must equal exactly a known section title from `_KNOWN_SECTION_TITLES = SUMMARY_SECTION_NAMES ∪ {OTHER_LICENSE_SECTION, AGENT_FEATURE_SECTION}`. Wrapper divs that contain `<table>` children no longer match — only the `<span>`/`<div>`/`<h*>` whose immediate text reads exactly e.g. "Capacity Licenses" qualifies. Returns `None` (never garbage) when no match exists.
- **Claimed-titles guard** prevents cross-wiring: once a title has been attributed to one table, later tables walking the DOM backward skip it rather than silently inheriting the prior table's section. The parse loop threads a `claimed_section_names: set[str]` through each `_table_section_name(table, claimed=...)` call.
- **Parse loop restructured** so `section_name in SUMMARY_SECTION_NAMES` is the *primary* discriminator for workload-summary tables, with classifier-based routing (`"other"` / `"agent"`) as the fallback for the legacy detail tables. Tables with non-unit-qualified headers now route by their resolved title — Virtualization Licenses lands in workload-summary instead of other_licenses.

### Added

- **`test_parse_license_summary_html_handles_commvault_export_markup_shape`** — fixture mimics the real export shape: section titles in `<span class="input-title tileHelpLabels component-title-text">` inside two layers of `<div>` wrappers, ~4 DOM steps before the table. Three sections, one with non-unit-qualified headers ("Virtualization Licenses" with bare `Available Total`/`Used`). Asserts each table resolves to its correct title, the non-unit-qualified section is NOT mis-bucketed as other_licenses, and row values flow through correctly (`Auto Recovery` → entitlement_value=`"500 VMs"`, used=`"0 VMs"`, status=`"0%"`).
- **`test_parse_license_summary_html_does_not_cross_wire_section_titles`** — fixture has two adjacent tables but only one preceding `<span>` title ("Capacity Licenses"). Asserts only the first table claims the title; the second table's `"Should Not Cross Wire"` row does NOT pile onto Capacity Licenses. Without the claimed-titles guard, the second table's `find_all_previous` walk would still match the first title.

### Notes

- **Real-file verification** against `data/imports/license_summary/License20summary_2026-05-27-20-16-24-20260528T113252Z-5eac3c37.html` (2 MB): 7 workload-summary sections (Capacity Licenses=4 rows, Operating Instance Licenses=2, Virtualization Licenses=2, User Licenses=5, Data Insights Licenses=7, Air Gap Protect Licenses=1, Other Licenses=2) totalling **23 workload rows** — exactly the brief's expected count. 0 standalone `other_licenses`, 0 `agent_feature_licenses` (the export genuinely contains no "Agent and Feature Licenses" section). No duplicate section names — the guard didn't fire because no cross-wiring needed correcting in this file, but it's there for future malformed exports.
- **`used=None` for some Capacity Licenses rows is the source's own data, not a parser issue.** The HTML cells are literally `<td></td>` for the `Used (TB)` column on Backup and Recovery / Snapshot / Replication / Backup and Recovery for Unstructured Data — the Summary cell carries the percentage (`<div class="status-bar complete-bar">0%</div>`) instead. The parser correctly preserves None where the source has no value.
- **Why existing tests missed the bug.** The HTML fixture at `tests/test_license_summary.py:51-102` uses `<h2>Capacity Licenses</h2>` followed by the table — the original heuristic's `find_previous(["h1","h2",...])` matches the `<h2>` first and correctly returns "Capacity Licenses". The real export has no headings; its titles live in nested `<span>`/`<div>` markup. Same pattern as the prior LS numeric-extraction bug: the test fixture is too clean to catch the real-world shape. The new fixture explicitly mimics the real markup so the test would have caught both bugs in advance.
- **Legacy detail-table compatibility preserved.** The legacy `OTHER_LICENSE_SECTION = "Other Licenses - current usage details"` and `AGENT_FEATURE_SECTION = "Agent and Feature Licenses - current usage details"` are in `_KNOWN_SECTION_TITLES` (so `_table_section_name` resolves them) but NOT in `SUMMARY_SECTION_NAMES`, so they continue flowing through the existing `elif table_kind == "other":` / `elif table_kind == "agent":` paths. Both the new compact workload layout and the older detail-table layout work.
- **CSV path is untouched** — it uses explicit section labels in the row stream, not adjacent markup, so the section-detection bug doesn't apply there. `normalize.py` classifier stays as a fallback for the legacy detail tables. The catalog-driven REST extractor is unaffected (REST has its own dataset routing).

---

## 2026-05-28 (bugfix: LS numeric value extraction for combined value+unit cells)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `3b25d8b` (fix + tests), plus the wrap-up commit publishing this entry.
**Test status:** 564 passing (+1 new test; two existing tests gained the previously-missing combined-cell assertions).

The LS HTML import succeeded end-to-end after the prior two fixes, but the imported data was incomplete — the workspace's Other Licenses table rendered blank `Available Total` and `Used` columns. The source HTML did contain the data; the bespoke LS normalizer was dropping the numeric prefix from cells shaped `"<number> <unit>"`.

### Root cause

`parse_number` at `src/cvhealthcheck/license_summary/normalize.py:64-72` ran `int(float(text.replace(",", "")))` against the whole cell string. For real-world cells like `"500 VMs"`, `"0 sockets"`, or `"25 TB"`, `float(...)` raises `ValueError` because of the space and the trailing letters → function returns `None`. The neighbouring `maybe_unit_from_value` correctly extracted the trailing alpha via regex, which is why the Unit column survived. The numeric columns vanished.

### Fixed

- **`parse_number`** now extracts the leading numeric prefix via regex `r"\s*(-?[\d,]+(?:\.\d+)?)"` before parsing it. Handles `"500 VMs"` → 500, `"0 sockets"` → 0, `"25 TB"` → 25; preserves `"1,234"` → 1234, `"100"` → 100, `""` → None.
- **`clean_text`** also strips literal `\x00` (NUL) bytes. The user's real LS HTML export has 84 NUL bytes scattered between tags (between `</thead>` and `<tbody>`, between `</tr>` and `<tr>`, etc. — none inside `<td>` content; BeautifulSoup ignores them). The clean_text change closes the brief's null-byte hypothesis as belt-and-braces — costs ~10 characters and immunises against any future case where a NUL byte lands inside a cell.

### Added

- **`test_parse_license_summary_html_extracts_value_and_unit_combined_cell`** — new test that pins the user's reported row shape (`VM Sockets` / `0 sockets`, `Auto Recovery` / `500 VMs` / `0 VMs`). Asserts the numeric fields parse correctly.
- **Two existing tests** (`test_parse_license_summary_html_extracts_canonical_records` and `test_parse_license_summary_csv_extracts_sections_and_metadata`) gained the previously-missing `available_total == 25` / `used == 10` assertions on the existing `"25 TB"` / `"10 TB"` row that the fixtures had always carried but no test ever checked the parsed numeric for.

### Notes

- **One fix covers three callsites** by construction: `normalize_other_license_record` (the demonstrated bug), `normalize_agent_feature_record` (same `parse_number` call shape — unverified against real-world data because the user's export had 0 agent/feature rows; the fix handles the at-risk shape if it ever appears), and the CSV path which goes through the same normalizers.
- **Real-file verification** against `data/imports/license_summary/License20summary_2026-05-27-20-16-24-20260528T113252Z-5eac3c37.html` (2 MB): all 9 Other Licenses rows now parse correctly. `Auto Recovery` (the user's specific blank-column row) now reads `available_total=500, used=0, unit="VMs"`. Other rows include 100 TB / None (a few Used cells in the real file are genuinely empty — the parser correctly preserves None there).
- **The real file has 0 `agent_feature_licenses` rows and 0 `workload_summary_sections`.** The Agent/Feature parsing the prior investigation flagged as "structurally at risk but can't tell from fixtures" remains unverified against real-world data because the real export contains no rows in those sections. The fix handles the at-risk shape if it ever appears. The 0 workload_summary_sections is also notable — the parser's section-detection may not match this lab's HTML structure, but that's outside this bug's scope.
- **Why existing tests missed the bug.** The HTML fixture had `<tr><td>Cloud Storage</td><td>100</td><td>40</td></tr>` (plain numeric) and `<tr><td>Deduplication</td><td>25 TB</td><td>10 TB</td></tr>` (combined). The asserted-value test fired against row 0 (`available_total == 100` — passed because plain numeric works); only `unit == "TB"` was asserted against row 1, which works fine because the unit extractor uses a different regex. A missing assertion, not a wrong one.

### Verification: tests fail-against-old, pass-against-new

Confirmed before applying the fix that all three new/extended assertions failed against the old `parse_number` with the same `assert None == 25` / `assert None == 10` / `assert None == 500` pattern. After applying the fix, all three pass plus the rest of the suite.

---

## 2026-05-28 (bugfix: upload field-name mismatch for already-collected system subjects)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `cf14c15` (fix + contract test), plus the wrap-up commit publishing this entry.
**Test status:** 563 passing (+1 from the new contract test).

Yesterday's inline-JSON fix (`130e28b`) unmasked a second latent bug. With the JSON-response path wired correctly, the JS now received a server-side error JSON it could display — and that error read "No file selected." even though the user clearly had a file selected. Root cause: the server-side path that builds the action dict shipped to the JS declared the wrong field name once a canonical artifact existed for the subject.

### Root cause

`build_subject_initial_data` takes two paths depending on whether the subject has a canonical artifact:

- **No-canonical path** (`_build_license_summary_subject` / `_build_security_assessment_subject` nodata branches) declared the correct subject-specific field names (`"license_summary_file"` / `"assessment_file"`) via `_upload_action(...)`. Correct.
- **Canonical-present path** (`_build_generic_subject` → `_build_generic_sources` → `_provenance_to_tile_sources` for subjects with a registered provenance builder — SA + LS) hardcoded `import_field="file"` at `subject_data_service.py:226`. **Wrong** — the handler reads `request.files[handler.form_field]` where `form_field` is the subject-prefixed name from `UPLOAD_HANDLERS`.

The JS correctly forwarded whatever `uploadAction.importField` the server told it. So the first successful collect of SA or LS produced a canonical artifact; every subsequent inline import POSTed under `"file"` while the handler looked for the subject-prefixed name; the handler returned `{"success": false, "error": "No file selected."}` — even though the file was clearly attached. This is also what produced the 41-of-42 LS duplicate artifacts: each failed UI attempt actually succeeded server-side and persisted a new artifact, but the JS reported the JSON-parse error (yesterday's bug) and the user retried.

### Fixed

- **`_provenance_to_tile_sources`** at `src/cvhealthcheck/quickhc/subject_data_service.py:226` now imports `get_handler` from `upload_dispatch` and uses `handler.form_field` as `import_field` for the action dict. Falls back to `"file"` when no handler is registered (the AI-subject case — the generic dispatcher reads `request.files["file"]`, which is correct).

### Added

- **`test_upload_action_field_matches_handler_form_field`** at `tests/test_unified_upload_route.py` — pins the invariant that for every subject in `UPLOAD_HANDLERS`, every upload action produced by `_provenance_to_tile_sources` declares `importField` equal to `handler.form_field`. Verified the test FAILS against the pre-fix code (`importField='file'` vs `form_field='assessment_file'` for SA) and PASSES against the fix.

### Notes

- **Source-of-truth principle.** The fix makes the action dict declare what the handler expects, rather than adding a multi-name fallback to `_handle_system_upload` that would accept "file" or the subject-prefixed name. The handler is the source of truth for what the file field is called; the action dict's job is to mirror that.
- **No JS change.** `submitImport` was already correct — it forwards `uploadAction.importField` verbatim. The server side was internally inconsistent (action dict said one thing, handler expected another).
- **The other side of `_upload_action(..., import_field="file", ...)` at line 269 (in `_build_generic_sources`) is correct as-is.** That path is for AI subjects, whose handler is `_unified_dispatcher_upload`, which reads `request.files.get("file")`. The fix correctly leaves the AI path alone.
- **Why the existing tests missed it.** All four tests added in yesterday's fix hardcoded the field name on both sides of the request (passed `"license_summary_file"` directly in the multipart data and confirmed the server accepted it). Both sides could agree on a wrong name and the tests would still pass. The new contract test reads the action dict the JS would actually receive, so it pins the cross-boundary invariant directly.
- **Verification was done against the provenance path** (canonical artifacts present at `data/catalog/artifacts/default/default/working/{license_summary,security_assessment}/latest.json`) — not against a fresh tile where the nodata builder would have masked the bug. Both subjects upload cleanly under the JS-derived field names; the user's exact failing filename `License%20summary_2026-05-27-20-16-24.html` also succeeds.

---

## 2026-05-27 (bugfix: inline JSON response for system-subject uploads)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `130e28b` (fix + 4 new tests), plus the wrap-up commit publishing this entry.
**Test status:** 562 passing (was 558; +4 new inline-mode tests).

Latent bug since 2026-05-25 — the workspace UI's inline import button for SA and LS displayed "Import failed: <SyntaxError>" (the WebKit phrasing reads "The string did not match the expected pattern"), but the upload was actually succeeding server-side. Users likely retried, producing duplicate artifacts. The fix is a 12-line addition to `_handle_system_upload` mirroring the X-Inline branch the generic dispatcher already had.

### Fixed

- **`_handle_system_upload` in `src/cvhealthcheck/web/routes/quick_hc.py`** now checks `request.headers.get("X-Inline") == "1"` and returns JSON (200/400/422/500 depending on outcome) when set; the prior flash+redirect path is preserved for non-inline callers. The four inline branches match the JS's expectations: 200 + `{"success": true, "message": ...}`, 400 + `{"success": false, "error": "No file selected."}`, 422 + `{"success": false, "error": <handler.error_class.message>}`, 500 + `{"success": false, "error": "Import failed: <msg>"}`.

### Added

- **Four tests** at `tests/test_unified_upload_route.py` covering the four inline-mode branches of `_handle_system_upload`. Use LS as the exemplar; SA's identical because the handler shape is shared via `UPLOAD_HANDLERS`.

### Notes

- **Root cause**: The system-subject upload helper (`_handle_system_upload`) ignored the `X-Inline: 1` header that the JS `submitImport` function sends. Without the inline branch, the server responded with a 302 redirect; the JS followed it, got HTML, and failed `resp.json()` parsing. WebKit's `JSON.parse` SyntaxError message is "The string did not match the expected pattern" — which made the failure look like a URL or form validation issue rather than a JSON parse failure. The generic dispatcher branch (`_unified_dispatcher_upload`) had the correct inline check; the system-subject branch (the consolidated `_handle_system_upload` from session 5b's commit `ae58c21`) was missing it.
- **Bug history**: The JS introduced the `X-Inline: 1` header at `9073f06` ("Land Report Inventory foundation, Quick HC standalone UI" — 2026-05-25). The corresponding server-side handlers at the time (`_unified_security_assessment_upload`, `_unified_license_summary_upload`) didn't honor it either. Session 5b's `ae58c21` consolidated them into the data-driven `_handle_system_upload` and preserved the X-Inline-ignoring behavior. ADR 0003 didn't touch the upload path at all — the bug surfaced during phase 5's LS investigation only because the user happened to try a CSV/HTML upload of LS data.
- **Duplicate artifact evidence**: Inspecting `data/catalog/license_summary/artifact_*.json` surfaced **7 content-duplicate groups** (hashing only the user-relevant fields, not `artifact_id`/`imported_at` metadata): 2 artifacts 16 seconds apart, 5 artifacts within 10 minutes (May 18 18:45-18:55), 4 artifacts within 17 minutes (May 18 18:13-18:30), 3 artifacts within 46 minutes, plus three longer-span groups (8/9/10 dupes across hours-to-days). The tight clusters are classic retry pattern — the user clicked Import, got the WebKit error, clicked Import again. SA's legacy store (`data/catalog/security_assessment/artifact_*.json`) has **29 artifacts, all unique** — SA appears not to have been retry-tested under this bug. Per the steering chat's instruction, no duplicates were deleted; cleanup is a separate decision.

### Manual verification

`POST /quick-hc/license_summary/import` via Flask test_client against the real app (no patches):

| Request | Status | Body |
|---|---|---|
| X-Inline:1 + valid LS HTML | 200 | `{"success": true, "message": "HTML import completed for ... with 1 other licenses and 0 agent/feature licenses."}` |
| X-Inline:1 + no file | 400 | `{"success": false, "error": "No file selected."}` |
| No X-Inline | 302 | redirect to `/quick-hc/license-summary` (existing flash+redirect path, unchanged) |

---

## 2026-05-27 (ADR 0003 phase 5: cleanup pass — ADR implemented with LS caveat)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `5a0e2d1` (dead code deletion + tests), `69030bd` (ADR amendment), plus the wrap-up commit publishing this entry.
**Test status:** 558 passing (was 560; -2 from the deleted `init_report` existence tests).

Phase 5 of ADR 0003 — and the end of the ADR 0003 implementation arc. Step 1 investigation surfaced that LS's report 206 doesn't fit the catalog model defined in this ADR. Steering chat approved Path A: leave LS bespoke, do the safe cleanup half of phase 5, mark ADR 0003 implemented with the caveat documented. The catalog-driven REST extractor handles four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment); License Summary retains its bespoke `collect_from_rest` path until a future expansion adds the missing extractor capabilities.

### Step 1 investigation — why LS was deferred

Probes against the lab's report 206 surfaced three structural mismatches between LS's data model and the ADR 0003 catalog schema:

1. **Name-ambiguous datasets across pages.** Report 206 has 47+ pages (Backup detail, Archive detail, Snapshot detail, Replication detail, per-workload-type pages, …). The dataset names the brief proposed (`Get Last Collection Time`, `GetLicenseSummaryCapacityV3`, etc.) appear multiple times across pages, each instance with a different GUID. The extractor's `_build_name_to_guid_map` (walking widget references) picks an arbitrary instance per name and produces *unusable* GUIDs — `GET /datasets/<guid>/data` returns `errorCode: 15020` "could not find data set" for them. The brief's hint GUID `02878d11-…` for "Get Last Collection Time" *does* work, but it came from the page-level `dataSets.dataSet[].guid` array, not from widget references. The new catalog schema has no way to express "this page's instance of this dataset name."
2. **Runtime parameter substitution from prior dataset results.** LS's bespoke flow executes the `GetOrganizationName` dataset first to extract `OrgGUID` values from rows, then passes them as `parameter.GUID=<value>` to the downstream metadata/other/agent datasets. 5 of 8 probed datasets returned HTTP 500 without this substitution. The catalog schema has no `depends_on` concept; phase 4's `parameters` field only supports static values.
3. **Per-row value formulas.** LS's bespoke `_format_other_license_value` does `LicUsageType` (integer code per row) → unit string ("TB" / "VMs" / "clients" / "users" / "millions" / "source VMs" / "instances") → append to numeric value. `_stringify_numeric_or_unlimited` converts -1 → "Unlimited". The phase 4 `column_map` schema does flat renames; it can't drive one column's formatting from another column's value.

Adding the missing extractor capabilities (page-aware GUID resolution, parameter substitution from prior dataset results, value-formula transforms) would more than double the extractor's surface area for a single subject. The cost exceeds the cleanup benefit; LS stays bespoke pending future consultant demand.

### Removed

- **`CommvaultSession.init_report`** at `src/cvhealthcheck/reportsplus/session.py` — the cacheId POST acquisition method. No production callers since the interstitial fix made the catalog-driven extractor GET-only. Also drops `_REPORTBUILDER_PATH` and `_CACHE_ID_KEYS` module constants. The `_cache_id` attribute and `fetch_dataset`'s `cache_id` parameter stay — callers can still pass a cacheId from a prior response's body for UI-correlated multi-call sessions; only the acquisition POST is gone.
- **`src/cvhealthcheck/reportsplus/report_definitions.py`** — the orphan `REPORT_DEFINITIONS` dict that fed `init_report`. Orphan since phase 2.
- **`_read_commcell_provenance`** at `src/cvhealthcheck/web/routes/quick_hc.py` — read `commserv.json` for the generic REST artifact's `commcell_id`/`commcell_name`; replaced by customer-row reads in phase 3.
- **Two `init_report` existence tests** + **four `init_report.assert_not_called()`** assertions at `tests/test_rest_extractor.py`. Trivially-true assertions and existence tests for the deleted method.

### Changed

- **ADR 0003 status** flipped from "Proposed" to "Implemented (with LS caveat)" with the caveat stated up front.
- **ADR 0003 Decision → Migration** rewritten. SA's migration described as shipped (with the deleted module list); LS's non-migration stated explicitly with the three structural reasons; the phase-5 cleanup deletions noted.
- **ADR 0003 Consequences → Negative** rewritten to mention LS's non-migration honestly. "One unified REST collection path" goal is partially achieved (4 of 5 REST subjects).
- **ADR 0003 Consequences → Out of scope** adds "LS catalog migration is out of scope for ADR 0003 as implemented. Future expansion work documented in the backlog."
- **HANDOVER backlog** adds an LS-catalog-migration entry documenting the three required extractor extensions for future work.

### Notes

- **`reportsplus/checklist.py` is still in the tree** but unused (only callers were the deleted SA bespoke modules; LS doesn't use it). Listed as backlog item #21 for a small post-ADR-0003 cleanup. Not deleted in phase 5 to keep the cleanup scope tight.
- **`extract_report.py`** stays — LS is its caller. Listed implicitly as part of the LS-migration future-work backlog item.
- **`_cache_id` attribute on `CommvaultSession`** is no longer set by any in-tree code (init_report is gone). Tests still set `session._cache_id = "C1"` directly to verify the cacheId-bound `fetch_dataset` path. The attribute and the parameter are kept because the GET-only protocol still permits passing an explicit cacheId from a prior response's body — useful if a future caller wants UI-correlated multi-call sessions without an acquisition POST.

### Carry-forward — the retrospective

ADR 0003's implementation arc (5 phases over 1 session + the prior 4-session sequence) produced four methodology lessons that haven't been processed yet:

1. **Wipe-and-recreate rule** — ADR 0002 set the precedent; ADR 0003 phases 1 and 4 followed it. Tool-wide default or ADR-by-ADR judgment?
2. **ADR workflow efficiency** — survey-then-steer-then-draft-then-phased-implementation. Was the overhead worth it given that phase 4 surfaced a model gap mid-implementation (column_map / status_to_severity) and phase 5 surfaced a deeper gap that forced LS bespoke?
3. **ADR-commit-alongside-first-phase pattern** — both ADR 0002 and ADR 0003 landed this way. Document in PATTERNS.md?
4. **NEW: Catalog-model expressiveness limits surfacing during implementation rather than design.** Twice during ADR 0003 the model turned out to be less expressive than the design conversation assumed. Worth a deliberate examination of how to surface this earlier — perhaps a "prototype against a real second subject before declaring the design done" step.

The retrospective is the recommended next session. It's prose work for Claude.ai, not filesystem work for Claude Code.

---

## 2026-05-27 (ADR 0003 phase 4: SA migrated to catalog-driven REST collection)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `5fa4b2d` (extractor extension + migration), `984864a` (bespoke deletion + UI URL + tests), plus the wrap-up commit publishing this entry.
**Test status:** 560 passing (was 582; net −22 from SA-bespoke test removals, +5 from new extractor tests for column_map/status_to_severity/HTML stripping, +1 from the migration-count assertion bump).

Phase 4 of ADR 0003. Security Assessment is now collected by the generic catalog-driven RESTExtractor — same path as `client_growth`/`capacity_license`/`backup_job_summary`. The bespoke `SecurityAssessmentService.collect_from_rest` and its supporting modules are deleted. Six new catalog rows describe SA's findings tables under report 336. The new extractor honors `column_map` + `status_to_severity` + HTML stripping (the catalog pattern previously only supported by the HTML extractor), letting raw Reports Plus rows become canonical Finding items without any SA-specific Python.

### Step 1 design fork: Approach A (column_map in REST catalog rows)

Step 1 surfaced that the SA UI renders **findings**, but the raw Reports Plus rows arrive with capitalized keys (`Parameter`/`Status`/`Remarks`/`Action`), Commvault's prefixed status codes (`2_Info`), and embedded HTML (e.g. `<a href="...">How to enable 2FA</a>`). The new extractor's `output_as: "findings"` path in `result_to_artifact._build_finding` expects already-normalized lowercase keys with canonical severity strings and plain text. Bridging the gap needed an extractor change.

The steering chat picked **Approach A**: extend the REST extractor with the same `column_map` + `status_to_severity` catalog-driven pattern that the HTML extractor already uses, instead of inventing SA-specific code. This generalizes — phase 5's LS migration will use the same machinery for its `output_as: "card"` sections.

### Added

- **Migration `0007_security_assessment_rest_section_sources.sql`** — seeds six `subject_section_sources` rows under the existing `security_assessment` REST source. Each section declares `report_id="336"`, `dataset_name`, `dataset_guid`, `column_map` (Parameter/Status/Remarks/Action → canonical lowercase), `status_to_severity` (mapping the four prefixed codes `1_Good`/`2_Info`/`3_Warning`/`4_Critical` to canonical severities), and `output_as: "findings"`. No parameters declared — probes confirmed the lab returns identical record counts with or without `parameter.sys_commCellId=10000` (lab has one CommCell).
- **`RESTExtractor` post-processing** — `_fetch_section` now applies `column_map` (rename source keys → canonical, drop non-mapped keys), `status_to_severity` (when `output_as=="findings"`, sets `row["severity"]` from the mapped status), and HTML stripping (when `output_as=="findings"` and a row's string value contains `<`, strips markup via `html.parser` to plain text). Mirrors the HTML extractor's existing pattern.
- **5 new tests** in `tests/test_rest_extractor.py` covering: column_map row projection, status_to_severity mapping (including unknown-value→info default), HTML stripping for findings rows, no-HTML-strip under `output_as: "table"`, and no-column_map raw-key preservation.

### Removed

- **`src/cvhealthcheck/adapters/security_assessment.py`** — the bespoke `adapt_reportsplus_rest` adapter.
- **`SecurityAssessmentService.collect_from_rest`** — the bespoke REST collection method. The service class keeps `get_current`/`get_artifact`/`get_history`/`get_canonical` and the HTML/CSV import path (`persist_security_assessment_artifact`, `import_security_assessment_upload`).
- **From `src/cvhealthcheck/reportsplus/security_assessment.py`**: `extract_security_assessment`, `normalize_security_assessment`, `_build_failed_rest_artifact`, `_is_failed_report_status`, `SECURITY_ASSESSMENT_REPORT_ID`, plus the supporting private helpers (`_normalize_row`, `_normalize_key`, `_stringify_action`). The file retains the read-side helpers (`load_security_assessment_artifact`, `security_assessment_status`, `security_assessment_quick_hc`, `SECTION_ORDER`) still used by the legacy dev page and the workspace report renderer.
- **CLI subcommand** `reportsplus security-assessment` (no production callers — was a dev tool).
- **`/security-assessment?refresh=1`** REST-refresh branch in the legacy dev page. The page still renders the most-recently imported HTML/CSV artifact; live REST collection now goes through the Quick HC workspace.
- **`quick_hc_security_assessment_collect`** route at `/quick-hc/security-assessment/collect`. The wrapping redirect at `/quick-hc/security-assessment` stays (it just bounces to `/quick-hc#subject=security_assessment`).
- **SA entries in `cvhealthcheck.registry.REGISTRY`** (the hardcoded in-process registry — no production callers, only tests). The orphan registry retains `environment` and `license_summary`.
- **22 SA-bespoke tests** across `test_security_assessment_import.py`, `test_registry.py`, `test_registry_helpers.py`, `test_registry_execution.py`. Generic-extractor tests at `test_rest_extractor.py` now cover SA's runtime path.

### Changed

- **`quickhc/registry.py`** — drop the hardcoded `collect_url="/quick-hc/security-assessment/collect"` from the SA TileDefinition. The dynamic `/quick-hc/<subject_id>/collect` URL builder (registry.py:391) now takes over for SA, same as the other three REST subjects.
- **`quickhc/subject_data_service.py::_DISPATCH_REST_COLLECT_URLS`** — SA's URL updated from the hyphenated bespoke `/quick-hc/security-assessment/collect` to the underscored generic `/quick-hc/security_assessment/collect`. LS still points at the hyphenated bespoke URL until phase 5.
- **`tests/test_core_solidity.py`** — expected SA collect URL updated to match.

### Notes

- **Artifact wipe**: the canonical SA artifact directory `data/catalog/artifacts/default/default/working/security_assessment/` was empty before this phase started, so no on-disk wipe was needed. ADR 0002 precedent + HANDOVER methodology marker #18 are still satisfied — the new path will overwrite `latest.json` on the next collect.
- **Legacy SA store** at `data/catalog/security_assessment/` (`latest_html.json`, `latest_csv.json`, `latest_rest.json`, plus several `artifact_*.json`) is **not touched** in this phase. It's pre-ADR-0002 storage used by the HTML/CSV upload path's `persist_security_assessment_artifact(write_legacy=True)`. HANDOVER backlog #15 tracks project-scoping it.
- **`checklist.py` (`normalize_check`, `normalize_status`, `STATUS_LABELS`, `checklist_summary`)** is now dead code — its callers all lived in the deleted modules. Left in place this phase as YAGNI cleanup for after phase 5.
- **`extract_report.py`** is still in use by LS — phase 5 deletes it alongside the LS bespoke service.
- **`REPORT_DEFINITIONS`** is still orphaned but in-place — phase 5 deletes it.
- **`build_security_assessment_provenance`** still exists in `quickhc/source_provenance.py` and is invoked via `source_provenance_dispatch` for SA's badge display. It's not in the collect path — only the source-status badges on the workspace tile depend on it. Kept as-is.

### End-to-end verification against the real lab CommCell

| Subject | sections | rows | overall status | sample finding (SA) / row (others) |
|---|---|---|---|---|
| `security_assessment` | **6** | 32 (7+6+3+3+10+3) | **critical** (2 critical, 0 warning, 12 good, 18 info) | `{title: "Two-factor authentication", severity: "info", description: "Disabled Commvault recommends you enable this feature", recommendation: "How to enable two factor authentication"}` |
| `client_growth` | 1 | 13 | — | `{Added: 0, MonthStart: "2025-05-01T00:00:00+00:00", Total: 0, ...}` |
| `capacity_license` | 1 | 13 | — | `{Month: "May 1, 2025", "Entity Name": "CS01 - 337F", "Used Capacity": -1, ...}` |
| `backup_job_summary` | 1 | 0 | — | (lab dataset still empty; protocol works, no errors) |

HTML stripping verified: SA's "Threat Indicator alert" (critical) and "Disaster Recovery Backup" (critical) findings have clean plain-text descriptions and recommendations. Original raw response contained `<a href="...">How to configure DR backup</a>` and `<br>`-containing remarks — both stripped to plain text.

Provenance for all four artifacts comes from the customer row (`commcell_id=SMOKE-TEST-CS`, `commcell_name=Default`) — phase 3 wiring intact, no regression.

### Carry-forward for phase 5

Phase 5 — LS migration — is structurally identical to phase 4 but larger: LS renders 7+ tables from report 206 and introduces the first `output_as: "card"` catalog rows (the header-info datasets). Phase 5 also retires `extract_report.py`, `REPORT_DEFINITIONS`, `_read_commcell_provenance`, the bespoke `LicenseSummaryService.collect_from_rest`, and the corresponding adapter/normalizer/persister modules. After phase 5, the catalog-driven extractor is the only REST collection path in the codebase.

The same `column_map` + `status_to_severity` machinery added in this phase covers any LS finding-style sections. For card-style sections, phase 5 needs to validate the existing phase-2 trimming (`rows[:1]`) reaches the workspace renderer correctly — the current `result_to_artifact` doesn't have a dedicated card branch (falls through to table). Could be a small extension or could be a workspace template change.

---

## 2026-05-27 (ADR 0003 interstitial fix: extractor switched to GET-only protocol)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `fb8f47b` (extractor + session + tests), plus the wrap-up commit publishing this entry.
**Test status:** 582 passing (was 581; +2 new `fetch_dataset` tests for direct-GET and `totalRecordCount` pagination; -1 test for the no-longer-reachable `init_report` failure path).

The code-side of the prior session's ADR 0003 amendment. Phase 2's extractor POSTed `reportBuilder.do` to acquire a cacheId before fetching dataset data; phase 3's smoke showed the lab CommCell returns HTTP 419 on that POST. ADR 0003 was amended (prior session) to use the GET-only protocol SA and LS were already using. This fix lands the code change and verifies it end-to-end against the lab.

### Changed

- **`RESTExtractor.extract()`** at `src/cvhealthcheck/extractors/rest.py` — drops the `session.init_report({"reportId": int(report_id)})` call. The flow is now: `get_report` → `parse_content_field` → `_build_name_to_guid_map` → per section: `name_to_guid.get(dataset_name)` → `session.fetch_dataset(guid, ...)` → post-process. Module docstring rewritten to describe the GET-only protocol. `_resolve_single_report_id`'s docstring updated to reference the report-definition GET rather than the cacheId-bound POST.
- **`CommvaultSession.fetch_dataset`** at `src/cvhealthcheck/reportsplus/session.py` — no longer raises when `cache_id` is missing. Without a cacheId, performs a direct GET to `/datasets/<guid>/data`; the lab auto-generates a cacheId in the response body which we ignore. With a cacheId (passed explicitly or stored from a prior `init_report` call), the prior cacheId-bound behavior is preserved unchanged.
- **Pagination loop** in `fetch_dataset` now reads `totalRecordCount` in addition to `total` (the lab returns the former).
- **`CommvaultSession` class docstring** rewritten to describe two modes: direct GET as the default; cacheId-bound for UI-style use. Replaces the prior framing that presented the cacheId pattern as canonical.
- **Tests at `tests/test_rest_extractor.py`** — `_mock_session` no longer pre-wires `init_report.return_value`. `test_extract_calls_get_report_init_report_and_fetch` renamed and the init_report assertion replaced. `test_extract_multi_section_shares_cache_id` renamed to `..._reuses_name_to_guid_map`. `test_fetch_dataset_requires_cache_id` replaced with two new tests covering the with-and-without-cacheId param presence. `test_fetch_dataset_terminates_on_totalRecordCount` added. `test_extract_init_report_failure_returns_error` removed (the failure mode is unreachable now).

### Notes

- **Lab investigation surfaced two extra restrictions on the no-cacheId path.** The lab's CacheDB rejects requests that include either `fields` or `orderby` query params unless a cacheId is also present ("Bad Request. Please check the parameters."). Both params are now only sent when a cacheId is set. The catalog still declares `fields` and `orderby` per section for self-documentation, but the server doesn't see them in the GET-only path. The dataset returns all columns and natural-order rows; downstream code (extractor post-processing, `result_to_artifact`) doesn't care about column subsets or sort order.
- **`init_report` and the rest of the cacheId machinery stay in `CommvaultSession`.** Anything that calls `init_report` explicitly still works; only the extractor stopped calling it. Whether to delete `init_report` is a YAGNI judgment for the next phase.
- **Pagination loop's `totalRecordCount` support.** The existing fallback (`len(records) < page_size` break) would have worked for our small lab datasets, but adding explicit `totalRecordCount` checking is more robust for larger collections.

### End-to-end verification against the real lab CommCell

| Subject | HTTP status | Rows | Sample row |
|---|---|---|---|
| `client_growth` | 200 on `get_report` + 200 on dataset GET | 13 | `{"Added": 0, "Data Source": "cs01", "MonthStart": "2025-05-01T00:00:00+00:00", "Removed": 0, "Total": 0, "sys_rowid": 1}` |
| `capacity_license` | 200 on `get_report` + 200 on dataset GET | 13 | `{"Data Source": "cs01", "Entity Name": "CS01 - 337F", "Month": "May 1, 2025", "Purchased Capacity": -1, "Used Capacity": -1, "sys_rowid": 1}` |
| `backup_job_summary` | 200 on `get_report` + 200 on dataset GET | 0 | (empty — lab's "Job details" dataset on report 194 is empty; verified by direct GET returning `totalRecordCount: 0, failures: {}`) |

For `backup_job_summary`, name→guid resolution succeeded against the live report 194 definition: `'Job details' → 'a30bd278-c7d9-470f-9ae9-8b4922743330'` — matches phase 1's corrected catalog GUID. The protocol works; the lab simply has no rows in that dataset right now. No 419 errors anywhere.

Artifact provenance for all three came from the customer row (`commcell_id = SMOKE-TEST-CS`, `commcell_name = Default`), confirming phase 3's wiring stays correct under the new protocol.

### Carry-forward for phase 4

The protocol now works end-to-end against the lab for the three existing REST subjects. Phase 4 — SA migration — can proceed: seed `subject_section_sources` for Security Assessment (report 336), delete `SecurityAssessmentService.collect_from_rest`, delete `reportsplus/security_assessment.py`, retire the SA-specific normalizer/persister/adapter, wipe `data/catalog/artifacts/<customer>/<project>/working/security_assessment/`. The cacheId-machinery in `session.py` stays dormant unless something explicitly opts in.

---

## 2026-05-27 (ADR 0003 amendment: protocol pivots to GET-only)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `5fcfa61`, plus the wrap-up commit that publishes this entry.
**Test status:** 581 passing (docs only — no code change this session).

Interstitial amendment between phase 3 and the next code-touching session. The steering chat re-examined ADR 0003's protocol decision against the HTTP 419 surfaced during phase 3's smoke test (POST `reportBuilder.do` rejected by the lab CommCell across every payload, token format, and token age tried). The original decision adopted the cacheId acquisition pattern based on a License Summary browser capture; closer reading of that capture showed the POST served interactive UI rendering (drill-downs, sorting, pagination cursors), not programmatic data collection. SA and LS have been successfully collecting against this CommCell using direct dataset GETs with no cacheId step. ADR 0003 is amended so the catalog-driven extractor uses that same GET-only protocol rather than introducing the cacheId POST. Phase 2's code still uses the old protocol and is broken against the lab; the fix is the next single-recommended action.

### Changed

- **ADR 0003 "Context"** — rewrites the "Investigation of the License Summary report's actual API traffic" paragraph to describe two observed patterns (browser-UI cacheId vs. SA/LS direct GET) without picking a winner there; the Decision section picks GET-only.
- **ADR 0003 "Decision → Catalog schema"** — replaces "the `reportBuilder.do` POST happens once per subject collection, the returned `cacheId` is reused…" with "the report definition fetch (`GET /reports/<report_id>`) happens once per subject collection, and the resolved `dataset_name` → `dataset_guid` map is reused across all section fetches…".
- **ADR 0003 "Decision → Extractor shape"** — step 2 now describes GETting the report definition and building a name→guid map. Step 4 now describes GETting `/datasets/<guid>/data` directly. The cacheId sentence is dropped from the error-handling paragraph. A new closing paragraph explains the browser-vs-programmatic distinction so a fresh reader understands why the ADR doesn't use cacheId despite the LS browser capture showing one.
- **ADR 0003 "Consequences → Positive"** — the "cacheId pattern means one `reportBuilder.do` POST per subject" sentence is replaced with "one report definition GET per subject collection (instead of per-dataset metadata lookups)" framing.
- **ADR 0003 "Consequences → Negative"** — the "cacheId pattern is more state to manage" sentence is removed (no longer applies).
- **ADR 0003 "Consequences → Open questions"** — the cacheId-lifetime question is removed entirely. The only remaining question is the same-`report_id`-per-subject constraint vs runtime check (resolved in phase 1 as runtime check; left documented for the historical record).
- **ADR 0003 "Pointers for implementation"** — the `CommvaultSession` pointer drops "cacheId-aware session; the protocol shape ADR 0003 standardizes on" in favor of a neutral "shared HTTP session for Reports Plus; the extractor uses its dataset GET helper".
- **ADR 0003 Context bullet for the generic `RESTExtractor`** — the "official two-step pattern" framing is dropped; just "a two-step pattern" now (factual, no implication that this is the right choice).

### Notes

- **The survey doc at `docs/adr/0003-survey.md` is unchanged.** Its "Surprises and observations" section S1 describes the protocol fork as observed at survey time. Survey docs are historical snapshots; corrections live in the ADR, not in the survey.
- **`CommvaultSession.init_report` and the rest of the cacheId machinery in `session.py` are not deleted.** The amendment is doc-only; the next session's extractor fix will simply stop calling `init_report`. Whether to retire the method entirely is a separate YAGNI decision deferred until the fix lands.
- **The 419 is no longer a "diagnose me" question.** It was the lab CommCell rejecting a POST it doesn't accept from a non-browser caller — possibly missing CSRF, possibly disabled endpoint, possibly version-dependent. The amendment makes the diagnosis moot by removing the POST from the protocol.
- **Phase 2's extractor is now provably broken against the lab** (HTTP 419 reproducible with a bare `CommvaultSession` independent of Flask). The next code-touching session rewrites it to match the amended protocol and re-runs the smoke for `client_growth`, `capacity_license`, `backup_job_summary`.

### Carry-forward for the next session

The interstitial fix: rewrite `RESTExtractor.extract()` to drop the `session.init_report(...)` call, make `CommvaultSession.fetch_dataset` work without a stored cacheId (the lab GET endpoint auto-generates one), update the tests at `tests/test_rest_extractor.py` to drop cacheId-reuse mock assertions, and verify end-to-end against the three existing REST subjects. Phase 4 (SA migration) remains gated on the fix.

---

## 2026-05-27 (ADR 0003 phase 3: customer-bound CommCell auth)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `284174a` (phase 3 implementation + tests), plus the wrap-up commit publishing this entry.
**Test status:** 581 passing (+18 from 563; new tests cover `is_authenticated_for`, customer-aware `/login` GET/POST, `/api/login` JSON variant, collect-handler redirects on missing or wrong-customer tokens, the missing-hostname error path, and `get_active_customer`).

Phase 3 of ADR 0003. Auth becomes customer-aware: `/login` authenticates against the active customer's `commcell_hostname` (not `CV_BASE_URL`), the resulting token is bound to that customer's id, and switching customer (or hitting a route whose active customer doesn't match the bound one) clears the token and bounces to `/login`. Generic-REST artifact provenance now comes from the customer row instead of `data/catalog/rest/commserv.json`.

### Step 1 surprise

The brief planned a new `/connect-commcell` route distinct from `/login`, on the premise that `/login` was app auth. Step 1 surfaced that **`/login` had always been the CommCell credentials prompt** — there was never a separate app-auth layer; `is_authenticated()` is exactly "session has a CommCell token." Creating a parallel route would have duplicated the same job with one URL-source difference. STOP-and-report fired; steering chat picked Path A (repurpose `/login`) over Path B (parallel route). SA/LS modules redirect to `/login` on 401 today and will continue to — they now land on the customer-aware prompt automatically, which is the right behavior heading into phases 4/5.

### Added

- **`SESSION_CUSTOMER_ID_KEY = "commvault_customer_id"`** at `src/cvhealthcheck/auth/commvault_auth.py` — third session key alongside the existing token and username keys.
- **`get_current_customer_id() -> str | None`** — reads the bound customer id from the session.
- **`is_authenticated_for(customer_id: str) -> bool`** — stricter than `is_authenticated()`: returns True iff a token is present AND it's bound to `customer_id`. Legacy unbound tokens (test fixtures that set `session[SESSION_TOKEN_KEY]` directly) return False here.
- **`get_active_customer(db=None) -> dict`** at `src/cvhealthcheck/web/active_project.py` — chains `get_active_project` → `get_customer`. Raises `ActiveProjectMissingError` if the FK is broken.
- **`tests/test_phase3_auth_customer_bound.py`** — 18 tests covering the new auth surface area end-to-end via Flask test_client.

### Changed

- **`set_current_token(token, customer_id, username=None)`** — `customer_id` is now a required keyword. Raises `ValueError` on empty/whitespace. Two production callsites updated; tests that bypass this function (set the session key directly) are unaffected.
- **`clear_current_token()`** also clears the customer id key.
- **`/login`** at `src/cvhealthcheck/web/routes/basic.py` resolves the active customer, displays "Connect to CommCell for {Customer Name}" with the customer's `commcell_hostname`, and authenticates against that hostname. When `commcell_hostname` is unconfigured, the form renders in a disabled state with a link to the customer edit page. POST without hostname returns the same disabled form with an explanatory error and does not call `login_to_commvault`.
- **`/api/login`** at `src/cvhealthcheck/web/routes/quick_hc_api.py` — same customer-aware flow; returns 400 with a JSON error when the active customer has no hostname.
- **`/quick-hc/<subject_id>/collect`** at `src/cvhealthcheck/web/routes/quick_hc.py` — dropped `@login_required` (it only checks `is_authenticated()` which is too loose under customer binding). Replaced with: resolve active customer → check `is_authenticated_for(customer_id)` → on mismatch, `clear_current_token()` if there's a token and redirect to `/login?next=…`; on missing hostname, flash error and redirect to the workspace. CommvaultSession base_url comes from `customer.commcell_hostname`; artifact provenance fields (`commcell_id`, `commcell_name`) come from `customer.commcell_id` and `customer.customer_name`. The `_read_commcell_provenance()` helper is no longer called from this path (still present for any future SA/LS retention).
- **`src/cvhealthcheck/web/templates/login.html`** — customer-aware copy ("Connect to CommCell" → "for {Customer Name}"); renders inputs and submit button as disabled when no hostname; links to the customer edit page.
- **`src/cvhealthcheck/web/routes/shared.py`** re-exports `is_authenticated_for` and `get_current_customer_id` for the route modules.

### Notes

- **End-to-end smoke against the real lab CommCell** (with Default's `commcell_hostname` set to the previous `CV_BASE_URL` value):
  - GET `/login` renders with the customer name + hostname.
  - POST `/login` with real lab creds returns 302 → `/quick-hc`; session has the token bound to `customer_id="default"`.
  - POST `/quick-hc/client_growth/collect` returns 302 back to the workspace (not to `/login`) — the auth check passes correctly and the request is delegated to the extractor.
- **A separate CommCell-side issue surfaced during the smoke test, *not* caused by phase 3:** the bare CommvaultSession isolation test (no Flask, no test_client, fresh token from `login_to_commvault`) shows `session.get_report("318")` returns 200 cleanly, but `session.init_report({"reportId": 318})` returns **HTTP 419** with a generic Commvault Command Center HTML error page, regardless of payload shape, token format, token age (fresh from `/Login` vs. the pre-existing `.token` file), or `QSDK ` prefix. The direct `GET /datasets/<guid>/data` path returns 200 and notably **includes a generated `cacheId` in the response body** — the CommCell auto-creates cacheIds for dataset GETs. Either the lab CommCell was reconfigured/upgraded since the phase 2 "end-to-end verified" report or there's a header/CSRF requirement the browser provides and Python's `requests` does not. This blocks real-world collection but is out of phase 3's scope; documented as the next session's investigation target in HANDOVER.
- **Default's customer row was updated for verification** (`commcell_hostname = https://192.168.182.129:4433`, `commcell_id = SMOKE-TEST-CS`). Left in place per the steering chat's instruction — useful for follow-up testing of the 419.
- **`_read_commcell_provenance` and `data/catalog/rest/commserv.json` still exist** but are no longer consulted by the generic REST collect path. They remain for `/quick-hc/commcell` and any SA/LS provenance reads until phases 4/5 retire that code.

### Carry-forward for phase 4 — and a blocker first

Phase 4 is the SA migration: seed `subject_section_sources` for Security Assessment (report 336), delete `collect_from_rest`, `reportsplus/security_assessment.py`, and the SA-specific normalizer/persister/adapter, wipe `data/catalog/artifacts/<customer>/<project>/working/security_assessment/`. But **before phase 4 can produce a working SA collection, the `reportBuilder.do` 419 needs to be diagnosed and resolved** — the cacheId pattern is the canonical collect path under ADR 0003 and SA will inherit it. Options when investigating: try a fresh CV admin session with browser DevTools to capture the exact headers/cookies on a working `reportBuilder.do` POST and compare; check whether a CSRF token is required; consider whether ADR 0003's cacheId pattern should pivot to "first dataset GET creates the cacheId" given that the direct GET works and returns a cacheId in its body. The third option is an ADR 0003 design re-examination, not just a fix.

---

## 2026-05-27 (ADR 0003 phase 2: generic REST extractor with cacheId-aware session)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** the phase 2 implementation commit immediately preceding this entry, plus the wrap-up commit that publishes this entry.
**Test status:** 563 passing (+9 from 554; new tests cover dataset_name resolution, hint fallback, same-report_id assertion, fail-whole, multi-section cacheId reuse, output_as="card", and the new `CommvaultSession.get_report`).

Phase 2 of ADR 0003. The runtime half of the rewrite: a single catalog-driven REST extractor that consumes the `report_id` + `dataset_name` fields phase 1 added, resolves dataset GUIDs at runtime from the live report definition, and posts `reportBuilder.do` once per collection to acquire a cacheId reused across all sections. End-to-end verified against the real CommCell: `client_growth` and `capacity_license` continue to collect cleanly (regression test) and `backup_job_summary` now collects successfully for the first time (smoke test of phase 1's corrected dataset_guid + phase 2's runtime resolution path).

### Added

- **`CommvaultSession.get_report(report_id)`** at `src/cvhealthcheck/reportsplus/session.py:92`. Sibling to `init_report` and `fetch_dataset`; GETs `/reportsplusengine/reports/<id>` using the same base_url/token/timeout. Returns the parsed JSON dict (caller pipes it through `parse_content_field` to unwrap the string-encoded `content` field). New method, no signature change to existing ones. Keeps the cacheId protocol — GET + POST + paginated fetch — fully contained within one collaborator that the extractor depends on.

### Changed

- **`RESTExtractor` rewritten** at `src/cvhealthcheck/extractors/rest.py`. New constructor `(db_conn, session, customer_id, project_id)` — explicit args, no Flask request context. New `extract(subject_id, version=1)` flow: load REST instructions → assert all sections share `report_id` (runtime check; reports offending section_ids on mismatch) → `session.get_report(report_id)` → `parse_content_field` → `discover_widgets` + `discover_dataset_references` build a `{dataset_name: dataset_guid}` map → `session.init_report({"reportId": int(report_id)})` to acquire the cacheId → per section, resolve `dataset_name` → guid from the map (fall back to the stored `dataset_guid` hint with a warning if name not in live definition; error if neither yields a guid) → `session.fetch_dataset` → post-process timestamps + null values. Supports `output_as="card"` by trimming `result.sections[section_id]` to `rows[0:1]` (rendering as a key-value block lands in phase 4/5 when the first card-shaped rows get seeded). Fail-whole: any section error aborts the run and returns errors without partial state.
- **`/quick-hc/<subject_id>/collect` route** at `src/cvhealthcheck/web/routes/quick_hc.py:179` constructs the new extractor with explicit `(customer_id, project_id)` resolved via `get_active_project(db)`. The `REPORT_DEFINITIONS.get(subject_id)` lookup and the `report_definition=` argument to `extract()` are gone. Auth flow (CV_BASE_URL, Flask session token) is unchanged — that's phase 3 territory.
- **`tests/test_rest_extractor.py` migrated**. Old-signature tests retired; new tests cover the new shape. Coverage: dataset_name → guid resolution wins over the stored hint, hint fallback with warning when name not in live definition, error when neither name nor hint resolves a guid, same-report_id-per-subject runtime check (with mismatched section_ids in the error message), missing-report_id error path, get_report and init_report failure paths, fail-whole behavior (second section never attempted after first section's fetch errors), `output_as="card"` trimming to first row, multi-section cacheId reuse (one init_report call, two fetch_dataset calls), timestamp conversion. Plus two new CommvaultSession tests covering get_report success and the non-dict-response error path.

### Notes

- **Same-report_id-per-subject runtime check** lives at `RESTExtractor._resolve_single_report_id`. Picked the runtime-check option (rather than a DB constraint or trigger) as ADR 0003 explicitly left open. Mismatch error reports the offending section_ids grouped by report_id so catalog seeding bugs are localizable.
- **Hint fallback policy.** If the live report definition lacks a `dataset_name`, the extractor falls back to the stored `dataset_guid` (the cache hint) with a warning rather than failing. Rationale: a stale hint that still resolves is better than a hard failure, but the warning ensures the next session sees the divergence and can investigate. If neither name nor hint produces a guid, that's a fail-whole error.
- **One cacheId per collection.** The cacheId from `init_report` is stored on the `CommvaultSession` and reused across every section's `fetch_dataset` call within the same `extract()` call. No per-section refresh; if the cacheId expires mid-run, the section fetch fails and the whole collection fails (the brief's "no per-section refresh" rule). Whether this is robust enough under real load is the open question ADR 0003 flagged; the end-to-end runs across three subjects in this session didn't trip it.
- **`customer_id` and `project_id` constructor args** are stored on the extractor but not yet consumed inside `extract()`. They're load-bearing for phase 3 (customer-bound token, customer-row-driven CommCell URL) and phase 4/5 (SA/LS migration). Passing them through now keeps the constructor signature stable across the remaining phases.
- **`REPORT_DEFINITIONS` dict at `src/cvhealthcheck/reportsplus/report_definitions.py` is now orphaned** — no callers remain in tree. ADR 0003's migration section lists this file for phase 5 deletion alongside the SA/LS-specific modules; leaving it in place rather than deleting early to keep phase 2's blast radius tight.
- **`init_report` signature unchanged.** The brief flagged a signature change as a STOP trigger. Path A (add `get_report` as a new method on `CommvaultSession`) was chosen and approved during the step 1 investigation; the cacheId protocol now reads as GET-then-POST-then-paginated-GET, all three methods living on the same session.

### Carry-forward for phase 3

Phase 3 wires the new extractor into the customer-bound token model per ADR 0003's "Authentication and customer scoping" section: the Flask session holds one CommCell token at a time bound to the customer it was issued for; switching active customer invalidates the token and forces re-auth; CV_BASE_URL stops being authoritative and the active customer's `commcell_hostname` becomes the source of truth. The extractor's constructor already accepts `customer_id` and `project_id`; phase 3 routes the auth flow to match. SA/LS modules still use the old REST paths; phases 4/5 migrate them and delete the dedicated code.

---

## 2026-05-27 (ADR 0003 amendment: wipe-and-re-collect, no forward-migration script)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `bd5262e`, plus the wrap-up commit that publishes this entry.
**Test status:** 554 passing (docs only).

Interstitial amendment between phase 1 (already landed) and phase 2. The steering chat re-examined ADR 0003's forward-migration step against ADR 0002's precedent ("existing canonical-store data on disk is not preserved during the migration; the current layout is throwaway dev state") and concluded the forward-migration is over-engineered for proof-of-concept stage. New rule: phases 4 and 5 delete existing SA/LS artifact directories rather than migrating them; subjects re-collect into the new canonical shape on first use of the new extractor.

### Changed

- **ADR 0003 "Decision → Migration"** paragraph rewritten to describe wipe-and-re-collect and cite ADR 0002's precedent. The "No forward-migration script, no dual-read compatibility, no shape-translation code" sentence states the rule plainly; the ADR reads as if this were the decision from the start (no changelog-of-itself).
- **ADR 0003 "Consequences → Negative"** sentence rewritten: SA/LS shapes still change, dev artifacts get deleted rather than migrated, consultants re-collect after phases 4 and 5.
- **HANDOVER backlog #3 (phase 4 — SA migration)** updated to drop the forward-migration substep in favor of "delete existing SA artifact directories so subjects re-collect."

### Added

- **HANDOVER backlog #20** — methodology marker: "Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered. Wipe and re-collect unless real customer data is at stake." Includes the directive to apply this rule to remaining ADR 0003 phases (4 and 5), and a retrospective trigger to decide whether it becomes a tool-wide default after ADR 0003 fully lands.

### Notes

- No code changes. No phase-count correction needed in HANDOVER — the forward-migration was a substep of phase 4, not a separate phase 6.

---

## 2026-05-27 (ADR 0003 phase 1: extraction_instructions extended for catalog-driven REST)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `40e8f3f` (ADR 0003 doc), `71a9c8f` (migration 0006 + test count update), plus the wrap-up commit publishing this entry.
**Test status:** 554 passing (unchanged — phase 1 is additive schema; the test-count assertion in `test_migration_status_reports_all_applied` updated 5→6 to match).

Phase 1 of the ADR 0003 implementation. The catalog now carries the new canonical reference for REST collection (report_id + dataset_name), and a wrong cache-hint value from migration 0004 is corrected.

### Added

- **ADR 0003 itself** at `docs/adr/0003-rest-extractor-with-credentials.md`. Status: Proposed. Designs a single catalog-driven, customer-scoped REST extractor that replaces the three current REST paths; introduces the `report_id` + `dataset_name` canonical reference with `dataset_guid` demoted to optional cache hint; adopts the cacheId-aware `CommvaultSession` pattern (production Commvault uses this) and migrates SA/LS away from their direct-GET path. Survey at `docs/adr/0003-survey.md` (committed earlier in the day) was the grounding doc.
- **Migration `0006_rest_extraction_instructions_report_id_and_dataset_name.sql`** — backfills the three existing REST rows under the new canonical reference.

### Changed

- **`client_growth.monthly_table`** extraction_instructions gains `report_id="318"`, `dataset_name="Client Count"`.
- **`capacity_license.table`** gains `report_id="318"`, `dataset_name="Capacity License Usage"`.
- **`backup_job_summary.recent_jobs`** gains `report_id="194"`, `dataset_name="Job details"`, AND has its `dataset_guid` corrected from `2638c3d3-...` (the report-level GUID for report 194, stored under the wrong key in migration 0004) to `a30bd278-c7d9-470f-9ae9-8b4922743330` (the real dataset GUID, captured manually from a `reportBuilder.do` trace). Justification for the inline correction: the migration was already rewriting this row; leaving a known-wrong cache hint in place could mask bugs in phase 2's runtime resolution.

### Notes

- **Migration style.** Pure SQL with `json_set` + WHERE guards. Each UPDATE filters on the field the first run sets (e.g. `report_id IS NULL` for the additive rows) or changes (the wrong dataset_guid value for backup_job_summary), so a second run matches zero rows. Idempotency verified by deleting the migration row from `schema_migrations`, re-running, and confirming JSON + `updated_at` are unchanged.
- **Runtime check chosen for "same report_id per subject" rule** rather than a DB constraint. Reasoning: SQLite can't express a multi-row CHECK; a TRIGGER would JOIN across siblings and be harder to debug than a one-line Python assertion in phase 2's extractor load path. ADR 0003 explicitly left this as an open question with no preference.
- **`output_as: "card"`** is documented in ADR 0003 but not consumed yet. Phase 4/5 (SA/LS seeding) introduce the first card-shaped rows.
- **No application code reads the new fields yet.** Phase 2 builds the new extractor. The backfill is invisible to current code paths; the only test churn was a count-pin in `test_migration_status_reports_all_applied`.
- **Surprise from step 1, confirmed.** The `2638c3d3-...` value migration 0004 stored as a "dataset_guid" for `backup_job_summary.recent_jobs` is actually the report-level GUID for report 194 — not a dataset GUID. No data-flow had been broken because the existing `RESTExtractor` never went through dataset discovery; it submitted the GUID directly. Under ADR 0003 the runtime resolver will look up datasets by name from the live report definition, so the corrected GUID is just a cache hint that may or may not be honored (phase 2 design decision).

### Carry-forward for phase 2

Phase 2 builds the new generic REST extractor: a `CommvaultSession`-based collector that takes `(customer_id, project_id, subject_id, token, base_url)` as explicit constructor args, POSTs `reportBuilder.do` once per subject collection, resolves each section's `dataset_name` to a runtime `dataset_guid` from the report definition, then paginates `fetch_dataset` with the obtained `cacheId`. Stored `dataset_guid` in the JSON is treated as untrusted (it may have been wrong, as backup_job_summary's case demonstrated).

---

## 2026-05-27 (tool-selection guidance)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** the two commits that publish this entry (the section addition and the last-commit pointer).
**Test status:** 554 passing (docs only).

Added a "Where work happens — Claude Code vs Claude.ai" section to HANDOVER, documenting which tool runs which kind of session and the handoff pattern between them. Prompted by a fresh Claude.ai chat correctly identifying that filesystem work can't happen there.

### Added

- **HANDOVER.md "Where work happens" section** sits between "Session workflow disciplines" and "Quick verification commands". Names Claude Code as the filesystem-aware tool (every implementation session in this project's history) and Claude.ai as the chat interface for design conversations and prompt drafting. Lists the explicit signal phrases ("read", "update", "run pytest", "the audit", "the schema", etc.) that mean a brief needs Claude Code.

### Notes

- No code changes. Docs only.
- The user remains the bridge between the two tools: Claude.ai drafts the brief, Claude Code executes, the user pastes the report back into Claude.ai if work continues strategically.

---

## 2026-05-27 (workflow discipline: push to GitHub regularly)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `c872b62`, plus this wrap-up.
**Test status:** 554 passing (docs only).

Motivating incident: a session discovered 59 local commits had accumulated without ever being pushed to GitHub. The work was only on the dev machine, couldn't be pulled to a second machine, and would have been lost if the machine had failed. Adding the push discipline as an explicit project workflow rule so future sessions can't drift the same way.

### Added

- **HANDOVER.md "Session workflow disciplines" section.** Sits between "Context" and "Quick verification commands". First subsection is "Push to GitHub regularly" — push after each major task, push at the end of every session, the session-end push is the final step of the single-recommended-next-action pointer. Cross-references the existing verify-before-write and STOP-and-report disciplines.
- **`docs/PATTERNS.md` third pattern: "Push to GitHub regularly".** Same shape as the existing two — brief description, why it matters (the 59-commit incident), when it applies (every session, not just ADR implementations).

### Notes

- Applies to every session going forward, including docs-only sessions and single-commit fixes.
- No force-push, no rebasing pushed branches — append-only.
- If a push fails, stop and report the failure rather than working around it.

---

## 2026-05-27 (housekeeping pass)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `7baa4a9` (HANDOVER backlog sweep), `cd23be3` (docs/PATTERNS.md + README links), plus this wrap-up commit.
**Test status:** 554 passing (unchanged — docs-only).

Small post-ADR-0002 housekeeping. No functional changes.

### Changed

- **HANDOVER backlog sweep.** Promoted ADR 0003 to explicit #1 (was only in the "single recommended next action" header). Added six items that had been raised across recent phases but not surfaced in the backlog list: refresh data flow audit, customer panel on quick_hc.html right side, shared.py split, SecurityAssessmentArtifactRegistry rename, hardcoded URLs in report_service.py audit, engagements table cleanup. Promoted two-CRUD-APIs investigation and template-inheritance cleanup from the smaller-cleanups list into the main backlog. Reordered: AI import workstream moved to #3 ("near top"), CommCell-discovery dropped from #1 to #4 (downstream of ADR 0003).

### Added

- **`docs/PATTERNS.md`** — two project-wide patterns documented as a single short doc:
  1. *Writes converge to canonical; reads stay diverse.* Cites Option A, ADR 0001, ADR 0002, and phase 5 finalize as four instances of the same shape.
  2. *Verify before write.* HANDOVER/CHANGELOG are starting points, not contracts. Cites two real cases where verification caught a mistake before code changed (the audit's `client_growth_summary.json` false-positive, and the init_db/schema.sql footgun).
- **README's "Architecture Documents" section** now links `docs/PATTERNS.md`, `docs/data_flow_audit.md`, and `docs/adr/`. The audit and the ADR directory were in the repo but not findable from the README's documents index.

---

## 2026-05-27 (ADR 0002 phase 5: finalize + reload — ADR 0002 IMPLEMENTATION COMPLETE)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `e4c582d` (core logic + unit tests), `8dfb0a3` (finalize UI), `e86ce90` (reload UI), `33c96fb` (finalizations placeholder refresh), `158841c` (route tests), plus the wrap-up commit that publishes this entry.
**Test status:** 554 passing (was 527 after phase 4; +15 from `tests/test_finalizations.py` + +12 from `tests/test_finalize_reload_routes.py`).

**ADR 0002 implementation is complete.** Five phases over 2026-05-26→27 took cv-healthcheck from "one customer, one project" to a full customer/project lifecycle with an audit-trail-safe finalize/reload workflow. The architecture's promise is now delivered.

### Added

- **`src/cvhealthcheck/db/finalizations.py`** — three operations plus one exception:
  - `finalize_project(db, customer, project) -> int` copies every subject directory under `working/` into `finalized/<n+1>/<subject>/`, inserts a `finalizations` row (capturing the project's current `ticket_reference` and `assigned_consultant` at finalize time so they're stable in the audit trail), and returns `n+1`. Raises `FinalizationError` if working has no subjects or the project is unknown.
  - `reload_latest_finalization(db, customer, project) -> int` clears `working/`, copies every subject from `finalized/<max>/` back in, bumps `working_state_modified_at`. Raises `FinalizationError` if no finalizations exist.
  - `diff_working_vs_latest(db, customer, project) -> list[str]` — content-based diff on `latest.json` per subject. Returns subject_ids that differ; uses symmetric-difference for subjects present in one side but not the other.
- **Finalize UI** at `GET|POST /customers/<c>/projects/<p>/finalize` (`templates/project_finalize.html`). GET shows the next finalization_number, the subjects in working state, the project's current ticket_reference/assigned_consultant (which will be captured), and a Confirm button. When working is empty the page renders in blocked mode. POST runs the finalize, flashes "Finalized as #N", redirects to project detail.
- **Reload UI** at `GET|POST /customers/<c>/projects/<p>/reload` (`templates/project_reload.html`). Three branches: blocked (no finalizations), soft info ("working matches latest"), firm warning ("discard N modifications") with the list of differing subjects. POST runs the reload, flashes "Reloaded finalization #N", redirects to project detail.
- **Finalize and "Reload latest" actions on the project detail page.** The Reload button only renders when at least one finalization exists.
- **27 new tests.** 15 in `test_finalizations.py` for the core logic (finalize success, twice produces 1 then 2, empty raises, finalized_by NULL vs set, ticket_reference captured at finalize-time, reload restores, reload removes added subjects, diff returns empty/symmetric-difference cases). 12 in `test_finalize_reload_routes.py` for the UI surfaces (GET/POST happy paths, blocked paths, finalizations list ordering, regression check on phase 4's delete-blocked-after-finalization invariant).

### Notes

- **Application-layer immutability.** No filesystem chmod, no read-only flags. The contract is that `finalize_project` is the only code path that writes under `finalized/<n>/`. ArtifactStore — the production write path used by every other artifact-saving code path — writes only to `working/`.
- **`shutil.copytree` for the snapshot copy.** `dirs_exist_ok=False` since `next_number` is always new. The copy isn't a transaction with the DB INSERT, but if the copy raises, no DB row is written — the next finalize attempt will get the same `next_number` and a clean slate. The window between "copy succeeded" and "DB row written" is very small; if a crash happened there, the orphan directory would be visible on disk but not in the DB, and the next finalize would write to a new `<n>` slot.
- **`ticket_reference` and `assigned_consultant` captured at finalize-time.** Editing the project's `ticket_reference` later doesn't bleed into earlier finalization rows. Verified by `test_finalize_captures_ticket_reference_at_finalize_time`.
- **Diff is content-based on `latest.json`.** Timestamped snapshot files (the append-only history) are ignored by the diff; only `latest.json` per subject is compared byte-for-byte. A touched-but-identical save doesn't trigger a false "modified" signal because `latest.json` is byte-identical after a no-op save.
- **Read-only per-finalization view (`GET /customers/<c>/projects/<p>/finalizations/<n>`) is deferred.** Listed in the HANDOVER backlog. Rendering a finalization's contents would need ArtifactStore (or equivalent) to read from a `finalized/<n>/` path, which is an architectural change beyond phase 5's scope.
- **End-to-end smoke test verified manually.** Create project → drop artifact → finalize #1 → see #1 on detail page → modify working → reload → verify restored → finalize #2 → see #2 above #1 on detail page (DESC order). All assertions passed.

### Carry-forward

ADR 0002 is now production-complete. The next focus shifts to ADR 0003 (REST extractor with credentials), which will use the active project's storage path for the artifacts it collects. The customer/project foundation is in place.

---

## 2026-05-27 (ADR 0002 phase 4: project page UI + active-project switcher)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `34a0f61` (customer detail), `ee28eb4` (project create), `aad4015` (project detail), `b08794b` (project edit), `5cad2ed` (project delete), `29c3666` (selector + API), `d3bcc55` (tests), plus the wrap-up commit that publishes this entry.
**Test status:** 527 passing (was 503 after the init_db retirement; +24 from `tests/test_projects_routes.py`).

Phase 4 of ADR 0002. Projects are now manageable through the web UI under their parent customer; the active-project session can be switched from any workspace page via the selector pinned to the top-right.

### Added

- **Customer detail page** at `GET /customers/<customer_id>` (`templates/customer_detail.html`). Shows customer metadata, an edit link, and a projects table sorted by created_at desc. Each project row links to its detail page; the active project's row is highlighted with an "Active" badge in place of the "Set as active" button. Empty-state when no projects exist. The Customers list now links each customer name to its detail page.
- **`src/cvhealthcheck/web/routes/projects.py`** — eight routes covering the full project CRUD lifecycle plus the active-project JSON API. Routes are nested under `/customers/<c>/projects/...` so they always carry the customer context in the URL.
- **Project create form** (`templates/project_form.html` shared with edit). Required field: project_number (free-form, will eventually come from an external ticket system). Optional: ticket_reference, assigned_consultant. `UNIQUE(customer_id, project_number)` collisions surface as a friendly form error. project_id is server-side slugified from project_number with global-uniqueness collision disambiguation. On successful create, the new project is auto-set as active and the user lands on its detail page.
- **Project detail page** at `GET /customers/<c>/projects/<p>` (`templates/project_detail.html`). Project metadata, Active badge or "Set as active" button, Edit/Delete actions, and a "Finalizations" section that's a placeholder for phase 5 ("No finalizations yet. The finalize action lands in a future phase."). Breadcrumb back to the customer.
- **Project edit form** — shares the create template. project_number is editable; URL stays stable (project_id is fixed at create time).
- **Project delete with strict-and-then-some guard** (`templates/project_delete.html`). The GET side renders a confirmation when finalizations is empty; when finalizations exist, the page renders in blocked mode ("Cannot delete: this project has N finalizations. Removal of finalized projects requires direct database access."). The POST side server-side re-checks finalization count and returns 400 on a bypass attempt. When the deleted project is the active one, the handler falls back to the migration-seeded Default project via `resolve_default_project()` + `set_active_project()`.
- **Active-project JSON API** at `/api/active-project`. GET returns the current `(customer_id, project_id)` plus customer_name, project_number, and the full list of customers and their projects for the selector dropdown. POST takes customer_id + project_id (form-encoded), validates that the project belongs to the customer, and updates the session. Optional `redirect_to` form field switches the response from JSON to a 302 redirect — used by form-driven "Set as active" buttons.
- **Active-project selector partial** (`templates/partials/active_project_selector.html`). Fixed to the top-right of every workspace page (`base.html` + the self-contained top-level templates). Renders as "Active <Customer> / <Project>" → click expands a panel grouped by customer with all projects. Clicking a project posts to `/api/active-project` with a redirect back to the current URL so the workspace reloads against the new active state. Click-outside closes the panel. No new localStorage keys — active project lives in the Flask session per phase 2.
- **`tests/test_projects_routes.py`** — 24 tests covering customer detail (2), project create (5), detail (4), edit (3), delete (5), and the active-project API (5).

### Notes

- **Project ID slug uniqueness.** A test ("DUP" for two different customers) caught a bug in `_slugify_project_id`: the collision check was scoped to the same customer, but `project_id` is the global PK on `projects`. Two customers slugifying the same project_number to the same project_id would have hit an `IntegrityError`. Fixed by checking project_id collisions across all projects, not just within the customer. The user-facing `UNIQUE(customer_id, project_number)` constraint is unaffected — it's still per-customer.
- **Auto-activate on create.** ADR 0002's "starting work for a customer, create a project, start working" workflow is the common case, so the new project becomes active without an extra click. The user can switch back via the selector if needed.
- **Strict-and-then-some delete.** ADR 0002's audit-trail safety: finalized projects cannot be deleted via the UI. Removal requires direct DB access (deliberate, per the ADR's "removal of finalizations requires direct database access" decision).
- **Selector visibility.** Added the partial to `base.html` (which `quick_hc_backup_job_summary`, `quick_hc_commcell`, `quick_hc_report`, `quick_hc_staging` all extend) and to the self-contained top-level templates (`quick_hc.html`, `quick_hc_settings.html`, customers/projects pages). End-to-end verified: create a new project, see workspace re-render against it via the selector, switch back to Default, workspace re-renders again.

### Carry-forward for phase 5

Phase 5 implements the finalize action and reload-latest-finalization. The Finalizations placeholder on the project detail page becomes a real history list once rows can be written. Closes out ADR 0002.

---

## 2026-05-27 (interstitial: retire init_db and schema.sql)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `bd7b4a0`, plus the wrap-up commit that publishes this entry.
**Test status:** 503 passing (was 508 after phase 3; -5 from the deleted `test_init_db_*` tests).

Small interstitial cleanup between phase 3 and phase 4. Phase 2 and phase 3 both flagged the same recurring footgun: tests using `init_db()` got a schema frozen at migration 0001 (the state `schema.sql` covered), and broke in surprising ways whenever a later migration added columns or tables. Phase 3's response was to switch two test fixtures to `run_migrations()`. This entry finishes the job — `init_db()` and `schema.sql` are gone, `run_migrations()` is the sole database-bootstrap path.

### Removed

- **`src/cvhealthcheck/db/schema.sql`** — only ever covered migration 0001's tables (`customers`, `engagements`, `staged_artifacts`). Stale; deleted.
- **`init_db()`** in `src/cvhealthcheck/db/database.py` + the `_SCHEMA_PATH` constant. No production callers.
- **`init_db` export** from `src/cvhealthcheck/db/__init__.py`.
- **Five `test_init_db_*` tests** in `tests/test_db_customers_engagements.py` that exercised `init_db` itself. Superseded by `tests/test_migrations.py` which covers `run_migrations`.

### Changed

- **`tests/test_staging_routes.py`** — `db_path` fixture switched from `init_db` to `run_migrations` + delete the migration-seeded default rows so the empty-table behaviour assumed by the tests still holds.
- **`tests/test_db_staging.py`** and **`tests/test_db_customers_engagements.py`** — drop the stale `init_db` import. Their fixtures were already on `run_migrations` from phase 3.
- **`src/cvhealthcheck/db/migrations/__init__.py`** — docstring updated to drop the historical "Replaces init_db()" framing now that init_db no longer exists.

### Notes

- The footgun the HANDOVER's priority-ordered backlog called out ("bring schema.sql in sync with migrations, or retire it") is resolved by the "retire" path. The next time a migration adds tables, no test fixture will silently miss them.

---

## 2026-05-27 (ADR 0002 phase 3: customer page UI)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `226c1ab` (nav), `9858bcc` (list), `b8877f4` (create form), `e22da6f` (delete), `ae8bc27` (tests), plus the wrap-up commit that publishes this entry.
**Test status:** 508 passing (was 493 after phase 2; +15 from `tests/test_customers_routes.py`).

Phase 3 of ADR 0002. The customers table is now fully manageable through the web UI — list, create, edit, delete. Manual entry is the primary path; CommCell-discovery (auto-populating identity fields from a CommCell login) is deferred to a future phase and shares plumbing with ADR 0003's REST extractor.

### Added

- **`Customers` nav item** in the left sidebar of `templates/quick_hc.html`, between Reports and Settings. Points at `main.customers_list`.
- **`src/cvhealthcheck/web/routes/customers.py`** — seven routes covering the full CRUD lifecycle (`GET /customers`, `GET|POST /customers/new`, `GET|POST /customers/<id>/edit`, `GET|POST /customers/<id>/delete`). The route file uses inline SQL through `get_db()` (matching the staging-route pattern) and owns its own slugify helper. Registered in `routes/main.py`.
- **`templates/customers_list.html`** — heading, "New customer" CTA, table sorted by name with Name / CommCell ID / Projects / Edit-Delete columns, empty-state fallback.
- **`templates/customer_form.html`** — shared between create (mode=new) and edit (mode=edit). Required field is customer_name; all others optional. Hints clarify when to set `company_guid` ("only if the CommCell hosts multiple companies") to discourage speculative filling.
- **`templates/customer_delete.html`** — confirmation page with customer summary card + project count. Renders in `blocked=True` mode when the customer has projects: red block message, disabled delete button. The server-side POST handler re-checks project count and returns 400 on a race or stale-form bypass.
- **`tests/test_customers_routes.py`** — 15 tests across list view, create form (including slugify collision disambiguation), edit form (including 404 on unknown), and delete (including the strict project-count guard on both GET render and POST defence-in-depth).
- **`src/cvhealthcheck/db/customers.py`** extended with the new fields, a `slugify_customer_id` helper, `list_customers_with_project_counts`, and `count_customer_projects`. The route layer doesn't depend on these (it uses inline SQL), but the module remains the canonical CRUD API for non-Flask callers (CLI, tests).

### Notes

- **Customer ID slug convention.** Matches the migration-seeded `default` style: lowercase, alphanumeric runs joined with underscores, leading/trailing underscores stripped. On collision, append `_2`, `_3`, etc.
- **No CommCell network calls anywhere in this phase.** Discovery is deferred — when implemented, it will be an addition to the existing customer form, not a replacement.
- **No authentication required on customer routes.** Consistent with the existing settings and staging pages.
- **Default customer is not specially protected.** It can be deleted like any other if it has no projects. Phase 1 + phase 2 step 1 seeded a Default project under it, so attempting to delete Default goes through the blocked path until that project is removed (phase 4 will handle project deletion).
- **Migration-seeded data and test fixtures.** `test_db_customers_engagements.py` and `test_db_staging.py` previously used `init_db()` which applies the legacy `schema.sql` (no `projects`/`finalizations` tables, no new customer columns). Both were switched to `run_migrations()` and the seeded `default` rows are deleted in the fixture so existing empty-table assertions still hold. `test_create_customer_returns_all_fields` updated to expect the extended column set.
- **Step 4 ('edit form')** had no new files — the route handler landed in step 2, the template is shared with the create form from step 3. Documented here for the audit trail; no commit was made.

### Carry-forward for phase 4

Phase 4 builds the project page UI: list projects per customer, create, switch the active project (the customer-level half landed here gives nav context; project-level needs the projects table). Phase 5 follows with finalize + reload.

---

## 2026-05-27 (ADR 0002 phase 2: project-scoped storage + active project session)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `d78e47c` (Default project), `119e360` (active-project helper), `f5c5946` (ArtifactStore project-scoping), `a16942c` (acceptance tests), plus the wrap-up commit that publishes this entry.
**Test status:** 493 passing (was 482 after phase 1; +11 = +6 active-project + +5 project-scoping acceptance).

Phase 2 of ADR 0002. The workspace now reads and writes artifacts from customer/project-scoped paths instead of the global path. The active project lives in the Flask session (namespaced `session['active_project']`); the migration-seeded Default customer + Default project is the fallback when no active project is set. **Existing dev artifacts at `data/catalog/artifacts/*` were already deleted in phase 1; phase 2 doesn't touch any new data on disk** — the new on-disk layout will populate organically as collections/imports run.

### Added

- **`src/cvhealthcheck/web/active_project.py`** — `get_active_project`, `set_active_project`, `clear_active_project`, `resolve_default_project`, plus the constructor helpers `make_active_project_store` (request-context callers) and `make_default_project_store` (non-request callers like MCP staging and CLI). Session key is namespaced; `clear_*` restores the Default fallback.
- **Migration 0005 extended** with an `INSERT OR IGNORE` for the Default project under the Default customer (`project_id='default'`, `project_number='DEFAULT'`). Idempotent; the dev DB was brought into sync by re-applying the INSERT directly since 0005 was already marked applied from phase 1.
- **`tests/test_active_project.py`** — 6 tests covering the helper.
- **`tests/test_project_scoped_artifacts.py`** — 5 acceptance tests pinning project isolation, active-project switching, the path structure, and defensive constructor checks.

### Changed

- **`ArtifactStore.__init__`** now requires positional `customer_id` and `project_id`. Path becomes `<base_dir>/<customer_id>/<project_id>/working/<artifact_type>/{latest.json, <timestamp>.json}`. The `finalized/<N>/` sibling directory is reserved for phase 5; the store exposes no write path for it (application-layer immutability per ADR 0002).
- **Module-level singletons retired** in four places. Each module now constructs the store on demand via `make_active_project_store()` so each call resolves the current session's active project:
  - `security_assessment/service.py` (`_artifact_store` → `_active_project_store()`)
  - `license_summary/service.py` (`_artifact_store` → `_active_project_store()`)
  - `quickhc/subject_data_service.py` (`_canonical_store` → `_canonical_store()`)
  - `registry/execution.py` (`_store` → `_active_project_store()`)
- **Route handlers** in `web/routes/quick_hc.py` migrated from bare `ArtifactStore()` to `make_active_project_store()` at three sites (delete_subject, generic collect, unified dispatcher upload).
- **`execute_approval` in `db/staging.py`** falls back to `make_default_project_store(db)` when no `store` is injected — non-request contexts (MCP) hit the Default project.
- **`mcp/server.py` delete tool** constructs its store via `make_default_project_store(db)` while the db connection is open.
- **Test infrastructure** updated to match. The autouse `_isolate_canonical_stores` fixture now monkeypatches `_DEFAULT_BASE_DIR` (matching the production `data/catalog/artifacts` directory name so path-structure assertions still pass), instead of monkeypatching the now-defunct module-level singletons. Tests that previously monkeypatched `ArtifactStore` as a module attribute now monkeypatch `make_active_project_store` / `make_default_project_store` returning fakes. One test (`test_dispatched_subjects_rest_source_shows_validated_with_collect_action`) that monkeypatched `sds._canonical_store` as an instance now monkeypatches it as a callable.

### Notes

- **Source-building fork unaffected.** ADR 0001's `_legacy_builders` / `_legacy_loaders` continue to read globally-scoped legacy on-disk files (`commserv.json`, `metrics/*.json`, `backup_job_summary_latest.json`, the legacy SA/LS stores). These remain customer-agnostic for v1 — the step-4 read-site audit explicitly preserved them. Project-scoped reads are only the canonical-store reads.
- **The legacy SA/LS Option A read-fallback paths** (`data/catalog/{security_assessment,license_summary}/latest.json`) also stay globally scoped. Their consumers will need a project-scoping story eventually; not phase 2.
- **Provenance builders' file-path strings** (`source_provenance.py:87, 125, 224, 274`) are informational display values, not actual reads. Left as-is for now; future iterations can teach them the project-scoped layout when the UI surfaces customer/project context.
- **Workspace verified rendering** in a request context: Default project, empty canonical artifacts directory. The six system subjects render through the legacy-builder fallback (reading legacy on-disk files); the two AI subjects show "Not collected" because their project-scoped paths are empty. This matches the expected post-phase-2 state.

### Carry-forward for phase 3

Phase 3 builds the customer page UI: list customers, create (manual + CommCell-discovery), edit. The schema and storage are ready; the missing piece is the surface for managing customers (and choosing which CommCell to connect to). Phase 4 follows with the project page (list per customer, create, switch active, view finalization history). Phase 5 implements finalize + reload.

---

## 2026-05-26 (ADR 0002 phase 1: schema and storage foundation)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `4c69034` (migration), `75ba4b9` (snapshot test deletion), plus the wrap-up commit that publishes this entry.
**Test status:** 482 passing (was 483; -1 from the deleted snapshot test).

Phase 1 of the 5-session ADR 0002 implementation. The database now knows about customers, projects, and finalizations; no application code uses any of it yet — phase 2 plumbs the active project through `ArtifactStore`.

### Added

- **Migration `0005_customer_project_finalization.sql`.** Three changes to the schema, all idempotent via `IF NOT EXISTS` / `INSERT OR IGNORE`:
  - `customers` extended with `commcell_id`, `commcell_hostname`, `company_guid`, `contact_info` (JSON-as-TEXT), `notes`. Existing `customer_id` PK and `customer_name` preserved so the `staged_artifacts.customer_id` FK from migration 0002 stays valid.
  - New `projects` table: `project_id` PK, `customer_id` FK CASCADE NOT NULL, `project_number` NOT NULL, `ticket_reference`/`assigned_consultant` nullable, timestamps. `UNIQUE(customer_id, project_number)`. No status column — history is the sequence of finalizations per the ADR.
  - New `finalizations` table: `finalization_id` PK, `project_id` FK CASCADE NOT NULL, `finalization_number` (CHECK >= 1), `finalized_at`, `finalized_by` nullable, `ticket_reference` nullable (the ticket that triggered *this* finalization, distinct from the project's), `notes` nullable. `UNIQUE(project_id, finalization_number)`.
  - Auto-seeds a `customer_id='default'` / `customer_name='Default'` row via `INSERT OR IGNORE`. ADR 0002's first-run experience: the empty-state is hidden behind a pre-created customer.

### Removed

- **`tests/test_subject_initial_data_snapshot.py`** and its fixture `tests/fixtures/subject_initial_data_snapshot.json` deleted. The snapshot pinned the behavior of `build_subject_initial_data()` against the single-customer architecture that ADR 0002 replaces. Phases 2-5 exercise the new customer/project-scoped paths through targeted tests as those paths come online.
- **`data/catalog/artifacts/{license_summary,security_assessment,storage_utilization}/`** contents deleted on the dev machine. Throwaway dev data per ADR 0002's "existing data not preserved" decision. The directory itself stays in place; the gitignored content is regenerated on first artifact write.

### Notes

- **`engagements` table is left alone.** Predates ADR 0002, empty, no code path inserts into it via app.db. Future cleanup can retire it; phase 1 keeps the migration tightly scoped.
- **Idempotency.** The migration runner already guarantees single-application via `schema_migrations` tracking. The ALTER statements (which SQLite doesn't support `IF NOT EXISTS` on) are protected by that mechanism rather than per-statement guards. Verified by simulating a fresh DB then running migrations twice.
- **Application code is unchanged.** No reads against the new tables, no writes to the new storage paths. Phase 2 (`ArtifactStore` project-scoping) is the next session.

### Carry-forward for phase 2

Phase 2 adds a `project_context` parameter (or equivalent) to `ArtifactStore.save_artifact` and `load_latest_artifact`, threading the active project through the route → service → store path. The new on-disk layout is `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject_id>/...` for mutable state and `.../finalized/<N>/<subject_id>/...` for immutable snapshots. The canonical schema and source-building paths do not move.

---

## 2026-05-26 (ADR 0002: Customer and Project entities)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `0cff36c` (ADR), plus the wrap-up commit that publishes this entry.
**Test status:** 483 passing (unchanged — ADR session, no code).

ADR-only session. Records the design for first-class Customer and Project entities to support real consulting work — see `docs/adr/0002-customer-and-project-entities.md`. The architectural shape: customer is a first-class entity with rich configuration including CommCell details; project belongs to a customer; finalization is the data-retention unit (immutable per-project snapshots, kept forever); finalize is not a one-way trapdoor (a finalized project reloads its latest finalization for editing, and re-finalizing produces the next immutable snapshot); immutability is enforced at the application layer, not the file system. Multi-CommCell and multi-company-within-CommCell are explicitly out of scope for v1; existing dev artifacts are deleted by the migration rather than preserved.

The ADR is orthogonal to ADR 0001's source-building fork — system subjects still flow through `_legacy_builders`, the customer/project work changes *where* artifacts are stored and *which* artifact a builder reads, not *how* tile data is shaped.

### Carry-forward

Implementation is the next session. ADR 0003 (REST extractor with credentials) follows that one and builds on ADR 0002's storage paths.

---

## 2026-05-26 (housekeeping: gitignore app.db, README refresh)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `e58adca` (gitignore), `6d2daed` (README refresh).
**Test status:** 483 passing (unchanged).

Two priority-ordered backlog items cleared in one session — both as small as expected.

### Changed

- **`data/app.db` is now gitignored.** `git rm --cached data/app.db` untracks the file; the local copy stays on disk. Added entries for the WAL/SHM/journal sidecars too. On a fresh clone, `run_migrations()` (`src/cvhealthcheck/db/migrations/__init__.py:69`) runs at app startup (`web/app.py:13`, `mcp/server.py:59`) and produces the working schema from the four migration files. Migration `0003_report_inventory.sql` seeds the six system subjects plus their sources and section-instruction rows via `INSERT OR IGNORE`, so the Quick HC workspace renders correctly out of the box — no separate bootstrap mechanism needed. Verified by simulating a fresh DB; the `subjects` table comes back populated with `environment`, `license_summary`, `backup_job_summary`, `capacity_license`, `client_growth`, `security_assessment`.
- **README refresh.** Three edits, no new sections:
  - Test count line `298` → `483` (the "Session Validation" line had been stale across many sessions).
  - "Legacy detail-route behavior" block replaced — it still described the hyphenated `POST /quick-hc/<subject>/import` routes that session 4 deleted. Now correctly describes the unified `POST /quick-hc/<subject_id>/import` dispatch (with `upload_dispatch.py` wiring), the two surviving hyphenated `/collect` endpoints for SA/LS, and the GET redirects carrying `#subject=<id>` fragments.
  - Bottom "Pages:" list split into "Customer-facing" (`/`, `/quick-hc`, `/quick-hc/commcell`, `/quick-hc/report`) and "Internal / development" (everything else). The previous list mixed the two — `/` is customer-facing (redirects to `/quick-hc`), everything else is dev.

### Notes

- **AI-subject state is dev-machine.** The two `ai`-created subjects in current `data/app.db` (`cloud_storage_egress_ingress`, `storage_utilization`) are user-created via MCP `propose_new_subject` or AI import flows; they're not load-bearing for a fresh clone. Losing them on a wipe is acceptable behavior.
- **Tests are unaffected.** `tests/conftest.py:32` `migrated_db_path` fixture creates tmp-path DBs for every test; the real `data/app.db` is never touched by the test suite.
- **Deeper README staleness flagged but not fixed.** The Security Assessment section (around L270-278) lists "Latest persisted multi-source artifacts" paths under `data/imports/security_assessment/latest*.json` that no longer match the canonical-store layout. Out of scope for this refresh — separate session.

---

## 2026-05-26 (post-5b — server-side half of the Collect-position fix)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** the redirect-fragment commit that publishes this entry.
**Test status:** 483 passing (was 482; +1 new pin).

Server-side complement to `fecf68c` ("Preserve active subject across Collect's full-page reload via URL fragment"). The earlier client-side fix wrote `#subject=<id>` to the URL on every `openConfig()` — but Collect's full-page reload comes from a server-issued `Location: /quick-hc` redirect that doesn't carry the fragment, so on reload `_readSubjectFromHash` found nothing and the JS init defaulted to `environment` (CommCell Details). Confirmed by user after force-reload.

### Fixed

- **`src/cvhealthcheck/web/routes/quick_hc.py`** — added `_workspace_redirect(subject_id=None)` helper that returns `redirect(url_for("main.quick_hc") + "#subject=<subject_id>")` when `subject_id` is supplied, plain `redirect(url_for("main.quick_hc"))` otherwise. Wired into every subject-specific redirect site:
  - `quick_hc_security_assessment` (legacy GET) and `quick_hc_license_summary` (legacy GET) — the indirection through which the SA/LS collect handlers chain to the workspace. One line each.
  - `quick_hc_generic_collect` — all four redirect sites (no base URL, exception, errors, success) now carry the subject fragment. The "subject not found" site stays bare (the subject doesn't exist; preserving its id would be nonsensical).
  - `_unified_dispatcher_upload` — both redirect sites (no file selected, completion) carry the subject fragment so AI-subject uploads also land on the right tile.
  - The `_handle_system_upload` path (SA/LS uploads via the unified import route) inherits the fragment through the legacy GET chain — no direct change needed.
- **`quick_hc_delete_subject`** intentionally left unchanged. After delete, the subject doesn't exist; preserving the fragment for a non-existent subject would be incorrect — the JS would fall back to the default anyway.

### Added

- **`tests/test_core_solidity.py::test_subject_specific_redirects_carry_subject_fragment`** — pins the legacy GETs (which all subject-specific upload/collect chains route through). Asserts both legacy GETs redirect to `/quick-hc#subject=<id>`.

### Notes

- **Existing test assertions safe.** All test redirect-location checks use `"/quick-hc" in response.headers["Location"]` (substring match) — the fragment doesn't break them. The one `endswith("/quick-hc")` check is on the `quick_hc_delete_subject` redirect, which intentionally stays bare. No test updates needed.
- **Subject ID form.** Fragments use the underscored DB form (`security_assessment`, `license_summary`), matching the subject IDs `build_subject_initial_data` produces and the JS regex `/^#subject=(.+)$/` compares against. Not the hyphenated route form.

---

## 2026-05-26 (post-5b regression fix — source-provenance dispatch)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** the regression-fix commit that publishes this entry. (An earlier attempt at the same fix landed in `8dda62a` as a registry-level URL map; reverted in favor of this dispatch approach.)
**Test status:** 482 passing (was 477; +5 new tests across `test_source_provenance_dispatch.py` and `test_core_solidity.py`).

Fix for a workspace-tile regression introduced by `db87676` ("Retire legacy Quick HC detail pages"). The License Summary and Security Assessment tiles were rendering REST / Reports Plus as "○ Not implemented" — REST collection was correctly implemented, but the source-building path that runs when a canonical artifact exists had no signal about it.

**This is the second seam between data-driven and hardcoded paths in this codebase — same architectural shape as session 5b's `upload_dispatch`.** Both subjects have behavior that doesn't fit the catalog-table model (upload has subject-specific import functions; collection has subject-specific REST services). Both seams are now resolved by a small `dict[str, callable]` keyed by `subject_id` in a dedicated dispatch module. If a third seam shows up, it should use the same pattern.

### Added

- **`src/cvhealthcheck/quickhc/source_provenance_dispatch.py`** — sibling to `upload_dispatch.py`. Contains `PROVENANCE_DISPATCH: dict[str, ProvenanceBuilder]` with two entries (`security_assessment`, `license_summary`) pointing at the existing `build_security_assessment_provenance` / `build_license_summary_provenance` functions in `source_provenance.py`. The `get_provenance_builder(subject_id)` helper is the consumption interface for `_build_generic_sources`.
- **`tests/test_source_provenance_dispatch.py`** — 4 tests: SA wiring, LS wiring, unknown-subject returns None, keys-pin asserting exactly 2 entries.
- **`tests/test_core_solidity.py::test_dispatched_subjects_rest_source_shows_validated_with_collect_action`** — integration pin. Saves canonical artifacts for SA and LS to a tmp store, runs `build_subject_initial_data`, asserts both subjects' REST source has status="v" and a Collect action pointing at the expected hyphenated route.

### Changed

- **`src/cvhealthcheck/quickhc/subject_data_service.py::_build_generic_sources`** — consults the dispatch before falling through to the catalog-table logic. If a builder is registered, it's called with the subject's canonical-artifact dict (passed via the new `artifact_payload` parameter), and the resulting provenance items are adapted to the tile-source schema by `_provenance_to_tile_sources`. The adapter maps provenance source types (`rest_reports_plus`/`csv`/`html`) to tile source IDs, maps long-form status strings (`validated`/`available`/...) to the short codes the frontend consumes (`v`/`a`/...), and builds the action list (upload for CSV/HTML, collect for REST with the dedicated hyphenated route URL from `_DISPATCH_REST_COLLECT_URLS`).
- **`_build_generic_subject`** — calls `artifact.model_dump(mode="json")` on the canonical artifact (when present) and threads it through to `_build_generic_sources` as `artifact_payload`. Provenance builders tolerate the canonical-shape dict (they use `.get()` with defaults; their status strings are hardcoded), so no shape adapter is needed at this boundary.

### Notes

- **Root cause was the retirement of dedicated detail pages.** Before commit `db87676`, the `quick_hc_security_assessment` and `quick_hc_license_summary` GET handlers called `build_security_assessment_provenance()` / `build_license_summary_provenance()` directly to produce their source lists. Those handlers became redirects to `/quick-hc`; the provenance builders went dead, and the workspace tile path took over with no equivalent wiring. This fix restores the connection through a dispatch module rather than a re-coupled call site.
- **Collect URL hyphenation.** The dedicated SA/LS routes use hyphenated paths (`/quick-hc/security-assessment/collect`, `/quick-hc/license-summary/collect`) — these are the canonical names; tests, route decorators, and the new `_DISPATCH_REST_COLLECT_URLS` constant all agree. The frontend (`quick_hc.js:371`) consumes whatever `collectUrl` the server emits, so there's no URL mismatch in the UI.
- **Snapshot test passes unchanged.** The `_isolate_canonical_stores` fixture in `conftest.py` redirects the canonical store to a tmp dir, so the snapshot's render path never reaches `_build_generic_subject` for SA/LS — it goes through the legacy builders (`_build_security_assessment_subject` / `_build_license_summary_subject`), which set their own source statuses and aren't touched by this fix. The bug only manifests when a canonical artifact exists (the production state).
- **Legacy builder paths unchanged.** `_build_security_assessment_subject` / `_build_license_summary_subject` still own the no-canonical-artifact paths and continue producing their own source lists. Bringing them onto the dispatch would be a refactor, not a wiring fix; out of scope here.
- **δ → β migration path stays clean.** Same rationale as `upload_dispatch.py`: if the set of dispatched subjects grows enough that the in-Python dict becomes painful, the migration unit is the builder function, not the dispatch shape. See `docs/refactor_unified_upload_session_5a_design.md` Section 6.

---

## 2026-05-26 (session 5b)

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `d04640d` (step 1 — dispatch module + tests), `ae58c21` (step 2 — route handler reads from the module, FIXME tags retired), plus the wrap-up commit that publishes this entry.
**Test status:** 477 passing (up from 472; +5 dispatch tests added in step 1, ±0 in step 2).

Session 5b — implements Option δ from the session 5a design. **The unified-upload refactor is now complete.** All three `FIXME(refactor-unified-upload-session-5)` tags are retired.

### Added

- **`src/cvhealthcheck/web/routes/upload_dispatch.py`** — data-only module containing the `UploadHandler` frozen dataclass and the `UPLOAD_HANDLERS: dict[str, UploadHandler]` lookup table. Two entries today: `security_assessment` and `license_summary`. Each handler bundles the five subject-specific behaviors the route needs (form field name, import function reference, error class, success-message format function, redirect endpoint). No Flask imports — the route handler is the only consumer.
- **`tests/test_upload_dispatch.py`** — 5 tests covering the SA handler wiring, the LS handler wiring, AI subjects returning `None` from `get_handler`, unknown subjects returning `None`, and a keys-pin asserting `UPLOAD_HANDLERS` has exactly the two known entries.

### Changed

- **`quick_hc_subject_import`** rewritten as a four-line dispatch: look up the subject in the db (404 if unknown), look up the subject_id in `UPLOAD_HANDLERS`, run `_handle_system_upload(handler)` if a handler exists, otherwise either 404 (system subjects with no handler entry) or fall through to `_unified_dispatcher_upload` (AI/user subjects). The hard-coded `if subject_id == "security_assessment"` / `if subject_id == "license_summary"` branches are gone.
- **`_handle_system_upload(handler: UploadHandler)`** — single new function consuming a handler. Reads the form file under the handler's form-field name, calls the handler's import function, catches the handler's error class for known failures (flashes `str(exc)`), catches `Exception` for unexpected failures (flashes `"Import failed: {exc}"` — note: the subject-specific prefix "Security Assessment import failed" / "License Summary import failed" is replaced by the generic phrasing, since the subject is already implied by the redirect destination and no test asserted on the old prefix), flashes the handler's success-format text on success, and redirects to the handler's endpoint.

### Removed

- **`_unified_security_assessment_upload`** in `quick_hc.py` — its job is now done by `_handle_system_upload` reading the SA handler.
- **`_unified_license_summary_upload`** in `quick_hc.py` — same. Note: the explicit extension pre-check (`if suffix not in LICENSE_SUMMARY_UPLOAD_EXTENSIONS`) is dropped; the importer itself already raises `LicenseSummaryImportError("Unsupported file type. Upload a License Summary CSV or HTML export.")` for the same case, which the handler's `error_class` catch translates into the same flash text.
- **All 3 `FIXME(refactor-unified-upload-session-5)` tags** in `quick_hc.py` — the data-driven dispatch they pointed at now exists.
- **Dead imports in `quick_hc.py`:** `LICENSE_SUMMARY_UPLOAD_EXTENSIONS`, `import_security_assessment_upload`, `import_license_summary_upload`. `SecurityAssessmentImportError` and `LicenseSummaryImportError` stay — the REST collect routes still raise them.

### Notes

- **The refactor is complete.** Sessions 1 (template wiring), 2 (unified-route shim with FIXMEs in place), 3 (dispatcher hardening), 3b (stop-and-report inventory), 3c (ADR 0001), 4 (old-route deletion), 5a (design proposal), 5b (data-driven dispatch). The dispatch smell that the FIXMEs marked is resolved. `POST /quick-hc/<subject_id>/import` is the sole upload path; the route handler is a four-line dispatch; subject-specific behavior lives in the dispatch module's data and in the importer functions themselves.
- **Option δ vs the alternatives.** The dict-based approach added 5 tests and ~120 lines of well-named data; a schema migration (Option β) would have added ~50 lines of SQL + Python plus a `propose_new_subject` change for two subjects with three differing fields each. The δ → β migration path stays clean — `UploadHandler` fields are typed scalars that map naturally to SQL columns if the set of upload-special subjects grows.
- **No behavior change from the user's perspective.** The route accepts the same form-field names, redirects to the same endpoints, returns the same 404s, and produces the same artifacts. The flash for unexpected exceptions reads "Import failed: ..." instead of "Security Assessment import failed: ..." / "License Summary import failed: ..." — no test exercised that exact prefix.
- **Snapshot test passes.** No source-building code was touched.
- **3 FIXME tags retired.** `grep -rn "FIXME(refactor-unified-upload-session-5)" src/ tests/` returns zero hits.

### Carry-forward

The refactor is done. `HANDOVER.md` is rewritten to drop the refactor-state tracking and to promote the next backlog item — moving `data/app.db` out of git — as the single recommended next action. Earlier session-6 candidates (the `TileDefinition.import_url=` dead data at `registry.py:131, 205`, the legacy `/security-assessment` dev page, the README test-count refresh) stay as smaller follow-ups.

---

## 2026-05-26 (session 5a)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `062ebcf`, plus the wrap-up commit that publishes this entry.
**Test status:** 472 passing (unchanged — investigation only).

Session 5a — investigation session for the dispatch smell that the three `FIXME(refactor-unified-upload-session-5)` tags mark.

### Added

- **`docs/refactor_unified_upload_session_5a_design.md`** — 7-section design proposal. Section 1 inventories the dispatch sites and the contract table. Section 2 narrows the "data the dispatch needs" set from the FIXME's six speculative dimensions down to three actual ones. Sections 3-6 evaluate four data-model options (α JSON column / β typed columns / γ separate table / δ Python lookup) against the dispatch contract, the AI-proposal workflow, and migration mechanics. Section 7 makes the recommendation.

### Notes

- **Headline recommendation:** Option δ (Python lookup table). The smell is smaller than the FIXMEs implied — only three fields differ between the SA and LS branches, and a `dict[str, _UploadHandler]` resolves both the duplication and the dispatch branching in one move. No schema migration, no `propose_new_subject` change, no new column.
- **The FIXME tag text said "likely a new column on `subjects`"** — that was suggestive when the tags were written in session 2, not prescriptive. The actual smell (subject-specific branching in route-handler code) is fully resolved by δ; database-stored alternatives are over-engineered for two subjects with three fields each. If a future AI subject needs custom upload behavior that can't be expressed in a code-side dict, δ → β is a one-session migration.
- **No code changes this session.** Test count 472 unchanged. 3 FIXME tags still in place (they remain until session 5b implements the recommendation).
- **ADR 0001 stays untouched.** The upload-special subjects (SA, LS) are a strict subset of the source-building-special subjects (the six in `_legacy_builders`), but unifying them would re-open the question ADR 0001 closed. Session 5b's data model is upload-only.

### Carry-forward for session 5b

Session 5b implements Option δ (or whichever option the user picks after review). Estimated work: define `_UploadHandler` dataclass, populate `_SYSTEM_UPLOAD_HANDLERS` dict with the 2 entries, write one `_handle_system_upload` function that consumes a handler, rewrite `quick_hc_subject_import` to use the lookup, delete `_unified_security_assessment_upload` / `_unified_license_summary_upload`, remove the 3 FIXME tags, add a parametrised test, update docstrings. One session, modest test-count delta (+1).

---

## 2026-06-05

**Branch:** `feature/basic-healthcheck-report-output`
**Commits:** `c06309d`, `b873431` (step 2 split — the first commit landed only the template deletion because a `git add` invocation died silently on the already-deleted path; the second commit landed the route bodies and comment updates). `6e0b1ed` (step 3 test cleanup). Plus the wrap-up commit that publishes this entry.
**Test status:** 472 passing (down from 477; -5 route-coupled tests deleted).

Session 4 of the unified-upload refactor — **the old upload routes are deleted.** Only the unified route `POST /quick-hc/<subject_id>/import` remains.

### Removed

- **`POST /quick-hc/security-assessment/import`** — handler `quick_hc_security_assessment_import` deleted from `src/cvhealthcheck/web/routes/quick_hc.py`.
- **`POST /quick-hc/license-summary/import`** — handler `quick_hc_license_summary_import` deleted.
- **`GET, POST /quick-hc/import`** — handler `quick_hc_generic_import` deleted (the multi-purpose old generic route, including its `?subject_id=`, `?stage=1`, and `X-Inline: 1` features).
- **`src/cvhealthcheck/web/templates/quick_hc_import.html`** — template only used by the GET branch of the deleted generic route.
- **5 route-coupled tests deleted** (per investigation report Section 5 categorisation):
  - `tests/test_recognition.py::test_import_route_{direct_save,staged,unrecognized,not_extractable}` — exercised behavior specific to the deleted generic route (recognition-from-payload without an explicit subject_id in the URL). The dispatcher's recognition + extractability mechanics remain covered by the unit tests in `test_recognition.py` (`test_recognize_*`, `test_dispatcher_*`) which exercise `extract_file` directly without going through any HTTP route.
  - `tests/test_import_flow.py::test_import_route_passes_subject_id` — exercised the deleted generic route's `?subject_id=` query-string handling. The unified route always has `subject_id` in the URL path; no equivalent test needed.

### Changed

- **`_unified_dispatcher_upload` redirect target.** Previously `url_for("main.quick_hc_generic_import")` (the deleted route) to be byte-equivalent with the old generic route's "redirect to self after upload" pattern. Now `url_for("main.quick_hc")` — the natural landing after a Quick HC upload. The docstring on `_unified_dispatcher_upload` documents this behavior change.
- **3 URL-coupled tests updated** to point at the unified URL (was the deleted hyphenated form):
  - `tests/test_security_assessment_import.py::test_quick_hc_security_assessment_upload_imports_html_and_redirects`
  - `tests/test_license_summary_web.py::test_quick_hc_license_summary_upload_imports_csv_and_redirects`
  - `tests/test_license_summary_web.py::test_quick_hc_license_summary_upload_rejects_unsupported_type`
- **3 parity tests in `tests/test_unified_upload_route.py` updated** to drop the OLD-route POST half (the OLD route no longer exists to compare against). Each test now POSTs only to the unified route and asserts directly on the outcome. `test_unified_route_ai_branch_produces_same_artifact_as_old_route` renamed to `test_unified_route_ai_branch_saves_artifact` since it no longer tests parity.
- **Module docstring** in `test_unified_upload_route.py` updated to reflect session-4 state.
- **Docstrings on `quick_hc_subject_import`, `_unified_security_assessment_upload`, `_unified_license_summary_upload`, `_unified_dispatcher_upload`** rewritten to describe behavior directly instead of as "mirror of <deleted route>".
- **`subject_data_service.py:170` comment** about "legacy aliases until session 4 deletes them" updated. `_SA_IMPORT_URL` / `_LS_IMPORT_URL` header comment also updated.

### Notes

- **Step 1 pre-deletion grep surfaced one critical not-quite-production issue:** the `_unified_dispatcher_upload` helper had two `url_for("main.quick_hc_generic_import")` calls (inside the no-file-selected branch and the after-completion fallthrough). These would have failed at request time once the generic route was deleted, but they weren't user-facing references — they were inside the unified route's helper that was specifically designed to be byte-equivalent with the old generic route in session 2. Fixed both to redirect to `main.quick_hc`.
- **Two dead-data sites NOT touched (out of session 4 scope):** `src/cvhealthcheck/quickhc/registry.py:131, 205` hold `TileDefinition.import_url=` with the OLD hyphenated URLs. The field has been unread since session 2 deleted `canonical_view._build_sources` (its sole consumer). These can be removed in a future cleanup pass; not session 4's scope.
- **`src/cv_healthcheck.egg-info/PKG-INFO`** mentions the deleted URLs ("POST /quick-hc/security-assessment/import remains active"). Built artifact; regenerated on next build. Not edited.
- **Historical references in `docs/refactor_unified_upload_2026-05-31.md`, `docs/refactor_unified_upload_session_3b_inventory.md`, and `docs/adr/0001-source-building-fork.md`** — left untouched. These are records of what was once true and should remain accurate to the moment they were written.
- **Source-building fork still in place** per ADR 0001. Not reopened. `_legacy_builders` and the AI/system dispatch in `build_subject_initial_data` continue to function as documented.
- **Snapshot test passes** (frontend was already on the unified URLs since session 3 step 3; this session only deleted route handlers, no source-building change).
- **3 `FIXME(refactor-unified-upload-session-5)` tags** unchanged at the dispatch sites in `quick_hc.py`. They mark the branch-dispatch smell — session 5's target, not session 4's.

### Carry-forward for session 5

The unified route is now the sole upload path. Session 5 replaces the branch dispatch (which currently hard-codes `security_assessment` and `license_summary` sub-branches in `quick_hc_subject_import`) with data-driven dispatch — likely a new column or JSON field on the `subjects` table describing each subject's upload behavior (form-field name, allowed extensions, success-message format, persist function reference).

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
