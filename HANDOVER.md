# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-04 (docs — documentation review & hygiene pass; one drift fixed, candidates flagged)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *docs: review pass — sync drifted docs, flag unused files* (this commit).
**Test status:** **1008 passing** (unchanged — docs-only session, no source touched).

---

## Read this first

1. `README.md`; 2. `HANDOVER.md` (this file); 3. **`docs/adr/0010-row-scope-evaluation-rules.md`** (Accepted).
4. The most recent CHANGELOG entries (2026-06-03: Evaluation band slice 2; per-row verdict rendering slice 1; the scope/verdict engine slice; the `save_rule` `kind` fix).

---

## What was just completed — documentation review & hygiene pass (docs-only)

Reviewed every tracked `*.md`/`*.txt`. **One drift fixed** (README + ROADMAP "no scoring" bullet → reflects ADR-0010 row-scope rules). Ports/paths/commands verified correct; PROMPT/CHANGELOG/HANDOVER/HEALTHCHECK_MATRIX/ADRs current. No source changed.

### ⚠ For Michiel — "no longer used" candidates (REPORT ONLY; nothing deleted)
| candidate | reason | recommendation |
|---|---|---|
| `HANDOVER_TO_CODE.md` | one-time design→Code handover (Report Inventory, 05-24); 0 refs; shipped | archive/delete |
| `design/CODEX_HANDOVER_v2.md` | Codex Quick-HC-UI-rebuild handover (05-20); 0 refs; rebuild shipped; project is Claude Code now | archive/delete |
| `cv_healthcheck_context.md` | generated "Project Context Report" snapshot (05-23); 0 refs; superseded by README/PROMPT | archive/delete |
| `docs/review_2026-05-20.md` | dated point-in-time codebase review; ref only by CHANGELOG | archive (keep for history) |
| `docs/research/license_summary_report_xml_analysis.md` | research input (05-18); 0 refs; research-only | keep (research reference) |
| `artifact_schema_v1.md` | "v1 Draft" canonical-artifact schema; partly current; ref by context only | keep, refresh status later |
| `DATA_SOURCE_MAPPING.md` | source strategy (05-15); overlaps API_MAPPING + ROADMAP; still ref'd by README | keep (overlap, not orphan) |

**Not candidates (active):** `docs/refactor_unified_upload_*.md` — that refactor is in-progress (session 3b is a 06-03 stop-and-report). The numbered ADRs + surveys/plans are permanent decision records — keep.

### Flagged factual gaps (NOT changed — your call)
- **API_MAPPING.md** omits the ADR-0009 live-validated CC endpoints (`commserv/audittrail`, `…/metricsreporting`, `…/addremovesoftware/commservesoftwarecache`, `…/v4/servergroup`). Adding them is sanctioned ("validated API behavior") but left for you to format.
- ROADMAP/README Phase-3 subject enumerations don't list the new CC-API subjects (historical snapshots — not edited).
- No documented decision/architecture conflicts with current code were found.

---

## Earlier this session — bind path: active-version scoping + transpose targets

`db/rules.py` `validate_row_match_rule` bind block now resolves the **active version** via `get_subject` and scopes the section-type query + `_section_column_ids` to it (`AND subject_version=?`), fixing the bug where binding to `commserve_software_cache.cache_configuration` (card v1-3 → table v4) was rejected as 'card' (unscoped `.fetchone()` picked v1). `_section_column_ids` also admits a transpose section's implicit `id`/`key`/`label`/`value` as valid rule **targets** (decoupled from display, which stays `table.columns`). +6 tests; **1008 passing**. Collection/read path + engine untouched.
- **Left as follow-up:** `bind_rule` (the WRITE) is still unscoped — writes dead refs into superseded versions (harmless; collection reads only active). Scope it to the active version when convenient (no downside).

### ⚠ Next step (Michiel) — the v4 binding + rules are now unblocked
With this fix, `save_rule` can bind a `row_match` rule (keyed on `key`+`value`) to the v4 `cache_configuration` transpose table. Author the rules via MCP `save_rule`; the v4 `table.transpose`/`table.columns` binding is already live (v4 active). Live re-collect needs a fresh Connect (token keeps expiring).

---

## Earlier this session — unified table verdict legend

Every table section (columns + property) now shows ONE legend — **good · warning · critical · not evaluated · info** — in `quick_hc.js`. This supersedes the `5a40e1e` two-legend split: any table's unruled rows fall through to the info-blue dot (`vdotClass(null)`), so info belongs on all table legends (the split was the wrong cut). `view_mode:"property"` stays as the discriminator for the future stacked-tile render but no longer drives the legend. Render-only JS; model/view/engine untouched. `not_evaluated` grey stays distinct from info-blue (`e0aa3287`). 1002 passing.

### ⚠ Still pending (Michiel) — author the `commserve_software_cache.cache_configuration` transpose binding
Unchanged from before: re-stage as `output_as:table` with `table.root_key:"commserveSoftwareCache"`, `table.transpose:[…12 settings…]`, `table.columns:[{id:"label",label:"Setting"},{id:"value",label:"Value"}]` (result_to_artifact then sets `view_mode:"property"` automatically) + author `row_match` rules keyed on `key`+`value` via MCP `save_rule`. Live re-collect needs a fresh Connect (token keeps expiring).

---

## Earlier this session — "property" table view_mode (legend carry, now legend-unified)

`TableSection.view_mode` gained a third value **`"property"`** (Option A). `result_to_artifact` sets it on a transpose section (gated on `spec.transpose`); `canonical_view` forwards it; `quick_hc.js` swaps the columns-mode legend to **good · info · warning · critical · not evaluated** when `view_mode==='property'`, leaving every other table on the unchanged data-table legend. Legend content only — layout, dots, the `vdotClass(null)→info` fallback, and the card path are untouched; `not_evaluated` grey stays distinct from info-blue (`e0aa3287`). +5 tests; **1002 passing**.

### ⚠ Still pending (Michiel) — author the `commserve_software_cache.cache_configuration` transpose binding
The materialization + property legend are in place, but the live subject's card is **not yet re-authored** as a transpose section. Re-stage as `output_as:table` with `table.root_key:"commserveSoftwareCache"`, `table.transpose:[…12 settings…]`, `table.columns:[{id:"label",label:"Setting"},{id:"value",label:"Value"}]` (result_to_artifact then sets `view_mode:"property"` automatically), and author `row_match` rules keyed on `key`+`value` via MCP `save_rule`. Until then, `cache_configuration` still renders the empty card. A live re-collect needs a fresh Connect (token keeps expiring).

---

## Earlier this session — transpose / property-table materialization

`_project_table_rows` (`command_center.py`) now recognizes `table.transpose: [{key,label,field}]`: one object → N rows `{id:key, key, label, value:<obj.field>}` (placed before the dict-wrap). Each setting is a real row with stable `id`=key, so the **existing row-scope engine** gives per-row verdicts (a `row_match` rule keyed on `key`+`value`) — **no engine change**. `result_to_artifact` honors the binding's `table.columns` for transpose display so `id`/`key` don't leak as columns (gated on `transpose`; other sections unchanged). +7 tests; **997 passing**.
- Renders today as a `Setting | Value` table with per-row STATUS dots (default `columns` mode). Stacked-tile "card look" deferred (the `view_mode:card` branch is 1-row-only + dotless).

### ⚠ Next step (Michiel): re-author `commserve_software_cache.cache_configuration` as a transpose section
Replace the empty card binding with:
- `output_as: table`, `table.root_key: "commserveSoftwareCache"`, `table.transpose: [{key,label,field}…]` for the 12 settings, `table.columns: [{id:"label",label:"Setting"},{id:"value",label:"Value"}]`.
- Author `row_match` rules (`scope:row`) keyed on `key == <setting> AND value <op> …` (MCP `save_rule`). Target the **`key`** (stable), never `label`. Settings with no rule bake `good` (use a section `scope` if only some should show a verdict).
- This is the same transpose vocabulary the read-only feasibility pass recommended; avoids the card `items` empty-bake trap.

### Still open — Fix 2 (card binding-shape) for `metrics_reporting.status`
Separate from transpose: that card wants `card.items` (not `columns`) with fully-qualified `field` paths + `"type":"epoch_to_iso"` on the timestamps (already supported, `842d39c`).

---

## Earlier this session — engine fix: list-index in _resolve_field_path

`_resolve_field_path` (shared ADR-0007 D2 resolver, `metric_section.py`) descended only into dicts, so a numeric segment into a **list** (`commserve_software_cache` table root_key `...cacheContents.0.softwareCacheServicePackDetails`) returned `default` → 0 rows. Now: dict→key (literal `"0"` key wins), list→non-negative integer index (out-of-range/non-numeric → default), else default. Additive — numeric-on-list only ever returned default before. +6 unit tests; **990 passing**.
- **Verified:** `cache_contents` now renders **3 rows** (WinX64 / linux-x8664 / linux-arm64, SP 11.40.47) — against the captured payload (live re-collect blocked: loopback token expired again).

### ⚠ Open — Fix 2 (separate, NOT code): the `commserve_software_cache` card
`cache_configuration` ("No card data") + `metrics_reporting`'s `status` card are the **same** root cause: the card binding declares table vocabulary (`columns`, and `root_key` the reader ignores) but `build_card_section` reads `items` with `label`/`field` (fully-qualified paths). Fix is a **v2 card-spec re-stage**, not code:
- `card.items` (not `columns`/`fields`), each `{"label","field"}` with fully-qualified paths (e.g. `field:"commserveSoftwareCache.cacheFreeSpace"`).
- For `metrics_reporting` timestamps, declare `"type":"epoch_to_iso"` (already supported, `842d39c`).
Worth an ADR note: **binding spec vocabulary diverges by section type** (table=`root_key`+`columns`, card=`items`) — the recurring mis-authoring trap.

---

## Earlier this session — Fix A: nested root_key + epoch_to_iso coercion

`metrics_reporting` baked empty due to two binding-vs-reader mismatches; this is the **code half**.
- **Table:** `_project_table_rows` now resolves `root_key` via `_resolve_field_path` (nested) instead of flat `raw.get()` — a nested `config.cloud.serviceList` resolves; single-segment keys are byte-identical (audit_trail/server_groups unchanged).
- **Card:** added `epoch_to_iso` as a closed-enum sibling of `hex` in `_coerce_item_value` (ADR 0007 D3) — `"type":"epoch_to_iso"` formats epoch-seconds → ISO 8601 UTC, raw kept. The card reader already coerces, so no new wiring.
- **Validated** (captured payload — live token expired again, `no active token; reconnect`): services table = **8 rows, service_name 8/8, Health Check id1/enabled-false → warning**. 984 tests.

### ⚠ Next step — Fix B (separate, in chat): re-stage the `status` card binding
The `status` card is **still empty** (expected). Its binding shape doesn't match `build_card_section`'s contract:
- uses `card.fields` with per-entry `id`/`field` → the reader wants **`card.items`** with **`label`**/`field`;
- declares `card.root_key:"config"` → the reader does **not** apply root_key, so each field path must be fully qualified (e.g. `field:"config.metricsReportPackageInstalled"`).
Re-stage with that shape, and declare **`"type":"epoch_to_iso"`** on the three timestamp fields (`config.lastCollectionTime`, `config.lastUploadTime`, `config.nextUploadTime`) — now supported by this commit.

---

## Earlier this session — TableSection `view_mode` (single-row table → card)

Option (b) from the render-mode map: a presentational discriminator so a single-row table renders as a Field/Value card while **its row rule + per-row verdict keep firing** (the engine, `validate_row_match_rule`, and the verdict bake are untouched).

- **4-file change:** `TableSection.view_mode: Literal["columns","card"]` (`models.py`, omit-when-default serializer) → read from the binding's table spec in `result_to_artifact` → passed through `artifact_to_view` → a `secBody` branch that renders a single-row table as a `meta-grid`/`meta-card` card (section pill in the header). Mirrors `CardSection.view_mode` / `MetricSection.render_mode`.
- **`audit_trail` opted in** (runtime binding edit, gitignored): `view_mode:"card"`. Re-baked → `view_mode==card`, 1 row, verdict `good`, 0 findings.
- **⚠ Live re-collect could not run** — the loopback token expired mid-session (`no active token; reconnect`). Validated against the live-captured `auditTrailInfo` payload instead (only the HTTP fetch substituted). **Re-collect `audit_trail` after a fresh Connect to confirm the card renders on the live page** — that's the one unverified step.
- **Open:** push (several commits ahead); `mcp/server.py` probe-timeout hunk still uncommitted; `audit_trail` rule has no authored `description`.

---

## Earlier this session — CC-API dict-wrap fix + `audit_trail` built & validated live

- **Collector fix (committed `d1860c4`):** `extractors/command_center._project_table_rows` returned an empty table when `root_key` resolved to a **dict** (single-object response); it now auto-wraps a dict as `[obj]`. Unit test covers dict-wrap + the unchanged list path. This was a **gap from inception**, not a regression (`auditTrailInfo` never existed in git; the dict branch was simply never written).
- **`audit_trail` subject (runtime catalog, gitignored — NOT committed):** fresh build (it never existed). Table section `audit_trail.retention` on `rest_command_center_api`, endpoint `/commandcenter/api/commserv/audittrail`, `root_key auditTrailInfo`, columns `retention_critical/high/medium/low ← retentionFor{Critical,High,Medium,Low}` (camelCase correction vs the brief), orphaned rule `audit_critical_retention_warning` bound.
- **Validated LIVE** through the ADR-0008 loopback (app-held token; no CS token held here): endpoint `200`, `auditTrailInfo` is a single dict → re-collect yields **exactly 1 row** `{critical 365, high 365, medium 240, low 120}`, verdict `good`, **0 findings** (`< 365` false at 365). Renders: Report-band table (1 row) + Evaluation-band criteria card.
- **Open:** push (now several commits ahead); the `mcp/server.py` probe-timeout hunk is still uncommitted; `audit_trail` has no authored rule `description` (criteria primary falls back to the rule title) — author one to match the slice-3 pattern.

---

## Earlier this branch — authored rule descriptions + Option-B criteria render (slice 3)

The criteria card's per-check **Checks** lines are no longer derived from rule ids. Each check now renders the rule's **authored `description`** (falling back to its static title, **never the raw id**) over a **mechanically-rendered condition** in mono — Option B.

- **The data:** `save_rule` accepts an optional `description` (nullable; persisted/returned/listed). `result_to_artifact` bakes each check as `{rule_id, severity, description, title, condition_text}`; `evaluative/row_match.format_conditions()` renders the condition (every operator) at bake time.
- **The render:** `canonical_view._evaluation_criteria_view` maps each baked check to `{sev, primary, condition}` (primary = `description` or `_title_static(title)` or "Check"); `quick_hc.js`/`.css` show badge + primary + mono condition. The interim `_RULE_SENTENCE`/`_rule_sentence` deriver is **removed**.
- **Verified via the real path** (re-baked `server_groups` artifact, runtime state): three checks — naming `name not contains "GRP_"`, rommelgroep `name = "rommelgroep" and company = "Company_1"` (critical), empty `server_count = 0` — each with its authored description, no raw id. Scope sentence + table caption unchanged.

**Visual confirmation is the operator's:** `./start.sh`, open `server_groups` → Evaluation band → "Evaluation criteria" → Checks: three rows, each a severity badge + a plain-English description + the condition in mono underneath. No raw rule id anywhere.

---

## Single recommended next action — scope-authoring MCP tool + authored scope label (retire the LAST interim phrasing)

The **only** remaining interim derivation is the criteria card's **Scope sentence** + the table's **scope caption** (`canonical_view._scope_phrases`, still id/operator-derived). Retire it the same way the descriptions were:

- Add a **scope-authoring MCP tool** — `save_section_scope(subject_id, section_id, {conditions, label})`, or a `scope`/`scope_label` arg on `save_rule`'s `bind`. `load_subject_section_scope` already reads `evaluative.scope`; add a sibling `label`.
- Bake the authored `label` into `metadata["evaluation"][section_id]` (next to `scope`) and render it verbatim as the scope sentence/caption, dropping `_scope_phrases`.
- Then author `server_groups`' scope label (e.g. "Manual server groups. Automatic groups are excluded.") through the tool.

## Other follow-ups
- **Criteria check ORDER** follows the binding order (currently naming → rommelgroep → empty), which is not the logical reading order. An authored order/priority on the rule (or the binding) would make it deterministic.
- The generated **report** (`quick_hc_report`) is a separate renderer from the workspace `secBody`; mirror the Evaluation band there if wanted (its own slice).
- A real Collect of `server_groups` re-bakes `_verdict` + the `evaluation` metadata identically (the re-bake here was a runtime convenience).
- **`sg_naming_convention`** had its redundant `association == MANUAL` condition dropped this slice (the section scope gates that population) — keep new rules scope-aware to avoid re-introducing redundant conditions in the criteria render.

---

## ⚠️ Uncommitted in the working tree (carry forward)
`src/cvhealthcheck/mcp/server.py` still has the **uncommitted probe read-timeout hardening** (`timeout=30 → (5, 30)`) from the probe-hang session — untouched again this session. Decide whether to commit it (its own small commit).

---

## Settled — do not relitigate
- Scope is section-level; `row_ref = id, never name`. Verdict baked at canonicalization, no separate store (D5).
- `not_evaluated` = explicit gray, distinct from info-blue. Criteria card has **no pill** (it describes the assessment, not a verdict); the Findings card carries the **worst-severity** pill (now critical on `server_groups`, since `sg_rommelgroep_company_1` fires). Both Evaluation cards toggle independently; excluding them must not remove the table's scope caption.
- After touching `mcp/server.py` or restarting, **reconnect the MCP client** (`pkill -f cv-healthcheck-mcp`).
