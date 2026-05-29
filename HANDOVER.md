# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-29 (ADR 0004 phase 4 — card section type, browser-verified)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `4a847ce` — HANDOVER #24: three-category classification for dev-tools retirement
**Test status:** **691 passing** under both `pytest` and `python -m pytest` (was 673).

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — fully implemented. Read it as the spec for what's in place.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Still active; orthogonal to ADR 0002.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives.

---

## What was just completed

**ADR 0004 phase 4 (card section type) implemented and browser-verified PASS.** The `card` section type — the last new section type in ADR 0004 (`multi_section` deferred). A card is a flat labeled key-value identity block that **also carries a section-level verdict** (steering decision: every card is judged), reusing the metric severity + verdict_chain machinery.

- **4a** (`1028265`) — new `CardItem`/`CardSection` models (own `type`; in the Section union); card carries `severity` + `verdict_chain` (reuse the metric shape) + a `columns` grid hint.
- **4b** (`a443043`) — migration 0012 table-rebuild widening `subject_sections` CHECK to allow `'card'` (follows migration 0004's pattern).
- **4c** (`4c244e1`) — `build_card_section`; `output_as:"card"` disambiguated (was a `rows[:1]` stub — now means only "emit CardSection"; the stub was removed); section_card_specs; emission folds card verdict into overall status.
- **4e/4f** (`d7b41eb`, `3301b83`) — Python + JS renderers (labeled grid reusing `.meta-card` styling).
- **4g** (`5d18ade`) — `card` added to `SUPPORTED_SECTION_TYPES` (agrees with the 0012 CHECK); loud guard re-pointed at `multi_section`.
- **4h+4d** (`92b0c7b`) — `_card_test` subject (migration 0013) + per-section conformance.
- **FIX 1** (`60c391c`) — section status badge moved to the section header for **both** card and metric (`[title … badge ☑]`); metric keeps its per-item badge as detail.
- **FIX 2** (`1b822ed`) — test subjects render in their own **"Test subjects"** sidebar chapter (via `is_test`), not mixed under Operations.

691 passing both invocations (was 673). Browser-verified: card renders the labeled grid + a header status badge; both card and metric show the header badge consistently; the environment identity block is **unchanged** (still plain `meta`, the card type did not displace it); test subjects group in their own chapter and hide when toggled off.

### Prior: ADR 0004 phase 3 (chart section type + MCP schema reconciliation) — PASS

**ADR 0004 phase 3 (chart section type + MCP schema reconciliation) implemented and browser-verified PASS** (Safari + Firefox). The `chart` section type lands as a single `chart_type`-discriminated renderer (line + pie), bundled with the MCP schema reconciliation (#30/#31). Deliverables, each its own commit(s) with tests:

- **3a+3b** (`6423a34`) — `build_chart_section` (reusable; a chart is a view over a table — labels + series column mapping; chart_type discriminates). The `ChartSection` model carried both shapes with **no change**. `result_to_artifact` emits on `output_as=="chart"`.
- **3d** (`225ddf7`) — `canonical_view` chart branch → one canonical chart-data structure.
- **3e** (`618b7c3`) — Chart.js 4 in the workspace; ONE `buildChartJsConfig`; module-level instance registry + `teardownCharts()` (no leaked canvases — browser-verified clean re-render); CDN-fail fallback.
- **3f** (`6f066a0`) — `chart` added to `SUPPORTED_SECTION_TYPES`; loud guard still rejects `card`/`multi_section`.
- **3g+3c** (`f929c7c`) — `_chart_test` subject (migration 0011) with line + pie sections from fixtures; conformance per chart section; `is_test` toggle.
- **3h** (`ce88cac`) — MCP `get_canonical_schema` now **derives** from `model_json_schema()` (drift structurally impossible); `supported_section_types` sourced from `SUPPORTED_SECTION_TYPES`; **non-negotiable drift-guard test** (verified it fires on a stale hand-schema). Backlog **#30 and #31 closed**.

673 passing both invocations (was 658). Browser-verified: line + pie render correctly from the same renderer; canvas lifecycle clean across Collect / re-navigation (the chart-regression-class bug is verified absent); SA, LS, the three regressed subjects, and the phase-2 metric subject all unchanged; toggle hides test subjects by default.

### Prior: ADR 0004 phase 2 (metric section type) — implemented + browser-verified PASS

**ADR 0004 phase 2 (metric section type) implemented and browser-verified PASS.** The `metric` section type lands end-to-end — the first canonical metric rendering through the full three-face vocabulary. Eight deliverables, each its own commit(s) with tests:

- **2a model** (`f78ab9d`) — MetricItem `value`→optional (None = sentinel "n/a"), `+derived/+severity/+verdict_chain`; new `VerdictEntry`; `MetricSection.render_mode` (default `"meta"`); `muted` added to `FindingSeverity`.
- **2c evaluator** (`bd811c8`) — `cvhealthcheck.evaluative.threshold.evaluate_threshold_rule` → severity + a one-entry `template_default` verdict chain with a populated reason; mute-on-sentinel.
- **2b build + CEL** (`2687062`) — reusable `build_metric_section(spec, rows)` (phase 5 reuses it); `ExtractionResult.section_metric_specs`; `result_to_artifact` emits MetricSection on `output_as=="metric"` and derives status from the worst verdict.
- **2e Python renderer** (`1626fa0`) — `artifact_to_view` dispatches the MetricSection branch on `render_mode` (`"metric"` rich / `"meta"` plain — LS unchanged).
- **2f JS renderer** (`18170f8`, +`b9a5cfe` sentinel-unit fix) — `secBody` metric branch + CSS.
- **2g+2d test subject** (`d85b5d0`) — `FixtureExtractor` (sandboxed to `data/test_fixtures/`), `data/test_fixtures/metric_test.json`, migration 0010 seeding `_metric_test`, `POST /quick-hc/<id>/collect-fixture`, phase-1 conformance on the metric path.
- **2h visibility toggle** (`5a2a817`) — `is_test` flag (prefix `"_"`), settings-page localStorage toggle, `renderLeft` filter; hidden by default.

658 passing under both invocations (was 625). **Browser verification PASS** (steering side): test subject renders correctly (Used 35 TB / Purchased 50 TB / Prev Active n/a / Utilisation 70% derived ƒ + Warning badge); toggle works both directions; SA, LS, and the three regressed subjects render exactly as at end of phase 1 (LS's `commcell_info` stayed on the `meta` path — the explicit `render_mode` discriminator did its job). No regression.

### Prior: ADR 0004 phase 1 (Foundation) — implemented + browser-verified PASS

**ADR 0004 phase 1 (Foundation) implemented.** Five deliverables, all infrastructure with **no user-visible change to existing subjects' content**:

- **2a CEL plumbing** (`2956afc`) — `cvhealthcheck.cel` evaluator wrapper over `cel-python` (`celpy`). `evaluate(expression, context)`, loud-fail, registers the ADR's `sum/count/avg/min/max/latest` aggregation primitives. ADR example #2 was shorthand (`.used_capacity` field-projection on a list isn't valid CEL; the working form is `.map(r, r.used_capacity)`).
- **2b `template_version`** (`d3b6da6`) — `ArtifactSource.template_version` (optional read, set on write); REST also sets `collected_at`.
- **2c family-derivation** (`aaeca6b`) — `subject_family(subject_id)` in `db/subjects.py`.
- **2d source-tile cleanup + version pinning** (`7e1e611` backend, `4852c93` UI) — migration 0009 `customer_subject_pin`; resolution helpers; collect route resolves the active version; environment source tile drops CommCell version (kept in identity card); "Last collected" + version dropdown in the Data Source section; `/quick-hc/<id>/pin-version` route.
- **2e conformance** (`5951750`) — `extractors/conformance.check_conformance`; `conformance` block in `extraction_instructions` JSON; verbatim ADR failure-record shape; section-grained in `RESTExtractor.extract`, emitted onto `artifact.metadata["conformance_failures"]`. Plumbing-only.

625 passing. Browser-verified PASS (no CommCell version on source tiles; Last-collected + single-option version dropdown present; existing subjects unchanged). CEL plumbing (`cvhealthcheck.cel`), `template_version` provenance, `subject_family`, per-customer version pinning (migration 0009), source-tile cleanup, and the conformance mechanism (`extractors/conformance.check_conformance`, section-grained) all landed here. Commits: `2956afc` 2a, `d3b6da6` 2b, `aaeca6b` 2c, `7e1e611`/`4852c93` 2d, `5951750` 2e.

### Prior: ADR 0004 phase plan committed at `docs/adr/0004-phase-plan.md`

**ADR 0004 phase plan committed at `docs/adr/0004-phase-plan.md`.** Nine phases: 1 Foundation (CEL plumbing, `template_version`, version dropdown, source tile cleanup, conformance mechanism) → 2 `metric` section type → 3 `chart` section type → 4 `card` section type → 5 capacity_license migration → 6 client_growth migration → 6.5 dev tools retirement (HANDOVER backlog #24/#25 land here) → 7 backup_job_summary migration → 8 evaluative face. Two scope adjustments from the ADR: `multi_section` deferred to whatever ADR addresses License Summary as a whole (no in-scope consumer; one open design question), and dev tools retirement explicitly folded into the sequence as phase 6.5 rather than left as post-ADR cleanup. The ADR's vocabulary documentation still stands at six section types; the implementation ships five.

### Prior session: ADR 0004 drafted

**ADR 0004 (three-face metadata vocabulary) drafted and committed at `docs/adr/0004-three-face-metadata-vocabulary.md`.** Status: Proposed. The ADR defines a three-face metadata vocabulary (semantic / presentational / evaluative), six section types (table / findings / metric / chart / card / multi_section), CEL as the formula language with a defined primitive set and STOP-and-steer rule for extensions, the three vendor-compliance shapes (per-row severity codes / StatusRow / inline threshold), the vendor → template → override rules layering with a `muted` severity for explicit suppression, section-grained conformance failures with a structured rebuild-bridge record, subject versioning via `_vN` suffix subjects (not a version field), and migration of the three regressed subjects (Capacity Licenses, Client Growth, Backup Job Summary) as the ADR's end-to-end validation. The survey at `docs/adr/0004-survey.md` is the evidence base. Explicitly out of scope: License Summary migration, the AI authoring loop, recommendations / predictive face, cross-CommCell report identification (HANDOVER backlog #23), and implementation phase planning.

### Prior session: ADR 0004 survey landed in repo

**Add ADR 0004 survey document: three-face metadata vocabulary stress-test.**

### Prior session: pre-ADR-0004 cleanup

**Pre-ADR-0004 cleanup: vendor-stable keys, loud failure for unsupported section types, report-ID backlog.** Three load-bearing fixes the ADR 0004 survey surfaced; none depend on ADR 0004's design being settled. (1) **SA vendor-stable identifiers preserved.** Migration 0007's column_map dropped `attrName` and `PARAMID` — Commvault's stable identifiers — leaving rule overrides nothing reliable to target. Migration 0008 extends the column_map for all six SA sections to add `attrName→vendor_key` and `PARAMID→vendor_id`. The Finding model gains additive `vendor_key`/`vendor_id` fields; `result_to_artifact._build_finding` populates them. Verified end-to-end against the on-disk raw 336 captures: all 32 SA findings now carry both identifiers populated. (2) **Loud failure for unsupported catalog section types.** New `cvhealthcheck.db.section_types` module pins `SUPPORTED_SECTION_TYPES = {findings, table, metric}` and raises `UnsupportedSectionTypeError` with a clear informational message. Two enforcement layers: insert-time in `create_subject_from_proposal` (rolls back on chart-type sections), collection-time in `RESTExtractor.extract` (fails before any GET). 7 chart-typed rows exist in the live catalog (1 system seed `client_growth.chart` + 4 cloud + 2 storage); rows preserved (no destructive cleanup), validator catches new attempts. (3) **HANDOVER backlog #23 — Report IDs are CommCell-specific.** Three lab captures showed LS=206/178, BJS=194/168, Storage Utilization By Application=199/603 across deployments — and dataset column schema differs too. ADR 0004 must address subject identity across deployments. 575 passing under both pytest invocations (was 566).

### Prior session: test-suite collection-error fix and pass-count reconciliation

**Infra: fix test-suite collection error; reconcile reported pass counts.** `tests/test_unified_upload_route.py` carried `from tests.test_security_assessment_import import HTML_SAMPLE` since 2026-05-25 (`dff43f1`). The project has no `tests/__init__.py`, so `tests` is not a package — and the result depended entirely on invocation: `pytest` (plain entrypoint) aborts at collection with 0 tests run; `python -m pytest` succeeds because cwd lands on `sys.path` and `tests` resolves as an implicit namespace package. 12 tests were silently uncollectable under plain `pytest`, including the 5 headline tests from the recent inline-upload and field-name-contract fixes. The prior session's "556 passing" report (the LS workload-section CHANGELOG) was a mis-count caused by running `pytest --ignore=tests/test_unified_upload_route.py` instead of investigating the collection error; the true count under `python -m pytest` at that point was 568. Fix drops the `tests.` prefix from the two cross-test imports — convention matches every other test file. Both invocations now collect 566 and pass 566. CHANGELOG carries a reconciliation table for every recent count claim.

### Prior session: LS HTML workload-section detection

**Bugfix: LS HTML workload-section detection for Commvault export markup.** The prior numeric-extraction fix made values render correctly, but the user pointed out that workload summary sections (Capacity / Operating Instances / Virtualization / User / Data Insights / Air Gap Protect / Other) are the CORE of a License Summary report — and the artifact was reporting **0 workload sections** for real exports. Investigation surfaced two stacked bugs. (1) `_table_section_name` at `license_summary/import_html.py:128-133` walked `find_previous(["h1",...,"div"])`, landed on the table's own wrapper `<div class="exportTable">`, then `.get_text()` dumped the table's full contents as the "section name" — never matched `SUMMARY_SECTION_NAMES`. Commvault exports wrap titles in `<span class="component-title-text">` inside nested divs, with zero `<h2>`-`<h6>` headings in the entire file. (2) Two workload tables (Virtualization Licenses, Data Insights Licenses) use bare `Available Total`/`Used` headers without unit qualifiers, so the header-only classifier returns `"other"` and the rows pile into `other_licenses`. The user's "9 Other Licenses rows" was actually 2+7 from mis-bucketed Virtualization and Data Insights sections. Fix: `_table_section_name` walks `find_all_previous()` matching against direct text only (string children, not recursive `get_text()`) against `_KNOWN_SECTION_TITLES`; a claimed-titles guard prevents cross-wiring; the parse loop routes section_name-in-SUMMARY_SECTION_NAMES tables to workload-summary regardless of classifier output. Real-file verification confirms 7 sections / 23 rows (4/2/2/5/7/1/2), 0 standalone other_licenses, 0 agent_feature, no cross-wiring. Two new tests use the real markup shape and would have caught both bugs.

### Prior session: LS numeric value extraction

**Bugfix: LS numeric value extraction for combined value+unit cells.** After the prior two fixes wired up the inline-import path correctly, the LS HTML import landed an artifact whose `Other Licenses` table rendered blank `Available Total` and `Used` columns in the workspace — only the unit survived. Root cause: `parse_number` at `license_summary/normalize.py:64-72` float-parsed the whole cell, so combined cells like `"500 VMs"` / `"25 TB"` raised `ValueError` and returned `None`. The unit extractor (a separate regex) worked fine, which is why the Unit column was the only one populated. Fix: regex-extract the leading numeric prefix; also strip `\x00` from `clean_text` as belt-and-braces (the real export has 84 NUL bytes scattered between tags, none inside cells, but the cost is negligible). One fix covers all three normalize callsites by construction (Other Licenses HTML+CSV; Agent/Feature uses the same `parse_number` call shape — unverified against real data because the user's export had 0 agent/feature rows). Real-file verification confirmed: 9 Other Licenses rows parse correctly; the user's `Auto Recovery` row now shows `available_total=500, used=0`. New + extended tests proven to fail-against-old / pass-against-fix. 564 tests pass (was 563).

### Prior session: upload field-name mismatch

**Bugfix: upload field-name mismatch for already-collected system subjects.** Yesterday's inline-JSON fix (`130e28b`) unmasked a second latent bug. With the JSON-response path wired correctly, the JS now received an error JSON it could display — and that error read "No file selected." even though a file was clearly selected. Root cause: `_provenance_to_tile_sources` at `subject_data_service.py:226` hardcoded `import_field="file"`, but the SA/LS handlers read `request.files[handler.form_field]` where `form_field` is `"assessment_file"` / `"license_summary_file"`. The bug fires when a canonical artifact exists for the subject (the orchestration takes the provenance path instead of the nodata path, where the right field names ARE declared). Fix uses `get_handler(subject_id).form_field` as the source of truth. Contract test added that pins the action-dict-importField ↔ handler.form_field invariant — it fails against the pre-fix code, passes against the fix.

### Prior session: inline JSON response fix

**Bugfix: inline JSON response for system-subject uploads.** Image evidence showed CSV and HTML offline imports for `license_summary` failing in the UI with "Import failed: The string did not match the expected pattern." Investigation surfaced a latent server-side bug since 2026-05-25: `_handle_system_upload` ignored the JS's `X-Inline: 1` header and always replied with flash+redirect (302 → HTML body); the JS then failed `resp.json()` parsing and surfaced WebKit's SyntaxError. The underlying import was actually succeeding — the LS legacy store has 7 content-duplicate groups (2-10 artifacts each, tight time windows) from user retries. SA's legacy store has 29 unique artifacts (no retry pattern). The fix added X-Inline handling to `_handle_system_upload` and 4 inline-mode tests. ADR 0003 was unaffected by this bug — it predates the ADR and the upload path is unrelated. The duplicate artifacts in the LS legacy store were not cleaned up — backlog #14 (legacy SA/LS store retirement) is the right place for that.

### Prior session: ADR 0003 phase 5 cleanup

**Phase 5 cleanup pass; ADR 0003 implemented with LS caveat.** Step 1 investigation surfaced that LS's report 206 structurally doesn't fit the catalog model defined in ADR 0003 (47+ pages with name-ambiguous datasets, runtime parameter-substitution-from-prior-results, per-row value-formula transforms). Steering chat approved Path A: leave LS bespoke, do the safe cleanup half of phase 5, mark ADR 0003 implemented with the caveat documented. Deleted: `CommvaultSession.init_report` (dormant since the interstitial fix), `REPORT_DEFINITIONS` dict + its file (orphan since phase 2), `_read_commcell_provenance` (zero callers since phase 3). ADR 0003's Migration / Consequences / Out-of-scope sections amended to reflect the actual outcome. The ADR status is now "Implemented (with LS caveat)."

---

## What is in-flight

**ADR 0003 is implemented (with the documented LS caveat).** The catalog-driven REST extractor handles four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment); License Summary retains its bespoke `collect_from_rest` path. The methodology retrospective is the recommended next session. Working tree is clean.

---

## Single recommended next action

**ADR 0004 phase 5 — migrate capacity_license (the first REAL subject migration). See `docs/adr/0004-phase-plan.md` §Phase 5 for scope.**

Phases 1–4 built the foundation + all four new section types (metric/chart/card; `multi_section` deferred), each validated against an internal test subject. Phase 5 is the inflection point: the **first migration of a real, user-facing subject** to the new vocabulary — capacity_license — which is also one of the three regressed subjects, so this is where the user-visible regression recovery begins.

Per the phase plan §Phase 5, capacity_license gets: a **`metric`** section computing `utilisation_pct` via CEL with **sentinel handling for -1** ("license not active that month"), template-default rules **warn at 70% / critical at 90%**; the **`table`** section restored with clean column names via `column_map`; and the **`chart`** (the trend the legacy builder computed and never emitted). Minimum evaluative-face machinery to fire the rules (phase 2's threshold evaluator already does this).

Phase 5 inherits everything: `build_metric_section` (sentinel + CEL + threshold verdict — capacity_license is the exact shape `_metric_test` was modelled on), `build_chart_section`, `build_card_section`, conformance, the renderers, the section-header badge. Unlike phases 2–4 it touches a **real subject** (not a `_test` one) — so it's the first to **not** ride the `is_test` toggle, must collect from the **live lab** (or the existing capacity_license REST catalog row), and the REST extractor will need to populate `section_metric_specs`/`section_chart_specs` from the catalog `extraction_instructions` (phases 2–4 only populated those in `FixtureExtractor`; the REST path doesn't yet). **That REST-path spec-carrying is the main new wiring phase 5 needs** — investigate it in step 1.

Two capacity_license-specific decisions for phase 5:
- **TWO chart-ish surfaces, neither built as a chart in phase 3.** (1) Per-row utilisation **bars** (`usage-fill`, the `workload` JS type) = a **table-with-bar-column** presentation. (2) A legacy inline monthly-trend **mini-chart** (raw-div `chart_capacity`). Phase 5 decides whether the trend becomes a real `ChartSection` (line — now possible) or stays a mini-chart; the per-row bars are a table-column presentation, not a chart.
- **`backup_job_summary` collects 0 rows** in the lab (noted in earlier handovers) — not phase 5, but relevant context for phase 7.

Inputs phase 5 needs:
- **`docs/adr/0004-phase-plan.md`** §Phase 5; **ADR** §"Migration of the three regressed subjects" (capacity_license: metric utilisation_pct, chart trend, table column_map, warn/critical rules).
- The legacy builder `_build_capacity_license_subject` (`subject_data_service.py`) — the derivation logic to reimplement in CEL.
- Phase 1–4 surfaces: `build_metric_section`/`build_chart_section`, `evaluative.threshold`, `cvhealthcheck.cel`, conformance, the REST extractor (`extractors/rest.py`) which needs the spec-carrying wiring.

### Carried forward for later phases

- **Environment identity → card (candidate follow-up).** The card type now exists and is the canonical successor to the `meta`-rendered identity displays (the environment identity block, LS `commcell_info`). Moving the environment identity display onto a `CardSection` is a clean candidate follow-up — NOT necessarily phase 5 (phase 5 is capacity_license), but the natural first real consumer of the card type beyond the test subject. Decide when convenient.
- **Chart types deferred (architecture allows, not built).** Phase 3 built only `line` + `pie`. `bar`/`area`/`doughnut`/`bubble`/`radar`/`polar`/`scatter` are "a `chart_type` string + confirming the data-shaping" away. Add when a real subject needs one.
- **Cosmetic styling pass (low priority — batch these together).** Renderer-only refinements, no model changes:
  - Per-item metric badge placement inside metric cells (the Warning badge under the value) and the card's per-value badge placement.
  - **Card status border treatment.** Propagate a section's severity to the card's border so verdicts are scannable at a glance. Recommended: a **left accent bar** (not a full colored border — full borders turn a multi-card report into a wall of color and stop signalling). Tint only attention-worthy statuses (warning = amber, critical = red; info optional); leave `good`/`muted` with the normal neutral border, so a colored edge always means "look here" and its absence means "fine." **Keep the header status badge in all cases** — the border is reinforcement, not the sole signal (accessibility: don't rely on color alone). Applies the severity already on the section.

### Methodology retrospective for ADR 0003 — deferred

The four methodology questions (wipe-and-recreate rule, ADR workflow efficiency, ADR-commit-alongside-first-phase pattern, catalog-model expressiveness limits — backlog #17–#20) remain open. They're orthogonal to ADR 0004's design and can run after.

### After the retrospective

Whatever surfaces. The current backlog is healthy (no urgent next code action); LS-migration future-work is documented; ADR 0003 is done.

### Priority-ordered backlog (everything else)

### Priority-ordered backlog (everything else)

1. **AI import workstream — staging UI for proposal review, compliance rules.**
2. **CommCell-discovery flow for customer creation.** Auth plumbing overlaps with ADR 0003 phase 3 (landed). The discovery flow can reuse `get_active_customer` and the customer-bound auth model directly.
3. **Report-provenance verification.** Check imported reports' embedded CommCell IDs against the active customer's stored CommCell ID. Catches "wrong customer's report" mistakes.
4. **Read-only per-finalization view.** Deferred from ADR 0002 phase 5 step 5.
5. **Customer panel on the right side of `quick_hc.html`.** Raised earlier, not acted on.
6. **`shared.py` split.** 413-line god-module; flagged in the 2026-05-20 review.
7. **`SecurityAssessmentArtifactRegistry` rename / generalize.** The registry pattern is used by both SA and LS but the class name is SA-specific. Decide: rename to a generic `ArtifactRegistry` and unify, or document the per-domain naming as intentional.
8. **LS catalog migration.** Phase 5 of ADR 0003 deliberately left `license_summary` bespoke after investigation showed the catalog model's expressiveness was insufficient. To migrate LS would require three extractor extensions: (1) runtime parameter substitution from prior dataset results (LS's organization dataset returns `OrgGUID`s that downstream datasets need as parameters); (2) page-aware GUID resolution (LS's report 206 has 47+ pages where the same dataset name appears multiple times with different GUIDs); (3) value-formula transforms (LS uses per-row unit suffixing via a `LicUsageType` integer code → unit string dispatcher). Defer until consultant demand justifies. Until then, LS uses its existing bespoke `collect_from_rest` path; new LS-shaped reports continue to require Python code rather than catalog rows.
9. **Hardcoded URLs in `report_service.py`.** Audit whether any remain after the 2026-05-20 partial cleanup.
10. **Left-nav structural review.**
11. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL and `db/customers.py` helpers — pick one.
12. **Template inheritance cleanup.** Uneven `base.html` extends.
13. **`engagements` table cleanup.** Empty since migration 0001; pre-ADR-0002.
14. **Project-scope the legacy SA/LS stores** under `data/catalog/{security_assessment,license_summary}/`. SA store still has its pre-ADR-0002 `latest_*.json` files (29 unique artifacts, no duplicates); LS store similarly with 42 `artifact_*.json` files — of which 41 belong to 7 content-duplicate groups from the 2026-05-25 → 2026-05-27 X-Inline bug's retry pattern (now fixed at commit 130e28b). Phases 4/5 didn't touch them — separate cleanup. The LS store remains in active use through the bespoke path. When this cleanup eventually lands, the duplicate-collapse is the natural first pass: keep the latest artifact per content-hash, delete the older retries.
15. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
16. **Audit Section 6 #2/#5/#6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.
17. **Methodology marker: wipe-and-recreate rule.** Default rule for proof-of-concept phase: any change touching dev-only data preserved across schema edits is over-engineered. Wipe and re-collect unless real customer data is at stake. ADR 0002 set the precedent; ADR 0003 phases 1 and 4 followed it. Phase 5 didn't need it (LS not migrated). Up for retrospective decision: tool-wide default or ADR-by-ADR judgment.
18. **Methodology marker: ADR workflow efficiency.** The survey-then-steer-then-draft-then-phased-implementation cycle ran end-to-end twice (ADR 0002, ADR 0003). Was the overhead worth it? Particular lens for ADR 0003: phase 4 surfaced an extractor-schema gap mid-implementation (column_map / status_to_severity), and phase 5 surfaced a deeper gap that forced LS to stay bespoke. Could a deeper survey or a prototype-against-real-data step have caught these earlier? Retrospective decides.
19. **Methodology marker: ADR-commit-alongside-first-phase pattern.** ADR 0002 and ADR 0003 both landed this way (ADR doc committed in the same session as phase 1). Should `docs/PATTERNS.md` or HANDOVER's "Where work happens" section document this explicitly so future ADR sessions don't leave the doc uncommitted? Low-priority decision.
20. **Methodology marker (new): catalog-model expressiveness limits.** ADR 0003 surfaced its model gaps twice — Approach A in phase 4 (added column_map + status_to_severity + HTML stripping) and the LS escalation in phase 5 (would need parameter substitution + page-aware GUID resolution + value-formula transforms). Both surfaced during *implementation*, not during *design*. Worth a deliberate examination of when to surface "the model isn't expressive enough" earlier in the ADR process. Retrospective fodder.
21. **Cleanup: retire `reportsplus/checklist.py`** (dead since phase 4 — only callers were the deleted SA bespoke modules; LS doesn't use it). Small post-ADR-0003 cleanup.
22. **LS Capacity Licenses consumption shape.** In the Commvault HTML export, the Capacity Licenses section encodes usage as a percentage status-bar in the Summary column (`<div class="status-bar complete-bar">0%</div>`), NOT as a number in the Used (TB) column — that cell is literally `<td></td>` for every Capacity Licenses row. After the 2026-05-28 workload-section fix, those rows now parse with `used=None`, `entitlement_value` populated, `status="0%"`. The recommendations / growth-trend work needs consumption in absolute terms — it must either derive TB-used from the Summary percentage × entitlement (with regex on the `0%` / `15%` text in `status`), or source consumption from the REST collect path where it may be structured. Flagged so the recommendations engine doesn't assume the Used column is populated for Capacity Licenses; the other six workload sections do populate Used.
23. **Report IDs are CommCell-specific, not portable identifiers.** API captures from three different CommCells confirmed: License Summary is report 206 on the dev lab but 178 on another; Backup Job Summary is 194 vs 168; Storage Utilization By Application is 199 vs 603. Worse, the column schema of "the same" dataset can differ across CommCells (e.g. BJS Job details has `JobStatus, JobId, SizeofApplication, EstimatedMediaSize, ProtectedObjects, FailedObjects, FailedFolders` on one CommCell and `ClientName, Status, StartTime, SizeKB` on another). Any catalog row that hardcodes a numeric `report_id` is implicitly single-deployment-scoped. ADR 0004 must address how subjects identify themselves across deployments — likely by report name or some other stable semantic identifier, with per-deployment resolution to numeric ID. Surface during ADR 0004 design conversation; don't try to fix in pre-cleanup.
24. **Dev tools retirement (full retirement, post-ADR-0004).** Dev tools surface (`src/cvhealthcheck/web/routes/development.py` plus 14 dedicated templates, 7 orphan helpers in `shared.py`, 4 stale data files in `data/catalog/metrics/`) is queued for retirement. Investigation 2026-05-28 produced a three-tier removal plan (Tier A safe-to-delete, Tier B requires callsite updates, Tier C requires product decisions). Most consequential dependency: the production Quick HC report's tile detail links resolve to dev routes (`main.metrics_client_growth`, `main.metrics_capacity_license`). Natural sequencing: retire after ADR 0004 phase 4 (chart section type) lands, so the workspace has its own canonical chart rendering surface that tile `detail_endpoint`s can point at. Investigation details in the chat transcript; concrete surfaces include 14 templates, 7 orphan helpers, the Chart.js CDN dependency (only consumer), the dev `/security-assessment` cluster (overlaps backlog item about retiring the legacy `/security-assessment` page in the smaller-cleanups list), the `/reportsplus/*` exploration pages (HTML wraps around CLI output), and updates needed in 4 test files plus README.md.

    **Phase 6.5 must FIRST classify every Development-page surface into one of three categories before deleting anything — do NOT wholesale-delete; the page is a mixed bag with three different fates** (the page exposes ~15 surfaces across three clusters: Environment — Quick HC Workspace / Lab Readiness / API Test; Metric Details — Client Count / Client Growth / Capacity License; Reports Plus / Metrics — Reports / Report 318 / License Summary / Report 318 Metrics / Security Assessment / Security Assessment Registry (internal) / Datasets / Health Candidates / Execution Validation):
    - **(a) AUTO-OBVIATED BY MIGRATION** — surfaces that become redundant as their subject migrates to canonical in phases 5/6/7. Candidates: Capacity License (phase 5), Client Growth / Client Count (phase 6), any backup-job-summary surface (phase 7), plus legacy detail pages like License Summary / Report 318 if they duplicate what the canonical workspace shows. Not "deleted" so much as obviated; confirm each is truly redundant post-migration before removing.
    - **(b) DISPOSABLE SCAFFOLDING** — genuine dev-only surfaces with no production consumer. Candidates: API Test, Execution Validation, Health Candidates, Datasets, Lab Readiness. Safe to retire in 6.5 after the LB-1 detail_endpoint repoint makes deletion safe (per #24/#25/#28).
    - **(c) LOAD-BEARING — KEEP or RELOCATE, do NOT delete.** The "Security Assessment Registry (internal)" surface is the human-review side of the MCP staging registry (`list_proposed_subjects` / `approve_staged_artifact` / `reject_staged_artifact`) — the ADR 0005 AI-authoring review loop. Retiring the dev *page* may be fine, but the *capability* behind it is load-bearing for future AI-authoring work. Do NOT conflate "remove the dev tools page" with "remove the staging registry"; if anything this wants RELOCATING to a proper home (a future-ADR concern), not deletion.

    The classification itself is a phase-6.5 step-1 task; recorded now (observed from the live page) so the three-bucket structure isn't re-derived later. **The load-bearing warning on the staging registry is the most important part** — deleting it lumped in with "dev tools cleanup" would be exactly the LB-1-class mistake the phased retirement exists to prevent.
25. **Tile detail_endpoint resolution during ADR 0004.** Quick HC report tile `detail_endpoint`s for `client_growth` and `capacity_license` currently resolve to dev routes. ADR 0004's chart section type (phase 4) must account for this: either repoint `detail_endpoint` to a new in-workspace chart view, or drop `detail_endpoint`s from these tiles. Decision point during phase 4 design. Affects: `quickhc/registry.py:248,282`; `quickhc/report_service._detail_url_for_tile()`; `templates/quick_hc_report.html:366,380,411`.
26. **ADR 0004 text fixes (queued for Proposed→Accepted).** Two wording inaccuracies surfaced during phase 1; per the established convention they are NOT amended mid-implementation — fix them when ADR 0004 changes status from Proposed to Accepted (end of all phases):
    - **Uniqueness-constraint phrasing.** §"Subject versioning" says the catalog's uniqueness constraint is "on `subject_id` (unchanged)." The actual constraint (ADR 0003 migration 0003) is `UNIQUE (subject_id, version)` — an integer `version` column plus the new `_vN`-suffix-on-subject_id convention. The two don't conflict (`capacity_license_v2` is a distinct `subject_id` row with its own `version=1`), so this is wording, not a design problem. Also worth a sentence then on the two-versioning-mechanisms coexistence.
    - **CEL example expression #2.** §"Formula language" example #2 uses field-projection on a filter result (`.filter(...).used_capacity`) which is not valid CEL. Working form is `.filter(...).map(r, r.used_capacity)`. Implementation tested with the working form per phase 1 finding #2; fix the ADR example at the Proposed→Accepted transition.
    - **Card carries an evaluative face (phase 4).** §"The three faces" line 31 says "an identity card carries only semantic and presentational." The phase-4 steering decision is that the compliance engine judges every card, so a `CardSection` carries a section-level verdict (`severity` + `verdict_chain`) too. Update the ADR text at the Proposed→Accepted transition to reflect that cards have an evaluative face.
27. **Source tile contract unification.** Define the target contract: every subject's source tile shows (a) a data-acquisition timestamp, (b) a source identifier (Endpoint + Host for REST, filename for file imports), consistently formatted and labeled. Current implementation violates this across LS Reports Plus, LS file-import paths, BJS Reports Plus, the environment subject, and possibly others — different field labels, field combinations, and empty states. The label naming inconsistency ("Last collected" / "Last Imported" / "Last Generated") falls under this entry — pick one term and apply consistently. Phases 5–7 fix this for the three regressed subjects as they migrate to canonical; the LS bespoke path and the file-import paths each need their own pass. Surfaced during phase 1 browser verification — phase 1 didn't cause it and didn't fix it.
28. **Legacy workspace pages investigation and retirement.** `/quick-hc/commcell` duplicates what `/quick-hc#subject=environment` shows on the canonical workspace; `/quick-hc/report` was flagged as needing "major rework" — possibly the same legacy-duplicate pattern; other legacy workspace pages may exist. Investigation needed before retirement: confirm which pages are genuine legacy duplicates of canonical surfaces; confirm what links to each (navigation entries, hardcoded URLs, redirects); identify any tile `detail_endpoint`s pointing at them (LB-1-style dependency). Natural retirement window: alongside or shortly after phase 6.5 (dev tools retirement), since the legacy pages share a navigation cluster with dev tools and the same architectural pattern — possibly fold into 6.5 if the work is small, or its own phase 6.6. A first read-only enumeration was run at the close of phase 1 (see the phase-1 closing session report / chat); it does not change phase 2.
29. **Active customer/project selector placement.** The `ACTIVE <customer>/<project>` selector floats top-right and crowds adjacent controls. Integrate it into the left-hand nav structure rather than floating in the content area's top-right corner. Pre-existing chrome issue, not tied to any phase. Part of the broader workspace navigation/chrome consolidation theme (cf. backlog #28 legacy pages). Address as a focused UI task when convenient; not blocking any ADR 0004 phase. Surfaced during phase 2 browser verification.
30. **[CLOSED — phase 3, commit `ce88cac`] `get_canonical_schema` drift — derive from models + drift guard.** Done: `get_canonical_schema` now derives from `CanonicalArtifact.model_json_schema()` (drift structurally impossible) and a non-negotiable drift-guard test was added (verified to fire on a stale hand-schema). Original finding for the record: The MCP server's `get_canonical_schema` (`cvhealthcheck/mcp/server.py::_canonical_schema`) is a hand-maintained dict that has drifted two phases behind the live `CanonicalArtifact` models: missing `template_version` (phase 1), the entire rich `MetricItem` surface (nullable `value`, `derived`, `severity`, `verdict_chain`), `MetricSection.render_mode`, `VerdictEntry`, and (pre-existing) `vendor_key`/`vendor_id` and `commcell_id`/`commcell_name`. Meanwhile `save_staged_artifact` validates against the live model, so the schema advertises a loose/stale shape that the validator then rejects — the root cause of the May-24 "Input should be an object" errors. Fix: derive `get_canonical_schema` from `CanonicalArtifact.model_json_schema()` so it cannot drift; OR if a curated hand-shape is kept for AI readability, update it for phases 1/2 AND add a drift-guard test that fails loudly when live-model fields aren't described in the schema. **The drift guard is the non-negotiable part** — it's the loud-fail mechanism missing from the one tool most central to ADR 0005 (AI authoring). Phase 3 already touches the section vocabulary; reconcile the schema there.
31. **[CLOSED — phase 3, commit `ce88cac`] `valid_section_types` vs `SUPPORTED_SECTION_TYPES` reconciliation.** Done: the MCP schema's `supported_section_types` is now sourced from the runtime `SUPPORTED_SECTION_TYPES` (which now includes `chart`), so they can't diverge; the drift guard asserts `SUPPORTED_SECTION_TYPES ⊆` the modelled section types. Original finding: the hand-schema advertised `chart` while the runtime rejected it — over-promising until phase 3 landed `chart`.
32. **MCP import-time `run_migrations()` silent DB creation (latent, low priority).** `get_db` resolves `app.db` via `parents[3]`/`parents[4]` from source location — correct under the current editable install. But `run_migrations()` runs at import (`mcp/server.py:59`), so under a NON-editable install (e.g. if the MCP is ever packaged for distribution), `parents[3]` would point into site-packages and silently create an empty `app.db` at the wrong path rather than failing loudly — serving an empty catalog. Not active today. Add a loud-fail guard (assert the resolved DB path is the expected project `data/` dir, or refuse to auto-create) IF the MCP is ever packaged. Revisit only at packaging time.
33. **MCP `list_subjects` exposes the `_test` subjects (decision, minor).** MCP `list_subjects` has no `is_test` filter, so it returns the internal `_metric_test` / `_chart_test` / `_card_test` subjects, while the web sidebar hides them behind the client-side toggle (and now groups them in their own chapter). Decide: expose-but-flag (mark `is_test` in the MCP output so an AI consumer knows they're internal), or filter them out like the web app. Lean expose-but-flag since the MCP is a dev/AI tool, but make the divergence intentional rather than accidental. Resolve whenever convenient.

### ADR 0004 implementation notes carried forward

- **The three-layer model (state explicitly in the ADR/docs).** Design decisions repeatedly hinge on which layer a concern belongs to, so name the layers: **catalog** (durable, shared — defines what a thing IS; a section's three faces, including presentation *config as declaration*, live here — NOT a runtime settings UI); **engagement** (per-customer, per-run, ephemeral — what the consultant DOES: report-inclusion via the per-section checkbox, description overrides; shared across all section types); **render** (dumb — consumes catalog + engagement, draws, decides nothing). Phase-4 decisions that hinged on this: card status → catalog/evaluative; card config → catalog declaration (no per-card runtime settings UI); report-inclusion → engagement (not a card feature). Stating it explicitly prevents re-deriving it each phase. Queue for the ADR/docs (alongside the #26 text fixes, or as its own architectural note).
- **Severity enum is fixed at five values — one enum across the evaluative face.** `critical` (breached hard limit) / `warning` (approaching threshold) / `info` (neutral notation, no judgment) / `good` (active positive judgment) / `muted` (suppressed / n-a, e.g. sentinels). Section-level header badge = the worst item by ordering `critical > warning > info > good` (muted outside the ordering). Display labels like "Healthy" are labels for `good`, NOT new codes — do not add synonyms. Phase 8's full evaluative face uses these same five values.
- **`extraction_instructions` is accumulating concepts — watch for catch-all drift.** It now holds, layered in by ADR 0004: the original extraction keys (report_id, column_map, …), phase 1's `conformance` block, and the per-section-type three-face blocks `metric` (phase 2) / `chart` (phase 3) / `card` (phase 4), plus `fixture_path` and `output_as`. Four+ concepts now live there. If the catalog-vs-code boundary review happens, this is the candidate for decomposing `extraction_instructions` into first-class columns/tables. A visibility note, not an action now.
- **Phase 6 (Client Growth migration): verify the all-zero monthly data.** Client Growth's legacy table renders 13 months all showing Added 0 / Removed 0 / Total 0. When phase 6 migrates this subject, confirm whether these zeros are real (a quiet lab environment) or a legacy extraction artifact. If the latter, the migration is the natural place to fix it. Observed during phase 2 browser verification; not a phase 2 issue.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section.

### Existing tooling worth surveying for ADR 0003

- `src/cvhealthcheck/auth/commvault_auth.py` — Flask session-backed CommCell token management.
- `src/cvhealthcheck/api_client.py` — Commvault API client.
- `src/cvhealthcheck/reportsplus/client.py` — Reports Plus client used by SA/LS collect paths.
- `src/cvhealthcheck/extractors/rest.py` — generic RESTExtractor used by `/quick-hc/<subject_id>/collect`.
- `src/cvhealthcheck/security_assessment/service.py::SecurityAssessmentService.collect_from_rest` and `license_summary/service.py::LicenseSummaryService.collect_from_rest` — dedicated REST collection per system subject.

ADR 0003 sits at the intersection of all of these. Its job is to design the unifying story — not implement it yet.

### Priority-ordered backlog

1. **ADR 0003 — REST extractor with credentials.** Design first, no implementation. Single recommended next action above repeats this; listed here as #1 for completeness. The data flow audit (`docs/data_flow_audit.md`) was refreshed this session as a prerequisite — the ADR 0003 design conversation now has a fresh post-ADR-0002 baseline to read against.
2. **AI import workstream — staging UI for proposal review, REST extractor with credentials, compliance rules.** Larger scope; ADR 0002's implementation likely surfaced architectural choices that simplify some of this. Auth/extractor design will overlap with ADR 0003.
3. **CommCell-discovery flow for customer creation.** Falls out of ADR 0003's auth design — same plumbing, different destination (customer record's identity fields vs project's working state).
4. **Report-provenance verification.** When an HTML/CSV report is imported, check the embedded CommCell identity matches the active customer's stored CommCell identity. Catches "wrong customer's report uploaded by accident" mistakes.
5. **Read-only per-finalization view.** Deferred from phase 5 step 5. `GET /customers/<c>/projects/<p>/finalizations/<n>` would let consultants see a delivered report's contents alongside the current working state. Needs either an ArtifactStore read-mode that points at `finalized/<n>/` paths, or a sibling helper. Architectural decision left to that session.
6. **Customer panel on the right side of `quick_hc.html`.** Raised previously, not acted on. A right-side panel surfacing the active customer's context (customer name, CommCell hostname/ID, active project metadata) alongside the existing subject workspace. Pairs with the active-project selector at the top.
7. **`shared.py` split.** `src/cvhealthcheck/web/routes/shared.py` is a 413-line god-module with 60+ imports spanning auth, ReportsPlus, metrics, license_summary, security_assessment. Flagged in the 2026-05-20 review; still open. Split by concern.
8. **`SecurityAssessmentArtifactRegistry` rename.** Class at `src/cvhealthcheck/security_assessment/registry.py` is SA-specific in name but the registry pattern is also used by License Summary. Decide: rename to a generic `ArtifactRegistry` and unify, or clarify the per-domain naming as intentional. Flagged in the 2026-05-20 review.
9. **Hardcoded URLs in `report_service.py`.** Partial work landed (CHANGELOG 2026-05-20 says detail URLs were replaced with `TileDefinition.detail_endpoint` resolution through `url_for()`). Audit whether any hardcoded URLs remain.
10. **Left-nav structural review.** The sidebar has accumulated items (Overview, Reports, Customers, Settings, Staging, plus SUBJECTS). Grouping or visual hierarchy will help at some point.
11. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL through `get_db()` AND `db/customers.py`'s module-level helpers — phase 3 surprise. Pick one, retire the other. Same review applies to projects.
12. **Template inheritance cleanup.** Some workspace templates extend `base.html`, others are self-contained — phase 4 surprise. Active-project selector is included in both ways, which is awkward. Consolidate.
13. **`engagements` table cleanup.** Empty since migration 0001; predates ADR 0002. No production writes. Retire if no future use surfaces (ADR 0002 explicitly replaced this concept with `projects`).
14. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). Globally scoped today (Option A read fallback). Needs a project-scoping story eventually.
15. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3 — 200+ raw extraction files accumulating with no retention policy.
16. **Audit Section 6 #2, #5, #6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section (still describes the pre-canonical artifact paths).

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **ADR 0002 is fully implemented.** Customers and projects are CRUD-managed through the UI under `/customers/...`. Each project has its own working state under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. Finalize captures an immutable snapshot under `.../finalized/<n>/<subject>/`. Reload restores the latest snapshot.
- **Finalize is the only code path that writes under `finalized/`.** `ArtifactStore` (the production write path used by every other artifact-saving code path) writes only to `working/`. This is the application-layer immutability invariant from ADR 0002.
- **Finalize/reload core logic lives in `src/cvhealthcheck/db/finalizations.py`.** Three functions: `finalize_project`, `reload_latest_finalization`, `diff_working_vs_latest`. Used by both the routes (`projects_finalize`, `projects_reload`) and by future automation (e.g. a CLI command if added later).
- **Finalize captures `ticket_reference` and `assigned_consultant` at the moment of finalization** and writes them into the `finalizations` row. Editing the project row later doesn't change earlier finalizations — this is the auditable history.
- **Diff is content-based on `latest.json`.** Timestamped snapshot files (the append-only history) are ignored. A no-op save (writing the same content) doesn't trigger a false "modified" signal.
- **Project deletion is blocked once any finalization exists.** Phase 4 introduced the guard with a direct-INSERT test fixture; phase 5 verified it still works with finalizations created via the new UI.
- **`init_db()` and `schema.sql` are gone.** `run_migrations()` is the sole bootstrap path.
- **ADR 0001 source-building fork is orthogonal.** `_legacy_builders` continue to serve their subjects globally; ADR 0002 changed *where* canonical artifacts live, not *how* legacy tile data is shaped.
- **Active-project session.** Lives in the Flask session as `session['active_project'] = {'customer_id': ..., 'project_id': ...}`. The active-project selector partial at `templates/partials/active_project_selector.html` is included on every workspace page (via `base.html` and the self-contained top-level templates).
- **ADR 0003 is implemented (with LS caveat).** Phase 1 extended catalog schema. Phase 2 built the GET-only `RESTExtractor`. Phase 3 made auth customer-aware. The interstitial fix and protocol amendment landed the GET-only protocol. **Phase 4 migrated Security Assessment** — extractor gained `column_map` + `status_to_severity` + HTML stripping; migration 0007 seeded six SA catalog rows. **Phase 5 was the cleanup pass; LS retained bespoke** because LS's report 206 requires runtime parameter-substitution-from-prior-results, page-aware GUID resolution, and value-formula transforms that the catalog model doesn't express. Four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment) use the generic catalog-driven path; LS continues through `LicenseSummaryService.collect_from_rest`.
- **REST extractor catalog keys honored**: `report_id`, `dataset_name`, `dataset_guid` (cache hint, used when the live name→guid map doesn't have the name), `fields`, `orderby`, `limit`, `parameters`, `timestamp_fields`, `timestamp_format`, `null_values`, **`column_map`** (rename source keys → canonical, drop the rest), **`status_to_severity`** (when output_as=="findings", set row.severity from status mapping), `output_as` (`"table"` / `"findings"` / `"card"`). Under `output_as: "findings"`, the extractor strips embedded HTML via `html.parser`. `fields` and `orderby` are only sent to the server when a cacheId is present — the lab's CacheDB rejects them without one.
- **Catalog-driven SA reference**: migration 0007 seeded six rows under `security_assessment.rest` with `report_id="336"` plus column_map renaming Parameter/Status/Remarks/Action to canonical lowercase + status_to_severity mapping `1_Good→good` / `2_Info→info` / `3_Warning→warning` / `4_Critical→critical` + `output_as: "findings"`. Use as a template for any future catalog-driven REST subjects.
- **Bespoke LS modules retained** (deliberately, per ADR 0003 amendment): `license_summary/collect_rest.py`, `license_summary/service.py::collect_from_rest`, `adapters/license_summary.py`, `normalize_license_summary_rest_extraction`, `persist_license_summary_artifact`, and `reportsplus/extract_report.py` (LS is its last caller). The LS UI continues to work through this path. Backlog item #8 records what extractor extensions would be needed to migrate LS in a future expansion.
- **`backup_job_summary` collects but produces 0 rows.** The lab's "Job details" dataset on report 194 is genuinely empty (probe: `GET /datasets/a30bd278-.../data?format=object` returns HTTP 200 with `totalRecordCount: 0, failures: {}`). Name resolution succeeds; the dataset just has no jobs.
- **Default customer's CommCell binding is configured.** `commcell_hostname = https://192.168.182.129:4433`, `commcell_id = SMOKE-TEST-CS` — set during phase 3 verification, useful for any future REST-path probing.
- **`set_current_token` signature.** Required positional arg `customer_id` after `token`. Two production callsites (`/login`, `/api/login`). Tests that wrote directly to `session[SESSION_TOKEN_KEY]` still work for the loose `is_authenticated()` gate; customer-aware routes use `is_authenticated_for(customer_id)`.
- **`is_authenticated()` vs `is_authenticated_for(customer_id)`** — the first is loose (any token in session); the second is strict (token AND bound customer matches). `login_required` decorator uses the loose check; the catalog-driven collect handler uses the strict check.
- **Dead code retired in phase 5**: `CommvaultSession.init_report` (no callers since the GET-only protocol amendment), `REPORT_DEFINITIONS` dict + `reportsplus/report_definitions.py` (orphan since phase 2), `_read_commcell_provenance` (zero callers since phase 3).
- **Still-dead code waiting on a cleanup pass**: `cvhealthcheck.reportsplus.checklist` (only callers were the SA bespoke modules; LS doesn't use it). Backlog item #21. Small post-ADR cleanup.
- **`output_as: "card"`** is implemented in the extractor (trims `rows[:1]`) but not exercised in production today (no catalog rows declare it). If a future subject needs card rendering, the workspace renderer needs either a `CardSection` artifact type or a template branch — neither shipped with ADR 0003.
- **Same-report_id-per-subject rule** is a runtime check in `_resolve_single_report_id`. Not a DB constraint. Reports offending section_ids in the error message on mismatch.

---

## Session workflow disciplines

These apply to **every session**, not just ADR implementations or
multi-step refactors. Treat them as project workflow rules, not
suggestions.

### Push to GitHub regularly

- **Push to `origin` after each major task completes.** A "major task"
  is: a phase of an ADR implementation, an interstitial cleanup, an
  ADR write-up, a multi-commit refactor, a documentation pass that
  produces multiple commits.
- **Push at the end of every session**, regardless of whether a major
  task just completed. The session-end push is the *last* action
  before stopping — after updating HANDOVER's last-commit pointer, the
  very next thing to do is `git push origin <branch>`.
- This is the final step of the "single recommended next action"
  pointer. Don't treat it as optional.

**Why:** local-only commits are one disk failure away from gone. This
discipline was added after a session discovered 59 local commits had
accumulated unpushed — the work was only on the dev machine and
couldn't be pulled to a second machine. Pushing regularly puts the
commits behind GitHub's durability guarantees and makes the branch
available to any other machine.

If a push fails (auth issue, network), report it and stop — don't
push-force or work around it. Pushes should be append-only and
no-rebase under normal conditions.

### Verify before write

See `docs/PATTERNS.md` — HANDOVER claims are starting points, not
contracts. Grep first, then act.

### STOP-and-report

Many session briefs say "if X happens, STOP and report." Take that
literally — when a step surfaces a design question not covered by
the brief, ask the user rather than fabricating an answer. Better to
leave a gap than to document the wrong thing.

---

## Where work happens — Claude Code vs Claude.ai

This project's sessions run in two different tools. Knowing which is
which saves a fresh chat from trying work it can't do.

### Claude Code (agentic CLI, filesystem access)

Runs every session that touches the codebase. Every implementation
session in this project's history has been Claude Code. Use it for:

- ADR implementation phases
- Audit refreshes and documentation passes that verify against code
- Schema migrations
- Refactors and cleanups
- Anything that needs to read source files, run tests, commit, or push

If the work involves the filesystem at all, it belongs here.

### Claude.ai (chat interface, no filesystem)

Handles work that is pure conversation and prose. Use it for:

- Design conversations and strategic decisions
- Prompt drafting for Claude Code sessions
- Meta-discussions about the project's direction
- ADR drafting *when* the ADR doesn't need verification against
  current code (if it does, Claude Code is faster — it can grep
  while drafting)

### The handoff pattern

The user is the bridge between the two tools:

1. Claude.ai conversation produces a session brief (prompt) and any
   strategic decisions
2. User runs the brief in Claude Code at the dev machine
3. Claude Code executes, commits, pushes, reports back
4. User pastes the report into the next Claude.ai conversation if
   the work continues strategically

### ADR design sessions: the survey-then-steer pattern

ADR drafting looks like prose work, but the prose's value depends
on accurate reading of the codebase. So ADR design sessions follow
this four-step pattern:

1. **Claude Code produces a survey report.** Reads the relevant
   files (existing services, schemas, related ADRs), summarizes
   findings, surfaces the design forks. No design work, no
   drafting — just grounding.
2. **User pastes the survey report into a fresh Claude.ai chat.**
3. **Claude.ai does the design conversation.** Surfaces forks
   from the survey, takes steers from the user, drafts the ADR.
4. **If the draft needs verification against code**, another
   Claude Code session handles that. Often this is the start of
   the implementation phases rather than a separate verification
   pass.

The survey is filesystem work even though it produces prose,
because guessing at file contents from a chat without filesystem
access produces unreliable design conversations. The pattern was
adopted after a Claude.ai chat drafted a Claude Code brief that
asserted "the diagrams are SVG embedded in the markdown" — the
file had no diagrams, and the wasted round trip motivated this
discipline.

**Operational note on survey persistence.** Future ADR surveys
should write their plan-file deliverable to
`/home/michiel/.claude/plans/` proactively before `ExitPlanMode`,
so the post-survey commit task has a persistent source. The
ADR 0004 survey had to be extracted from the chat transcript
retroactively because no plan file was written — it worked but
relied on transcript JSONL access that may not always be the
right tool. Write the plan file as a first action of the survey
session, then update it as findings accumulate, then exit plan
mode with the file present.

**Operational note on WORKFLOW.md.** WORKFLOW.md committed at the
repo root. Living document describing the AI-assisted architecture
workflow. Sections 14 (lessons learned) and 15 (retrospectives)
will need revisiting after the first methodology retrospective
lands. The "established vs emerging practices" split in section 10
should be promoted item-by-item as emerging practices stabilize.

### Signal that a session needs Claude Code

Any of these in the brief means filesystem access is required:

- "read `<file>`", "update `<file>`", "edit `<file>`"
- "run the tests", "run pytest", "confirm test count"
- "commit", "push", "update CHANGELOG", "update HANDOVER"
- "verify against current code", "grep for", "check whether"
- "the audit", "the schema", "the migrations"

A Claude.ai chat seeing these signals should respond: *"this work
needs Claude Code — here's the prompt"*, then draft the prompt rather
than attempting the work.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 691 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001-0004 + phase-plan + survey + README
```
