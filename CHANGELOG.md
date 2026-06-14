# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — sections for **Added / Changed / Fixed / Removed** where they apply, plus a short prose **Notes** section per entry for findings, root causes, architectural decisions, and gotchas worth preserving.

This file is append-only. Past entries are never deleted or rewritten — corrections are made by adding a new entry.

See `HANDOVER.md` for what to do next. See `README.md` for what the project is.

---

## 2026-06-14 (feat — ADR-0015 D4a: rule ownership/classification axis (INERT))

**Branch:** `main`. First D4 slice: the rules registry gains an ownership axis separating universal **policy** rules from **customer_assertion** (customer/person/org-specific) rules. **INERT** — classification only; no firing/binding/override change (like the project_id stamp was inert). Full suite 1318 passed.

### STEP 0 (read-only classification, 2026-06-14) — binary CLEAN
All 16 live rules classified; no rule was "genuinely neither" (no third value needed).
- **policy (10):** audit_critical_retention_warning, capacity_utilisation, metrics_healthcheck_service_disabled, sg_empty_group, spcj_aux_copy_pending, spcj_data_not_available, spcj_job_failed, spcj_job_killed, spcj_unencrypted_job, users_never_logged_in.
- **customer_assertion (6):** clients_company1_warning, clients_company2_critical, michiel_account_enabled, sg_rommelgroep_company_1, users_michiel_enabled_critical, and **sg_naming_convention** (the one judgment call — a `GRP_` org naming standard, i.e. a customer-specific policy, classified customer_assertion; flagged for review, a one-line flip if read as policy).

### Added
- **Migration `0036_rule_ownership_axis.sql`:** `ALTER TABLE rules ADD COLUMN rule_class TEXT NOT NULL DEFAULT 'policy' CHECK (rule_class IN ('policy','customer_assertion'))` + backfill UPDATE of the 6 customer_assertion rule_ids (policy rules take the column default — so no customer_assertion silently rides the default). Backfill no-ops where a rule is absent (rules are runtime-authored, not migration-seeded).
- **`db/rules.py`:** `RULE_CLASSES` / `DEFAULT_RULE_CLASS`; `save_rule(…, rule_class=None)` — validates against the vocabulary, **preserves** the existing class on a body re-save (mirrors `created_by`), defaults `policy` for new rules; `list_rules` and the MCP `save_rule` output **expose** `rule_class`. Stored as a COLUMN, never in `definition_json` — so the evaluator never sees it (INERT / firing-safe).

### Tests — `tests/test_rule_ownership_axis_adr0015.py` (+11, tests-first)
vocabulary; new rule defaults policy; seeded `capacity_utilisation` is policy; CHECK + `save_rule` reject an invalid class; explicit customer_assertion stored; class preserved on re-save; `list_rules` exposes it; `rule_class` absent from the definition body (firing-safe); bind/delete back-compat; migration backfills exactly the Step-0 set. Migration count 35→36. Existing rule/eval/MCP tests green.

### Non-goals (explicit) + the D4b flag
NO firing change, NO row_rules move, NO bindings table, NO profile object (that is **D4b**), NO SPCJ resolved-id/parameter portability or §119 (that is **D4c** — needs a second live-environment collect). **D4b flag:** default-policy is safe ONLY while the axis is inert. When D4b makes the axis scope firing, it must decide whether scoping should REQUIRE explicit classification rather than defaulting universal — a customer_assertion mis-defaulted to `policy` would otherwise fire against every customer.

## 2026-06-14 (docs — Context Integrity read-isolation gate CLOSED (browser-verified); D4 unblocked; renderer backlog)

Browser verify passed — docs only, no code change.

### Context Integrity read-isolation gate: **CLOSED**
Evidence (browser-verified 2026-06-14):
- No-context session → honest empty / no-active-context state.
- Canonical APIs return `active_context=false`, `artifact=null` — no Default data rendered.
- HomeLab (`test_customer_1`) selected → renders only HomeLab scoped data.
- `Test_Customer_2` selected → renders only TC2 scoped data.
- A TC2 **License Summary HTML import** landed under the active TC2 context; the import mechanism scopes to the selected customer/project, NOT to anything baked into the file.
- **Two-customer cross-isolation is therefore considered proven for the current lab.**
- **D4 report-profile / bindings-ownership boundary check is now UNBLOCKED** (the next read-only investigation).

### Verification-verdict behavior (recorded, correct)
The LS HTML import produced an **attested / trusted-not-verified** identity verdict:
- the source carries no comparable CommCell identity;
- the guard did NOT block the import;
- the banner is correct for this source type — **trusted because the user imported it into the selected context, not verified from embedded source identity**.
- This is DISTINCT from the CommServ endpoint mismatch case (a per-source identifier-namespace issue — see the Fix-4 backlog).

### Caveats / non-closures (not overclaimed)
- **ADR-0015 §119 cross-environment id-variance: OPEN** — a template-portability / source-identifier question requiring a second live-environment **collect**, NOT a customer read-isolation blocker.
- **active-context → app.db: DEFERRED (not cancelled)** — the narrow read-side enforcement closed the current gate without requiring that migration.
- **Fix-4 per-source CommCell identifier precision: BACKLOG** — CommServ endpoint may report internal `commCellId=2` while the customer record declares licensed CCID `337f`. Logged previously; not blocking this gate.

### New backlog — generic table renderer value coercion (deferred / cosmetic)
Some generic table-render paths display structured values such as `{'unit': None, 'value': 100}` raw (observed in License Summary capacity/license rendering). Desired follow-up: generic display coercion for `{value, unit}` value objects → user-facing scalar text instead of a Python/JSON dict. Cosmetic; does NOT block Context Integrity, D4, or data isolation. Likely the generic complement to bespoke License Summary formatting.

### Final state
- Context Integrity read-isolation gate: **CLOSED**.
- D4 bindings/profile ownership boundary check: **UNBLOCKED** (next read-only investigation).
- Fix-4 CCID-form mismatch: backlog, not blocking.
- Generic table renderer raw `{unit,value}`: backlog, not blocking.

## 2026-06-14 (docs/backlog — Fix-4 follow-up: per-source CommCell identifier precision)

Backlog item only — NO code change, NO Fix-4 edit, NO banner change in this commit.

**Fix-4 follow-up: per-source CommCell identifier precision.** The Fix-4
identity/provenance guard false-mismatches on the CommServ environment endpoint:
`GET /commandcenter/api/CommServ` reports the internal `commCellId` (`2`), while
the customer record may declare the licensed CCID (`337f`). These are different
identifier namespaces for the same CommCell — not necessarily wrong-customer data.

- **Observed live 2026-06-14:** HomeLab reaches cs01 via gw02; the CommServ
  endpoint reports `commCellId=2`; HomeLab declares `337f`; the guard raised a
  mismatch banner.
- **Follow-up:** the per-source CCID resolver must distinguish identifier *type*
  (licensed CCID vs internal `commCellId` vs CommServe GUID/name), must NOT treat
  the CommServ endpoint's internal `commCellId` as the licensed-CCID comparison
  key, and the banner must NOT claim "possible wrong-customer data" for a known
  identifier-namespace difference.
- **Re-opens** the Fix-4 session's "single CCID field" conclusion — different
  Commvault surfaces expose different CommCell identifier forms.
- Backlog/follow-up; does **NOT** block Context Integrity read-isolation closure.

## 2026-06-14 (feat(context) — Context Integrity READ-side enforced; isolation gate closed pending browser verify)

**Branch:** `main`. The D5 complement: a no-context web READ no longer silently renders the Default customer's scoped artifacts — it returns an honest no-active-context state. Closes the last open half of the Customer/Project Context Integrity gate (writes were already enforced by D5). Full suite 1307 passed.

### STEP 0 (recorded) — `registry/execution.py` is NOT a live write gap
`build_and_save_artifact` (which saves via `_active_project_store()`, the read fallback) has **zero production callers** — only `registry/__init__` re-exports it and `tests/test_registry_execution.py` calls it. Live collection writes go through the dispatcher → `ArtifactStore(*require_active_context())` and the LS/SA `_require_project_store` (D5). So its `_active_project_store()` default is unreachable in production — not a write-to-Default-without-context gap. Left unchanged (out of scope).

### Changed — read-context resolution gains no-fallback opt-out
- **`web/active_project.py`:** `get_active_project` / `get_active_customer` / `make_active_project_store` gain `allow_default: bool = True`. With `allow_default=False` an absent explicit selection raises `NoExplicitContextError` instead of resolving the Default customer. The legacy fallback survives only for the opted-in non-request callers (CLI, tests, MCP/staging).
- **Live web reads pass `allow_default=False`:** `subject_data_service._canonical_store` (workspace tiles), `license_summary`/`security_assessment` `_active_project_store` (the canonical API). `_load_from_canonical_store` catches `NoExplicitContextError` → honest not-collected tile (never an error log).
- **No-context behavior, one shape both surfaces:** `GET /quick-hc` renders the not-collected workspace + an "No customer or project selected" notice + `initial_data["active_context"]=False`; the canonical API GETs return a structured `{"active_context": false, "artifact": null, "message": …}` at **HTTP 200** (not 404 — "nothing selected" is a normal state).
- Explicit selection preserved: an explicitly-selected customer reads only its own scoped store; no read returns Default unless the caller opts in.

### Tests — `tests/test_context_read_isolation.py` (+6, tests-first)
no-context resolver raises (project/customer/store); opt-in still falls back; a Default-customer artifact is NOT rendered without explicit selection; explicit selection renders only that customer's store (no cross-leak); canonical API with no session → structured no-context 200 (LS + SA). Two Fix-2 tests that asserted the *old* fallback-renders-Default behavior were adapted to render via explicit selection (the new contract). D5 write tests stay green.

### Gate status
- **Two-customer cross-isolation: PASSED** (2026-06-14 read-only audit) — the scary half (A's data under B) was already structurally + physically impossible.
- **No-context → Default display hazard: CLOSED** by this slice (bounded-to-Default fallback removed from live reads).
- **Context Integrity (customer/project isolation) gate: CLOSED pending Michiel's browser verify** (no-context → empty state on workspace + canonical APIs; select TC1 → TC1; select TC2 → TC2). On pass, **D4 (report-profile / bindings ownership) unblocks**.
- **Separate, still open:** ADR-0015 §119 cross-environment id-variance — a *template-portability* question needing a live two-environment **collect**, NOT a customer-isolation blocker. Also not done (deferred, named): moving active context out of the Flask session into `app.db` (this slice proved the narrower read-fix sufficient without it).

## 2026-06-14 (feat — ADR-0015 D2a: recipe immutability guard makes approval truthful)

**Branch:** `main`. A post-approval write to a section's `extraction_instructions` may now change ONLY `evaluative.row_rules`; the extraction recipe (and every other `evaluative` subkey) is locked at approval. Interim realization of D2 ahead of D4 (bindings stay co-located but become un-mutable-except-row_rules). No bindings table, no migration, no multi-version scoping change. Full suite 1301 passed.

### EXCEPTION CHECK (recorded)
`row_rules` is the ONLY `evaluative` subkey mutated at runtime post-approval — confirmed: the only runtime writes to `subject_section_sources` are `bind_rule` (rules.py) and `delete_rule`, both touching only `evaluative.row_rules`; the other subkeys (`rules` for card/metric, `scope`, `vendor`, `threshold`) are read-only at runtime (written solely by migrations / `create_subject_from_proposal`). So the allowlist is correct and does not break card/metric rules.

### Added (`db/rules.py`)
- `RecipeImmutabilityError` + `assert_recipe_unchanged(old, new)` — an **allowlist** guard: passes iff `(NEW − evaluative.row_rules)` structurally equals `(OLD − evaluative.row_rules)`. Compares PARSED structures (each arg may be a raw JSON string or a dict), so key reordering never trips it; an emptied `evaluative` is treated as absent (first-bind case); a recipe key nobody enumerated is protected by default.
- `_write_section_instructions(db, row_id, old, new)` — guarded UPDATE; `bind_rule`/`delete_rule` now write through it.

### Preserved (explicit non-goals)
- The authoring loop: `save_rule(bind=…)` adds/removes `row_rules` refs on an active subject; `delete_rule` strips refs — both still one-call, no version bump.
- **Multi-version write behavior UNCHANGED** — `bind_rule` still writes every matching section row across versions (incl. superseded); the guard is version-agnostic. Asserted explicitly in a test so a future scoping change is loud.

### Tests — `tests/test_recipe_immutability_guard_adr0015.py` (+12, tests-first)
guard allows row_rules add/change/empty; rejects a recipe-key delta, a new recipe key, and another evaluative subkey delta; compares parsed-not-raw; treats empty/absent evaluative as equal; bind/delete round-trip through the guard preserving the recipe; idempotent rebind; and the multi-version write is asserted unchanged (writes both versions). Existing rule tests (`test_bind_version_scoping`, `test_delete_rule_reaping`, `test_rules_mcp_adr0010`, …) stay green.

### Docs
ADR-0015 gains **D2a** (recipe locked at approval; evaluative bindings an intentionally-mutable layer, co-located now, physically separated by D4; not a bindings-immutability decision; no multi-version scoping change).

## 2026-06-14 (docs — correct the strategic-inflection overclaim: extraction proven, collection not)

**Branch:** `main`. Docs only — sharpen the ROADMAP Strategic Inflection note (and the HANDOVER title) that previously read as "platform proven end-to-end."

- **`ROADMAP.md` Strategic Inflection (scope-corrected):** LS proved declarative
  **EXTRACTION** for report-shaped, already-obtained data (the upload path,
  file → recipe → canonical, no bespoke parser). It did NOT prove declarative
  **COLLECTION** (call/page/auth/correlate/merge — LS REST collect stays bespoke)
  nor declarative extraction for **non-table REST shapes** (nested-by-key,
  typed-rows needing pivot — the `rest`/`rest_command_center_api`/
  `reportsplus_dataset` vocabulary exists but no live subject has proven it
  end-to-end; pivot/partition is open). **The next architectural test is a
  REST-primary subject via `rest_command_center_api` / `reportsplus_dataset` with
  NO bespoke adapter** — probes easiest-first: CommCell Details (card), then a
  list/typed-row REST subject (Capacity License / Backup Job Summary). Outcome
  decides how much bespoke collector code is needed long-term — still a
  platform-capability test, not yet pure product development.
- **`HANDOVER.md` title** corrected to match (extraction proven, not collection;
  points to the ROADMAP inflection). Current State bullet tightened.

## 2026-06-14 (docs — record the LS upload promotion + boundaries; ADR-0017 Accepted)

**Branch:** `main`. Docs only — no code change.

- **`docs/adr/0017-…md`:** Status **Proposed → Accepted (2026-06-14)** with a
  **Realization** section: the parity target is realized (live CSV/HTML upload
  matches it, browser-verified, parity 738/0; D1–D8 + B1/B2 + titleless-exclusion
  hold). The one criterion met only in part — "bespoke LS path retired" — is
  scoped to the **upload** path; LS REST-collect retirement is a separate slice
  (not a regression of the target). Commit arc recorded.
- **`HANDOVER.md`:** retitled to the LS upload promotion; current state refreshed
  (HEAD `a334b8f`, 1289 tests, parity 738/0); a dedicated "LS upload promotion
  (ADR-0017)" section with the commit arc + boundaries (REST stays bespoke;
  `import_html.py` retained as parity/test reference; `_handle_system_upload`
  dormant; parity option-(b) parked); deferred register + validation count updated.
- **`ROADMAP.md`:** Current State gains the LS declarative-upload milestone; new
  **Strategic Inflection** note (platform proven to represent a real complex
  subject end-to-end → next high-value move is a NEW subject, i.e. product
  development, not platform-building); the "Later" LS-conversion entry updated
  (upload COMPLETE; REST-collect migration / product decision remains; #36 SA-module
  retirement still gated on LS REST).

## 2026-06-14 (refactor — ADR-0017 LS bespoke upload ROUTING cleanup, option (a))

**Branch:** `main`. Browser verify passed (workload-only HTML + CSV both import via the generic route; the workload-only HTML succeeding is proof the generic path is live, since bespoke cannot import it). Retire ONLY the live upload-specific, now-unused, parity-backed bespoke routing. NO parity-harness conversion, NO `import_html.py` deletion, NO REST/shared-code deletion. Full suite 1289 passed; parity 738/0.

### Removed (upload-specific, zero-consumer after the route switch)
- **`service.py` `import_license_summary_upload`** — the live upload orchestrator — and its exclusive helpers `_save_upload` / `_build_saved_filename`, the `ALLOWED_EXTENSIONS` map, and the now-unused imports (`secure_filename`, `secrets`, `BinaryIO`, `datetime/UTC`, `import_license_summary_html`, `import_license_summary_csv`, `import_license_summary_xlsx_recording`). The dead `.xlsx` upload entry point goes with it.
- **`upload_dispatch.py`:** `_LICENSE_SUMMARY_BESPOKE_HANDLER` (the retained revert object), `_license_summary_success`, and the LS-specific imports. `UPLOAD_HANDLERS` stays `{}`; the generic `UploadHandler` / `get_handler` machinery is retained for any future custom-upload subject.
- **Vestigial re-exports:** `web/routes/shared.py` and `license_summary/__init__.py` (`__all__`) — confirmed no real importer.
- **Handler-machinery tests** that exercised the deleted bespoke path: `test_upload_dispatch` (handler-wired case → routes-generically), `test_unified_upload_route` (the `_handle_system_upload` inline success/422/500 + LS no-legacy cases), `test_ls_route_switch` / `test_ls_generic_recipe_migration` handler-retained assertions flipped to "gone".

### Kept (explicitly NOT touched)
- **`import_html.py` + its 4 `parse_license_summary_html` unit tests** (`test_license_summary.py`) — now a pure parity/test reference, not a live upload path.
- The **parity harness** `bespoke_canonical` (still calls the bespoke parsers directly) — parity is unchanged at 738/0.
- **All REST/shared code:** `collect_rest`, `import_csv._artifact_from_rows`, `normalize`, `models`, the adapter, `persist_license_summary_artifact`, `import_license_summary_xlsx_recording` (REST collect is still bespoke and live).
- The generic `UploadHandler` / `get_handler` / `_handle_system_upload` infra (reusable; now dormant + untested — re-pointing to a synthetic handler is a possible follow-up if that machinery is to stay covered).

### Notes — STEP 1 zero-consumer finding
`import_html.py` had an extra consumer beyond the harness — `test_license_summary.py` unit-tests `parse_license_summary_html` directly — so option (a) (keep `import_html.py` alive) was chosen over (b) (drop bespoke + golden fixtures), which would have required deleting those parser tests too. Gates: live LS upload generic+working; `import_html` + its 4 tests still pass; parity 738/0; REST untouched; compile gate still accepts the LS recipe; suite green.

## 2026-06-13 (feat — ADR-0017 LS promotion commit 4b/4: route switch + field align)

**Branch:** `main`. License Summary CSV/HTML upload is SWITCHED to the generic dispatcher (`extract_file → result_to_artifact + D2 enrichment`). NO shared-code or bespoke deletion. Full suite 1293 passed; parity 738/0. **The live LS upload is now the generic path** — Michiel's browser verify is the final gate before any cleanup.

### Changed
- **`upload_dispatch.py`:** `UPLOAD_HANDLERS["license_summary"]` removed → `UPLOAD_HANDLERS == {}`. The handler is RETAINED as `_LICENSE_SUMMARY_BESPOKE_HANDLER` (one-line-revert safety net). With the handler unregistered, `get_handler("license_summary")` returns `None`, so the route falls through to `_unified_dispatcher_upload` AND the UI auto-ships the generic `"file"` upload field (`subject_data_service` derives it from `get_handler`). No new field-name code.

### Added — `tests/test_ls_route_switch.py`
- **ROUTE-IDENTITY PROOF:** the workload-only HTML imports via the GENERIC path — the bespoke `_handle_system_upload` branch is rigged to `pytest.fail` if taken (it isn't), the response carries the generic `"title"` marker, and the saved artifact is a `CanonicalArtifact` (subject `license_summary`, `capacity_licenses` extracted, `commcell_info` present with the **declared** name `DeclaredCS`). "Import succeeded" alone is insufficient — this distinguishes the route.
- CSV imports via the generic path; the upload field is `"file"` (gate 3); the handler is unregistered-but-retained (gate 1); the REST collect path is still wired to `LicenseSummaryService` (gate 9); no shared/bespoke LS code deleted — all still import (gate 10).

### Changed — tests (ripple from unregistering the last handler)
- `UPLOAD_HANDLERS` is now empty: `test_upload_dispatch` updated (handler unregistered, retained object still correct; dict empty). `test_unified_upload_route` handler-machinery tests (`_handle_system_upload` inline success/422/500, no-legacy) re-register `_LICENSE_SUMMARY_BESPOKE_HANDLER` via `monkeypatch.setitem` to exercise the RETAINED handler (the revert path); the field-match test now asserts LS's generic `"file"` field. Commit-1/3 "still bespoke" gates flipped to "switched".

### Notes — post-state
recipe live (1) · D2 seam live (2) · recognition broadened (3) · HTML extraction tolerant + commcell_name threaded (4a) · **routing GENERIC (4b)** · REST untouched · bespoke upload + shared code retained. NON-GOALS held: no REST change, no deletion. Next: **Michiel browser-verifies** (LS tile → import the workload-only HTML + a CSV → both via the generic path, data renders, commcell_info enriched, reg-code masked, route is generic) before any cleanup.

## 2026-06-13 (feat — ADR-0017 LS promotion commit 4a: HTML absent-section non-fatal + commcell_name threading)

**Branch:** `main`. Prerequisite for the route switch (4b). Two changes so the generic dispatcher can import real LS HTML. NO route switch, NO REST change, NO deletion. Full suite 1287 passed.

**Why:** the unified upload route uses `extract_file`, which treats ANY `result.errors` as fatal, and the HTML extractor recorded `"Section 'X' not found"` as an *error*. The LS recipe declares 6 workload sections + the other/agent tables, but no single file has all of them (workload XOR tables), so EVERY LS HTML file produced "not found" errors → `extract_file` rejected it. (The parity harness never caught this — it bypasses `extract_file`, calling `HTMLExtractor.extract` + `result_to_artifact` directly.)

### Changed
- **`html.py` `_find_section_table`:** a declared-but-ABSENT section (`"Section 'X' not found"`) is now a `result.warnings`, not `result.errors` — consistent with the CSV extractor and ADR-0017 D4 (empty ≡ absent). Config errors (`missing selector/title_match`) and malformed `found but contains no table` STAY errors (the non-fatal change is scoped to "declared-but-absent", not "any problem").
- **`dispatcher.py` `extract_file`:** new `declared_commcell_name` param, forwarded to `result_to_artifact(commcell_name=...)`.
- **`quick_hc.py` `_unified_dispatcher_upload`:** threads the active customer's `commserve_name` (NEVER `customer_name`; Fix-3) as `declared_commcell_name`, so the D2 top-tier identity (declared context) fires live — not just report-evidence/placeholder.

### Tests
- `extract_file` produces an artifact for a workload-only HTML and an other+agent HTML (absent sections are warnings); a misconfigured section (no selector/title_match) STILL errors; a declared CommServe name reaches `commcell_info` via `extract_file` (shows the declared name). Updated the SA `test_section_not_found` → now a WARNING (more robust partial import, not a regression). Parity unchanged: 738/0.

### Notes — post-state
recipe: live (1); D2 seam: live (2); recognition: broadened (3); HTML extraction: tolerant of absent sections + commcell_name threaded (4a); routing: still **bespoke** (4b pending); REST: untouched. The generic dispatcher can now import every real LS HTML file — the route switch (4b) is unblocked.

## 2026-06-13 (feat — ADR-0017 LS promotion commit 2/4: D2 commcell_info enrichment → live seam)

**Branch:** `main`. Port the D2 `commcell_info` enrichment from test/parity-support into PRODUCTION, called from `result_to_artifact`, caller-fed. Hard prerequisite for commit 4 (else the promoted path drops `commcell_info`). NO recognition change, NO route switch, NO upload-handler change, NO REST change. Full suite 1282 passed.

### Added
- **`src/cvhealthcheck/extractors/commcell_enrich.py`** — `enrich_commcell_info(artifact, commcell_name=None)` assembles the `commcell_info` MetricSection from caller-fed identity + report-evidence observational fields (consumed from the recipe's `_commcell_observed` staging section). `COMMCELL_OBSERVED_SECTION` / `COMMCELL_PLACEHOLDER` constants. Identity precedence: declared context > report evidence > `"Unknown CommCell"` — the placeholder is treated as absence-of-identity (so real evidence beats it; ADR-0017 D2). ADDITIVE + DATA-DRIVEN: a no-op returning the SAME object when the staging section is absent (non-LS byte-unchanged).
- **`tests/test_commcell_enrich.py`** — the gates: caller-fed assembly via `result_to_artifact` with NO db/session (gate 4); non-LS artifact passes through as the SAME object (gate 5); placeholder-as-absence precedence; observational `"N/A"` preserved; evidence-when-no-context.

### Changed
- **`result_to_artifact`** calls `enrich_commcell_info(artifact, commcell_name)` before returning — reusing the existing caller-fed `commcell_name` param (Fix-3/4) as the D2 identity. No new param; still caller-fed (no DB / session / context discovery).
- **`license_summary/generic_recipe.py`** sources `_OBSERVED_SECTION` from `COMMCELL_OBSERVED_SECTION` (single source of truth; same string → migration 0034 byte-unchanged).
- **Parity harness** (`tests/ls_generic_recipe.py`): `generic_candidate` now feeds `commcell_name` to `result_to_artifact` (enrichment happens IN the seam) instead of calling a separate test-side enrich; the test-side `_enrich_commcell_info` is removed and re-exported from production. D2 unit-test signatures updated to the caller-fed name; `_art_with_observed` now emits an EMPTY staging section for the no-evidence case (matching the recipe, which always emits the section). Commit-1 gate flips from "D2 not live" to "D2 live".

### Notes — post-state
D2 seam: **live**; recipe: live (commit 1); recognition: broadened (commit 3); routing: still **bespoke** (commit 4 pending); REST: untouched. The seam CAN now assemble `commcell_info`, but LS upload is still bespoke. Parity unchanged: pass 738, fail 0. With commit 2 done, commit 4's route switch will no longer drop `commcell_info`.

## 2026-06-13 (feat — ADR-0017 LS promotion commit 3/4: broaden HTML recognition)

**Branch:** `main`. Broaden License Summary HTML recognition so the live generic path can RECOGNIZE real workload-heavy exports (it can already extract them; recognition rejected them first). Recognition ONLY — NO route switch, NO recipe change, NO D2 change, NO REST change, NO header-shape recognition. Full suite 1274 passed.

### Added
- **`src/cvhealthcheck/db/migrations/0035_license_summary_recognition.sql`** — `UPDATE`s the `license_summary` html `recognition_hints`:
  - `has_selector` `.reportstabletitle` → `.reportstabletitle, h2` (accept either title marker).
  - **DROP `table_count`** (was `2`, matched with `!=`) — real workload exports have 7 tables, so they were rejected before extraction (the direct cause of the live HTML failure). Not replaced with another exact count.
  - **DROP `first_table_headers`** (`["License","Available Total","Used"]`, exact subset). A workload export's first table is "Capacity Licenses" with `Available Total (TB)` — the unit suffix fails the exact subset, so this *also* rejected the file. Removed, not fuzzed (fuzzing → header-shape recognition, which ADR-0017 D3 retires).
  - `title_contains "License summary"` **retained** — it keeps the scoped-out titleless fixtures (no `<title>`/`<h1>`, no marker) from recognizing; recognition does NOT fall back to header shape.

### Tests (`tests/test_recognition.py`)
- workload-heavy export (>2 tables, unit-suffixed first table) now recognizes as `license_summary`; an `<h2>`-titled export recognizes; a bare titleless `[License, Available Total, Used]` table is still NOT recognized (no header-shape fallback); standard 2-table export still recognizes (existing test); LS upload still bespoke (`UPLOAD_HANDLERS` unchanged).
- Migration count 34 → 35; the commit-1 recognition gate updated to assert the broadened form.

### Notes — post-state (still boring on routing)
recognition: **broadened**; catalog recipe: live (commit 1); D2 seam: **NOT yet live (commit 2 pending)**; routing: still **bespoke** (commit 4 pending); REST: untouched. So the workload-only HTML now RECOGNIZES but still fails LIVE via the bespoke guard until the commit-4 route switch — recognition is necessary, not yet sufficient. **Note:** the plan's expected post-state listed D2 as live, but commit 2 has not been done in this sequence.

## 2026-06-13 (feat — ADR-0017 LS promotion commit 1/4: generic recipe → production migration)

**Branch:** `main`. Port the generic License Summary recipe into the catalog under subject_id `license_summary` (replacing the 0003-era bespoke-shaped recipe), via a GENERATED, drift-guarded SQL migration. Recipe-only — NO D2-live, NO recognition change, NO route switch, NO bespoke deletion (those are commits 2–4). Full suite 1270 passed.

### Added
- **`src/cvhealthcheck/license_summary/generic_recipe.py`** — the production recipe (single source of truth): `LS_RECIPE_PROPOSAL` (subject_id `license_summary`), `publish_ls_recipe`, and `render_migration_sql` — a DETERMINISTIC generator (`sort_keys`, fixed separators/order) that renders the proposal into the migration SQL. The parity harness (`tests/ls_generic_recipe.py`) now re-exports from here, so live catalog and parity share ONE recipe.
- **`src/cvhealthcheck/db/migrations/0034_license_summary_generic_recipe.sql`** — GENERATED from the recipe (`python -m cvhealthcheck.license_summary.generic_recipe`). Tears down the prior `license_summary` recipe content (every source's section_sources + all its sections) and installs the generic recipe's bare-id sections + csv/html instructions. The `subjects` row is NOT touched (`created_by='system'` preserved); csv/html `recognition_hints` are NOT rewritten (`INSERT OR IGNORE` keeps the 0003 values — commit 3 broadens them); the `rest` source row is NOT touched (REST is out of scope).
- **`tests/test_ls_generic_recipe_migration.py`** — the 9 commit-1 gates: file committed + SQL-only runner; byte-identical regeneration; drift guard FAILS on a real recipe mutation (transform change + section add) and still matches when unmutated; subject_id stays `license_summary`; `created_by='system'` preserved; no stale `license_summary.*` ids; compile gate accepts the recipe; recognition/route/D2 untouched. Plus a functional check: the migrated catalog recipe extracts the workload-only 2 MB export end-to-end (the file bespoke rejects).

### Changed
- **Bare section ids for LS are now the catalog shape** (matching the bespoke adapter, `registry/catalog.py`, and the ADR-0017 parity target). `test_every_section_id_starts_with_tile_id_prefix` gets ONE named, justified exemption for `license_summary` (the prefix invariant still holds for every other subject — not generalized).
- **Extractor-machinery tests decoupled from the LS recipe:** the 7 `test_extractor_{csv,html}` LS-vehicle tests now run against a synthetic, prefixed-id `extractor_machinery` subject (new `conftest.machinery_subject` fixture). They test extractor machinery (single_table scan, null_values, BOM, metadata-skip, html title-match), not LS's canonical recipe — so future LS recipe changes don't churn them.
- Migration-count assertion 33 → 34.

### Notes
Migrations are SQL-only (`run_migrations` globs `*.sql`), so the recipe can't call `create_subject_from_proposal` from a migration — hence the generate-from-proposal + byte-identical drift-guard approach (the recipe, not hand-written SQL, stays the source of truth). Parity unchanged: pass 738, fail 0. The live LS upload is STILL bespoke until commit 4.

## 2026-06-13 (test/docs — ADR-0017 residual (b): named scope-out + corpus dedup → parity GREEN)

**Branch:** `main`. Formal close of ADR-0017 Open-question residual (b): the 5 titleless synthetic classifier fixtures are excluded from the parity corpus BY NAME, and duplicate upload copies are collapsed to distinct contents, leaving parity green over the real-export corpus.

### Changed (`tests/ls_parity_harness.py`)
- `EXCLUDED_SYNTHETIC_FIXTURES` — an explicit, per-file, classified list of the 5 titleless fixtures (3× `lab-*`, 2× `License20summary_*`, 142–180 B). Each is `<html><body><table>…</table></body></html>` with the bare `[License, Available Total, Used]` header and NO title markup (no `.reportstabletitle`, no `<h2>`). Reachable only by header-shape recognition — a capability the target deliberately does NOT implement (the header collides with the workload sections; ADR-0017 D3). Not a broad "drop untitled files" rule.
- `discover_ls_fixtures` now dedups by content hash. The fixture dir IS the live bespoke import dir, so re-uploads accumulate byte-identical copies (one content had 14). The corpus is now the set of DISTINCT export contents — honest signal (each export counted once) and stable across re-uploads. Discovery found **40 saved files → 9 distinct contents (7 LS-bearing + 2 non-LS)**.

### Added
- **`test_excluded_synthetic_fixtures_exist_on_disk_but_are_scoped_out`** — each named file still exists on disk (list not stale), is exactly the titleless shape (no `.reportstabletitle`, no `<h2>`), and is omitted from the discovered corpus.
- The corpus signal test now asserts `fail == 0` (was `fail > 0`).
- Drift-detector constants updated to the distinct-corpus counts: `EXPECTED_CORPUS 41→9`, `EXPECTED_CSV 10→3`, `EXPECTED_HTML 31→6` (deliberate, per the test's own contract).

### Notes — post-scope-out + dedup parity (real corpus): pass 738, fail 0, pending 0
Residual (b) RESOLVED in two parts: the sample reached via the `.reportstabletitle, h2` selector extension (prior commit `6c398da`); the 5 titleless fixtures named-excluded here. The prior "pass 6246/6944 over 38–40 files" was honest but **inflated by duplicate uploads** — the true corpus is **7 distinct LS exports** (incl. the workload-only 2 MB export that the bespoke HTML upload rejects). Dedup makes that explicit. ADR-0017 Open questions updated.

## 2026-06-13 (feat/test — ADR-0017 selector extension: <h2>-titled tables reachable (Case A))

**Branch:** `main`. The LS recipe's title selector now also accepts `<h2>`; the HTML extractor associates a section title with the table that FOLLOWS it. Still title-anchored, still exact match — NO header-shape matching. Full suite 1256 passed (+2).

### Changed
- **Recipe (`tests/ls_generic_recipe.py` `_html_table`):** `section_title_selector` broadened from `.reportstabletitle` to `.reportstabletitle, h2`. Covers `other_licenses`, `agent_feature_licenses`, and the workload sections uniformly. Still EXACT `section_title_match`; the extension only broadens WHERE a title may live, not what counts as a section.
- **Extractor (`src/cvhealthcheck/extractors/html.py`):** `_find_section_container` → `_find_section_table`. A section title now labels the table that FOLLOWS it in document order (bounded to the nearest table-scoping ancestor, ≤5 levels). Handles both the tightly-wrapped export layout (`<div class="reportstabletitle">…</div><table>`) and a sibling-heading layout (`<h2>…</h2><table>`); for the common one-table-per-wrapper case it resolves to the same table the old ancestor-walk returned (no regression — legacy security_assessment + license_summary extractor tests stay green). The earlier walk-up mis-assigned a sibling `<h2>` section to the first table under `<body>`.

### Added — `tests/test_ls_parity_signal.py`
- **+2 tests:** sibling-`<h2>` sample layout — both `other_licenses` and `agent_feature_licenses` are reached and the agent `<h2>` resolves to ITS following table (no cross-wiring); a bare untitled table is still NOT reached (the extension is "title may be in more places", not "match untitled tables by header shape").

### Notes — post-extension breakdown (38): pass 6246, fail 10 (was 14)
The 4 `license-summary-sample` fails cleared (its `other_licenses` + `other_license_count` + `agent_feature_licenses` + `agent_feature_count`). **No new field-level diffs** on the now-reachable sample tables: `other_licenses` matches via the existing D1 value/unit equivalence (bespoke flat `value`+`unit` ≡ generic nested `{value,unit}`); `agent_feature_licenses` is byte-identical — bespoke `normalize_agent_feature_record` ALSO drops `Client`/`Agent`/`Install Date`, so the recipe's 5-field `_AGENT_CM` exactly matches bespoke's kept fields. Remaining 10 = the 5 titleless classifier fixtures (3× lab-*, 2× License20summary_*) × (`other_licenses` present-on-one-side + `other_license_count`) — Case B, scope-out candidates (next step).

## 2026-06-13 (test/docs — ADR-0017 D8: workload "Other Licenses" id-collision not preserved)

**Branch:** `main`. ADR-0017 D8 recorded (docs) + scoped comparator acceptance. No recipe change, no bespoke change, no general bespoke-only pass. Comparator suite 34 passed; full suite green.

### D8 (recorded, `docs/adr/0017-license-summary-canonical-parity-target.md`)
- The bespoke workload "Other Licenses" section takes `_to_snake` id `other_licenses` — the same id as the `other_licenses` TABLE. Across the 38-file corpus the two never co-occur (30 table / 8 workload / 0 both): the shared id never modeled a real relationship, it is a historical naming artifact. `subject_sections` is unique on section_id, so the recipe cannot mirror the workload under `other_licenses`; the canonical target does NOT preserve it. Same class as D7 — a deliberate, named drop.
- Resolves Open-question residual (a) (workload-vs-table id collision); residual (b) (HTML-structure variation, 14 fails) is the next read.

### Changed (`tests/ls_parity_harness.py`)
- `compare_artifacts` accepts a bespoke(baseline)-only section keyed `(other_licenses, workload)` as a D8 PASS ("workload 'Other Licenses' id-collision quirk, not preserved"). SCOPED to that exact (id, shape-tag) pair.
- **+4 D8 tests** (`tests/test_compare_adr0017.py`): accepted workload-only `other_licenses`; **negative guards** — an unrelated bespoke-only section still FAILS, the bespoke-only `other_licenses` TABLE (default tag) still FAILS, another workload section id (`capacity_licenses`) still FAILS.
- Updated the B1 cross-compare test: the baseline-only workload `other_licenses` is now a D8 PASS, so the assertion checks both sections are handled at the section level (no field cross-compare) rather than counting two section FAILs.

### Notes — post-D8 breakdown (38): pass 6236, fail 14 (was 22)
The 8 workload "Other Licenses" present-on-one-side fails cleared. Remaining 14 are exactly the HTML-structure-variation residual across the 6 files with no `.reportstabletitle` (6 `other_licenses` present-on-one-side + 6 `other_license_count` value + 1 `agent_feature_licenses` present-on-one-side + 1 `agent_feature_count` value) — the subject of the next read-only DOM investigation (no recipe change until classified Case A/Case B).

## 2026-06-13 (feat/docs — ADR-0017 D2: commcell_info mixed-source enrichment)

**Branch:** `main`. ADR-0017 D2 clarified (mixed-source) + the enrichment implemented (candidate-seam side). No comparator tolerance, no recipe "inject context", no bespoke change. Suite 1250 passed (+5).

### Changed
- **ADR-0017 D2 clarified (docs):** `commcell_info` is a MIXED-SOURCE enrichment section — IDENTITY (`commcell_name`) from CUSTOMER CONTEXT, OBSERVATIONAL (`commcell_version` / `license_expiry` / `last_collection`) from REPORT EVIDENCE (transport-agnostic; the ExtractionResult is today's transport, not the authority). Identity precedence: declared context > report-evidence > placeholder; "Unknown CommCell" is treated as absence-of-identity, so a real evidence name beats it. Enrichment-ASSEMBLED, not a recipe section.
- **D2 enrichment (`tests/ls_generic_recipe.py`):** `_enrich_commcell_info` assembles the `commcell_info` MetricSection at the candidate seam — identity from context (precedence), observational from a staged `_commcell_observed` `metadata_pairs` section (consumed, never emitted; `null_values=[]` so `"N/A"` is preserved). Observational labels confirmed from the corpus: `Version`, `License expiration`/`License Expiry`, `Usage collection time`; evidence name `CommCell Name`. No new file-reading in enrichment — the recipe extracts the labels (report evidence).
- **+5 tests** (context-beats-evidence; evidence-when-no-context; placeholder; `"N/A"` preserved; end-to-end `commcell_info` == bespoke).

### Notes — post-D2 breakdown (38): pass 6228, fail 22 (was 60)
The 38 `commcell_info` present-on-one-side fails cleared (real parity — `commcell_info` now compares present-on-both, no tolerance). Remaining is exactly the two known residuals:
- **workload "Other Licenses" (8)** — DB-constraint (ADR decision pending).
- **HTML-structure variation (14: 6 table + 6 count + 1 agent + 1 count)** — 6 files with no `.reportstabletitle`.

## 2026-06-13 (test — ADR-0017 B2: unit trailing-token equivalence)

**Branch:** `main`. Comparator-side B2: a unit's identity is its TRAILING token; the qualifier before it is ignored for parity (it qualifies the quantity, not the unit). No `number_with_unit` / recipe / D2 / bespoke change. Suite 1245 passed (+6).

### Changed (`tests/ls_parity_harness.py`)
- `_to_unit_pair` normalizes each unit to its trailing token (`_unit_token`): `"source VMs"` → `"VMs"`, `"target VMs"` → `"VMs"`, `"VMs"` → `"VMs"`. Equal iff value AND trailing token match. **Trailing-token, NOT suffix-match** — so `"source VMs"` ≡ `"target VMs"` (a suffix comparison would wrongly differ). The unit token itself is still respected (`VMs` ≠ `TB` ≠ `users`); a value difference still FAILS.
- +6 tests (qualifier-ignored positive; unit-respected negative; value-still-matters; null/empty safe; token extraction; through-the-comparator).

### Notes — post-B2 breakdown (38): pass 6164, fail 60 (was 88)
The 28 B2 unit-parse fails cleared. Remaining classes — exactly the non-B2 set:
- **D2 commcell_info (38)** — context-injected; awaits the enrichment seam (deferred).
- **workload "Other Licenses" (8)** — DB-constraint residual (bespoke `_to_snake` id collides with the table; the recipe can't declare two `other_licenses` sections; needs an ADR decision).
- **HTML-structure variation (14: 6 table + 6 count + 1 agent + 1 count)** — 6 files have no `.reportstabletitle` element; the selector recipe can't reach their tables (the bespoke custom DOM-walk can).

## 2026-06-13 (test — ADR-0017 "Other Licenses" recipe disambiguation (table by full title))

**Branch:** `main`. Recipe-side "Other Licenses" disambiguation + decomposition of the residual. No B2 / D2 / comparator / bespoke change. Suite 1239 passed (+2).

### Changed (`tests/ls_generic_recipe.py`)
- The other_licenses TABLE (HTML) is matched by its EXACT full title `"Other Licenses - current usage details"`, so it no longer collides with the bare `"Other Licenses"` workload-summary title — the generic stops mis-grabbing the workload as a degenerate table.
- +2 tests (full-title table extracted, not the workload; a bare-`"Other Licenses"` workload is not grabbed as a degenerate table).

### Notes — post-disambiguation breakdown (38): pass 6136, fail 88 (was 104)
The full-title fix cleared the 8 degenerate generic-only tables + their 8 downstream count fails (16 total). Remaining classes:
- **D2 commcell_info (38)** — enrichment seam, deferred.
- **B2 unit-parse (28)** — one pattern, OPEN.
- **workload "Other Licenses" (8)** — DB-constraint residual: bespoke `_to_snake("Other Licenses")` = `other_licenses` (the table's id); the recipe can't declare two `other_licenses` sections (`subject_sections` unique). NOT recipe-fixable — needs an ADR decision (distinct target id + comparator mapping, or accept the bespoke collision as a dropped quirk). Authoring it under a distinct id would double the fails.
- **HTML-structure variation (14: 6 table + 6 count + 1 agent + 1 count)** — 6 files (lab-*, some License20summary, the sample) carry no `.reportstabletitle` element; the selector-based recipe can't reach their tables (the bespoke custom DOM-walk can). Separate from "Other Licenses"; this is the "HTML section not found" class.

### Findings (ADR-0017 open questions updated)
The title-prefix ambiguity is fixed; the two residuals (DB section-id collision; HTML-structure variation) are recorded in ADR-0017's open questions — neither is the title-prefix problem.

## 2026-06-13 (feat/docs — ADR-0017 D3/F5 comparator equivalence + ADR-0017 doc (Proposed))

**Branch:** `main`. Harness-side D3/F5 comparator equivalence + the ADR-0017 decision record (the doc that was missing — D1–D7 lived only in the comparator + CHANGELOG). No recipe/bespoke/enrichment/unit change. Suite 1237 passed (+4).

### Added
- **`docs/adr/0017-license-summary-canonical-parity-target.md` (Proposed, D1–D7)** — what "parity" proves for the LS de-bespoke: the generic produces the decided canonical TARGET, not byte-replication of bespoke omissions. Records D1 (value/unit equivalence), D2 (identity is enrichment, deferred to the seam), D3 (counts as computed sections ≡ summary metrics), D4 (empty≡absent / dedup tolerance), D5 (usage_percent omitted), D6 (mask-format-independent), D7 (registration_code in the target when present), plus B1 (section-id collision, fixed) and B2 (unit-parse, open). README ADR range → 0001–0017.

### Changed (`tests/ls_parity_harness.py`)
- **D3/F5 equivalence:** counts are compared in a unified namespace — a bespoke `summary` metric `X` ≡ a generic single-value computed-section `X` (`_is_count_section` = one row `{"value": N}`), matched by name + value. Count-sections are excluded from the section comparison (accounted for in the namespace). **Negative guard:** same name + different value still FAILS; a count present on only one side still FAILS (never blanket-passed).
- +4 tests (equivalence; different-value fails; metric-with-no-section fails; section-with-no-metric fails).

### Notes — post-D3/F5 breakdown (38): pass 6128, fail 104 (was 241)
The 152 placement failures cleared. Residual: **D2 commcell_info (38)** — deferred to the enrichment seam; **B2 unit-parse (28)** — one pattern; **"Other Licenses" title ambiguity (22 sections + 14 downstream count-value fails** — the generic misses the table → its `other_license_count` is 0 ≠ bespoke 1, which the D3 negative guard correctly fails); **one sample structural variation (1 section + 1 downstream count)**. The residual count-value fails are symptoms of the title/sample extraction gaps, not a separate class.

## 2026-06-13 (test — ADR-0017 D7: registration_code is part of the LS canonical target)

**Branch:** `main`. Amendment D7 applied to the parity comparator. (No ADR-0017 doc file exists yet — the ADR-0017 decisions live in the comparator + this CHANGELOG.) No recipe/bespoke change. Suite 1233 passed (+3).

### D7 (recorded)
registration_code is part of the LS canonical target when the source carries it. The generic recipe extracts + masks it (ADR-0016 Security-by-Construction); bespoke dropping registration_code was a historical omission, not a canonical requirement. Parity ACCEPTS generic-present masked registration_code vs bespoke-absent, provided the generic value is masked and no raw survives — same class as D4/F3: where bespoke lost data the file carries, the generic path is the more faithful one; parity proves the decided target, not replication of bespoke gaps.

### Changed (`tests/ls_parity_harness.py`)
- A generic(candidate)-only section carrying only masked sensitive fields (`_is_masked_sensitive_section`) is accepted (PASS) against a bespoke-absent one; a RAW value still FAILS (security). Directional: a bespoke-only sensitive section is NOT auto-accepted (the generic dropping data is a real difference).
- +3 tests (accepted-when-masked; fails-on-raw; directional).

### Notes — post-D7 breakdown (38): pass 6067, fail 241 (was 249)
The reg_code / commcell_meta class (8) is resolved → PASS. Remaining failure classes: F5/D3 computed-counts-as-sections vs summary metrics (152), D2 commcell_info context-injected (38), B2 unit-parse one pattern (28), "Other Licenses" title ambiguity (22), one sample structural variation (1).

## 2026-06-13 (test — ADR-0017 LS parity: B1 comparator fix (section-id collision) + failure decomposition)

**Branch:** `main`. ONE comparator bug-fix (B1) + read-only decomposition. No recipe change, no bespoke change, no ADR-decided-class fixes (pending decisions). Suite 1230 passed (+2).

### Fixed (B1 — comparator correctness, `tests/ls_parity_harness.py`)
- Sections are keyed by **(id, shape-tag)** instead of id alone. The bespoke `_to_snake("Other Licenses")` workload section and the other_licenses TABLE collapse to the same id `other_licenses`; the old `{id: s}` map dropped one and cross-compared a table against workload fields. The shape-tag (`"workload"` iff the section carries `entitlement_value`, else `"default"`) keeps them distinct. Empty sections are dropped (D4/F4: empty ≡ absent), so a non-empty section present on one side only is a real difference. (Bonus: an artifact carrying BOTH a table and a workload `other_licenses` now compares both, instead of silently collapsing one.)
- `run_signal` excludes the 3 misfiled non-LS exports (real LS corpus = 38).
- `tests/test_compare_adr0017.py` +2: table vs same-id workload not cross-compared; reflexive collision keeps both sections.

### Notes — post-B1 breakdown (38 files): pass 6059, fail 249 (was 280 / 41)
- **F5/D3 computed counts (152 = 4×38):** generic computed SECTIONS vs bespoke SUMMARY METRICS — ADR-decided, unchanged by B1.
- **D2 commcell_info (38):** context-injected, recipe omits it — ADR-decided, unchanged.
- **reg_code commcell_meta (8):** recipe extracts + masks, bespoke drops it — ADR-decided, unchanged.
- **B2 unit-parse divergence (28):** ONE pattern — raw `"0 source VMs"` → bespoke unit `"VMs"` (trailing word) vs generic `"source VMs"` (everything after the number; `number_with_unit`). Decision pending.
- **"Other Licenses" title ambiguity (22):** the SOURCE title "Other Licenses" matches both the table ("Other Licenses - current usage details") and the workload ("Other Licenses") — generic grabs the workload as a degenerate table (8), misses the real table (6), and omits the workload (8). Recipe disambiguation, pending.
- **license-summary-sample structural variation (1):** agent_feature_licenses missed on one mock sample export.

## 2026-06-13 (test — ADR-0017 LS recipe: first parity signal, generic-vs-bespoke)

**Branch:** `main`. First parity SIGNAL — the generic LS recipe authored against the ADR-0017 target + adjusted comparator, published through the compile gate, compared generic-vs-bespoke over the corpus. Bespoke LS STAYS; no UI/upload change, no bespoke deletion, no recipe-model change, no compile-gate change. NOT green, NOT retirement. Suite 1228 passed (+2). **The compile gate accepted the recipe.**

### Added
- **`tests/ls_generic_recipe.py`** — the generic LS recipe proposal (canonicals match the bespoke ADAPTER's field/section ids), `publish_ls_recipe` (through the gate), `generic_candidate` (the harness candidate seam), `run_signal` (generic-vs-bespoke with failure-class aggregation). Extracts only what files carry: other_licenses (single_table + `number_with_unit`), agent_feature_licenses (single_table + `to_integer`, no dedup), workload ×6 (HTML `section_title_selector` + coalesce + `number_with_unit` — HTML-only; no CSV carries workload), registration_code (metadata_pairs, exact label `"Registration code"`, mask), computed other_license_count / agent_feature_count (computed sections). NO commcell_info identity (D2, deferred), NO usage_percent (D5).
- **`tests/test_ls_parity_signal.py`** (2) — the recipe publishes through the gate; the generic candidate produces an artifact for every fixture and the comparison runs (pass>0, pending==0, fail>0 — the signal).

### Notes — first parity breakdown (41 fixtures): **pass 6141, fail 280, pending 0**
Failure classes (to read together, NOT yet fixed):
- **F5/D3 computed counts (164 = 4×41):** generic emits computed SECTIONS; bespoke emits SUMMARY METRICS — no summary-metric ≡ computed-section equivalence in the comparator.
- **D2 commcell_info (41):** bespoke always emits a context-injected commcell_info; the recipe omits it (D2 enrichment seam, deferred).
- **registration_code (8):** the recipe extracts + masks it; the bespoke adapter drops it from the canonical.
- **other_licenses HTML (60):** `_to_snake("Other Licenses")` workload id COLLIDES with the other_licenses table id (comparator id-map keeps the workload one → table compared against workload fields); plus a unit-parse divergence (`"0 source VMs"` → generic unit `"source VMs"` vs bespoke trailing-word `"VMs"`).
- **HTML section not found (7):** `.reportstabletitle`/title_match misses on some exports.

### Findings flagged (ADR items, not silent workarounds)
F5 needs a comparator equivalence (summary-metric ≡ computed-section) or a bespoke-side move; D2 commcell_info awaits the enrichment seam; the `other_licenses` ⇄ "Other Licenses" workload id collision is a bespoke quirk; the `number_with_unit` (everything-after-number) vs bespoke (trailing-word) unit-parse divergence.

## 2026-06-13 (test — ADR-0017 comparator adjustment: decided equivalences in the LS parity harness)

**Branch:** `main`. Harness-side only — adjusts the parity comparator so subsequent LS-recipe parity failures are REAL differences, not comparator artifacts. NOT the LS recipe, no recipe-model change, no bespoke change. Suite 1226 passed (+15).

### Changed (`tests/ls_parity_harness.py`)
- **D1 value/unit equivalence:** `available_total` / `used` / `entitlement_value` are now ACTIVELY compared (lifted out of PENDING-UNIT) via `unit_value_equal` — bespoke flat (a number + a separate row `unit`, or a `"N unit"` string) is treated as equal to generic nested `{value, unit}` when the (value, unit) pairs match. The standalone `unit` field is subsumed into those pairs (not compared on its own).
- **D4/F4 empty ≡ absent:** a section with no rows compares EQUAL to an absent section; a non-empty section vs absent still FAILS (no over-equating).
- **D6 mask-format independence:** the sensitive branch asserts BOTH-masked + raw-absent only — no longer byte-identical masks (generic segment-mask ≡ bespoke first-4/last-4); a raw value on either side still FAILS.
- **D4/F3 dedup tolerance:** table rows match by `license` key (distinct-set comparison), so duplicate-row multiplicity differences are tolerated where the distinct set matches; a differing distinct set still FAILS.

### Notes
- Corpus reflexive run (bespoke-vs-bespoke) after the adjustment: **pass 6339, fail 0, PENDING-UNIT 0** (was pass 5251 / pending 1448 — the three value fields moved pending→pass, the `unit` field is subsumed). pass/fail stays honest.
- New `tests/test_compare_adr0017.py` (15): each equivalence + guards that the comparator still FAILS on genuine differences (value diff, missing field, wrong content). Two existing harness self-tests updated (pending now 0; unit fields actively compared).
- NOT done: the LS recipe (next, authored against this adjusted comparator).

## 2026-06-13 (feat — ADR-0015 compile gate: publish-time recipe validation, transform-aware)

**Branch:** `main`. The ADR-0015 compile/publish gate, built transform-aware per ADR-0016 D2 — runs at the publish chokepoint before any write and rejects a proposal whose recipe fails validation, listing every violation. The interim apply-time raises stay as defense-in-depth. NOT the LS recipe, no bespoke deletion, no new transforms, no recipe-model changes. Suite 1211 passed (+14). Parity harness over the 38 unchanged.

### Added
- **`compile_validate_proposal` (`db/compile_gate.py`)**, called at the top of `create_subject_from_proposal` (`db/subjects.py`) before any INSERT. Walks every `(source_type, section_id)` recipe in `proposal["extraction_instructions"][…]["sections"][…]`, collects ALL violations, and raises one `ProposalCompileError` (per-violation messages with source/section/field context) before the write transaction starts — a rejected proposal never becomes catalog-live. Four recipe-static checks:
  1. every `transforms` name ∈ the closed `TRANSFORMS` registry (column_map AND label_map entries);
  2. a canonical field ∈ `SENSITIVE_FIELD_REQUIREMENTS` carries its required transform(s) (column_map AND label_map);
  3. a `format:"computed"` section's `computed_type` ∈ `COMPUTED_TYPES`;
  4. a section's `format` ∈ the allowed set for its source type — csv `{single_table, multi_section, metadata_pairs, computed}`, html `{table, metadata_pairs, computed}` — replacing today's soft handling (CSV → `result.errors`, HTML → silent fall-through) with a loud publish rejection (a format valid for CSV used in an HTML section is rejected).
  Scope confirmed from the extractors: only csv/html have a format dispatch and feed `resolve_columns` — REST has its own transform-free `_apply_column_map`, and CC/RP/json use neither — so checks 1-4 are csv/html-scoped.
- **Defense-in-depth retained:** the apply-time raises (`UnknownTransformError`, `SensitiveFieldError`, `UnknownComputedTypeError` in `column_map`) stay; publish is now the primary gate, apply-time the backstop.
- **`tests/test_compile_gate.py`** (14) — each violation type rejected; a CSV-only format used in HTML rejected; MULTIPLE violations → one rejection naming all three (not fail-on-first); clean proposal publishes; rejection happens AT PUBLISH before any write (subject not created); apply-time backstop still raises; non-csv/html sources not format-checked.

### Notes
- Parked (named, not built): unknown-keys hardening — would reject a smuggled `regex`/`fuzzy` field on a metadata_pairs recipe (defense against a non-existent capability, deferred).
- The gate VALIDATES the closed model; it does not extend it. NOT done: the LS recipe, bespoke-LS deletion.

## 2026-06-13 (feat — ADR-0016 transform layer slice 6: computed sections — transform layer complete)

**Branch:** `main`. Sixth and LAST transform-layer slice — the three computed sections only. NOT the compile gate, NOT the LS recipe, NOT bespoke deletion. Suite 1197 passed (+13). Parity harness over the 38 unchanged. With this slice the ADR-0016 transform layer (coalesce + closed registry + mask + number_with_unit + metadata_pairs + computed) is feature-complete; next is the compile gate, then the LS recipe + parity flip.

### Added
- **computed sections (`format: "computed"`)** on both extractors — exactly three extraction-time row aggregates over another (already-extracted) section's rows (ADR-0016 D1d, closed set): `row_count` → int; `distinct_count` (non-null values of a named `field`) → int; `grouped_count` (over `field`) → `{group: count}`. The aggregate lands as one output row under `output_field` (default "value"). A missing/empty source section yields 0 / `{}` (no crash); an unknown computed type raises `UnknownComputedTypeError` (interim apply-time enforcement; the compile gate rejects at publish later). NO expressions / filters / arithmetic / custom functions. These SHAPE at extraction time — distinct from the ADR-0010 evaluative layer, which JUDGES after extraction.
- **`tests/test_computed_sections.py`** (13) — the three aggregates (incl. None exclusion), missing/empty source → 0/empty, unknown type → raises, the `extract_computed` builder (output_field, missing-source warning), the `grouped_count` `{group: count}` map round-tripping through the `CanonicalArtifact` model, and a compose test (one CSV → table + metadata_pairs + `row_count` + `grouped_count`, all produced in a single extraction).

### Notes
- Ordering: a computed section reads `result.sections[source_section]`, so its `sort_order` must exceed its source's (the source is extracted first) — a recipe-authoring responsibility; out-of-order resolves to an empty source (0/empty + warning), never a crash.
- NOT done: the compile gate, the LS recipe, bespoke-LS deletion. The harness PENDING-UNIT fields still move pending→comparable only when the LS recipe is authored to use the transforms.

## 2026-06-13 (feat — ADR-0016 transform layer slice 5: metadata_pairs)

**Branch:** `main`. Fifth transform-layer slice — the `metadata_pairs` section format only. NOT computed sections (slice 6), the compile gate, the LS recipe, or `number_with_unit` changes. Suite 1184 passed (+17). Parity harness over the 38 unchanged.

### Added
- **`metadata_pairs` section format** (CSV + HTML) — deterministic exact-label → value extraction from scattered `label: value` rows/lines. `label_map` maps a source label → canonical field. Matching is **trim-only, case-sensitive exact** (a case-only difference does NOT match); NO regex / fuzzy / hierarchical / multi-line (ADR-0016 §1c). Each mapped field uses the SAME closed registry, transforms, and unknown-transform + sensitive-field enforcement as table sections: `extract_metadata_pairs` feeds a label→value map through `resolve_columns(case_sensitive=True)` + `extract_row` — **one registry, one enforcement point, two formats feeding it** (no metadata_pairs-specific copy).
- **`split_label_value`** (first-colon split, trims both sides, value keeps later colons), a `case_sensitive` flag on `resolve_columns`, and `_extract_metadata_pairs` on both extractors (CSV: a `[label, value]` 2-cell row or a `label: value` single cell; HTML: `label: value` text lines; first occurrence wins, deterministic).
- **`tests/test_metadata_pairs.py`** (17) — split helper; exact match; case-difference → no match; whitespace trim; unknown label ignored; absent label → no key; transform chain via the shared registry; `registration_code` without mask → `SensitiveFieldError`; with mask → masked; a raw reg-code → fail-closed (not leaked); CSV + HTML end-to-end; HTML case-mismatch → nothing matched.

### Notes
- `registration_code` is a scattered metadata pair, so `metadata_pairs` is its primary real use — the sensitive-field gate fires identically here (proven end-to-end: a `registration_code` metadata_pairs recipe without mask raises on extract).
- NOT done: computed sections (slice 6), the compile gate, the LS recipe.

## 2026-06-13 (feat — ADR-0016 transform layer slice 4: number_with_unit)

**Branch:** `main`. Fourth transform-layer slice — `number_with_unit` only. NOT metadata_pairs (slice 5), computed sections, `to_float_percent` (spec'd-blocked, no corpus sample), header-unit extraction (deferred `unit_from_coalesce_source_name`), or the LS recipe. Suite 1167 passed (+15). Parity harness over the 38 unchanged.

### Added
- **`number_with_unit`** in the closed registry — parses a "<number> <unit>" cell into `{value, unit}` per ADR-0016 Amendment A (resolved Open Item 1: parse-and-keep, NO base-unit normalization; grounded on the 38 exports). **Cell contents only** (Amendment B — header-encoded units deferred). `"25 TB"` → `{value: 25, unit: "TB"}`; `"500"` → `{value: 500, unit: None}`. `value` is numeric (int when integral, float when decimal); thousands commas tolerated; null / empty / no-leading-number → None. Plain counts and unit-bearing values are handled uniformly (no separate `to_integer` carve-out, Amendment A).
- **`tests/test_number_with_unit.py`** (15) — unit-bearing values, plain counts, zero, null/empty/non-numeric → None, whitespace tolerance, numeric-type assertions (int vs float), thousands separators, compose-after-`trim`, the `{value, unit}` shape round-tripping through the `CanonicalArtifact` model, and end-to-end through the real CSV extractor.

### Notes
- The harness PENDING-UNIT fields (`available_total` / `used` / `unit` / `entitlement_value`) stay pending — they move pending→comparable only when the LS recipe is authored to USE `number_with_unit` (a later slice), not here.
- NOT done: `metadata_pairs` (slice 5), computed sections, `to_float_percent`, header-unit extraction (`unit_from_coalesce_source_name`), the compile gate, the LS recipe.

## 2026-06-13 (feat — ADR-0016 transform layer slice 3: Security-by-Construction)

**Branch:** `main`. Third transform-layer slice — `mask_registration_code` + the sensitive-field mandatory-transform rule. NOT number_with_unit (slice 4), metadata_pairs, computed sections, compile gate, or LS recipe. Suite 1152 passed (+25). Parity harness over the 38 unchanged (no LS recipe uses mask; the bespoke path masks via its own function).

### Added
- **`mask_registration_code`** in the closed registry — `XXXX-XXXX-XXXX-1234` → `****-****-****-1234` (reveals only the trailing identifier segment). **Fail-closed:** any input it cannot confidently mask (null, empty, or a shape that is not the dash-segmented form) returns None — a raw registration code never survives under ANY input, anticipated or not. Idempotent (`*` is an allowed segment char, so re-masking a masked value is stable).
- **Sensitive-field enforcement (Security-by-Construction).** `SENSITIVE_FIELD_REQUIREMENTS = {"registration_code": ["mask_registration_code"]}`. A recipe that declares a sensitive-tagged canonical field MUST include the SPECIFIC required transform in its chain (not merely "some transform"); `resolve_columns` raises `SensitiveFieldError` eagerly otherwise. A recipe that does NOT declare the sensitive field is accepted. Interim apply-time enforcement, same pattern as slice 2 — the ADR-0015 compile gate will reject at publish later.
- **`tests/test_sensitive_field_mask.py`** (25) — masking (canonical / 2-segment / length-preserving); fail-closed across 7 unexpected shapes (raw never survives); idempotent + already-masked; null/empty/whitespace safe; compose-after-trim; the enforcement rule (no mask → error, only-`trim` → error, with-mask → accepted, `trim`-then-mask → accepted, no-sensitive-field → accepted, non-sensitive field → accepted); a clear error message; and end-to-end through the real CSV extractor (masked output; a `registration_code`-without-mask recipe raises on extract).

### Changed
- `tests/test_transform_registry.py` registry-contents assertion relaxed from exact-four to subset — slice 3 legitimately adds `mask_registration_code`.

### Notes
- The generic `mask_registration_code` uses a segment-mask scheme (`****-****-****-1234`); the bespoke LS `normalize.mask_registration_code` uses first-4 + last-4. They are SEPARATE functions (LS not converted); the difference is a slice-5 / conversion concern that the parity harness will surface when the LS recipe is authored.
- NOT done (later slices): `number_with_unit` (slice 4), `to_float_percent`, `metadata_pairs`, computed sections, the compile gate, the LS recipe.

## 2026-06-13 (feat — ADR-0016 transform layer slice 2: closed registry + simple transforms)

**Branch:** `main`. Second transform-layer slice — the closed-registry mechanism + the four pure coercions only. NOT mask (slice 3), NOT number_with_unit (slice 4), NOT to_float_percent / metadata_pairs / computed sections, no sensitive-field enforcement, no compile gate, no LS recipe. Suite 1127 passed (+18). Parity harness over the 38 unchanged (no LS recipe uses transforms; transforms are in the generic extractor, not the bespoke LS path).

### Added
- **`transforms: [name, ...]` on a recipe field** — applied in order to the (coalesced) source value; names resolve only against a closed, platform-owned registry (`TRANSFORMS` in `extractors/column_map.py`). Initial registry: `trim`, `null_if_empty`, `to_integer`, `to_float`. When a column declares transforms the chain produces the value (replacing the legacy `type` coercion for that column); a column without transforms is byte-identical to before.
- **Interim Compile-Validated enforcement:** an unknown transform name raises `UnknownTransformError` at recipe-application time — eagerly in `resolve_columns`, once per column, with field + section context (and defensively in `apply_transforms`). Held now even though the ADR-0015 compile gate (which will reject at publish) does not yet exist.
- **`tests/test_transform_registry.py`** (18) — each transform in isolation; ordered chains; unknown-name raises (apply + resolve, including when the source column is absent); composition with slice-1 coalesce (list source → first present → transform chain); a no-transforms regression; and end-to-end through the real CSV extractor.

### Notes
- Transforms are pure value→value; `to_integer` / `to_float` return None on non-numeric. When present, the chain replaces the column's `type` coercion (the chain is authoritative), and whitespace is preserved unless `trim` is in the chain.
- NOT done (later slices): `mask_registration_code` (slice 3, with sensitive-field gate enforcement), `number_with_unit` (slice 4), `to_float_percent`, `metadata_pairs`, computed sections, the compile gate, and the LS recipe itself.

## 2026-06-13 (feat — ADR-0016 transform layer slice 1: source coalesce)

**Branch:** `main`. First transform-layer slice — **coalesce only** (NOT the full registry, NOT mask / number_with_unit / metadata_pairs / computed sections, NOT the LS conversion, NOT compile-gate work). Suite 1109 passed (+14). Parity harness over the 38 unchanged — coalesce lives in the generic extractor, not the bespoke LS path.

### Added
- **`source` coalesce (`string | list[string]`).** A recipe column's `source` may now be a list: among the candidates, in order, the first present-and-non-empty (and non-null) value wins — no merge / concat / arithmetic (ADR-0016 D4). A string source is unchanged (1:1). New shared resolver `cvhealthcheck/extractors/column_map.py` (`resolve_columns` / `extract_row` / `coerce` / `header_has_all`), imported by BOTH the CSV and HTML extractors so coalesce behaves identically across formats (License Summary imports either — the parity the harness depends on).
- **`tests/test_column_coalesce.py`** (14 tests) — the five required behaviors (string 1:1 regression; first present; first absent/empty → second; none → null; order honored) at the resolver level, plus end-to-end wiring through the real CSV and HTML extractors.

### Changed
- **`extractors/csv.py` + `extractors/html.py`** now delegate column resolution / row extraction / coercion to the shared `column_map` module; their duplicated `_resolve_columns` / `_extract_row` / `_coerce` were removed. String-source behavior is identical (the existing extractor suites stay green).

### Notes
- **Coalesce unblocks (input to the eventual LS conversion — NOT authored here):** the LS workload-summary `entitlement_value` and `used` fields, which the bespoke `_first_present_text` resolves across report-version / license-type column-name variants (`Available Total` / `Available Total (TB)` / `(instances)` / `(users)` / `Permanent Purchased…`). `other_licenses` `available_total` / `used` are single columns and need no coalesce.
- NOT done (later slices): mask, number_with_unit, to_float_percent, metadata_pairs, computed sections, compile-gate validation, the LS recipe itself.

## 2026-06-13 (docs — ADR-0016 amendment: number_with_unit resolved, Open Item 1)

**Branch:** `main`. A read-only grounding probe over the LS corpus resolved ADR-0016 Open Item 1; the amendment is recorded in `docs/adr/0016-recipe-transform-layer.md` (stays in 0016, not a new ADR) plus the small harness prune it mandates. Transform implementation NOT started.

### Changed
- **ADR-0016 amended (A–D); Open Item 1 RESOLVED.** The grounding pass found **no canonical quantity appears with a differing unit** across the **corpus = 38** license-bearing LS exports (41 files on disk − 3 misfiled non-LS: two Security-Assessment exports + the `cv_redesign_option_a_refined` mock). So **`number_with_unit` returns `{value, unit}`** (parse-and-keep); base-unit normalization is rejected (Amendment A). It is a CELL transform — header-encoded units (`Available Total (TB)` with plain cells, 112/184 workload rows) are out of scope and dropped to match bespoke; capturing them is a deferred capability, **`unit_from_coalesce_source_name`** (Amendment B). **`to_float_percent`** added to the registry, **spec'd but deferred** — `Used %` is absent in the corpus (0/184 rows), so there is no fixture to validate (Amendment C). Parity coverage is corpus = 38, not 41 (Amendment D).
- **Parity harness (`tests/ls_parity_harness.py`):** `usage_percent` removed from the PENDING-UNIT set (absent in corpus; a percentage, not unit-bearing — Amendments C/D); `available_total` / `used` / `unit` / `entitlement_value` stay quarantined until `number_with_unit` is implemented. Doc cites corpus = 38.

### Notes
- The `{value, unit}` verdict holds only while the generic candidate matches bespoke's header-unit-drop; capturing header units (`unit_from_coalesce_source_name`) would change the baseline and must be re-grounded.
- Review before transform code — transform implementation is the next step, not started here.

## 2026-06-13 (test — ADR-0016 parity harness for License Summary)

**Branch:** `main`. Harness only — **no transform layer, no LS conversion, no bespoke-LS deletion, no user-facing change.** Suite 1095 passed (+11). The acceptance gate for the later LS de-bespoke is in place; transform implementation NOT started.

### Added
- **`tests/ls_parity_harness.py`** — reusable semantic `CanonicalArtifact` comparator + a bespoke-pipeline baseline (`parse → persist(write_legacy=False) → adapt`, side-effect-free) + a pluggable candidate seam (`bespoke_candidate`, today the bespoke pipeline; the generic recipe output plugs in here during the conversion). Parity definitions are exactly ADR-0016 §4: semantic equivalence (sections / items / field values — not raw-JSON, timestamps, or artifact ids); `registration_code` / sensitive fields compared in **masked** form with both-sides-masked asserted (a raw value is a FAIL); computed summaries compared semantically; **three outcomes — pass / fail / PENDING-UNIT**, where unit-bearing fields (the `number_with_unit` domain, ADR-0016 Open Item 1) are quarantined — never silently skipped, never auto-failed.
- **`tests/test_ls_parity_harness.py`** (11 tests) — fixture discovery, the bespoke baseline over the corpus, comparator reflexivity, and targeted tests proving the comparator genuinely detects value / section / summary differences, quarantines a differing unit field as PENDING-UNIT, and FAILs on a raw (unmasked) sensitive value — so a green run is meaningful, not vacuous. Plus a pluggable-seam test (a degraded candidate is detected).

### Notes — baseline corpus findings (recorded before transforms exist)
- **41 real exports** under `data/imports/license_summary/` — **10 csv, 31 html**; **all 41 produce a `CanonicalArtifact`, 0 parse errors.**
- **3 produce no license rows** (documented, not a failure): two stray Security-Assessment HTML exports + the `cv_redesign_option_a_refined` mock are filed in the LS imports dir but are not license summaries.
- **Bespoke-vs-bespoke parity: 5067 pass, 0 fail, 1632 PENDING-UNIT** — comparator reflexive.
- **PENDING-UNIT field classes encountered** (feeds the `number_with_unit` grounding probe next): `used` (544), `available_total` (360), `unit` (360), `entitlement_value` (184), `usage_percent` (184).
- **Transform layer NOT started** — ADR-0016 build order: this harness (step 2) precedes the transform layer (step 3); the `number_with_unit` return shape (Open Item 1) remains unresolved and is the next grounding probe.

## 2026-06-13 (docs — ADR-0016 Proposed: recipe transform layer)

**Branch:** `main`. Single docs commit; the reviewed draft's status set to **Proposed** at `docs/adr/0016-recipe-transform-layer.md`; README ADR range → 0001–0016. From the Piece-B recipe-feasibility inventory (two specimens: client_growth verdict **(a)** mis-authored, no model change; License Summary verdict **(c)** needs model work before any de-bespoke).

### Added
- **ADR-0016 (Proposed) — recipe transform layer: declarative shaping without code-in-data.** Adds bounded, declarative shaping to the recipe model: `source: []` coalesce/first-present (report-version / license-type column variance), a closed named-transform registry (`trim`, `null_if_empty`, `to_integer`, `to_float`, `number_with_unit`, `mask_registration_code`), a `metadata_pairs` section format (deterministic exact-label→value only — no regex/fuzzy/nested), and minimal computed sections (`row_count` / `distinct_count` / `grouped_count`).
- **Four named invariants** keep it from becoming code-in-data:
  - **Closed Registry** — transforms invoked only by name from a platform-owned closed registry; no arbitrary-expression escape hatch (this is what keeps transforms data, not code).
  - **Compile-Validated** — every transform name is validated at publish against the registry; an unknown name is a compile error and the template cannot publish.
  - **Security-by-Construction** — a field tagged *sensitive* MUST carry its mandatory transform via a gate-enforced mapping (initial: `registration_code` → `mask_registration_code`); a missing required transform is a compile error, never a silent gap.
  - **Reusable, not subject-specific** — every transform is a general capability usable by any subject; LS is the first consumer, not the owner.

### Notes
- **Relation to ADR-0015:** extends it — the recipe is the template's extraction definition, and the transform registry becomes part of the ADR-0015 compile gate's validation contract. The gate is therefore built **transform-aware from its first implementation**, which reorders the redesign: the transform-layer design (this ADR) precedes the compile gate. Builds on ADR-0010 (rules) and the Fix-3/Fix-4 identity/provenance work.
- **Deliberate bet, recorded:** the strongest evidence today is a single subject (LS); accepting this ADR accepts that bet, bounded by the closed-registry design.
- **Build order (fixed):** ADR Proposed → parity harness (all 41 real LS exports) → transform layer → LS conversion → delete bespoke LS (only behind parity proof).
- **Open item:** `number_with_unit` return shape is unresolved and blocks that transform, pending a grounding pass over the 41 exports.
- Proposed, not Accepted — Accepted requires one full implementation cycle (transform layer + parity harness passing all 41 exports + bespoke LS deleted with no regression), the same standard as ADR-0015.

## 2026-06-13 (refactor — ADR-0015 redesign slice 1: delete the vestigial artifact-approval path)

**Branch:** `main`. Commits `e9acf2e`, `6971734`, `a12d59e`, `03f00c4`; suite 1075 passed. Subtractive cleanup only — NO compile gate, NO profile schema, NO schema drops (those are later slices). Verdict from the design pass: the redesign is mostly subtraction; this slice removes the vestige.

### Removed
- **Web `?stage=1` artifact-staging branch** (`quick_hc.py`): no UI ever set it (grep zero); imports now always write the artifact to the scoped store directly. Dropped unused `import uuid`.
- **`execute_approval`'s artifact branch** (`db/staging.py`): it did `store.save_artifact` — identical to direct collect, which already writes scoped + context-gated (D5) + provenance-verified (Fix 4). `execute_approval` is now proposal-only (the ADR-0015 compile/publish boundary); a non-proposal row raises `ValueError`. Dropped the dead `CanonicalArtifact` import and the D5/0033 coherence machinery inside it.
- **MCP `save_staged_artifact` tool**: no producer (the AI holds no token and the probe persists nothing — ADR-0008), and its only consumer was the deleted artifact-approval. Removed the tool, registration, and `create_staged_artifact`/`ValidationError` imports. `approve_staged_artifact` stays (publishes proposals).
- **`/quick-hc/staging` approved-artifact column** + the two approve handlers' context dance / dead artifact-result branches; page is a proposals-only review queue.
- **Tests:** the artifact-approval tests deleted with the behavior (delete, not gut) — ?stage=1 tests, the D5 + evidence-context approval-coherence sets, the MCP save/approve-artifact sets, the staging-route artifact-approve set, the core-solidity artifact case; proposal-flow + D5 write-gates + Fix-4 round-trip stay green.

### Notes — DOCUMENTED-DEAD (for the later, separate schema-drop cleanup; named so it's discoverable)
- **`staged_artifacts` columns now inert** (no production writer remains; proposals leave them NULL by design): `customer_id`, `project_id` (migration 0033), `engagement_id`, and the pre-existing-unused `verification_status` / `verification_sources` / `verification_notes` / `verified_at` / `user_edits_json` / `filter_state_json`. Safe to `DROP COLUMN` in a deliberate later migration — **not dropped this slice**.
- **`db.staging.create_staged_artifact`** — no production caller now (test-only). Kept as a generic primitive; candidate for removal with the schema cleanup.
- **Accepted-but-unused params:** `execute_approval(customer_id, project_id, store)` and MCP `approve_staged_artifact(customer_id, project_id)` — kept so callers were undisturbed this slice; drop in a follow-up.
- **`.staging-badge-approved`** CSS — trivially-dead after the approved column removal.
- Slice 1 of the ADR-0015 redesign. Next slice is the only construction: attach the **compile gate** (allocation-table validation / Catalog Purity / Publication Integrity) to the now-clean `execute_approval` publish boundary. Profile schema lands later, with the redesign — not before.

## 2026-06-13 (feat — Fix 4: declared-vs-wire CommCell ID guard, provenance not workflow)

**Branch:** `main`. Commits `6607caf`, `413abdb`; suite 1102 passed. The verification-result home (pre-Fix-4 foundation) is now populated by a declared-vs-wire CCID guard — recorded as evidence, never enforced.

### Added
- **`identity.verify_commcell_id`** — compares `normalize(declared)` vs `normalize(wire)` and returns the four ArtifactSource verification_* values. Four verdicts, attested ≠ unverifiable (never merged): **verified** (both present, equal), **mismatch** (both present, differ), **attested** (declared present; source can't provide a wire value), **unverifiable** (declared absent/un-normalizable, or source could prove but wire value missing). The record preserves BOTH normalized inputs (`declared_normalized=.. / wire_normalized=..`), the wire source, and verified_at. Never raises, never blocks.
- **`result_to_artifact` wiring**: the CC-API (rest_commserve) tier reads the wire `commcell.commCellId` (raw int) from the single-object card record (`_wire_commcell_id`); every other source type → attested/unverifiable. Both sides normalized (raw compare would false-mismatch hex vs decimal). Stamped on ArtifactSource ONLY — nothing in subjects/subject_sources/staged_artifacts.status/ai_notes. On mismatch the artifact still assembles and persists.
- **Surfacing (display only):** `artifact_to_view` exposes a `verification` block; the collect route flashes the verdict (mismatch loud, unverifiable warning, verified brief, attested silent) after a successful persisted collect; MCP `evaluate_subject` returns the verdict. None of these gate collection.

### Notes
- Tests (+20): the four-verdict matrix, attested-vs-unverifiable distinctness, no-false-mismatch (337f vs int 13183 → verified; 337F vs 337f → verified), both inputs persisted, CC-API integration, csv → attested, round-trip, and the surfacing (view/evaluate/flash-does-not-block).
- **Step-1 correction carried forward:** the brief's "commCellId=2 is an internal sequence id distinct from the licensed CCID" is wrong per ADR-0007 §189 — there is one CCID field (`commcell.commCellId`); the default lab's is genuinely 2. The guard reads that field.
- **License Summary not wired in v1** — LS collects through a bespoke service path (not result_to_artifact), so its artifacts carry no verdict (view/evaluate handle None). Follow-on.
- **FIRST LIVE VALIDATION (done):** collected `environment` against HomeLab/gw02 — wire `commcell.commCellId` = **337f**; HomeLab declared = **337f**; Fix 4 verdict = **verified** (the first live provenance verdict). This resolves the ADR-0007 §189 open question: gw02 fronts a **337f** CommServe, distinct from the `.129` lab box's `commCellId=2`; the earlier `33f7` was a transposition typo in the declared value, not an architectural ambiguity — there is one CCID field (`commcell.commCellId`), as Step 1 found, and the two hosts simply front different CommServes.

## 2026-06-13 (feat — evidence-context + verification-result foundation, pre-Fix-4)

**Branch:** `main`. Commits `a6cccd3`, `754287e`, `a3d0dd0`; suite 1082 passed. An inert enabler for Fix 4 — NO declared-vs-wire check, NO approval authority flip, NO D5 weakening.

### Added
- **Migration 0033** — `project_id` on `staged_artifacts` (additive/nullable). Completes the creation-context stamp (customer_id from D5 + project_id now). `create_staged_artifact` accepts/writes it; the web `?stage=1` path stamps the full explicitly-selected (customer, project). subject_proposal rows stay catalog-global (both NULL by design).
- **Verification-result home on `ArtifactSource`** — `verification_status`, `verification_sources`, `verification_notes`, `verified_at` (optional, default None; names mirror the `staged_artifacts` columns). Nothing populates them yet — Fix 4 does. Confirmed round-trips through ArtifactStore; pre-existing artifacts load with them None.

### Changed
- **`execute_approval` coherence-reads the row's creation context:** a stamped row's (customer, project) is AUTHORITY — the approval-supplied context is checked against BOTH stamped customer_id and project_id (mismatch on either → ContextMismatchError, row untouched). Legacy NULL-stamped rows keep D5 behaviour unchanged (approval context authority; customer_id back-stamped, project_id not). Behaviorally identical to D5 on the match case; the "approval stops re-asking" UX change stays deferred.

### Notes
- Tests (+10, `tests/test_evidence_context_foundation.py`): project_id stamped on web artifact rows / NULL on proposals; approval match/mismatch(project)/mismatch(customer)/legacy-NULL/refusal-without-context; ArtifactSource defaults + full round-trip + pre-fields-artifact load.
- No verdict is written anywhere; nothing touches subjects / subject_sources / staged_artifacts.status / ai_notes.

## 2026-06-13 (feat — Fix 3: identity-schema split, the three identity values kept distinct)

**Branch:** `main`. Commits `1fc94d2`, `6a4ae97`, `8a52589`; suite 1072 passed. Splits the conflated customer identity into distinct, normalized fields (ADR-0015 profile layer) — the foundation Fix 4 (report-identity / dataset-GUID portability, #34) consumes.

### Added
- **Migration 0032** — five additive customers columns: `connection_url` (reach URL), `commserve_name` (human/product label, e.g. CS01), `registration_code` (license verifier), `rp_server_url` + `rp_scoping_id` (optional Reports Plus server + resolved scoping id). URL-shaped-only data move: `commcell_hostname` values matching `http(s)://` migrate to `connection_url`; non-URL values stay put, flagged (`db.customers.legacy_hostname_review_flags`). No backfill guesses — `default.commcell_id='SMOKE-TEST-CS'` and `test_customer_1.commcell_id='33f7'` (suspected transposition of 337f) left for manual fix.
- **`cvhealthcheck/identity.py`** (leaf): `normalize_commcell_id` (canonical lowercase hex; hex F9EE5 == decimal 1023717 -> `f9ee5`; junk raises), `normalize_connection_url` (schemeless -> https://, validated; kills the `gw02:4433`-read-as-scheme class), `effective_connection_url` (connection_url with legacy fallback, junk -> None).
- **Customer form** identity fields teaching reach-vs-identity: "Connection URL (WebServer/gateway)", "CommServe name", "CommCell ID (licensed, hex or decimal)", "Registration code", "Reports Plus server URL", "Reports Plus scoping ID". Detail page shows the split; customers list shows the flag banner.
- **Tests** (+20, `tests/test_identity_schema_fix3.py`): normalization (hex≡decimal, scheme repair, junk), migration data-move (re-runs the real UPDATE loaded from the .sql), conflation fix, writer-freeze.

### Changed
- **Writers re-pointed; `commcell_hostname` is READ-ONLY-LEGACY** (frozen, never written; dropped in a later cleanup that also removes the read fallback): customers routes + `db.customers.create_customer`/`update_customer` write `connection_url` + the identity columns; `commcell_id` stored normalized. Bad input at the customers page re-renders with a form error, never a 500/garbage.
- **Readers** at the three connect sites (basic `/login`, quick_hc collect, quick_hc_api `/api/login`) read `connection_url` with the legacy fallback, validated.
- **Conflation fix (honest-empty):** the collect stamp sets `commcell_name <- commserve_name` (None when unset — **never** `customer_name`) and `commcell_id <- normalized CCID or None`; the silent `commcell_name=customer_name` conflation is gone.

### Fixed
- **`start.sh`** no longer regenerates the session secret per start (D5 amplifier — landed alongside; persists to `data/.secret_key`, gitignored).  *(carried from the D5 entry; noted here as the same-session amplifier.)*

### Notes
- Live validation on `data/app.db`: migration applied, both URL hostnames moved to `connection_url`, `commcell_hostname` frozen, flagged CCIDs untouched (zero flags). Edit form renders all six identity fields; a schemeless save (`gw02:4433`) normalized to `https://gw02:4433` and a decimal CCID (`1023717`) to `f9ee5`, with `commcell_hostname` unchanged. Fabricated test values were restored — HomeLab carries no guessed identity data.
- **Later cleanup (own commit):** drop `commcell_hostname` + remove the read-time fallback in `effective_connection_url` and the three connect sites, once no row needs the legacy value.
- `commcell_hostname` write-path retirement makes the column safe to drop; `company_guid` left entirely untouched (Step-1 found zero consumers; unproven — no rename on suspicion).

## 2026-06-13 (feat(context) — D5: the Context Integrity invariant is ENFORCED at the write layer)

**Branch:** `main`. Commits `ef6adfb`, `a533da3`, `425136c`, `261f7d8`; suite 1052 passed. ADR-0015's **Context Integrity** invariant — *a customer-data write may only occur against an explicitly selected context; absence of explicit selection is an error, never a silent default* — is now enforced, not aspirational.

### Added
- **The enforcement primitive** (`ef6adfb`): `require_active_context()` in `web/active_project.py` returns (customer_id, project_id) ONLY when explicitly selected this session and raises typed `NoExplicitContextError` otherwise — it never consults the Default fallback. Typed errors live in the new leaf `cvhealthcheck/context.py` (`NoExplicitContextError`, `UnknownContextError`, `ContextMismatchError`) so db/ and web/ share the vocabulary without db importing web. The module docstring documents the read/write split: `get_active_project`/`resolve_default_project` survive for READ paths only.
- **The write gates** (`a533da3`): collect, fixture-collect, import, artifact delete, version pin, the LS scoped saves (`_require_project_store` at the data layer + early route gate), and MCP `delete_subject` (artifact half requires explicit, row-validated customer/project params; the catalog half stays context-free by design — commented asymmetry). One web-layer translation (`_context_required_response`): "Select a customer and project before collecting/importing/deleting." (flash, or JSON 409 for X-Inline).
- **Approval requires context as an input** (`425136c`): `execute_approval`'s artifact branch takes explicit customer_id + project_id (validated against existing rows; store constructed internally; `store` kwarg demoted to test-only). Stamp coherence: stamped-for-X-approved-under-Y → `ContextMismatchError`, nothing written; NULL-stamped legacy rows are back-stamped with the approval context (recorded in `ai_notes`). Staging writes stamp `customer_id` (web `?stage=1` from the gate; MCP `save_staged_artifact` validates caller-asserted ids). `propose_new_subject` stays NULL by design — Catalog Purity, commented as intent. `make_default_project_store` lost its last caller and was **deleted**.

### Fixed
- **Session-amplifier** (`261f7d8`): `start.sh` no longer regenerates `CV_SECRET_KEY` per start — the key persists in `data/.secret_key` (mode 600; env override wins), so a restart no longer invalidates every session cookie and silently reverts the active context. The gitignore was verified NOT to cover dotfiles under `data/` and the pattern was added in the same commit.

### Notes
- Tests: 30 new in `tests/test_context_gate_d5.py` — per choke point: no context → typed error and nothing written (tripwire monkeypatches prove the writes are unreached); with context → lands in exactly (customer, project); approval refuse/mismatch/back-stamp matrix; reads keep the fallback unchanged. Existing route/approval tests updated to select explicit context (new `explicit_context` conftest fixture).
- Live check (fresh session, no cookie): anonymous collect → 302 + the clean prompt; artifact store byte-unchanged (no Default write). Authenticated fresh-browser check: Michiel.
- Found along the way: `staged_artifacts.customer_id` carries an FK to `customers` — the back-stamp/stamp writes get a structural guard for free.

## 2026-06-12 (fix(isolation) — Fix 2: the unscoped global-file layer is retired)

**Branch:** `main`. Commits `1892dd8`, `ab13f34`, `c9487e1`, `7e93c12`, `1c343c7`; suite 1022 passed. Closes the "new project shows old data" leak (2026-06-12 isolation audit): the scoped canonical store is now the ONLY data source for the workspace.

### Fixed
- **Legacy-loader fallthrough removed** (`1892dd8`): an empty scoped store renders the honest not-collected state — never another customer's last collection from the global files. Regression tests: `tests/test_fix2_scoped_isolation.py` (empty store → all six legacy subjects `nodata`; cross-project artifacts don't leak; scoped artifacts render only for their project).
- **CommCell header reads the scoped environment artifact** (`ab13f34`) — was the global `commserv.json`, cross-customer in every project's banner.
- **Global `commserv.json` write retired** (`c9487e1`): `get_commcell_identity` is payload-only; the unauthenticated `/quick-hc/commcell` cache view renders honest-empty. **Supersedes** ADR-0007's "raw payload remains as provenance" clause (recorded in the commit body); environment's collect semantics are otherwise unchanged.

### Removed
- **The legacy report layer — deliberate, on record** (`7e93c12`): `/quick-hc/report`, `quickhc/report_service.py`, `quick_hc_report.html`, the workspace report affordances, and the orphaned `overview_service.py`. Rationale: unused, output not customer-presentable, and **the presentation layer is a future project on the ADR-0015 template/profile/runtime foundation** — its absence is a decision, not a loss. It was also the isolation leak's second surface (its builders read the same global files).
- **The frozen global files** (`1c343c7`, disk-only/gitignored — full path list in the commit body): LS/SA catalog artifacts + registries, the four metrics JSONs, `backup_job_summary_latest.json`, `commserv.json`. All reproducible by re-collection into the scoped store.
- **The code they orphaned** (`1c343c7`): the six legacy loaders + five legacy view builders + their private helpers, the `reportsplus/security_assessment.py` wrapper, the `cvhealthcheck/metrics` package, and dead `shared.py` imports — every symbol multiline-grep verified zero-consumer first.

### Notes
- The description-override display (`resolve_tile_description`) turned out to be consumed ONLY by the deleted legacy builders — it was wired into `_build_generic_subject` so the workspace Save button keeps working for system subjects.
- The BJS detail page (`/quick-hc/backup-job-summary`) tolerates the deleted global file (renders empty); its repoint-or-retire is a follow-up decision, not part of this fix.
- Live smoke (anonymous): `/quick-hc/report` → 404, `/quick-hc` → 200, `/quick-hc/commcell` → 200 honest-empty. Authenticated fresh-project browser check: Michiel.

## 2026-06-12 (docs — ADR-0015 Proposed: template/profile/runtime separation)

**Branch:** `main`. Status flip of the reviewed draft (`90433e7`); README ADR range updated to 0001–0015.

### Added
- **ADR-0015 → Proposed** (`docs/adr/0015-template-profile-runtime.md`, reviewed by Michiel + external reviewer): the subject-catalog lifecycle separates **template definition** (transferable, customer-free), **project/customer profile binding** (per-customer resolved ids, parameters, customer-assertion rules), and **runtime-only execution artifacts** (re-resolvable GUIDs, DOM ids, paging mechanics) — allocated element-by-element in a normative table. Names four invariants: **Context Integrity** (customer-data writes require explicit context selection — never a silent default), **Publication Integrity** (the object reviewed is the object executed; published templates are immutable, rule bindings move out of the template blob), **Template Catalog** (a template transfers to a brand-new customer without modification), and **Catalog Purity** (review criterion: the catalog is understandable/reviewable/transportable without access to any customer). Relations: **amends ADR-0013** (subjects-as-foundation gains the draft→template→profile lifecycle), **tightens ADR-0010** (rules registry gains a template-vs-profile axis), **hardens ADR-0014** (the typed RP source becomes the enforced authoring path).

### Notes
- Cross-reference annotations on ADR-0013/0010/0014 themselves are deliberately deferred until ADR-0015 reaches Accepted.

## 2026-06-12 (fix(catalog) — delete_subject reaps orphaned rules; dead-code sweeps; 12-rule registry cleanup)

**Branch:** `main`. Commits `39758f1`, `16d0dec`, `5b91fbf`; suite 1070 passed.

### Fixed
- **`delete_subject` reaps rules its deletion orphaned** (`39758f1`). It cascaded catalog rows, staging rows, and the stored artifact, but never the rules registry — a rule whose only binding was the deleted subject's sections survived as inert residue. Reap semantics, scoped deliberately: candidates are only the rule ids referenced by the deleted subject's own bindings (captured before the binding rows are deleted, by JSON-walking every `{"ref": …}` — row_rules + metric/card shapes, one ref model per ADR-0010); a candidate is reaped iff it now has zero bindings across ALL subjects AND zero `rule_overrides` rows. In-transaction direct DELETEs (`db/rules.delete_rule` commits mid-flight, so it is not callable from inside `delete_subject`'s all-or-nothing transaction); the return gains `rules_reaped`. Four regression cases (`tests/test_delete_rule_reaping.py`): bound-only-to-deleted → reaped; shared-with-survivor → survives, and reaps when the last binder goes; orphaned-with-override → kept; authored-but-unbound-elsewhere → never swept by an unrelated delete.

### Removed
- **Dead security-assessment imports in `web/routes/shared.py`** (`16d0dec`): `SecurityAssessmentImportError`, `export_security_assessment_registry`, `import_security_assessment_upload` — orphans of the 2026-06-05 dev-SA retirement — plus `quick_hc.py`'s dead re-imports of ImportError/Service from `.shared`. **Correction to the prior read-only pass:** `SecurityAssessmentService` was NOT dead — `quick_hc_api.py:142` consumes it live (`SecurityAssessmentService().get_canonical()` behind `/api/security-assessment/canonical`); the earlier zero-consumer conclusion missed multiline `from .shared import (…)` blocks. Its re-export stays, with a comment naming the live consumer.
- **Orphaned `.lnav-sm` CSS** (`5b91fbf`): base rule + `:hover` in `quick_hc.css` — left behind when their only user (the workspace "Dev tools" link) was removed in the 2026-06-05 `/development` retirement; flagged there as the follow-up, closed here.

### Notes
- **DB maintenance (not a code commit):** swept 12 dangling rules from the `app.db` registry — `csc_ua_package_cache_not_zero`, `csc_cache_sp_below_min`, and 10 `ccprop_*` — residue of the deleted `commserve_software_cache` / `commcell_properties` subjects. Each deleted through the app's own `delete_rule` path, guarded by a fresh zero-binding + zero-override re-assert immediately before deletion; all confirmed pure registry residue (`bindings_stripped=0` each). Registry now holds the 16 live rules.
- **#36 scoping (read-only):** the SA canonical read is already generic (`get_canonical()` = `load_latest_artifact("security_assessment")` on the standard ArtifactStore), but License Summary is structurally welded to the SA module — its import machinery runs on the SA `ArtifactRegistry` alias (`artifact_registry.py` → `license_summary/service.py`) and it shares 7 SA model classes (`license_summary/models.py`). #36 is an LS-coupled decision, not an API cleanup.
- **Process lessons (recorded):** single-line greps miss multiline parenthesized imports — prove a symbol dead by grepping the bare name repo-wide; and never gate a commit on piped pytest (`pytest | tail` takes tail's exit code — `16d0dec` initially landed red and was amended).

## 2026-06-11 (fixes — wide-table horizontal scroll; dispatcher active-version resolution)

**Branch:** `main`. Commits `2eee3c4`, `6359f57` (same day as the ADR-0014 entries below; logged here as their own entry).

### Fixed
- **Horizontal scroll for wide table sections in /quick-hc** (`2eee3c4`). Table sections wider than the tile (the 29-column `storage_policy_copy_jobs` exposed it) were clipped by `.sec-tile{overflow:hidden}` (the border-radius clip) with no scrollbar. The column-table branch of `secBody` now wraps the `<table class="wl-table">` in `<div class="tbl-scroll">` at both emission sites (data rows + the ADR-0009 empty header shell); the verdict legend stays outside the wrapper. CSS: `.tbl-scroll{overflow-x:auto;max-width:100%}` + `.tbl-scroll .wl-table{width:max-content;min-width:100%}` — natural width inside the wrapper, never narrower than the tile, so narrow tables render unchanged. `view_mode 'card'`, kv-table, and workload tables untouched (verified by executing `secBody` against all seven shapes). **Deferred:** sticky first column (opaque sticky-cell background vs the semi-transparent row borders + excluded-tile opacity interaction).
- **Import extracts with the subject's ACTIVE version, not version 1** (`6359f57`). `extract_file`'s explicit-subject_id branch (the upload route's call shape — it never passes a version) defaulted `v = version or 1`, so once a superseding v2 existed, imports silently read the superseded v1's instructions: HTML failed with "missing selector or title_match" (a v2-only key), CSV "succeeded" with 0 rows (v1's empty `column_map`). First hit by `storage_policy_copy_jobs` v1→v2 — the catalog's first superseding subject. The branch now resolves the highest `status='active'` version (the same selection rule as `get_subject(version=None)` and the recognition engine's `status='active'` join); an explicit `version` still pins; no active version is a loud named error. Regression tests: `tests/test_dispatcher_active_version.py`.

### Notes
- The dispatcher bug's approval flow was ruled out (it writes the new version's source rows correctly) and the extractors' per-version queries were already correct — they were fed the wrong version. REST collect and the recognition path were already version-correct by mechanism.

## 2026-06-11 (verify — ADR-0014 end-to-end pass, live; throwaway subject cleaned up)

**Branch:** `main`. Completes the entry below: the `reportsplus_dataset` source type is verified live, full loop.

### Notes
- **E2E pass (green):** throwaway subject `audit_trail_rp_dataset` (bare-GUID AuditTrailDataset, `parameters: {userlist: [1, 2]}`, `column_map`, `limit: 25`) was AI-proposed into staging (`stage_e739bbd5…`), independently reviewed (Claude web) and human-approved, then collected through the new "REST / Reports Plus dataset" source tab: 25 rows rendered with canonical column names (`id`/`time`/`user`/`severity_level`/`operation`/`details`), artifact stamped live `rest` with `collected_at` set. The pass exercised migration 0031 on the live DB, persist-time address validation, collect dispatch, metadata-backed parameter-name validation, `parameter.userlist[]` encoding, shared row-shaping, and the artifact tail — every new seam, one loop.
- **Cleanup:** `delete_subject('audit_trail_rp_dataset')` removed the catalog rows (1 version), the stored artifact, and the staging record. No residue.
- **Next (parked, human-triggered):** the ADR-0006 D5 re-assessment precondition ("after Fix 4 ships") is now met; License Summary / security_assessment conversion remains parked until Michiel asks.

## 2026-06-11 (feat — ADR-0014 reportsplus_dataset source type: declarative, directly-addressed Reports Plus datasets)

**Branch:** `main`. Closes the last known source-family gap in the zero-code authoring path (HANDOVER Fix 4). Preceded by a Step-0 reconciliation that retired the brief's other three fixes as already-shipped/not-reproducible/superseded (HANDOVER commit `9567f5f`), and by the ADR-0014 curl-first gate run live through the ADR-0008 loopback.

### Added
- **ADR-0014** (Accepted, with two acceptance amendments): Reports Plus dataset extraction as a dedicated source type `reportsplus_dataset` — rejected overloading `rest_command_center_api` (different API family) and extending the ADR-0003 `rest` discovery protocol (would fork its name-as-canonical-reference contract). Amendments: composite address verified live 2026-06-06 against CS01 (gate = re-confirmation; deviation = regression, not design fork); artifact mapping resolved to `SourceType.rest` (extraction type carries the addressing grammar, source type carries the transport).
- **Gate findings** (`docs/research/adr0014-gate-findings.md`; probes via `scripts/adr0014_gate.py`, captures gitignored under `data/catalog/adr0014_gate/`): for report-bound datasets only `datasets/{reportGuid}:{entryGuid}/data` works — the second half is the per-report `dataSets.dataSet[]` entry `guid`, NOT the inner `dataSetGuid` (bare `dataSetGuid` → 500 errorCode 15020); bare GUIDs serve standalone datasets; parameters are `parameter.<datasetParamName>` / repeated `parameter.<name>[]` and are honored (`userlist[]=999999` filtered 782→0); **unknown parameter names are silently ignored** (782 rows, no failure) — the silent-misconfiguration risk that shaped the extractor's loud validation; the envelope (`cacheId`/`columns`/`records`) is the same one `CommvaultSession` already parses.
- **Migration 0031** — widens the `subject_sources.source_type` CHECK to admit `reportsplus_dataset` (0027's FK-safe, id-preserving rebuild; no seed rows — subjects of this type are MCP-authored per ADR-0014 D4).
- **`extractors/rp_dataset_address.py`** (leaf, mirrors `cc_endpoint.py`): `validate_rp_dataset_address` (bare GUID or `{reportGuid}:{entryGuid}`, REQUIRED — no default, lowercase-normalized) and `encode_dataset_parameters` (bare declared names → `parameter.<name>` / `parameter.<name>[]`). Applied at persist (`create_subject_from_proposal` — invalid/missing address rolls the whole proposal back) and re-applied at collect (defence-in-depth).
- **`extractors/reportsplus_dataset.py`** — `ReportsPlusDatasetExtractor`: per-section GETs against the one declared dataset via the existing `CommvaultSession.fetch_dataset` (pagination + envelope normalization reused; the composite address is an opaque path segment), row-shaping via the shared `shape_dataset_rows`, conformance + section-spec carrying as the `rest` path. **Validates declared parameter names against the dataset's declared `GetOperation.parameters` before any fetch** (new `CommvaultSession.get_dataset_metadata`; both address forms serve `/datasets/{address}`) and fails the whole collection on an undeclared name or unreadable metadata — a typo must not collect wrong data successfully.
- **Wiring:** `/collect` dispatch third branch (`_has_reportsplus_dataset_source`); `result_to_artifact` maps the type to `SourceType.rest` (live → `collected_at`); registry label "REST / Reports Plus dataset" + canonical-id map + shared collect URL; source-panel Collect action (`requiresSession`); `propose_new_subject` docstring vocabulary (the source kind, the address grammar incl. the entry-guid-not-dataSetGuid trap, bare-name parameters).
- **Tests** (+33: `test_rp_dataset_address.py`, `test_reportsplus_dataset_adr0014.py`, and a round-trip guard `test_proposal_field_roundtrip.py` from the Step-0 reconciliation): address/parameter policy; persist round-trip + rollback; extract + artifact tail; parameter encoding; loud undeclared-name / metadata-failure / fetch-failure cases; shared row-shaping.

### Changed
- **`RESTExtractor._fetch_section` row-shaping hoisted** to module-level `shape_dataset_rows` (behavior-preserving) so both dataset-envelope extractors share one shaping vocabulary.
- **HANDOVER.md** reconciled to repo state (the brief's Fixes 1–3 closed: shipped `819c723` / not-reproducible-now-guarded / superseded by `d1860c4`); License Summary & security_assessment ("Health") conversion **parked** — ADR-0006 D5 and ADR-0013 stand; re-assess the D3 blockers only after this feature ships.

### Notes
- The brief's "leading-slash 401 errorCode 5" probe quirk did not reproduce: both slash forms 401 identically on a stale token and the leading-slash convention works on a fresh one. The observed 401s were stale-token artifacts — root cause: `flask run --debug`'s reloader restarts the child process on any `.py` edit in the tree, wiping the ADR-0008 in-memory token store (the documented single-process constraint). Operational rule: finish `.py` edits before connecting; `.md`/`.json` writes don't trigger the reloader.
- v1 bound, deliberate: one `reportsplus_dataset` source row per subject (the `subject_sources` UNIQUE key) = one dataset per subject; sections are different projections/queries (own `fields`/`orderby`/`limit`/`parameters`) of that dataset. A multi-dataset subject is a revisit, not a silent extension.
- `scripts/adr0014_gate.py` capture-slug wart (long addresses truncate to one slug and overwrite) left as-is; the findings doc is the durable record.

## 2026-06-05 (refactor(web) — retire the vestigial /development hub)

**Branch:** `main`. Removes the last dev-workspace remnant; all its sub-tools were retired in prior passes.

### Removed
- **`GET /development`** — deleted `web/routes/development.py` (the file was down to this one route) and dropped its `from . import development` line from `routes/main.py`. No blueprint to unregister: route modules share one `main` blueprint, so removing the import is the deregistration. No orphaned imports — the view's `bp`/`login_required`/`render_template` are shared `shared.py` exports used by every other route module.
- **`templates/development.html`** — the hub page (deleted whole). It had degenerated to a husk: a "tools retired" subtitle and two links that both pointed back at `/quick-hc`.
- **Both inbound "Dev tools" links:** the `base.html` sidebar-footer link (including its now-dead `{% if 'development' in ep or 'security_assessment_registry' in ep %}` is-active clause — both endpoints are gone) and the `quick_hc.html` workspace left-nav link.
- **`.sidebar-dev-link` CSS** (3 rules: base, `:hover`, `.is-active`) in `styles.css` — styled only the removed footer link.

### Changed
- **Docs:** trimmed the stale "Internal / development pages" section of `README.md` (it listed `/api/test`, `/reportsplus/*`, `/lab-readiness`, `/metrics/client-growth` — all already-retired URLs, and it never listed `/development` itself). Left dated snapshots, `data_flow_audit.md`, the ADR-0004 phase plan, and `architecture/quickhc.md`.
- **Tests:** dropped the `/development` route-map assertion from `test_platform_foundation.py` (kept the `/quick-hc*` ones); deleted `test_development_routes_require_login` and `test_development_routes_render_after_login` (both had narrowed to a single `/development` loop); dropped the now-unused `token_store` import from the file.

### Notes
- **`lnav-sm` was not shared after all.** The brief expected the workspace "Dev tools" link's `lnav-sm` class to be shared with other nav items, so the instruction was to remove only the `<a>` line and keep the class. On removal it turned out the Dev tools link was its **only** user, leaving `.lnav-sm` (`quick_hc.css:139,144`) as **orphaned dead CSS**. Left in place this pass per the explicit scope; flagged as a one-line follow-up cleanup (symmetric with the `.sidebar-dev-link` rules removed here).
- After this, there is **no "Dev tools" entry point anywhere** — correct, since the page was empty. `/development` now 404s; `/quick-hc` and `base.html` pages render with no `BuildError`.

## 2026-06-05 (refactor(web) — retire the entire dev Security Assessment surface)

**Branch:** `main`. Removes the dev SA cluster + its two registry siblings; closes the consumer-sweep backlog from d5d4227.

### Removed
- **The whole dev SA route surface in `web/routes/development.py`:** bare view `GET /security-assessment`, legacy alias `GET /reportsplus/security-assessment`, upload `POST /security-assessment/import`, and both registry siblings `GET /security-assessment/history` + `GET /security-assessment/registry-export`. The file's SA section empties out; **14 now-unused imports dropped** (only `bp`, `login_required`, `render_template` remain, used by `/development`).
- **`templates/security_assessment.html`** — the dev SA page (deleted whole); it was the sole renderer.
- **Dev-workspace SA link + section** (`templates/development.html`) and corrected the page subtitle (it no longer claims the SA tools "remain here pending their dedicated retirement pass").

### Changed
- **Consumer sweep run (the d5d4227 backlog item): clean.** Grepped MCP (`src/cvhealthcheck/mcp/`), CLI (`cli.py`), and `scripts/` for the sibling endpoints + their underlying functions (`SecurityAssessmentService.get_history`, `export_security_assessment_registry`). No MCP/CLI/automation consumer — only the dev routes (removed), tests, and docs. So the siblings retired with the cluster instead of staying backlogged.
- **5 import-behavior tests converted to direct-function unit tests** (`test_security_assessment_import.py`). The dev `/security-assessment/import` route that drove them is gone, and the workspace SA upload routes through the **generic extractor** (`_unified_dispatcher_upload` → `extract_file` → canonical store), *not* `import_security_assessment_upload` — so the route could not be repointed without changing the code path under test. The tests now call `import_security_assessment_upload` directly, keeping the importer's behavioral assertions (returned artifact, raw file saved, legacy-not-written, and the importer-emitted messages "No file selected." / "Unsupported file type." / "HTML import produced no findings."). The two "HTML/CSV import completed" strings were the dev route's success flash (route layer, not the importer) and fall away with the route round-trip.
- **Tests trimmed:** deleted `test_flask_page_uses_imported_artifact_when_present` (legacy dead-data reader — the page read `latest.json`, which fresh imports no longer write); deleted the two sibling-only registry tests (`test_hidden_history_and_registry_export_endpoints_work`, `test_internal_registry_routes_require_login` — the latter had no non-sibling branches left after d5d4227, so "strip" became "delete"); dropped the `GET /security-assessment == 200` line from `test_platform_foundation.py`'s render loop.
- **Docs:** trimmed `docs/subjects/security_assessment.md` (removed the internal history/registry tooling block + the dev-page URL) and dropped the now-stale `API_MAPPING.md` SA history/debug-read-API row. Left the dated `docs/review_2026-05-20.md` snapshot and CHANGELOG history.

### Notes
- **New backlog — retire-vs-keep `import_security_assessment_upload`.** With the dev route gone, the bespoke SA importer (`import_security_assessment_upload` + the `parse_security_assessment_html/csv` parsers) is **route-orphaned** — the workspace SA upload uses the generic extractor. It's now exercised only by the converted unit tests. Whether to retire it (and its parsers) or keep it as a supported library function is deferred pending a consumer sweep of `parse_security_assessment_html/csv` (which may have other callers).
- **`/api/security-assessment/canonical` untouched** — it lives in `quick_hc_api.py`, reads the canonical project store, and still returns the canonical artifact (verified 200).

## 2026-06-05 (refactor(web) — retire the dev-only /development/security-assessment-registry view)

**Branch:** `main`. Removes a self-contained read-only debug surface; no live consumer touched.

### Removed
- **`GET /development/security-assessment-registry`** (`web/routes/development.py`) — the internal registry-history debug view (`security_assessment_registry_view`). Read-only; listed registry-backed artifact/import-run/report-run metadata via `SecurityAssessmentService.get_history`.
- **`templates/security_assessment_registry_history.html`** — its template (deleted whole).
- **Dev-workspace link** (`templates/development.html`) — the "Security Assessment Registry (internal)" `<li>`.

### Changed
- **Tests trimmed, not deleted, where shared.** `test_platform_foundation.py`: dropped the registry path from the two `/development` login-guard loops (the `/development` assertions stay). `test_security_assessment_registry.py`: removed the `viewer_response` branch from `test_internal_registry_routes_require_login` (history/export branches kept); deleted the view-specific `test_internal_registry_view_renders_artifact_table`.
- **Docs** — dropped the stale `/development/security-assessment-registry` line from `docs/subjects/security_assessment.md`.

### Notes
- **No orphaned imports.** Unlike the `/connections` pass, every one of `development.py`'s 18 shared imports is still used by another route in the file (`SecurityAssessmentService`, `_security_assessment_registry_filters`, `render_template`, `url_for` all have other callers), so no import line was dropped. `base.html:49`'s `'security_assessment_registry' in ep` active-state clause was left as-is (still matches the surviving `security_assessment_registry_export` endpoint; harmless).
- **Backlog — UI-orphaned JSON endpoints kept this pass.** The deleted template was the sole UI link to two sibling routes, which remain registered and tested but are now reachable only by direct URL: `GET /security-assessment/registry-export` and `GET /security-assessment/history`. Retiring these is deferred pending a consumer sweep (confirm no MCP/CLI/automation reads them) — backlogged, not dropped.

## 2026-06-05 (refactor(web) — retire /connections; header pill modal is the sole connect surface)

**Branch:** `main`. Surface consolidation; no change to the auth chokepoints themselves.

### Removed
- **`GET /connections` and `POST /connections/disconnect`** (`web/routes/basic.py`) — the standalone connection page and its disconnect action. The now-unused `get_current_username` import was dropped from `basic.py` with them.
- **`templates/connections.html`** — the page template (deleted whole).
- **"Connections" sidebar nav link** (`templates/base.html`) — removed; the sidebar-footer "Sign out" button is unchanged.
- **`tests/test_connections_page.py`** — the 5 route tests from 7214ea7 (deleted whole), since the page they covered no longer exists.

### Changed
- **ADR-0008 updated** — the connect/disconnect surface it originally described as a dedicated `/connections` page is now the header connect pill / its modal (`/api/login` to connect, `/logout` to disconnect). Both references in the ADR ("the connection UI", "the same connection page later") were amended.

### Notes
- **Same chokepoints, fewer surfaces (ADR-0008).** The pill modal already routes through the canonical token lifecycle: Connect → `/api/login` → `login_to_commvault` + `set_current_token` (publishes into the in-process `token_store`); Disconnect → `/logout` → `clear_current_token()`; badge state → `/api/auth/status` → `is_authenticated()` → `get_active_token()` (same `token_store` slot the retired page read via `status()`). No bespoke connect path existed on the page, so removing it drops UI only — no behavior.
- **Disconnect is not single-surfaced.** The sidebar-footer "Sign out" button (`base.html`) also POSTs `/logout`, so the pill modal is the sole *connect* surface but shares the *disconnect* path with the footer button. Both hit the same `clear_current_token()` chokepoint — no drift risk; left as-is by design.
- **Connection target was always informational.** The page's read-only target panel showed the env-managed `~/.cv-healthcheck-env` CommCell URL, which was never UI-editable; nothing editable was lost.

## 2026-06-05 (refactor(catalog) — export category vocabulary to shared db.categories module)

**Branch:** `refactor/category-vocabulary`. Behavior-preserving refactor; no functional change.

### Changed
- **`_LABELS` lifted to an importable module** — the function-local category-vocabulary dict inside `db/subjects.py::create_subject_from_proposal` now lives in `db/categories.py` as `CATEGORY_LABELS` (slug → display) plus a derived `CATEGORY_VOCABULARY` (frozenset of slugs). `create_subject_from_proposal` imports and uses it; the display-label expression is unchanged.
- **Disjointness invariant now references the real category vocabulary** — `tests/test_domain_labels_migration.py` imports `CATEGORY_VOCABULARY` from `db.categories` instead of a hand-mirrored copy, so the Domain Labels disjointness test (`category ∩ domain-label == ∅`) tracks the authoritative term set and fails by construction if a colliding category is ever added.

### Notes
- **Behavior-preserving:** `CATEGORY_LABELS` equals the former `_LABELS` exactly; known categories keep their display labels, unknown categories are still accepted and title-cased. **`category` is still not validated at authoring** — that backlog item remains open (this refactor only relocated the vocabulary; it added no validation).
- **New backlog line:** `quickhc/registry.py` carries per-tile `category_label="…"` literals (e.g. "Identity", "Licensing") — a separate set of hand-written category display strings not yet sourced from `CATEGORY_LABELS`. Candidate for the same consolidation onto the shared source.

## 2026-06-05 (feat(catalog) — backfill domain labels for active subjects (Domain Labels Phase 4))

**Branch:** `feature/domain-labels`. Data migration + test maintenance only; no schema change, no source change, `category` untouched.

### Added
- **Migration `0030_domain_label_backfill.sql`** — the approved sparse label set (ADR-0012), 8 assignments onto each target's **active** version row:
  - `security_assessment` → compliance, governance
  - `audit_trail` → compliance, governance
  - `users` → governance
  - `metrics_reporting` → governance
  - `backup_job_summary` → backup
  - `client_growth` → reporting
- **`tests/test_domain_label_backfill_migration.py`** (6 tests) — seeded targets carry their planned labels; non-targets unlabeled; categories unchanged; idempotent re-apply; absent targets are safe no-ops.

### Changed
- **Test maintenance** (the backfill makes the seeded test catalog non-empty): repointed Phase-2 read tests off the now-labeled seeded subjects and made the filter assertions **consistency-based** (expected computed from the association data, not hardcoded), so neither this backfill nor a future one re-breaks them; the zero-member case now seeds a fresh *valid* vocabulary term (distinct from the unknown-label path); the Phase-1 "association seeded empty" test became a structural no-orphans check; migration-count guardrail `29 → 30`.

### Notes
- **Backfill via data migration**, consistent with the Phase-1 vocabulary seed. It resolves each target by `subject_id` + `status='active'` at apply time (not a hardcoded id), and `INSERT OR IGNORE` makes it idempotent.
- **Labels attach to each target's active version at backfill time and, per ADR-0012, do not follow a future supersede** — a re-proposed version re-authors its own labels (the new version row starts unlabeled).
- **Runtime-only finding:** 4 of the 8 rows target **AI-authored runtime subjects** (`audit_trail`, `users`, `metrics_reporting`) that exist only in the real `app.db`, not in the migration-seeded catalog. So on a fresh catalog `0030` labels only the **3 seeded targets** (4 rows); the 4 runtime rows land only where those subjects exist (the real catalog), verified by the post-commit live read smoke — they are not exercised by the test-DB suite.
- **Backlog (catalog reconstructibility):** the above means the seeded migrations + `0030` cannot fully reconstruct the labeled catalog from scratch — part of the label state depends on runtime-authored subjects. This is the same gap the **Subject Inventory convergence** initiative targets (migrate the system/AI subjects into the database Report Inventory as seed data); once those subjects are seed-represented, `0030`-style backfills become fully reconstructible. Tracked there.

## 2026-06-05 (feat(mcp) — accept + validate domain labels on propose_new_subject (Domain Labels Phase 3))

**Branch:** `feature/domain-labels`. Authoring path + persist point + tests; no backfill, `category` unchanged, read path unchanged.

### Added
- **Optional `labels` arg on `propose_new_subject`** — domain labels (the additive axis, ADR-0012) authored alongside a subject. De-duped (order-preserving) and **loud-validated against the vocabulary at authoring time, before staging**: an unknown label raises `ValueError` naming the offender(s) and lists the valid labels, and **nothing is written** (all-or-nothing). Accepted labels travel in the proposal JSON.
- **Persist at approval** — `create_subject_from_proposal` writes the accepted labels into `subject_domain_labels` keyed on the new `subjects.id`, inside its existing transaction. `INSERT OR REPLACE` + the Phase-1 FK `ON DELETE CASCADE` means re-proposing a version replaces its label set (no stale rows, no duplicates); superseding attaches labels to the new version's row without bleeding into the superseded one.

### Notes
- **Two-guard model (ADR-0012):** loud authoring-side validation at `propose_new_subject`, and the structural `subject_domain_labels.label` FK at persist. The lifecycle forces the split — `propose_new_subject` only stages a proposal; the `subjects` row (and its id) is created later at approval. There is deliberately **no second vocabulary pre-check** in `create_subject_from_proposal`; a stale/hand-crafted proposal that reaches approval with a bad label hits the FK, and a targeted 2-line wrap re-raises that one `IntegrityError` as `ValueError("proposal references a label not in the vocabulary")` (the transaction rolls back — nothing written).
- The read filter stays graceful-empty (Phase 2, unchanged); only the authoring path is loud.
- **Backlog — `category` is not validated at authoring.** `propose_new_subject` accepts any `category` and `create_subject_from_proposal` silently title-cases unknowns via the function-local `_LABELS` (display only, no rejection). Left unchanged here per ADR-0012 / scope (category behavior is out of scope for Domain Labels); recorded so the finding isn't lost. The loud label guard stands on its own ADR-0012 authority — it is a new pattern, not a mirror of category.
- **Backlog (carried):** export the `category` `_LABELS` constant (function-local in `db/subjects.py::create_subject_from_proposal`, against a free-text column) to a shared importable source, so the disjointness invariant references one source of truth rather than a mirrored copy in the test.

## 2026-06-05 (feat(mcp) — domain labels in list_subjects + read-side label filter (Domain Labels Phase 2))

**Branch:** `feature/domain-labels`. MCP read path + tests; no authoring/backfill, `category` unchanged.

### Added
- **`list_subjects` returns `labels`** — each subject carries a `labels` list of domain-label slugs (always present; `[]` when none), populated from a single bulk query (`db/domain_labels.subject_labels_map`, `subject_row_id` → ordered slugs; avoids N+1).
- **`list_subjects(label=…)` read filter** — returns only subjects carrying that label.

### Notes
- The filter is **graceful-empty by design**: an unknown or zero-member label returns `[]` with no exception. Authoring-side reject-unknown is deferred to Phase 3.
- Additive only — `id` is fetched to key the label map and popped before returning, so the output gains `labels` and nothing else; `category`/`category_label` unchanged.
- Labels attach to `subjects.id` (the per-version row); `list_subjects` does not collapse versions, so superseded versions carry their own labels.
- The two-axis classification (`category` single/primary vs `labels` many/additive, disjoint vocabularies) is recorded in **ADR-0012** (committed separately).

## 2026-06-05 (feat(catalog) — domain-label vocabulary + association schema (Domain Labels Phase 1))

**Branch:** `feature/domain-labels`. Schema + tests only; no MCP/authoring change, no subject labeled.

### Added
- **Migration `0029_domain_labels.sql`** — a second, additive classification axis for subjects. `domain_label` controlled-vocabulary table (`label` PK, `display_label`, `description`, `sort_order`), seeded with exactly four terms: `compliance`/Compliance, `governance`/Governance, `backup`/Backup, `reporting`/Reporting. `subject_domain_labels` many-to-many association (`subject_row_id` → `subjects.id` `ON DELETE CASCADE`; `label` → `domain_label.label`; `UNIQUE(subject_row_id, label)`; index on `label`). No association rows seeded — backfill is a later phase.
- **`db/domain_labels.py`** — read accessors over the vocabulary: `list_domain_labels(db)` (ordered rows) and `domain_label_vocabulary(db)` (slug set). Reused by later phases (authoring-side reject-unknown, MCP read path) and the tests.
- **`tests/test_domain_labels_migration.py`** (9 tests) — migration applies + recorded; seeded exactly four; association empty; FK rejects unknown label and unknown subject row; valid insert succeeds; `UNIQUE` blocks duplicates; accessor returns the four terms; the disjointness invariant.

### Notes
- The `domain_label` vocabulary is **disjoint** from the `category` vocabulary (`identity/security/licensing/performance/operations/storage`) → the two axes are **additive-only by construction**; a test asserts the intersection is empty and must never silently regress.
- **Finding / backlog:** the `category` vocabulary is a **function-local `_LABELS` constant** inside `db/subjects.py::create_subject_from_proposal`, against a **free-text `category` column** (no DB enum). The disjointness test therefore *mirrors* those six terms as a documented reference set (plus a data-driven cross-check of `SELECT DISTINCT category FROM subjects`). Backlog: export `_LABELS` to a shared importable source so the invariant references one source of truth rather than a mirrored copy.
- The FK on `subject_domain_labels.label` is the structural guard that an unknown label can never be associated; the authoring-side reject-unknown check is deferred to Phase 3 (adding it now would be dead code crossing the phase boundary).

## 2026-06-04 (docs — README pass 2: relocate internals to owned docs, drop migration history, shrink to overview+index)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source touched. Exactly three new files created.

### Added
- **docs/architecture/quickhc.md** — owns Quick HC architecture: product surface (HealthCheck/Customers/Advanced/Development), subjects, the unified routing model (import/collect/report routes), report composition + customer-facing report rules, the UI shell, the registry/tile framework (`TileDefinition`/`SectionDefinition` contract, module boundaries, the add-a-subject extension model), business-state separation (`app.db` vs import registries vs canonical artifact storage), and scope/boundaries.
- **docs/subjects/security_assessment.md** — owns the Security Assessment subject: REST/HTML/CSV sources, the collect→normalize→persist→render model, module layout (`src/cvhealthcheck/security_assessment/`), sections list, the `reportsplus/checklist.py` normalizer role, the registry/persistence model, and the canonical JSON read endpoints.
- **docs/subjects/license_summary.md** — owns the License Summary subject: CSV/HTML/XLSX/REST-206 sources, module layout (`src/cvhealthcheck/license_summary/`), the artifact + persistence model, the detail-table + workload/category section model, and the missing-values policy (links PATTERNS).

### Changed
- **README.md** rewritten to its final shape — Project Overview → Scope → Strategic Direction → Data Sources & Collection Strategy → High-Level Architecture (links the three new docs) → Quick Start → Configuration → CLI → Web UI → Documentation Index. Reduced from 759 to ~250 lines. The Documentation Index now describes every home truthfully (README/ROADMAP/PROMPT/HANDOVER/CHANGELOG/the three new docs/API_MAPPING/HEALTHCHECK_MATRIX/DATA_SOURCE_MAPPING/PATTERNS/lab_environment/data_flow_audit/adr).
- **docs/lab_environment.md** gained the Reports Plus inventory login-token workflow (the `POST /commandcenter/api/Login` → `.login_token` → `CV_LOGIN_TOKEN` flow + the `probe_*_with_login_token.sh` scripts + CLI token precedence), moved out of the README Phase 2 section (its proper home).
- **HANDOVER.md** refreshed: cleared the stacked stale per-session sections, fixed the dead `README:368` reference for the SA source-precedence issue (now points to `HEALTHCHECK_MATRIX.md` + `docs/subjects/security_assessment.md`), and recorded the settled doc tree (ROADMAP strategic, PROMPT constitution, README pass 1+2, three new docs). Genuine engineering next-actions preserved (scope-label MCP tool; the `cache_configuration` transpose binding; the card-shape re-stages; API_MAPPING `/v4/servergroup`; DATA_SOURCE_MAPPING decision).

### Removed
- **README.md** "Phase 2: Reports Plus Discovery" and "Phase 2.4: Lab Readiness Baseline" historical narrative — already logged in CHANGELOG `2026-05-11` (Phase 2.1 catalog persistence, 2.2 prioritization, 2.3 candidate validation, 2.4 lab-readiness baseline). Per the mixed-section rule, only the historical narrative was deleted; the operational CLI how-to (`reportsplus reports/datasets/catalog/prioritize/validate-candidates`, `lab readiness`, output paths, validation statuses, readiness states) was preserved under README "CLI".
- **README.md** large internals sections, now owned by the three new docs: Quick HC Foundation, Customer-Facing Report Composition, UI Foundation, Quick HC Framework, Current Limitations, Business State and Persistence, Reports Plus Security Assessment, License Summary Artifact Pipeline.

### Notes
Relocate → verify → delete throughout: each new doc was written and its content confirmed present before the corresponding README section was removed. Module paths were verified against the tree before documenting — Security Assessment and License Summary modules live at `src/cvhealthcheck/security_assessment/` and `src/cvhealthcheck/license_summary/` (not under `reportsplus/`, which only holds `checklist.py`). New docs are present-tense architecture (settled fact), with temporal/status language ("now", "current refactor direction", "next logical phase", per-session narration) actively stripped during relocation.

## 2026-06-04 (docs — PROMPT.txt restructured to a timeless operating constitution)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; reorganization — no KEEP rule's meaning changed.

### Added
- **PROMPT.txt** two new governance sections: **DECISION HIERARCHY** (explicit user instructions override docs; user is final approval authority; the 6-level conflict-authority order: user instructions → Accepted ADRs → PROMPT → ROADMAP → HANDOVER → CHANGELOG; observations/tool-output/reviews advisory only) and **DECISION MAKING** (9-step pre-change checklist: understand behavior → tests → ADRs/roadmap → extend-generic → declarative → escalate uncertainty → verify-first → grep-first → docs-over-chat).

### Changed
- **PROMPT.txt** restructured into a timeless operating constitution. Final order: PROJECT PURPOSE → ARCHITECTURE PRINCIPLES → PROJECT BOUNDARY → DECISION HIERARCHY → DECISION MAKING → ENGINEERING RULES → DO NOT → VALIDATION REQUIREMENTS → DOCUMENTATION MODEL → START OF SESSION → SESSION WRAP-UP. PROJECT PURPOSE tightened to two paragraphs. PROJECT BOUNDARY moved up into the governance cluster. The IMPORTANT STRATEGIC DIRECTION section was split: "must not assume direct CommServe access" was already a DO-NOT bullet (deduped); "collection must support remote/customer-side execution" folded into ARCHITECTURE PRINCIPLES → collectors/; the rest (central-platform/S3/modes-as-direction) is already covered by ROADMAP and was removed. Timeless navigation principles folded into ARCHITECTURE PRINCIPLES → web/.
- **PROMPT.txt** ENGINEERING WORKFLOW section folded away: "commit at every green checkpoint / don't batch unrelated changes" merged into the existing SESSION WRAP-UP commit bullet; "Claude Code does the heavy lifting, user reviews/steers" kept as one line under DECISION MAKING.
- **README.md** gained a "Data Sources & Collection Strategy" section (relocated from PROMPT's REPORTS PLUS / METRICS STRATEGY + COLLECTION STRATEGY — Reports-Plus-as-primary-source, cross-environment caveats, the REST→datasets→reports→uploads→SQL-last order, and the avoid-list).
- **docs/PATTERNS.md** gained pattern 5 — the metric-visualization Chart.js payload convention (route → server-side payload → metric_detail.html → Chart.js), relocated from PROMPT's METRIC VISUALIZATION.
- **docs/lab_environment.md** gained a "Lab Realism & Health-Rule Readiness" section (relocated from PROMPT's LAB ENVIRONMENT NOTES — minimal-lab limitations, what stays valid, and the pre-health-rule realism checklist).

### Removed
- **PROMPT.txt** implementation-state snapshots (all captured in README or obsolete): the "Current Quick HC items" inventory, the Security Assessment state block (report-336 path, "32 total checks…" counts, checklist.py path, legacy-GET-redirect, POST handlers), the License Summary state block, the "Current Quick HC platform notes" (TileDefinition fields, list_tiles(), canonical_view.py, subject_data_service.py fallback), and the "Current UI/product structure direction" item-lists (the nav *principles* were kept; the specific HealthCheck/Customers/Advanced/Development + Quick HC item names were removed). Also removed the OPERATING MODES / DAILY REPORTING / QUICK HEALTHCHECK / FULL HEALTHCHECK prose — already covered by README Strategic Direction and ROADMAP's Operating-Modes initiative.

### Notes
PROMPT is now state-free (no implementation snapshots, no file/function names except in the ARCHITECTURE boundaries). ROADMAP needed no edit — the operating-modes / central-platform / S3 direction was already present there. Pending (not in this commit's scope): HANDOVER.md line 27 still cites `README:368` for the Security Assessment source-precedence issue, a line removed in README pass 1 (`a9dd98e`); fix on the next HANDOVER refresh.

## 2026-06-04 (docs — README pass 1: strip session state, collapse lab setup, refresh doc index)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; thinning pass — no internals sections moved or deleted (deferred to pass 2).

### Removed
- **README** session/lab-run state: the "Session Validation" block (stale `483 tests passing` / "May 24, 2026 session" — current count is tracked in HANDOVER); the Security Assessment "Current artifact summary" counts (transient lab artifact state); the Security Assessment "Current unresolved issue" paragraph (REST/source-precedence — a live issue item, already captured in HANDOVER); and three UI-Foundation "now does X" per-session refactor narration paragraphs.

### Changed
- **README** "Lab Environment Connection Setup" collapsed to a pointer + a 3-line quick-connect; the full connection/token/login-helper/probe-script detail now lives in **docs/lab_environment.md** (no new file — appended a "Connection & Token Setup" section there with the env-file, token-file, login-helper, and probe-script steps that were genuinely unique to the README section).
- **README** "Architecture Documents" refreshed into a proper documentation index: added ROADMAP.md, PROMPT.txt, HANDOVER.md, and docs/lab_environment.md links; updated the ADR note from "0001 / 0002" to the current "0001–0011" range (links `docs/adr/`, no inline enumeration); kept DATA_SOURCE_MAPPING / API_MAPPING / HEALTHCHECK_MATRIX / PATTERNS / data_flow_audit.
- **README** "Strategic Direction" condensed: kept the three operating modes (one line each) and the no-direct-CommServe-access constraint; trimmed repetition and the S3-transport detail, pointing to ROADMAP for direction detail.

### Notes
Pass 1 deliberately leaves the large internals sections in place (Quick HC Foundation/Framework, Report Composition, UI Foundation, Current Limitations, Business State, Security Assessment, License Summary, Metric Charts, Phase 2, Phase 2.4 Lab Readiness) for a pass-2 relocation once the target docs/ tree is approved. The login-token curl workflow lives in the protected Phase 2 section and was left untouched.

## 2026-06-04 (docs — restructure ROADMAP as a strategic roadmap; principles → PATTERNS; status/changelog hygiene)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; structural reorganization — meaning preserved, no direction change.

### Changed
- **ROADMAP.md** — rebuilt as a strategic roadmap (Vision · Current State · Strategic Themes · Initiatives Now/Next/Later · Sequencing & Dependencies · Known Risks · Deferred Work). Rolled the old phase/task log up to capability/outcome level — completed sub-work is no longer enumerated here (that history stays in CHANGELOG). The evaluation-boundary debt is condensed into Deferred Work, keeping the "deliberate, not a defect" framing.
- **docs/PATTERNS.md** — relocated the enforceable principles the old ROADMAP carried into a new "Standing conventions (project invariants)" section: no ORM (raw SQL), `latest.json` compatibility/cache-only, file-based catalog (no DB for catalog), the License Summary missing-values policy, and SSL-verification-default-on. None were already stated in PATTERNS (verified by grep). These now live only in PATTERNS.
- **docs/adr/0011** — Status `Proposed` → `Accepted` (shipped this session: operators + comparator, Rule 2 authored + confirmed live).

### Fixed
- **CHANGELOG.md** — corrected a stray **future-dated** `## 2026-06-05` heading (today is 2026-06-04) to its real date `## 2026-05-25` (the entry's commits `c06309d`/`b873431`/`6e0b1ed` are all 2026-05-25); it's a real "unified-upload session 4" entry, so the date was fixed, not removed. Not reordered within the consolidation tail; the rest of the tail is left untouched.

### Notes
- **ADR 0003 and 0006 left unchanged** (flagged, not edited): both already carry a meaningful `## Status` header — 0003 "Implemented (with LS caveat)" (a deliberate nuanced status, not a bare gap), 0006 "Accepted (2026-06-01)". Neither lacked a status; an earlier reconciliation mis-reported them because it grepped only the inline `**Status:**` form, missing the `## Status` header form.

---

## 2026-06-04 (docs — Rule 2 confirmed live on /quick-hc)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only.

### Changed
- **HANDOVER.md** — flipped the Rule 2 note from the token-gated "expected UI result" assumption to a confirmed-live record: `commserve_software_cache` REST re-collected 2026-06-04, `cache_contents` renders 3 amber warning dots + 4 Findings (1 critical + 3 warning), criteria card shows the authored sentence. Token confirmed alive this session.

---

## 2026-06-04 (docs — add live-validated /v4/servergroup to API_MAPPING)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only.

### Added
- **API_MAPPING.md** — `/commandcenter/api/v4/servergroup` appended as the 4th ADR-0009 `rest_command_center_api` endpoint (PROVEN), now that it's been **live-captured 2026-06-04** via the ADR-0008 loopback (HTTP 200, `{"serverGroups": [...]}` — a collection of 21 group objects, each `{id, name, association, company, description, isSyncInProgress, serverCount}`; feeds the `server_groups` subject). This was the previously declared-but-unvalidated ADR-0009 acceptance-test endpoint. Existing rows unchanged.

---

## 2026-06-04 (ADR-0011 acceptance — Rule 2 authored on commserve_software_cache.cache_contents)

**Branch:** `feature/basic-healthcheck-report-output`. Runtime catalog + docs; no code change (the operators landed in `5ad8b64`).

### Notes
- Authored + bound **`csc_cache_sp_below_min`** (runtime, `data/app.db`, gitignored): `row_match` on `commserve_software_cache.cache_contents`, condition `service_pack version_lt "11.40.51"`, severity **warning** (Michiel's minimum + severity choices). `evaluate_subject` dry-run over the stored artifact: all **3 cached-SP rows (`11.40.47`) flag warning** — completes the ADR-0011 acceptance test. The live `/quick-hc` re-render is token-gated (a fresh Connect), not required for correctness. (All 3 rows are identical `11.40.47`, so this rule is all-or-none on real data; the lexical-trap ordering is exercised by the unit tests, not this data.)

---

## 2026-06-04 (feat(rules) — version-aware comparison primitive + version_lt/version_gte (ADR-0011))

**Branch:** `feature/basic-healthcheck-report-output`. **1014 passing** (was 1008; +6). Localized to the evaluative + authoring layers; **`result_to_artifact` untouched** (the boundary recorded as deferred debt in the prior entry).

### Added
- **`evaluative/coerce.parse_version` + `compare_versions`** — the standalone, importable version primitive (ADR-0011 D1/D2): `parse_version` normalizes a dotted string to a left-aligned integer tuple (max leading integer run, optional leading `v`/`SP` token ignored), `None` when there's no numeric component; `compare_versions` pads trailing 0s and returns −1/0/1, or `None` if either operand is unparseable. Lives in `coerce.py`, **not** `result_to_artifact`, so a future live-baseline evaluator reuses it.
- **`version_lt` + `version_gte` operators** (ADR-0011 D3 — only these two, no `gt`/`lte`/`eq`/`ne` yet). Added to the **single shared** `_KNOWN_OPS`/`KNOWN_OPERATORS` set (so authoring-validation and evaluation accept them together) plus an evaluation dispatch branch in `row_match`, and readable rendering in `format_conditions`.
- **D4 semantics:** an unparseable **rule literal** is rejected at authoring time by `validate_row_match_rule` (`db/rules.py`), same class as an unknown operator (a `{ref}` value is skipped — it's a column, not a literal). An unparseable **row value** evaluates to **not_evaluated** (grey) with a recorded reason — never a false good/critical. Implemented via a tri-state `_predicate_value` (True/False/None) + `_rule_row_state` + an unevaluable pass in `evaluate_section_rows`; reuses the existing `not_evaluated`/`in_scope` path, no new verdict, no `result_to_artifact` change.
- `tests/test_version_operators_adr0011.py` (+6): comparator grammar + ordering (incl. the lexical trap `11.40.9 < 11.40.51`, padding, unparseable→sentinel); authoring accepts a valid literal / rejects an unparseable one; evaluation splits below/at/above a minimum and greys an unparseable row (with reason); `version_gte` complement.
- `docs/adr/0011-version-aware-comparison-operators.md` (Proposed) committed with the feature.

### Notes
- **Verify-first findings:** operator dispatch is `row_match._eval_predicate` / now `_predicate_value` (`row_match.py:~234`); the authoring whitelist is `db/rules.validate_row_match_rule` (`:273`) consuming `KNOWN_OPERATORS` — which **is** `_KNOWN_OPS` (one shared frozenset, `row_match.py:55`), so a single edit covers both. The stored `commserve_software_cache.cache_contents` version column is **`service_pack`**; all three rows are **"11.40.47"** (WinX64 / linux-x8664 / linux-arm64) — a real Rule-2 minimum must be chosen to split them (e.g. `version_lt "11.40.48"` flags all; pick per intent).
- **No Rule 2 authored** (deferred to Michiel: severity + minimum are authoring choices). **The running `cv-healthcheck-mcp` caches modules** — it must be restarted (`pkill -f cv-healthcheck-mcp` + reconnect) before `save_rule`/`evaluate_subject` see the new operators.

---

## 2026-06-04 (docs — record evaluation-boundary as deferred architectural debt)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only.

### Notes
- Recorded deferred architectural debt (the evaluation boundary — some rule/verdict logic runs in `result_to_artifact`) as a new ROADMAP section; proceeding with the ADR-0011 version operators within the current structure, no refactor.

---

## 2026-06-04 (docs — link WORKFLOW from PROMPT, add push-confirm, retire artifact_schema_v1, track lab env doc)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source/schema/behavior change. Verify-first.

### Changed
- **PROMPT.txt** — two operational additions: (1) a one-line pointer in START OF SESSION to WORKFLOW.md ("Methodology, workflow stages, and historical lessons live in WORKFLOW.md — read it when doing architecture-sensitive work"); (2) merged WORKFLOW.md §10.1's **push-and-confirm** rule into the SESSION WRAP-UP push step — after pushing, verify the remote actually moved (`git status` in-sync / `origin/<branch>` HEAD matches local) before declaring done; "Pushed" is verified, not asserted. WORKFLOW.md was **not** edited.

### Removed
- **`artifact_schema_v1.md`** — retired (git history preserves it). It was a "v1 Draft" schema spec, superseded by the **live canonical artifact shape the engine enforces** (the Pydantic models — numeric metric values, `{id,label}` columns, item ids). Re-proved orphan first: zero structural/link refs; the only mentions were this CHANGELOG's own consolidation Note + the rolling HANDOVER, both non-blocking (history/handover, not dependencies).

### Added
- **`docs/lab_environment.md`** — the previously-untracked `docs/Lab_Environment v1.01.md` lab-environment draft, moved to the repo's lowercase-underscore naming and committed. **Secret-scanned before staging** (authtoken/bearer/access_token/refresh_token = value, JWT `eyJ…`, password/secret/`CV_PASSWORD_B64`/PEM) — **no pasted credentials found** (only documentation of token files/mechanics). Only one draft existed (the earlier `… copy.md` was already gone).

---

## 2026-06-04 (docs — add ADR-0009 validated Command Center API endpoints to API_MAPPING)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source/schema/behavior change. Verify-first; only endpoints with documented live-200 evidence were asserted.

### Added
- **API_MAPPING.md** — three ADR-0009 `rest_command_center_api` endpoints appended to the validated-endpoint table (existing 8-column format, host/shape in Notes per the table's convention), all **PROVEN** from live-200 validation earlier on 2026-06-04 via the ADR-0008 loopback against the lab CommServe `192.168.182.129:4433`:
  - `/commandcenter/api/commserv/audittrail` → `{auditTrailInfo:{retentionForCritical/High/Medium/Low}}` → `audit_trail` subject.
  - `/commandcenter/api/commserv/metricsreporting` → `{config:{…, cloud.serviceList[8]}}` → `metrics_reporting` subject.
  - `/commandcenter/api/commserv/addremovesoftware/commservesoftwarecache` → `{commserveSoftwareCache:{cacheFreeSpace, UaInfo.cacheContents[].softwareCacheServicePackDetails}}` → `commserve_software_cache` subject.

### Notes
- **`/commandcenter/api/v4/servergroup` was NOT added (declared, unvalidated).** ADR-0009 frames it as the *deferred* end-to-end acceptance-test capture, and CHANGELOG (earlier entry) records its shape as "unverified until a live capture" — no live-200 evidence exists. Skipped per the verify-first rule; left for a future live capture.
- **Verify-first / token state:** a re-probe of all four endpoints this session returned **HTTP 401** — the CS token is expired (whole-connection, every endpoint 401s), not an endpoint failure. The three additions rest on documented earlier-2026-06-04 live-200 validations (CHANGELOG entries + stored `rest_commserve` artifacts), and each row carries the stale-token caveat — consistent with API_MAPPING's existing PROVEN rows (e.g. Client Growth, which is PROVEN despite a current-token 401). No existing API_MAPPING content was reworded or restructured.

---

## 2026-06-04 (docs — consolidate doc tree: delete orphans, rehome workflow into PROMPT.txt)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source/schema/behavior change. VERIFY-FIRST: every claim below was proven by `grep` before acting.

### Removed
- **`HANDOVER_TO_CODE.md`, `design/CODEX_HANDOVER_v2.md`, `cv_healthcheck_context.md`** — shipped/superseded one-off handover & context notes. The 0-ref grep showed their only inbound references were this review's own bookkeeping (the prior HANDOVER candidate table, refreshed this session, + a CHANGELOG history note), not structural/content dependencies — so they are true orphans. git history preserves them.
- **`docs/Workflow.md`** — the per-session checklist, removed after rehoming its content into PROMPT.txt (the file was already deleted from the working tree).

### Changed
- **PROMPT.txt** — merged the two session-workflow elements it lacked (it already covered the rest across ENGINEERING RULES / DO NOT / VALIDATION REQUIREMENTS / DOCUMENTATION MODEL / START OF SESSION / SESSION WRAP-UP, so per "merge, don't duplicate" nothing else was added): a start-of-session **git-state check** (`git status / branch / log --oneline -5`) and a **validation-honesty** rule ("report the exact failing command… never pretend success"). DEVLOG-free; the existing "Do not reintroduce DEVLOG.md" note is unchanged.

### Notes
- **STOPPED on `DATA_SOURCE_MAPPING.md` (kept, not folded)** — it is an operating-mode *source-strategy* doc (explicitly "does not define… implementation"), not validated-API behavior. Folding it into API_MAPPING.md (the validated-API home) would change that doc's meaning; its unique content (per-subject source preference across Quick HC / Daily / Full + Operating Mode Guidance) overlaps conceptually with ROADMAP's "Future Architecture: Operating Modes," not API_MAPPING. Left in place; README:450 reference unchanged. Recommend: keep as-is, or fold into ROADMAP (a separate decision).
- **Step 5 (gitignore/untrack build noise) was a no-op** — `.gitignore` already has `.pytest_cache/` and `*.egg-info/`, and `git ls-files` showed none tracked.
- **`artifact_schema_v1.md` is now a true orphan** (its only inbound ref was the deleted `cv_healthcheck_context.md`) — left in place, flagged for later refresh/retire.
- Left untouched per scope: `docs/adr/*`, `docs/PATTERNS.md`, `docs/data_flow_audit.md`, `docs/research/*`, `docs/refactor_unified_upload_*` (active WIP), `memory/*`, root `WORKFLOW.md` (methodology doc), and the unrelated untracked `docs/Lab_Environment v1.01*.md` drafts.

---

## 2026-06-04 (docs — remove retired DEVLOG.md from docs/Workflow.md)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source/schema/behavior change. Reconciles the per-session workflow checklist with the DEVLOG-retired decision (PROMPT.txt; retired 2026-05-25).

### Changed
- **`docs/Workflow.md`** (the per-session "Follow this workflow…" checklist — newly added to the repo; distinct from the root `WORKFLOW.md` methodology doc) — removed the two `DEVLOG.md` references:
  - **Read-docs-first list:** dropped `DEVLOG.md`; added `HANDOVER.md` (start-here) + `CHANGELOG.md` (running log); kept README/ROADMAP/API_MAPPING/PROMPT.
  - **Documentation-updates list:** replaced the `DEVLOG.md` bullet with `CHANGELOG.md: what changed, validation results, commit hash` + `HANDOVER.md: rolling forward note for the next session`; left the ROADMAP/API_MAPPING/README/PROMPT "only if…" bullets intact.
- No other content in the file changed.

### Notes
- The earlier "WORKFLOW.md — no DEVLOG refs" review was about the **root `WORKFLOW.md`** (a methodology/philosophy doc with no doc-lists, genuinely DEVLOG-free). The DEVLOG instruction lived in this separate **`docs/Workflow.md`** checklist, which was not in the repo at review time.
- **Other (active) DEVLOG references left for separate scope:** `docs/adr/0007-…:121` (historical ADR — don't rewrite), `cv_healthcheck_context.md:13` (stale snapshot, already an archival candidate). Historical/retirement mentions in PROMPT.txt + CHANGELOG stay.
- **Flagged, not changed (out of scope):** `docs/Workflow.md` §5 still shows `git add .`, which conflicts with this project's explicit-staging discipline; and there are now two workflow docs (root `WORKFLOW.md` vs `docs/Workflow.md`) worth reconciling.

---

## 2026-06-04 (docs — documentation review & hygiene pass)

**Branch:** `feature/basic-healthcheck-report-output`. Docs-only; no source/schema/behavior change. (Recorded here, not in a DEVLOG — DEVLOG.md was retired 2026-05-25, per PROMPT.txt; this file + HANDOVER are the log.)

### Changed
- **README.md / ROADMAP.md** — corrected the one factual drift the review found: the "no scoring or recommendations yet" limitation predated ADR 0010. Now reads "no recommendations yet; scoring is limited to row-scope evaluation rules on table subjects (ADR 0010), not the Reports Plus subjects." No other prose touched.

### Notes
- **Reviewed** every tracked `*.md`/`*.txt` (excl. `venv/`, `.git/`, and auto-generated `*.pytest_cache/README.md` + `src/*.egg-info/*.txt`). Ports (5001), paths (`~/dev/cv-healthcheck`), and commands in README verified correct. PROMPT.txt is an accurate stable primer (incl. the still-true "DEVLOG/docs-handover retired" note). The canonical docs (CHANGELOG/HANDOVER/HEALTHCHECK_MATRIX/ADRs 0001–0010) are current.
- **Flagged for Michiel's decision (NOT changed):** (1) API_MAPPING.md is missing the ADR-0009 live-validated Command Center endpoints (`/commandcenter/api/commserv/audittrail`, `…/metricsreporting`, `…/addremovesoftware/commservesoftwarecache`, `…/v4/servergroup`); (2) the subject enumerations in ROADMAP's Phase-3 capability snapshot don't list the new CC-API subjects (server_groups / audit_trail / metrics_reporting / commserve_software_cache) — left as historical snapshots; (3) a set of shipped/superseded handover & context notes proposed for archival (see HANDOVER). No architecture/decision conflicts found.

---

## 2026-06-04 (fix(rules) — bind path scopes to the active version + recognizes transpose key/id targets)

**Branch:** `feature/basic-healthcheck-report-output`. **1008 passing** (was 1002; +6). Two coupled fixes in `db/rules.py` (authoring/validate path only; the collection/read path and the engine are untouched).

### Fixed
- **Active-version scoping (the reported bug).** `validate_row_match_rule`'s bind block resolved the bound section's `section_type` (and `_section_column_ids`) with an **unscoped** `WHERE subject_id=? AND section_id=?`. `subject_sections` holds one row per version, so `.fetchone()` returned the lowest-rowid (oldest) version — and binding a row rule to `commserve_software_cache.cache_configuration` (card v1–3 → **table v4**, v4 active) was wrongly rejected as `'card'`. The bind block now resolves the **active version once via `get_subject`** (the same helper the collector uses) and scopes both lookups with `AND subject_version = ?` / `AND src.subject_version = ?` — mirroring `load_subject_row_rules`/`load_subject_section_scope`. A subject with no active version raises a clear error.

### Added
- **Transpose key/id are valid rule targets.** With the lookup now scoped to v4, `_section_column_ids` validates targets against v4's `table.columns` (display = Setting/Value only). A row rule on a transpose property table legitimately targets the stable `key`/`id` (the locked "target key, never label" principle), so `_section_column_ids` now also admits the transpose rows' **implicit** columns — `id`, `key`, `label`, `value` — when the section's extraction block has `table.transpose`. **Targetability and display are decoupled**: the implicit keys are valid *targets* but are NOT added to the *displayed* columns (display stays driven by `table.columns`); the line is drawn entirely in `_section_column_ids` (target validation), with no change to `result_to_artifact`, the materializer, or the engine.
- `tests/test_bind_version_scoping.py` (+6): bind succeeds on the active (table) v4 although the unscoped query still returns v1's `'card'`; `_section_column_ids` returns the active version's columns only (no cross-version union, no v1 `free_space` leak); a `key`+`value` rule binds end-to-end while a bogus target is still rejected; no-active-version raises; single-version table bind unchanged (regression).

### Notes
- **`bind_rule` (the WRITE, `:192-197`) was deliberately left unscoped** (the task marked it optional). It still writes the `{ref}` into every version's binding incl. superseded — harmless dead data (collection reads only the active version's binding, which gets the ref), so the goal "bind to v4 succeeds and fires" is met. Scoping it to the active version is a recommended follow-up (no downside; just stops the dead writes).
- Why existing rules never hit the bug: `audit_trail`/`server_groups`/`users` are single-version; `metrics_reporting` is 2-version but its bound section types are stable across versions. `commserve_software_cache` is the first subject that is multi-version **and** changed a bound section's type across versions.

---

## 2026-06-04 (fix(view) — unify the table verdict legend to one order; supersedes the 5a40e1e split)

**Branch:** `feature/basic-healthcheck-report-output`. **1002 passing** (unchanged count; the two split-legend tests were replaced by three unified ones). Render-only (JS legend content); no model/view/engine/rule/binding change.

### Changed
- **One shared verdict legend for EVERY table section** (`quick_hc.js`, columns-mode table branch): **good · warning · critical · not evaluated · info** (exactly this order). The `5a40e1e` two-legend split (a property legend *with* info vs a data-table legend *without*) is removed — `legendDots` no longer branches on `sec.view_mode === 'property'`; the `propLegend`/`dataLegend` consts are gone.
- **Rationale:** any table's unruled rows fall through to the info-blue dot (`vdotClass(null) → 'vdot-info'`), not just the property table — e.g. `cache_contents` is a plain `columns` data table whose rows show info-blue. So info belongs on every table legend; the `5a40e1e` cut was wrong. Collapsed to one.
- `tests/test_transpose_property_table.py`: replaced the two split-legend assertions with — the unified legend order good/warning/critical/not evaluated/info (info present + not evaluated present); the split is gone (`view_mode === 'property'`/`propLegend`/`dataLegend` absent from the JS); and the dot-fallback + card-routing regression guard.

### Notes
- **`view_mode:"property"` stays** (model + `result_to_artifact` unchanged) as the discriminator for the future stacked-tile render — it just **no longer drives the legend**.
- **Lock honored:** `not_evaluated` (grey) and `info` (blue) remain **separate legend entries with separate colours** (`e0aa3287`) — never merged. Dot colours, the `vdotClass(null)→'vdot-info'` fallback, the 1-row `view_mode==='card'` card path, row layout, and the STATUS column are all untouched.

---

## 2026-06-04 (feat — "property" table view_mode: transpose section gets the property verdict legend)

**Branch:** `feature/basic-healthcheck-report-output`. **1002 passing** (was 997; +5). Presentation carry (model + collection + view + JS); **no engine/builder/rule/binding change**, no dot colours or verdict computation touched.

### Added / Changed
- **`TableSection.view_mode` gains `"property"`** (`models.py`) alongside `columns`/`card` — a third presentational value on the existing discriminator (no new field; omit-when-default serializer unchanged, so non-property tables stay byte-identical).
- **`result_to_artifact`** sets `view_mode="property"` on a **transpose** section (gated on the existing `spec.get("transpose")`); every other table section keeps its prior value (`card` opt-in, else default `columns`).
- **`canonical_view`** already forwards `sec.view_mode` (`:137`) — `"property"` passes through to the JS section object untouched (no change).
- **`quick_hc.js`** columns-mode table branch: when `sec.view_mode === 'property'`, the legend is **good · info · warning · critical · not evaluated**; every other table keeps the unchanged data-table legend (**good · warning · critical · not evaluated**). **Legend content ONLY** — layout, the STATUS column, dot rendering, the `vdotClass(null) → 'vdot-info'` fallback, and the 1-row `view_mode==='card'` card path are all untouched. "property" does not route to the card path.
- `tests/test_transpose_property_table.py` (+5): transpose section serializes `view_mode=="property"` through model + canonical view; a non-transpose data table stays `"columns"` (omitted default); the property legend is exactly good/info/warning/critical/not evaluated (ordered, info present); the data-table legend is unchanged (no info — regression guard); the info-blue fallback + card routing are untouched.

### Notes
- **Why a transpose property table wanted its own legend:** it renders through the columns-mode table branch, and its unruled rows fall through to the info-blue dot (`vdotClass(null)`), so info is a real verdict state on it — but the data-table legend omits info. The fix surfaces info in the legend for property tables only.
- **Locks honored:** `not_evaluated` (grey) stays visually **distinct** from info-blue (`e0aa3287`) — the property legend *adds* info, it does not merge grey into blue or alter grey semantics. Data-table sections (e.g. `server_groups`) are opt-out by construction (only `view_mode==='property'` switches the legend).

---

## 2026-06-04 (feat — transpose / property-table materialization in _project_table_rows)

**Branch:** `feature/basic-healthcheck-report-output`. **997 passing** (was 990; +7). Additive materialization branch; **reuses the existing row-scope engine + columns render — NO engine change.**

### Added
- **`table.transpose` (object → N rows).** `extractors/command_center._project_table_rows` recognizes a new `table.transpose: [{key, label, field}]` spec key: when the resolved root object is a dict, it explodes that ONE object into N rows — one `{id: key, key, label, value: <obj.field>}` per declared field (`field` resolves nested + list-index via the shared walker). Placed **before** the single-object dict-wrap, so a declared transpose wins over the 1-row wrap; `label` defaults to `key`; entries missing `key`/`field` are skipped. Each setting becomes a real row with a stable `id` (= key), so a `row_match` rule keyed on the `key` + `value` columns gives an **independent per-row verdict** — the existing row-scope engine, unchanged. This is the N-row sibling of the dict-wrap (`d1860c4`, object → 1 row).
- **Declared-column display for transpose** (`result_to_artifact`): a transpose section keeps `id`/`key` on each row (for ref-stability + rule targeting) but **honors its binding's `table.columns` for display**, so those internal keys don't leak as columns. Gated on `table.transpose` — every other table section still derives display columns from row keys (`_derive_columns`), unchanged.
- `tests/test_transpose_property_table.py` (+7): object → N typed rows (int/str/bool, nested paths); label-defaults / incomplete-entry skip; transpose-over-raw (no root_key); dict-wrap regression unchanged without a transpose key; declared columns restrict display while id/key stay on the row; a `key`+`value` rule yields a per-row verdict (in_sync→warning, others→good) with no engine change; verdict bakes per-row end to end.

### Notes
- **Why this avoids the deferred ADR-0010 field/object-scope engine:** that engine was needed to judge a *card's fields in place* (value-grained, no rows). Transpose materializes fields **as rows**, so the row-scope engine (which exists) gives the per-row dots directly. Confirmed read-only-pass-then-implement.
- **Renders today in the default `columns` view_mode** — a `Setting | Value` table with a per-row STATUS dot (`quick_hc.js:355-378`). The stacked-tile "card look" is **out of scope** (the `TableSection.view_mode:"card"` branch is 1-row-only + dotless, `:346`); a tile aesthetic is a separate later commit.
- **No live re-collect / rule authoring this slice** (no token needed). `commserve_software_cache`'s `cache_configuration` can now be re-authored as a transpose section (replacing the empty card) — that binding + its row rules are Michiel's next step (MCP `save_rule`).

---

## 2026-06-04 (fix(engine) — numeric path segment indexes into a list in _resolve_field_path)

**Branch:** `feature/basic-healthcheck-report-output`. **990 passing** (was 984; +6). Global engine fix; additive, no behavior change for existing dict paths.

### Fixed
- **`extractors/metric_section._resolve_field_path`** — the shared ADR-0007 D2 field-path resolver descended only into dicts, so a path with a numeric segment pointing into a **list** (e.g. `commserve_software_cache`'s table root_key `commserveSoftwareCache.UaInfo.cacheContents.0.softwareCacheServicePackDetails`) hit `.0` against a list and returned `default` → the table rendered **0 rows**. The resolver now: descends a **dict** by key as before (a literal `"0"` key still wins via dict semantics), indexes a **list** by a non-negative integer segment (out-of-range / non-numeric → `default`), and returns `default` for any other mid-path type. Used by every section type (table root_key + columns, card/metric fields).
- **Purely additive:** a numeric-on-list segment previously only ever returned `default`, so no existing path changes. Same spirit as the recent generic fixes in this path (Fix A nested root_key `842d39c`, dict-wrap `d1860c4`).
- `tests/test_resolve_field_path.py` (+6, new): list index; nested dict→list→dict→value (the real cache shape); out-of-range → default (incl. custom default); non-numeric/negative on a list → default; literal `"0"` dict key resolves by key; dict-only regression cases.

### Notes
- **Validated** against the `commserve_software_cache` payload captured live last turn (the live re-collect's loopback token had expired again: `error='no active token; reconnect'`): `cache_contents` table now renders **3 rows** — WinX64 / linux-x8664 / linux-arm64, each SP `11.40.47`. The `cache_configuration` **card is still empty** — that's **Fix 2** (separate), unchanged here.
- **Diagnosis confirmed (out of scope to fix here):** the original mis-authoring root cause is that the binding **spec vocabulary diverges by section type** — a table declares `root_key` + `columns`, a card declares `items` (and `build_card_section` ignores `root_key`). The `commserve_software_cache` card was authored with `columns`, so it bakes empty. Worth an ADR note later; Fix 2 is a v2 card-spec re-stage, not code.
- The `.0` positional index makes list-indexing **work**, not **version-correct** (it hardcodes "v11 is first in cacheContents"). Version-predicate vs positional index is a later spec question — left as-is.

---

## 2026-06-04 (Fix A — nested root_key resolution + epoch_to_iso coercion)

**Branch:** `feature/basic-healthcheck-report-output`. **984 passing** (was 982; +2). Two generic, additive read-path fixes surfaced by `metrics_reporting` (which baked empty). The card binding-shape half (Fix B) is separate.

### Fixed / Added
- **Nested `root_key` (table read path).** `extractors/command_center._project_table_rows` now resolves `root_key` through the shared nested-path walker `_resolve_field_path(raw, root_key)` instead of a flat `raw.get(root_key)`. The column `field` paths already nested (`service.name`), so root_key being flat was an asymmetry — a nested `root_key` like `config.cloud.serviceList` silently yielded an empty table. **Behavior-preserving:** a single-segment key (`auditTrailInfo`, `items`, …) resolves byte-identically to the old flat get (missing → `None` → `[]`); same spirit as the prior generic fixes in this path (dict-wrap `d1860c4`, view_mode `5f5f136`).
- **`epoch_to_iso` coercion (card read path).** Added `epoch_to_iso` as a closed-enum sibling of `hex` in `extractors/card_section._coerce_item_value` (ADR 0007 D3): a card item declaring `"type":"epoch_to_iso"` formats an epoch-**seconds** integer as an ISO 8601 UTC string (`1700000000 → "2023-11-14T22:13:20Z"`), keeping the raw epoch in `raw_value`. Seconds only — no millisecond guessing. The card reader already runs every field value through `_coerce_item_value`, so no new wiring; absent/other `type` and non-integers pass through byte-identical. **Declared in the binding, not a field-name heuristic.**
- Tests +2: `test_project_table_rows_nested_root_key_path` (nested `a.b.c` resolves to the inner list with `service.name` populated + Health Check id 1/enabled false; single-segment unchanged; missing nested path → `[]`); `test_epoch_to_iso_coercion` (known epoch → ISO + raw kept; undeclared field left an int).

### Notes
- **Validated end-to-end** against the `metrics_reporting` payload captured live earlier this session (only the HTTP fetch substituted — the live re-collect's loopback token had expired: `error='no active token; reconnect'`): `services` table = **8 rows, `service_name` populated 8/8**, **Health Check (id 1, enabled false) → `warning`** with finding "Health Check cloud service disabled". The `status` card is **still empty (0 items)** — expected; its binding shape (`card.fields`/`id` vs the reader's `card.items`/`label`, and the `root_key` the reader doesn't apply) is **Fix B**, handled separately. `epoch_to_iso` is now available for Fix B to declare on the three timestamp fields.
- This is the CODE half only; no staged artifacts / subject definitions / rules were touched.

---

## 2026-06-04 (TableSection.view_mode — single-row table renders as a card)

**Branch:** `feature/basic-healthcheck-report-output`. **982 passing** (was 976; +6). Presentational discriminator (option b); **no change to the rule engine, `validate_row_match_rule`, or the verdict bake** — a card-rendered table still fires its row rules + per-row verdict.

### Added / Changed
- **`TableSection.view_mode: Literal["columns","card"]` (default `"columns"`)** (`artifacts/models.py`) — mirrors `CardSection.view_mode` / `MetricSection.render_mode`: a presentational layout discriminator carried on the artifact from the catalog binding, never keyed on subject id. A `@model_serializer` **omits it from JSON when default**, so existing table artifacts stay byte-identical.
- **`result_to_artifact`** reads the mode from the already-plumbed `section_table_specs` (`view_mode="card"` only when the binding says so; any other/absent value → `"columns"`, so a typo never crashes collection).
- **`artifact_to_view`** passes `view_mode` through the TableSection branch alongside the existing `row_verdicts`/`sev`/`scope_caption`.
- **`quick_hc.js::secBody`** — new branch: a **single-row** table with `view_mode==='card'` renders as a Field/Value card reusing the existing `meta-grid`/`meta-card` markup (the layout behind CommCell Details), with the section-level verdict pill in the header (`secTile`, from `sec.sev`). Any row count other than exactly one falls through to the column table.
- `tests/test_table_card_view_mode.py` (+6): model default + omit-when-default serialization + round-trip; collection reads the mode (card / default / bad-value-degrades); the view carries `view_mode` while `row_verdicts` still ride along; JS card-branch render marker.

### Notes
- **Design point (settled):** a row rule yields one verdict *per row*, so a card shows one **section-level** badge — no per-field dots (unlike the card `view_mode==='table'` path, which has per-field `CardItem.sev`). Correct for `audit_trail`.
- **`audit_trail` opted into card mode** (runtime binding edit, gitignored): `view_mode:"card"` added to its `table` spec. Re-baked artifact → `TableSection.view_mode=="card"`, **1 row, verdict `good`, 0 findings** (`retention_critical 365` not `< 365`); view = `type:table, view_mode:card, sev:good`.
- **Validation honesty:** the **live re-collect failed** — the loopback returned `error='no active token; reconnect'` (the connection expired since the earlier live collect this session). The pipeline above was validated against the `auditTrailInfo` payload **captured live earlier** (stable retention settings), substituting only the network call — so binding→extract→project→evaluate→bake→view is exercised end-to-end; only the live HTTP fetch (orthogonal to this presentational change) is unverified this run. Visual confirmation is the operator's after a reconnect + `./start.sh`.

---

## 2026-06-04 (audit_trail subject built + the CC-API dict-wrap fix validated LIVE)

**Branch:** `feature/basic-healthcheck-report-output`. Catalog/runtime + live-validation pass on top of the dict-wrap collector fix below; **no code change** (the subject + binding are db-driven runtime state, gitignored). **Resolves the "held pending review" caveat in the preceding entry** — the endpoint and shape are now verified live.

### Added (runtime catalog — data/app.db, gitignored)
- **`audit_trail` subject** (fresh build — it never existed in code/catalog/git; only an orphaned, unbound `audit_critical_retention_warning` rule did). One table section `audit_trail.retention` on the `rest_command_center_api` source, endpoint `/commandcenter/api/commserv/audittrail`, `output_as: table`, `root_key: auditTrailInfo`, with the orphaned rule bound via `evaluative.row_rules`. Nothing to supersede (single rule version, was unbound).

### Notes
- **Endpoint + shape verified live** through the ADR-0008 loopback (`POST /internal/commserve`, app-held token; no CS token ever held here): `/commandcenter/api/commserv/audittrail` → `200`, body `{"auditTrailInfo": {…}}` where `auditTrailInfo` is a **single dict** (`retentionForCritical/High/Medium/Low`). This is a *different* endpoint from the proven ReportsPlus audit **dataset** in `API_MAPPING.md` (event records) — the earlier "differs from the proven dataset / shape unverified" caveat was over-cautious; both are real, distinct endpoints.
- **Field-name correction vs the brief:** the API returns camelCase `retentionForCritical/High/Medium/Low`, not `retention_critical/...`. The binding maps column id → field accordingly (`retention_critical ← retentionForCritical`, …), so the rule's `retention_critical` target resolves.
- **Live re-collect** (real `CommandCenterExtractor.extract()`, only `_fetch` routed through the loopback) → the `auditTrailInfo` dict auto-wraps to **exactly 1 row** `{retention_critical: 365, high: 365, medium: 240, low: 120}`, verdict `good`, **0 findings** (`retention_critical < 365` is false at 365 — boundary-compliant). Renders as a Report-band table (1 row, green STATUS dot) + an Evaluation-band criteria card (`Low critical audit retention` · `retention_critical < 365`). Visual check is the operator's after `./start.sh`.

---

## 2026-06-04 (Fix — CC-API table adapter: single-object root_key → one row)

**Branch:** `feature/basic-healthcheck-report-output`. **976 passing** (was 975; +1). Collector-only fix in the `rest_command_center_api` source adapter; no schema/catalog/view change.

### Fixed
- `extractors/command_center._project_table_rows`: when `root_key` resolved to a **dict** (a single-object response, e.g. `auditTrailInfo: {...}`) the projector hit `if not isinstance(records, list): return []` and emitted an **empty table**. It now auto-wraps a dict as `[obj]` before projecting, so a single-object response becomes a one-row table (columns selected/renamed or passed through, same as the list path). `wrap_object_as_row` is **not** plumbed through the binding, so the dict auto-detect is unconditional. The multi-record list path and all degenerate cases are unchanged.
- `tests/test_cc_api_multi_object_adr0009.py` (+1): `test_project_table_rows_wraps_single_object_under_root_key` — column-mapped dict-wrap + no-columns passthrough + an explicit assertion the existing list path is unaffected.

### Notes
- This is a **gap from inception**, not a regression: the dict branch never existed — `_project_table_rows` was introduced (ADR 0009, `5891076`) only ever handling lists; git history shows no prior dict-wrap and `auditTrailInfo` has never appeared in the tree.
- Discovered while investigating a handover note about an `audit_trail` collector regression. The collector fix is real and lands here; the `audit_trail` **subject does not exist** in code/catalog/git (only an orphaned, unbound `audit_critical_retention_warning` rule), so building/validating that subject is held pending review (its endpoint shape is unverified and differs from the proven ReportsPlus audit dataset in `API_MAPPING.md`).

---

## 2026-06-03 (ADR-0010 — authored rule descriptions + Option-B criteria render (slice 3))

**Branch:** `feature/basic-healthcheck-report-output`. **975 passing** (was 963; +12). Retires the interim per-rule prose deriver in favour of authored text + a mechanical condition render; **view/data only** (no scope/verdict/binding/engine change beyond the new `description` field).

### Added / Changed
- **Authored `description` on a rule (DATA).** `save_rule` accepts an optional `description` (string, nullable); it is persisted, returned, and surfaced by `list_rules`. Absent ⇒ null (no extra validation — it rides the rule body, which `save_rule` already stores verbatim). Documented on the MCP `save_rule` tool.
- **Mechanical condition formatter** — `evaluative/row_match.format_conditions(conditions)`: renders a conditions list as one AND-joined human string, covering **every** supported operator (`eq =`, `ne ≠`, `gt >`, `gte ≥`, `lt <`, `lte ≤`, `contains`, `not contains`, `between <v> and <v2>`, `exists → is set`, `not_exists → is not set`, `stale_days → older than <n> days`). Strings quoted, numbers bare, a `{"ref":col}` rendered as the bare column name. ONE tested place — not inference.
- **Bake gains the rendered fields.** `result_to_artifact` now bakes each check as `{rule_id, severity, description, title, condition_text}` (the formatter runs at bake; the view renders strings only).
- **Criteria card = Option B.** Per check: severity badge + a **primary line** + the **condition** underneath in mono/muted. The primary line is the authored `description`, falling back to the rule `title` with its `{row.*}` template placeholders stripped (`canonical_view._title_static`) — **never the raw rule id** (the bug this slice fixes). `quick_hc.js`/`.css` render the two-line check.
- **Interim prose deriver RETIRED.** `canonical_view._RULE_SENTENCE` / `_rule_sentence` (the hard-coded rule-id→sentence mapping) are removed. The scope-block sentence (`_scope_phrases`) stays as-is for this slice.
- `tests/test_authored_descriptions_adr0010.py` (+12): formatter one-case-per-operator + quoting/AND-join; bake carries description/title/condition_text (absent ⇒ null); render contract — primary is description / static-title / **never the rule id** (the regression guard); deriver removed; `save_rule` description persists/returns/lists, absent ⇒ null. `test_evaluation_band_adr0010.py` updated to the new check shape.

### Notes
- **Seeded (runtime, gitignored — the proof):** `server_groups`' three bound rules got authored descriptions — `sg_empty_group` "Every server group must contain at least one server.", `sg_naming_convention` "Manual server group names must follow the GRP_ naming convention.", `sg_rommelgroep_company_1` "Company_1 must not contain a group named “rommelgroep”." `sg_naming_convention`'s redundant `association == MANUAL` condition was dropped (the section scope already gates that population, so this is verdict/finding-neutral) — leaving its criteria condition the substantive `name not contains "GRP_"`.
- **Verified via the real path** (re-baked stored artifact, runtime state): criteria card Checks → `name not contains "GRP_"` (naming), `name = "rommelgroep" and company = "Company_1"` (rommelgroep, critical), `server_count = 0` (empty), each with its authored description; **no raw rule id**; scope sentence + table caption unchanged. Card visuals are the operator's check after `./start.sh`.
- **Check ORDER** follows the binding order (naming → rommelgroep → empty), which differs from the acceptance's logical listing — a deterministic authored order is still the open follow-up (bindings were not touched).
- **Open follow-up:** the scope-authoring MCP tool (`save_section_scope` / a `scope` arg on bind) + an **authored scope label** to retire the remaining interim `_scope_phrases` derivation; an authored check order.

---

## 2026-06-03 (ADR-0010 — Evaluation band: criteria + findings cards (layout slice 2))

**Branch:** `feature/basic-healthcheck-report-output`. **963 passing** (was 956; +7). Restructures where evaluation lives in the report; **presentation/view only** (no scope/rule/binding/verdict change).

### Added / Changed
- **New "Evaluation" band** — a peer to Data Source / Report Sections, ordered **after** Report Sections — with TWO independently-includable cards: **"Evaluation criteria"** (read-only) and **"Findings"** (the former Compliance findings list, moved verbatim + retitled). Each is a normal section, so it gets its own include toggle via the existing `secTile`.
- **The pipe:** `result_to_artifact` bakes a per-section `metadata["evaluation"] = {scope, checks:[{rule_id, severity}]}` from the resolved rules + scope. `artifact_to_view` reads it to: move the `<subject>.compliance` findings into the evaluation band (retitled "Findings", keeps its pill), build the criteria card, set a `band` on every section (default `report`), and add a `scope_caption` to the data table.
- **"Evaluation criteria" card** — **no status pill** (it describes the assessment, it is not a verdict): a plain-language **Scope** sentence + one severity-tagged **check** sentence per bound rule.
- **Scope caption** on the data-table legend bar (muted, right-aligned, e.g. "Scope: manual server groups · automatic excluded") — the **always-present safety net**: it lives on the table, so it survives toggling both Evaluation cards out.
- `quick_hc.js` partitions sections into the Report vs Evaluation bands and renders the `criteria` type + the scope caption; `quick_hc.css` adds the criteria card + caption styling.
- **Derived phrasing is INTERIM** — one clearly-marked place in `canonical_view.py` maps the scope (`association eq <v>`) and the two named rule ids to sentences. **Not** an inference engine (between / stale_days / … are out of scope).
- `tests/test_evaluation_band_adr0010.py` (+7): the band ordered after Report with exactly criteria+findings; findings moved out of Report + retitled; criteria scope/checks with no pill; independent toggles; the table scope caption; no-evaluation subjects get no band/criteria/caption (only `.compliance` rebands); render markers.

### Notes
- **Verified headless** against the live page: server_groups → table (report band) with caption "manual server groups · automatic excluded"; Evaluation band → "Evaluation criteria" (scope sentence + two warning checks, no pill) + "Findings" (11, Warning pill). The stored artifact was re-baked (runtime state); a real Collect bakes the same. The card visuals are the operator's check after `./start.sh`.
- **Other subjects unchanged:** CommCell Details / License Summary / Security Assessment carry no `evaluation` metadata (or use their own builders) → no Evaluation band, sections default to the report band, captions `None`.
- **Open follow-up:** an authored rule `description` + scope label (rendered verbatim, replacing the interim derivation) — pairs with the scope-authoring MCP tool, still the open authoring follow-up.

---

## 2026-06-03 (ADR-0010 — report section layout + per-row verdict rendering (layout slice))

**Branch:** `feature/basic-healthcheck-report-output`. **956 passing** (was 948; +8). Renders the per-row `_verdict` the engine slice bakes; **presentation only** — no engine / scope / rule / verdict change.

### Added / Changed
- **The pipe:** `artifact_to_view`'s table branch now carries the baked per-row `_verdict` to the view as row metadata `row_verdicts` (row-aligned), **not** as a visible data column, and rolls a section `sev` pill from the worst row verdict **excluding `not_evaluated`**. The findings branch gains the same `sev` (worst finding severity) so the derived `<subject>.compliance` section gets a pill.
- **STATUS column** on the data table (`quick_hc.js` `secBody`): one verdict dot per row — good→green, warning→amber, critical→red, **`not_evaluated`→gray (`vdot-na`)** — plus a legend gaining a "not evaluated" entry. Rendered only when the section carries `row_verdicts`; tables without verdicts are unchanged.
- **The explicit-verdict trap, guarded:** the dot maps the verdict **directly**; only a genuinely ABSENT verdict (`null`) falls back to info-blue. `not_evaluated` is its own gray token — out-of-scope rows never paint blue.
- The card **shell** (header title + `sec.sev` status pill + visibility toggle + legend) is the **existing `secTile` / card chrome reused as-is** — server_groups' table + compliance sections already render through it, so they now match CommCell Details. New CSS: `.vdot-na` (gray), `.vdot-col` (status column).
- `tests/test_layout_verdict_adr0010.py` (+8): view carries `row_verdicts` (row-aligned, not a data column); pill = worst excluding `not_evaluated` (+ critical>warning, all-not_evaluated → no pill); no-verdict table unchanged; compliance pill = worst finding; render markers assert `not_evaluated`→`vdot-na` and that only `null` falls back to info.

### Notes
- **Verified headless** against the live page: server_groups table → pill `warn`, `row_verdicts` = {not_evaluated 7, warning 9, good 5}; compliance → pill `warn`, 11 findings — exactly the acceptance (5 green / 9 amber / 7 gray). The stored server_groups artifact was **re-baked** (gitignored runtime state) so verdicts show without a re-collect; a real Collect regenerates the identical bake. The actual dot visuals are the operator's check after `./start.sh`.
- **Other subjects unchanged:** CommCell Details (`_card_section_view`) and License Summary (`license_summary_to_view`) use their own builders; the table-branch change only adds metadata that non-verdict tables carry as all-`None` (no STATUS column).
- **Open follow-up:** the scope-authoring MCP tool (`save_section_scope`, or a `scope` arg on `save_rule`'s bind) — scope is still set directly in the catalog.

---

## 2026-06-03 (ADR-0010 — section-level evaluation scope + per-row verdict (engine slice))

**Branch:** `feature/basic-healthcheck-report-output`. **948 passing** (was 941; +7). An explicit evaluated **population** per section + a real **per-row verdict** — so the report can show good vs not-evaluated rather than infer from the absence of findings. Layout/render is a follow-up slice.

### Added
- **Section-level scope (data, not code):** an optional `evaluative.scope` on a section's binding — a list of AND-ed conditions (same shape/operators as `row_match` conditions). A row is IN SCOPE iff it satisfies every scope condition; absent ⇒ all rows in scope (unchanged default). Resolved by `db.rules.load_subject_section_scope`; carried on `ExtractionResult.section_scope` by both REST extractors.
- **Scoped evaluation + per-row verdict:** `evaluative.row_match.evaluate_section_rows(rules, rows, *, scope)` — bound rules run ONLY on in-scope rows, and every row gets an explicit verdict: out-of-scope → `not_evaluated`; in-scope clean → `good`; in-scope flagged → worst severity (`warning`/`critical`). The shared `matches_conditions` (extracted from the rule matcher) backs both rule and scope predicates.
- **Verdict baked at canonicalization:** `result_to_artifact` writes the per-row `_verdict` onto the `TableSection` items (D5 — no separate store; the same mechanism as a card field's `sev`; set **explicitly** so `not_evaluated` ≠ `good` ≠ `info`). `evaluate_subject` returns the identical per-row verdicts (`row_verdicts: [{section_id, row_ref, in_scope, verdict}]`) so the dry-run preview matches the baked artifact — and persists nothing.
- `tests/test_section_scope_adr0010.py` (+7): scope gating; absent-scope no-op; the three verdicts on one fixture; worst-severity roll-up; multi-condition AND scope; the `result_to_artifact` bake; `evaluate_subject` preview consistency.

### Notes
- **Verified live** (read-only dry-run, persists nothing): `server_groups` scope = `association == "MANUAL"` → findings **14 → 11** (the 3 automatic empty groups 4/5/17 no longer flagged); per-row verdicts **5 good** (7,8,11,13,14), **9 warning** (6,9,10,19,36,37,39,40,41), **7 not_evaluated** (1,2,3,4,5,17,18); `rommelgroep` 19 & 41 still distinct, each warning. The seeded scope + `sg_naming_convention` are left in place as the acceptance probe (gitignored runtime state).
- **Follow-ups:** the **layout slice** (render per-row `_verdict` — good/warning/critical/not_evaluated — in the report/UI); an **MCP tool to author section scope** (`save_section_scope`, or a `scope` arg on `save_rule`'s bind) — this slice set scope directly in the catalog.

---

## 2026-06-03 (Fix — `save_rule`-authored row rules were never evaluated: `kind` not persisted)

**Branch:** `feature/basic-healthcheck-report-output`. **941 passing** (was 939; +2 regression tests). ADR-0010 follow-up bug.

### Fixed
- **A `row_match` rule authored + bound via the `save_rule` MCP tool persisted, listed, and bound correctly but was never evaluated** by `evaluate_subject` / collection. Root cause: `save_rule` did not **persist** `kind`, while `load_subject_row_rules` filtered `kind == "row_match"` and silently skipped a kind-less def. The authoring validator defaults a missing `kind` to `row_match` (so the rule passed validation), but the stored def carried no `kind` — an author↔evaluator divergence. (NOT a bind/read **location** divergence: the data showed the `{ref}` correctly placed in the collected source's binding; the `"bound_sections": 2` fan was a red herring.)
- **Fix (both sides now agree):** `load_subject_row_rules` treats a ref in `evaluative.row_rules` as `row_match` when `kind` is absent (`resolved.get("kind", "row_match")`) — matching the validator's default, so existing kind-less rules fire with **no data repair**; and `save_rule` now persists the canonical `kind:"row_match"` / `scope:"row"` so future stored defs are explicit.
- **Regression guard (the coverage that was missing):** a true bind-write → eval-read **round-trip** test (`save_rule` + `bind` → `evaluate_subject` → assert the findings appear), on a fixture whose section exists under **two** source types (so the bind fans, `bound_sections == 2`) with a rule authored **without** an explicit `kind` — the exact structural trigger; plus a test that the tool persists canonical kind/scope. The earlier Phase-2b tests only checked persistence/`list_rules` (which agreed) or evaluated a rule bound a different way, so none exercised this path.

### Notes
- **Verified live** (read-only dry-run, persists nothing, live rule preserved): `evaluate_subject("server_groups")` now `rules_evaluated=2` → `sg_empty_group` (12) **and** `sg_naming_convention` on exactly rows **19 & 41** (both `rommelgroep`, MANUAL non-`GRP_`); those two rows carry both findings (multi-rule-per-row). `sg_naming_convention` is left in place as the live acceptance probe.

---

## 2026-06-03 (ADR-0010 Phase 2b — MCP authoring surface for row-scope rules)

**Branch:** `feature/basic-healthcheck-report-output`. **939 passing** (was 929; +10). Completes ADR-0010: row-scope rules are authored/managed via MCP, validated at authoring time.

### Added
- **MCP tools** (`mcp/server.py`): `evaluate_subject` (dry-run — wraps the Phase-2a service; reads the canonical/approved latest artifact, **not** the staging queue), `list_rules` (`subject_id?` / `enabled?`), `save_rule` (upsert + optional one-call bind), `delete_rule` (removes the registry row + strips its `{ref}` from every binding). Registered through the existing `_run_in_thread` event-loop offload.
- **`db.rules` authoring helpers**: `save_rule` (upsert by `rule_id`; **bumps `version` on a body change**; preserves `created_by`; `enabled` defaults true), `bind_rule` (idempotent `{ref}` write onto a section's `evaluative.row_rules`), `delete_rule` (delete + strip refs), `list_rules` (subject/enabled filters), and `validate_row_match_rule`. `load_subject_row_rules` now **skips disabled rules**.
- **Authoring-time validation** — rejected, not silently dropped at collection: unknown operator; `between` without `value2`; `emit:"count"` without `count_operator`/`count_value`; `scope` ≠ "row" (summary scope not yet implemented); and, when binding, a missing section, a non-table section, or a condition target / `{"ref":col}` that isn't a column of that section.
- `tests/test_rules_mcp_adr0010.py` (+10): version bump on change; list filters (subject/enabled); idempotent bind; unbound save; disabled-not-loaded; delete strips binding; the full a–f + scope rejection matrix; and tool wiring (`save_rule` validates-before-persist; `evaluate_subject` no-artifact preview).

### Notes
- **Verified live in-process** (the MCP client must reconnect / `pkill -f cv-healthcheck-mcp` to pick up the new tool list): `list_rules()` returns the catalog rules; `evaluate_subject("server_groups")` → 12 findings via the tool.
- `save_rule` keeps the rule body and the section binding **separable** (bind is optional; one rule can bind to several sections via repeated `save_rule` targets) — the common author+fire case is one call.
- **ADR-0010 is complete** (Phase 1 core + 2a binding/dry-run + 2b authoring). Deferred (ADR): summary-scope rules (the validator carries the TODO); a count/aggregate kind if cross-row duplicate *detection* is wanted (`row_match` is per-row); a separate findings store only on the D5 revisit trigger (persistent ack surviving re-collection, or cross-engagement trend).

---

## 2026-06-03 (ADR-0010 Phase 2a — catalog binding + the `evaluate_subject` dry-run)

**Branch:** `feature/basic-healthcheck-report-output`. **929 passing** (was 922; +7). Connects the Phase-1 evaluator to the catalog and proves it live. Stops **before** the MCP authoring surface (Phase 2b).

### Added
- **`db.rules.load_subject_row_rules(db, subject_id, version)`** — resolves a subject's row-rule bindings (`extraction_instructions.evaluative.row_rules: [{"ref": rule_id}]`) against the rules registry into `{section_id: [resolved row_match defs]}` (the ref-from-binding model the metric/card rules use; unknown ref fails loudly; only `kind="row_match"`; deduped per section). Feeds both the dry-run and the extractors.
- **`evaluative/subject_eval.py` — `evaluate_subject(db, subject_id)`** — the dry-run, the rules-side parallel to `probe`: re-runs the subject's bound row rules over its **latest stored artifact** and returns a findings preview, **persisting nothing** and never touching the artifact (D4/D5). `has_artifact=False` when nothing is collected yet (empty, not an error).
- **Extractor wiring** — `RESTExtractor` and `CommandCenterExtractor` now set `result.section_row_rules = load_subject_row_rules(...)`, so bound rules fire on a real collection (the canonicalization pass bakes a `<subject>.compliance` FindingsSection).
- `tests/test_subject_eval_adr0010.py` (+7): binding resolution (+ unknown-ref raise, empty-when-unbound); dry-run fires over the latest artifact with **distinct `row_ref` on same-named rows**; no-artifact is empty-not-error; **persists-nothing** (artifact bytes unchanged); the extractor populates `section_row_rules` and the pass bakes a finding end-to-end.

### Notes
- **Proven live** against the real catalog (2 rules + bindings authored into `data/app.db`): `evaluate_subject("server_groups")` → **12** empty-group findings incl. **both `rommelgroep` ids 19 & 41 as distinct findings** (row_ref=id — the duplicate-name correctness); `evaluate_subject("users")` → **2** never-logged-in (`last_logged_in == 0`: ids 4, 8). These rules now also fire on the next collection via the extractor wiring.
- True duplicate *detection* is cross-row (not a per-row predicate) — out of `row_match`'s grain; the `rommelgroep` case is handled as distinct per-row findings, which is exactly the row_ref=id guarantee.
- **Boundary (Phase 2b):** the MCP authoring surface — `list_rules` / `save_rule` / `delete_rule` / `evaluate_subject` + `save_rule` validation (row rule on a non-table section; `{ref}` to a missing column; `emit=count` without `count_operator`/`count_value`). Rules are authored by direct catalog writes until then.

---

## 2026-06-03 (ADR-0010 Phase 1 — row-scope evaluation rules: core + canonicalization pass)

**Branch:** `feature/basic-healthcheck-report-output`. **922 passing** (was 885; +37). Layer 5 (evaluation) reconciliation — see `docs/adr/0010-row-scope-evaluation-rules.md` (Accepted). Phase 1 is the **pure evaluation core + the canonicalization integration point**; **no catalog rule fires yet** (catalog binding + MCP authoring is Phase 2).

### Added
- **`evaluative/row_match.py`** — the row-scope evaluator (ADR 0010 D3): `evaluate_row_rule(rule, rows)` ANDs a list of predicates over each table row and emits findings. Operators `lt/lte/gt/gte/eq/ne/contains/not_contains/exists/not_exists/between/stale_days`; a predicate `value` is a literal or `{"ref": <other column>}` for field-to-field comparison (`used > available`); `emit=per_row` (one finding per matching row, **`row_ref` = the row's `id`, not its name**) or `emit=count` (one finding when the match count satisfies `count_operator`/`count_value`); `{value}/{target}/{count}/{row.<col>}` templating. A new **grain** in the engine package — not a branch in the per-value `engine._evaluate_rule`.
- **`evaluative/coerce.py`** — centralized value coercion (ADR 0010 D6): `to_number` (leading-numeric out of unit strings `"0 TB"`→0; `"Unlimited"`→+∞; bool rejected), `is_absent` (`N/A`/`-`/``/`null` → a comparison against absent is **false**, not an error; `exists`/`not_exists` test it), `age_days` (ISO **and** unix-epoch — incl. `users.lastLoggedIn` `0`=never) for `stale_days`.
- **`result_to_artifact` compliance pass** — after the extracted sections are built, runs each section's bound `row_match` rules over its rows and emits a derived **`<subject>.compliance` FindingsSection**, folding severities into the summary (ADR 0006 D1, one canonicalization path). Read-only over the rows; the rules never mutate the artifact. New `ExtractionResult.section_row_rules` carries the bindings; empty for every existing path (the pass is a no-op until a rule is bound).
- `tests/test_row_match_adr0010.py` (+37): coercion; every operator; AND (all-true vs one-false); field-ref + `Unlimited`; `exists`/absent-is-false; `stale_days` (epoch-0 never + ISO); never-logged-in `eq 0`; `emit=count` threshold; templating; the **`rommelgroep` duplicate-name → distinct `row_ref` 19/41**; and the `result_to_artifact` integration (compliance section + summary status; no rules → no section).

### Notes
- **D5 accepted** (the key call): findings are a derived **in-artifact** FindingsSection (consistent with the existing engine baking verdicts at collection), **not** a separate store. Consequence: a rule change re-derives on the next collection / in the `evaluate_subject` dry-run, not by rewriting stored artifacts. Revisit a separate store only if persistent finding acknowledgement (surviving re-collection) or cross-engagement trend analysis becomes a goal.
- **Phase 1 boundary:** nothing populates `section_row_rules` from the catalog yet, so no catalog-authored rule fires on a real collection. Phase 2 wires it: registry `kind:"row_match"` rows + the section binding (`extraction_instructions.evaluative.row_rules: [{ref}]`) + the extractors resolving them, plus the MCP tools `list_rules`/`save_rule`/`delete_rule`/`evaluate_subject`.
- The original Layer-5 spec's collisions were dropped: no `0005` / second `rules` table (a registry extension instead), no DEVLOG, no separate findings store, and §9 (migrate `environment`) is void — already declarative (migration 0023).

---

## 2026-06-02 (Fix — `delete_subject` reconciles staging; full `server_groups` reset)

**Branch:** `feature/basic-healthcheck-report-output`. **885 passing** (+1). A logically **separate** change from the ADR-0009 D1/D2 build and Phase 1 — it shares `db/subjects.py` with the still-uncommitted D2 hunk, so the `delete_subject` hunk is staged separately when committing.

### Fixed
- **`delete_subject` now reconciles the review queue.** It already cascaded `subject_sections` / `subject_sources` / `subject_section_sources` / `subjects`, but left the subject's `staged_artifacts` rows behind — so a delete **orphaned** approved proposals (an approved `subject_proposal` with no catalog subject, which the staging UI / `list_proposed_subjects` misreads as "belongs in the catalog"). It now **hard-deletes** the subject's `staged_artifacts` rows (proposals AND imported `artifact` rows) in the same transaction, and returns `staging_rows_removed`. Chosen over mark-terminal: consistent with the function's "delete all related rows" contract, fully prevents orphan accumulation, and needs no new status value. The shared approval path (`execute_approval` / `reject_staged_artifact`) is untouched.
- `tests/test_delete.py` (+1): a subject with a pending proposal + an approved artifact staged row → `delete_subject` removes both (`staging_rows_removed == 2`) and nothing for the subject resurfaces in `list_staged_artifacts(status="pending")`.

### Removed
- **Full `server_groups` data reset (live DB).** Deleted all **3** `staged_artifacts` rows for `server_groups` (the two real approved rows `stage_97a9…` / `stage_9513…` and the Phase-1 seed `stage_phase1_validate_server_groups`) so the next import starts clean. An **exhaustive value scan** confirmed `server_groups` survived in **no other table** (no `subjects` / `subject_sources` / `subject_section_sources` / `subject_sections` / `customer_subject_pin` / `rule_overrides` rows — all already 0). Post: `list_staged_artifacts(subject_id="server_groups")` empty; `list_subjects` has no `server_groups`.

### Notes
- Root cause of the orphan mess (from the prior read-only diagnosis): promotion always worked, but `delete_subject` never cleaned `staged_artifacts`, so deleted subjects stranded their approved proposals. This closes that gap going forward; the manual wipe clears the existing strand.
- Sibling cleanup noted, out of scope: `delete_subject` also leaves `customer_subject_pin` / `rule_overrides` rows for a deleted subject — not orphan-visible in the staging queue, but a candidate for the same treatment later.

---

## 2026-06-02 (ADR-0009 Phase 1 — consolidated `/quick-hc` Staging + Subjects zones)

**Branch:** `feature/basic-healthcheck-report-output`. **884 passing** (was 876 after the ADR-0009 D1/D2 build; +8). **Built, not committed** — pending the in-browser confirmation ("tests green ≠ works"). The old `/quick-hc/staging` page, its template, the `artifact_card` macro, and the nav link are deliberately **left intact** as the fallback (removal is Phase 3).

### Added
- **Staging zone on `/quick-hc`** (above the existing Subjects / Report-Sections content). Pending subject proposals render as **empty structural shells** — section titles + types, with **table sections showing their header row even when empty** (the one `secBody` enrichment; collected-but-empty tables benefit too), metric sections as labeled placeholders, findings/card/chart as their empty bodies. Built **server-side**: `build_proposal_shell()` (`quickhc/subject_data_service.py`) synthesizes an empty-bodied `CanonicalArtifact` from a proposal's `artifact_json` and runs it through the existing `artifact_to_view`, reusing its canonical→view-token mapping — the JS stays a pure renderer.
- **Pending-proposal data into `initial_data`** as a new `staging` list, filtered to `artifact_type=='subject_proposal' AND status=='pending'` (`_build_staging_shells`) — orphaned approved proposals and all `artifact`-type rows are excluded by construction.
- **Two new endpoints** (`web/routes/quick_hc.py`): `POST /quick-hc/proposals/<stage_id>/approve` and `…/reject`, beside each shell's title (approve = primary success-outline, reject = quiet ×). Both route through the **unchanged** `execute_approval` / `reject_staged_artifact` and **redirect to `/quick-hc`** — a full reload re-renders both zones from fresh server state (no DOM surgery) and preserves the localStorage `_test` hide toggle.
- `tests/test_proposals_routes.py` (+8): approve promotes into the catalog + redirects; reject marks rejected + redirects; double-approve flashes "not pending"; `/quick-hc` lists the pending shell; `build_proposal_shell` keeps table columns with empty rows, degrades gracefully on a garbage section, and returns None without a subject_id; `_build_staging_shells` includes only pending subject_proposals.

### Notes
- **Explicitly unchanged** (verified): `execute_approval`, `reject_staged_artifact`, `db/staging.py`, the `_test` hide button (`showTestSubjects()` / `TEST_SUBJECTS_KEY` / `renderLeft`), and the entire `/quick-hc/staging` page. The four shared-path suites (`test_staging_routes`, `test_db_staging`, `test_core_solidity`, `test_mcp_tools`) are untouched.
- Headless render check against the live DB confirms `/quick-hc` serves the staging shell (`is_proposal`, title, `type:table`, header columns) and `/quick-hc/staging` still 200s — but the **in-browser eyeball is the operator's**. A pending `server_groups` proposal (re-proposed as `rest_command_center_api` / `/v4/servergroup`, stage_id `stage_phase1_validate_server_groups`) was seeded for that and left **pending** — approve it in the browser or discard.
- Deferred to later phases: deleting `/quick-hc/staging` + the nav link (Phase 3); a home for `artifact_type=='artifact'` rows (Phase 2 design).

---

## 2026-06-02 (ADR-0009 D1/D2 — MCP-authored + multi-object Command Center API sources)

**Branch:** `feature/basic-healthcheck-report-output`. **876 passing** (was 862; +14). Implements the Accepted ADR-0009 D1/D2 (the decision record landed in the prior commit). `server_groups` is only the throwaway end-to-end test case — not authored or shipped here.

### Added
- **`cvhealthcheck/extractors/cc_endpoint.py`** — leaf policy module (stdlib only): `validate_cc_endpoint()` resolves/validates a Command Center collect endpoint as **relative + read-only** under `/commandcenter/api/` (rejects absolute URLs, protocol-relative, traversal, scheme/host), defaulting to `/commandcenter/api/CommServ`; plus the `COMMAND_CENTER_SOURCE_TYPE` / `DEFAULT_CC_ENDPOINT` constants (re-exported from `command_center.py`).
- **D1 — generalized `CommandCenterExtractor`** (one extractor, no parallel producer; ADR 0006 D4.1): (1) collects from a **binding-declared relative endpoint** (`recognition_hints.endpoint`, validated), defaulting to CommServ so `environment` is byte-for-byte unchanged (still via `get_commcell_identity`); any other endpoint is a plain in-process GET. (2) an `output_as="table"` arm projects a multi-record collection (`raw[root_key]`) into rows via the shared nested-path resolver — **structural projection only, no operators** (ADR 0006 D2) — alongside the existing single-record card arm. Feeds the unchanged `result_to_artifact` tail.
- **D2 — MCP-authored CC-API source**: `propose_new_subject` documents `rest_command_center_api` + an explicit relative `endpoint` field; `create_subject_from_proposal` validates that endpoint relative + read-only and persists it into `recognition_hints` (no schema migration). No labeller change needed (`_SOURCE_TYPE_TO_LABEL` already maps the type).
- `tests/test_cc_api_multi_object_adr0009.py` (+14): endpoint policy (accept relative; reject absolute / protocol-relative / out-of-namespace / traversal / whitespace / non-str); `_project_table_rows` (column-map select+rename, passthrough, top-level list, degenerate cases); default-endpoint resolution; full propose→persist→extract→`TableSection`; absolute-endpoint rejection rolls back the proposal write.

### Notes
- **D4 trust boundary unchanged** (ADR 0008): the collect GET stays app-side / in-process with the in-memory token; the MCP layer asserts only a classification + a relative path string, never a token, host, or write. "Read-only" is the GET-only collect contract plus the `/commandcenter/api/` allowlist.
- The `/v4/servergroup` shape (root key / column fields) is **unverified** until a live capture — nothing about it is hardcoded in the extractor; the per-subject binding carries it.
- Operator-run acceptance test remains: re-propose a CC-API subject → approve → Collect hits the declared endpoint (not CommServ) and renders a table.

---

## 2026-06-02 (ADR-0008 B — Connections page; **ADR-0008 COMPLETE end to end**)

**Branch:** `feature/basic-healthcheck-report-output`. **862 passing** (was 857; +5). **This is the last piece —
the trust boundary is built, proven against the live CommServe, and now has a real connect/status surface.**

### Added
- **`GET /connections`** + `connections.html` (extends `base.html`; matches the app's look — CSS variables,
  `localtime_span` for timestamps) — a live connection surface:
  - **Status from `token_store.status()`:** `connected` → shows the principal + connected-at (+ token-expiry
    when known) and a **Disconnect** button; `disconnected` / `expired` → an honest **"Disconnected —
    reconnect"** prompt (expired is worded as a reconnect, not an error) with a **Connect** action.
  - **Connect** reuses the existing login — a link to `/login?next=/connections` (no second login path; the
    operator enters the password live, the store fills, the page reflects `connected`).
  - **Disconnect** (`POST /connections/disconnect`) calls `clear_current_token()` (store + session markers) and
    returns to the page as `disconnected`.
  - **Read-only connection target** from `Settings`: CommServe URL (`CV_BASE_URL`), SSL verification, customer,
    username — **no token, no password ever rendered**. Noted as environment-configured (editing is out of scope).
- A **"Connections"** sidebar nav link (`base.html`) — the long-planned Settings/Connections item.
- `tests/test_connections_page.py` (+5): disconnected→reconnect+Connect link; connected→principal+Disconnect (token
  never rendered); expired→reconnect (not error); disconnect→clears store + redirects; target shown without secrets.

### Notes
- **ADR-0008 is complete end to end:** the AI/MCP layer never holds a CommServe token and reaches the CommServe
  only through the app's loopback endpoint (C); the app holds the token in memory only (A, Flavour 1); the token
  is out of the cookie with the gate on the store (B); redaction is shared and app-side (D); the direct probe is
  retired (E); and the operator now has a connect/status surface (B, this).
- Remaining work is only the **named, deferred future items**, none in this ADR: RBAC over the principal/capability
  pair, Flavour 2 (encrypted stored credentials / multi-user), oversized-response tiering, and reactive expiry
  (flip the store to expired on a CommServe 401).

---

## 2026-06-02 (ADR-0008 B consolidation — CommServe token out of the cookie, auth gate on the store)

**Branch:** `feature/basic-healthcheck-report-output`. **857 passing** (was 856; +1). **The CommServe token is
no longer at rest in the browser** — it lives only in the in-process store.

### Changed
- **De-cookie:** `set_current_token` (`auth/commvault_auth.py`) **no longer writes the token to the session
  cookie** — only the non-secret `CUSTOMER_ID` / `USERNAME` markers. The token lands solely in the in-process
  store (`set_active_token`, wired in the prior brief).
- **Read seam repointed:** `_current_token()` (`web/routes/shared.py`) now returns `get_active_token() or ""`
  (was `get_current_token()`); its four web consumers (`/collect`, `get_commcell_identity`, `_reportsplus_client`,
  the dormant `_api_client`) follow automatically, `""` semantics preserved.
- **Auth gate keyed off the store:** `is_authenticated()` → `get_active_token() is not None`;
  `is_authenticated_for(cust)` → `get_active_token() is not None and get_current_customer_id() == cust` (the
  binding customer stays a non-secret cookie marker). `get_current_token()` is now dead (no real callers, reads
  the now-absent cookie key) — left returning `None` harmlessly.
- **`token_store` defense-in-depth (the one net production delta vs the original plan):** `get_active_token()`
  returns `None` for a non-string / blank / whitespace-only stored token, and `status()` reports `disconnected`
  for it — preserving the old cookie-token whitespace guard at its new home.

### Notes
- **Lock-out behaviour is honest** (the reason we de-cookied with care): a process restart empties the in-memory
  store, so the next request is **not-authenticated → `/login` redirect**; a **stale cookie token is ignored**
  (the gate reads the store, not the cookie) — no false logged-in, no silent failure. Verified via a test-client
  simulation of the restart scenario (operator browser check still recommended).
- **Test reshape (guiding principle: move the property, don't drop coverage):**
  - `test_phase3_auth_customer_bound.py` — **rewritten** to the store model: the `set_current_token` test now
    asserts the **de-cookie invariant** (token in store, `SESSION_TOKEN_KEY` NOT in the cookie, markers present);
    `is_authenticated_for` cases keep the binding-required property (store token + matching marker → True;
    mismatched/missing marker / no token → False); the legacy-unbound-**cookie**-token case became
    `requires_a_customer_marker` (binding-required, store-side); login/collect tests assert token-to-store.
  - `test_api_auth_status.py` — repointed to the store (via a new `authenticate` fixture); the whitespace case
    **retargeted** to a blank **stored** token reading as unauthenticated.
  - `test_token_store.py` — the brief-#5 cookie-unchanged test **flipped** to the de-cookie invariant; added the
    blank/whitespace-token-disconnected case.
  - Mechanical auth-setup pokes (`test_license_summary_web`, `test_platform_foundation`,
    `test_security_assessment_registry`) switched from `session[SESSION_TOKEN_KEY]=` to populating the store.
  - **New in `conftest.py`:** an `authenticate(client, …)` fixture (store token + cookie markers) so the next
    auth change doesn't ripple across files, and an autouse `_reset_token_store` (the store is process-global —
    a token set in one test must not leak).

---

## 2026-06-02 (ADR-0008 E — retire the probe to the app-mediated endpoint; AI holds no CommServe token)

**Branch:** `feature/basic-healthcheck-report-output`. **856 passing** (was 851). **This makes the direct
AI-holds-token model (committed at `e193e4b`) superseded in fact, not just on paper — ADR-0008's core is
complete:** the AI/MCP layer reaches the CommServe **only through the app**.

### Changed
- **`probe(path)` (`mcp/server.py`) is now app-mediated.** It no longer holds a CommServe token or calls the
  CommServe directly: it `requests.post`s the app's loopback endpoint `POST /internal/commserve` (default
  `http://127.0.0.1:5001`, overridable via `CV_INTERNAL_ENDPOINT_URL`) with `X-Internal-Secret`
  (`CV_INTERNAL_SECRET`) and the read contract `{path, principal:"mcp-operator", capability:"read"}`. The
  **app** fetches with its own held token and returns the response **already redacted** — so the probe's own
  `redact_user_descriptions` call is gone (redaction is app-side). Connected → returns `data` + surfaces
  `status_code`/`ok`/`error` (a CommServe non-200 stays visible); disconnected/expired → a clear
  "log in via the app to reconnect" message (visible-not-silent); raises only on a missing
  `CV_INTERNAL_SECRET`, an unreachable app, or a guard rejection (403/503).
- **Removed the direct-token machinery:** `_probe_token()` and the `CommvaultApiClient` / `load_login_token`
  / `load_token` / `redact_user_descriptions` imports in `mcp/server.py` (probe was their only user).
- **`run-mcp.sh`:** dropped the `CV_LOGIN_TOKEN_FILE` export (and there is no `CV_LOGIN_TOKEN` now). It only
  `source`s `~/.cv-healthcheck-env` for `CV_INTERNAL_SECRET`; the `.login_token` file is simply no longer read
  (left on disk, untracked).

### Notes
- Probe tests repointed to mock the **HTTP POST to the endpoint** (no CommServe client): connected (asserts
  the redacted data passes through + the shared-secret/read contract is sent), disconnected reconnect message,
  CommServe-non-200 surfaced, missing-secret raises, app-unreachable raises, guard-rejection surfaces.
- Added `tests/test_redaction.py` (+4) — the shared `redact_user_descriptions` lost its only test home when the
  probe stopped redacting; gave it direct unit coverage (basic / nested / non-str / scalar passthrough).
- **Capstone live smoke (operator + AI) still required** — `tests green ≠ works`: add `CV_INTERNAL_SECRET` to
  `~/.cv-healthcheck-env`, **reconnect the MCP** (re-spawns on the retired-probe code), log in via the browser,
  then `probe("/commandcenter/api/v4/user")` returns the same redacted data — now fetched through the app with
  the MCP holding no CommServe token. Deferred (unchanged): the Connections page + cookie consolidation (step 7).

---

## 2026-06-02 (ADR-0008 C — loopback internal endpoint `POST /internal/commserve`)

**Branch:** `feature/basic-healthcheck-report-output`. **851 passing** (was 839; +12 endpoint tests).

### Added
- **`POST /internal/commserve`** (`src/cvhealthcheck/web/routes/internal.py`) — the single trust-boundary
  door the AI/MCP layer may call; the **app** makes the CommServe GET with its own held token and returns a
  redacted envelope. Registered via one import in `routes/main.py` (same `main` blueprint).
  - **Guards (fail-closed, generic):** missing shared secret → **503** (never serve unguarded); non-loopback
    `remote_addr` → **403** (defense-in-depth); `X-Internal-Secret` mismatch (constant-time `hmac.compare_digest`)
    → **403**. All guard failures return a generic `{"error":"forbidden"}` — never revealing which failed; the
    secret/token are never logged.
  - **Request contract:** JSON `{path, principal, capability}` (all required strings). `capability` must be
    `"read"` (GET-only, read-only) else **400**; `path` must be relative (rejects scheme / netloc /
    protocol-relative) else **400**. `principal` is carried but not yet authorized (RBAC deferred, ADR-0008
    Decision 6 / future ADR).
  - **Token + call:** reads `get_active_token()`. **Disconnected/expired → HTTP 200** with
    `{"ok":false,"state":"disconnected"|"expired","status_code":null,"data":null,"error":"no active token; reconnect"}`
    and **never constructs a client** (a `None` token would make `CommvaultApiClient` fall back to the `.token`
    file — the path ADR-0008 kills). Connected → `CommvaultApiClient(token=tok).get(path)` (base_url/SSL from
    env), returns `{"ok":result.ok,"state":"connected","status_code":...,"data":redact_user_descriptions(result.data),"error":...}`.
    A CommServe non-200 (incl. 401) **passes through in the envelope** (our endpoint still returns 200) — not
    translated into a bare endpoint 401.
- **`Settings.internal_secret`** (`config.py`) from `CV_INTERNAL_SECRET` (default `None`). Operator sets it
  out-of-band in `~/.cv-healthcheck-env` (sourced into both the app and MCP envs); never in the repo.
- `tests/test_internal_endpoint.py` (+12, CommServe mocked, no live call): 503-not-configured (+client never
  built), 403 wrong/missing secret, 403 non-loopback, 400 ×6 (missing fields / bad capability / absolute /
  protocol-relative path), disconnected-200-no-client, connected-happy-redacts-description, CommServe-401
  passthrough.

### Notes
- **MCP not yet repointed** — the probe still calls the CommServe directly; pointing it at this endpoint is
  the final build step. Deferred in-endpoint (noted in code): oversized-response summarisation and reactive
  expiry (flip store to expired on a CommServe 401 — needs the auth-failure distinction).

---

## 2026-06-02 (ADR-0008 A wiring — login populates the held-token store; reads + cookie unchanged)

**Branch:** `feature/basic-healthcheck-report-output`. **839 passing** (was 837; +2 wiring tests).

### Changed
- **`set_current_token` (`auth/commvault_auth.py`) now ALSO publishes the token into the in-process
  `token_store`** (`set_active_token(token, principal=<cleaned username>, expires_at=None)`), after the
  existing session writes — an **addition**, the session cookie writes are byte-for-byte unchanged.
  `expires_at=None` because `login_to_commvault` returns only the token, no TTL (reactive expiry on a
  CommServe 401 is a later endpoint-side enhancement).
- **`clear_current_token` now also calls `clear_active_token()`** so the store never outlives the session.
  It's the single clear chokepoint behind `/logout` (`basic.py:73`) and the auto-clear paths
  (`quick_hc.py:214/381/441`, `shared.py:99`); the store-clear is unconditional (the store is
  process-scoped, not request-bound).

### Notes
- **Deliberately narrow:** this only *fills* the store so the upcoming loopback endpoint (brief #6) can
  read it via `get_active_token()`. **No token read is repointed, `is_authenticated()`/`is_authenticated_for()`
  are untouched, the web path is unchanged.** The read-repoint + de-cookie + gate change is the later
  consolidation step, done with the Connections-page "reconnect" UI — because the store is in-memory and
  empties on restart while the cookie survives, repointing reads before that UI exists would turn a restart
  into a silent failure.
- Tests authenticate by poking `session[SESSION_TOKEN_KEY]` directly (bypassing `set_current_token`), so
  those sessions don't fill the store — harmless here (reads unchanged), but a ripple to handle at the
  consolidation step.

---

## 2026-06-02 (ADR-0008 A — in-process held-token store module, not yet wired)

**Branch:** `feature/basic-healthcheck-report-output`. **837 passing** (was 829; +8 token-store tests).

### Added
- **`src/cvhealthcheck/token_store.py`** — the app's single in-memory held-token slot (ADR-0008 Flavour 1,
  no credential at rest). Stdlib only; imports nothing from Flask / web / MCP / `shared.py`, so both the web
  process and the future loopback endpoint can use it without a circular import. Public surface:
  `set_active_token(token, *, expires_at=None, principal=None)`, `get_active_token() -> str | None`,
  `clear_active_token()`, `status() -> dict`. A `threading.Lock` guards the slot (the dev server may serve on
  multiple threads). **Expiry is enforced in the store** — `get_active_token()` returns `None` once past
  `expires_at` (never a stale string), and `status()` distinguishes `"expired"` from `"disconnected"` so
  "expiry is visible, not silent" (ADR-0008 Decision 5) has a home. `get_active_token()` mirrors today's
  `_current_token()` shape (`str | None`) so the read-seam swap is a drop-in. **Single-process, single-slot**
  (ADR-0008 Consequences) — a multi-worker deployment would reintroduce cross-process sharing, which this
  does not solve. Token value never logged or returned by `status()`.
- `tests/test_token_store.py` (+8): set→get, clear/unset→disconnected, past-expiry→None+expired,
  future-expiry→connected, metadata round-trip through `status()`, epoch-float expiry, overwrite-replaces-slot.

### Notes
- **Not yet wired** — nothing imports this module yet (zero behaviour change, like `redaction.py`). Populating
  it at login and repointing the `_current_token()` reads is the next brief.

---

## 2026-06-02 (ADR-0008 D — extract user-description redaction to a shared module)

**Branch:** `feature/basic-healthcheck-report-output`. **829 passing** (unchanged — leaf refactor, no behaviour change).

### Changed
- **`redact_user_descriptions` moved out of the MCP probe into `src/cvhealthcheck/redaction.py`** (renamed
  from the private `mcp/server.py::_redact_user_descriptions`). Self-contained (stdlib only; imports nothing
  from the MCP/web/Flask layers), so **both** the MCP layer and the future app-mediated loopback endpoint
  (ADR-0008 C) can import it without a circular dependency — the app-mediated path must redact before
  returning, so redaction can no longer live only in the MCP module. `mcp/server.py` now imports it and the
  probe's single call site points at the new name. Logic + recursion are identical; the redaction tests
  (exercised through `probe`) stay green at 829.

---

## 2026-06-02 (MCP — `probe(path)` tool: exploratory Command Center REST GET, store-free)

**Branch:** `feature/basic-healthcheck-report-output`. **Not committed** (held for review + live smoke). **829 passing** (was 824; +5).

### Added
- **`probe(path: str) -> dict` MCP tool** (`mcp/server.py`) — an authenticated GET against an arbitrary
  Command Center REST path (e.g. `/commandcenter/api/v4/user`) that returns the response **store-free**
  (no artifact/catalog/db write, ever). Reuses the existing fetch primitive `CommvaultApiClient.get`;
  registered in the offload tuple so its blocking call runs in a worker thread (the #35 loop-blocking
  guard the registration comment already anticipates for "a live REST/CommCell call"). GET only.
  - **Non-200 is returned readable** (`ok`/`status_code`/`error`/`data` intact) so the first live call
    doubles as the auth-acceptance check; only a **transport failure** (connection/DNS/timeout, or unset
    `CV_BASE_URL` → `status_code is None`) raises `ValueError`.
  - **Redaction:** every user-record `description` is replaced with `[redacted: <n> chars]` (recursive,
    shape-agnostic — the V4 `/user` shape isn't pinned), all sibling fields raw. The raw `text` field is
    **dropped** from the result (it's the verbatim pre-redaction body that duplicates `data` for JSON —
    returning it would bypass redaction). Secret *detection* stays a propose-stage evaluator (field
    shape, not contents).
- Tests (`tests/test_mcp_tools.py`, +5, no live calls): passthrough+redaction, sibling-intact,
  non-200-returned-not-raised, transport→`ValueError`, nested/shape-agnostic redaction, and a
  writes-nothing guard (any `save_artifact`/`get_db` call explodes).

### Notes
- **Token model — interim, deliberate (documented in `_probe_token`'s docstring).** The probe authenticates
  with the operator-maintained, **session-less** token via a single swappable seam `_probe_token()` →
  `load_login_token()` (`​.login_token`/`CV_LOGIN_TOKEN`) falling back to `load_token()` (`.token`). This is
  **decoupled from the web Connections flow on purpose**: web connect binds a token to the Flask session
  (signed cookie) and persists nothing to disk/env (`set_current_token`), so a separate process can't read
  it. This is **not the end state** — the known destination is a **shared server-side token store** both the
  web and MCP processes read (Option 3), adopted when the MCP server becomes a routine companion to the web
  app; a connect-writes-token-to-disk bridge (Option 2) is a possible stopgap that may be skipped. Moving to
  the shared store swaps `_probe_token` only — `probe` is unaware of the source.
- **Identity guard deferred (noted, no round-trip added).** Acting-user identity is not cheaply available
  from an arbitrary-path GET: `ApiResult` carries no acting-user, the V4 `/user` response shape isn't pinned,
  and a dedicated whoami call would be a round-trip the brief said not to add. Flagged as a follow-up (a
  `whoami` probe or an acting-user field once a cheap source is confirmed). Surfacing the token *source* was
  rejected — it would make `probe` care where the token comes from, violating the swappable-seam principle.
- **`API_MAPPING.md` intentionally NOT updated** — gated on a live `GET /commandcenter/api/v4/user` validation
  (auth acceptance + actual response shape); the first `probe` call is that check.

---

## 2026-06-01 (ADR 0007 Phase 3 slice B — retire the live environment builder; environment fully on the declarative path — **ADR 0007 COMPLETE**)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `c44d6b1`. **824 passing** (was 836; −14 = the obsolete `test_environment_per_field.py` removed, +2 new). Net **−337 lines** of code.

### Removed
- **`_build_environment_subject` and its helper cluster** (217 lines): `_build_environment_identity_section`,
  `_load_environment_card_block`, `_load_environment_identity_rules`, `_normalize_timezone`,
  `_hex_commcell_id` — plus the `if subject_id == "environment"` dispatch special-case and the
  now-unused `import re` / `build_card_section` import. Environment is no longer registered in
  `_legacy_builders()`; it is served by the uniform "canonical store wins" generic path like every
  other subject. **The live-serve special case for environment is GONE.**
- `tests/test_environment_per_field.py` (257 lines) — entirely tested the removed live builder; the
  9-field card + per-field rules + view_mode are covered by the extractor / canonical-view tests.

### Changed
- **Empty-state (pre-first-collect):** `_build_generic_subject`'s no-artifact branch now default-selects
  the first source, so the command-center tab's Collect button is visible before the first collect; and
  the dispatch builds the generic not-collected state for builderless tiles in the no-db `list_tiles`
  path too (previously dropped) — so environment is never skipped there.
- **3 cosmetics absorbed in the generic path** (so removal is a visual no-op): CC source badge `v`
  (Validated) when an artifact exists else `a`; CC source description from `SOURCE_DESCRIPTIONS` (was
  empty); subtitle `"<host> · <version>"` derived from the identity card for command-center artifacts
  (was "Data available").

### Notes
- **Caller audit (the gate before deletion):** the only live reference to the removed functions was the
  `legacy_builders` registration; everything else was the dying cluster, migration **comments**, or
  tests. No route / report page / detail GET called them. **KEPT** (shared, not env-specific):
  `_load_legacy_commcell` (feeds the CommCell header), `get_commcell_identity` (used by the Command
  Center **extractor**), `_build_tile_sources`, `_nodata_subject`, `_command_center_*`.
- **Row 7** (the stale plain-`rest` environment source) left **INERT, not deleted**: its only reader
  (`_load_environment_card_block`) is now gone and its tab was suppressed in slice A; deleting it would
  require cascading its FK-child binding (`subject_section_sources`) for zero functional gain — so per
  the "don't delete if an FK depends on it" guard, it stays (invisible).
- **Behavior change worth noting:** environment no longer auto-renders its card from the global
  `commserv.json` — it shows its card from a **collected artifact** (nodata until first collect), exactly
  like every other subject. The CommCell header still reads `commserv.json` via `_load_legacy_commcell`.
- **Visual no-op verified** (real dispatch, stored artifact): CommCell Details · subtitle
  `cs01 · 11 SP40.47` · CC tab active · badge Validated · Endpoint/Host meta · "Last collected" (local) ·
  9-field table · per-field verdicts. **Reviewer gate:** `./start.sh` + cache-busted reload — environment
  must render the SAME as before, plus sanity-check the empty state (a fresh/uncollected environment
  shows the not-collected tile with the Command Center tab + Collect, not a crash/blank). Final
  confirmation is the reviewer's browser + a fresh live collect.

---

## 2026-06-01 (UI — surface command-center source metadata in the generic panel + group "Last collected" with Collect)

**Branch:** `feature/basic-healthcheck-report-output`
**Commit:** `7e85c95`. **836 passing** (was 832; +4).

### Added
- **`SOURCE_ENDPOINTS` registry constant** — the REST endpoint a live source collects from, keyed by
  canonical source id (`rest_command_center_api → "GET /commandcenter/api/CommServ"`). Source-TYPE
  metadata, mirroring `SOURCE_DESCRIPTIONS`; sources without a fixed single endpoint are absent.

### Changed
- **The shared generic source panel now surfaces the command-center descriptor** instead of "No source
  metadata is available yet." `_build_generic_sources` attaches **Endpoint** (the `SOURCE_ENDPOINTS`
  constant) + **Host** (read from the collected identity card via `_command_center_host` — Hostname,
  fallback CommCell Name) to the `rest_command_center_api` source. Built entirely in the **generic
  path**, so it survives the live builder's retirement. Other source types keep empty meta (no
  regression — no generic source surfaced meta before; the placeholder still shows when meta is
  genuinely absent).
- **"Last collected" moved INSIDE the source card**, grouped with the Collect button (action + last-run
  as one unit), rendering whether or not a Collect action exists. Still routed through `fmtUtc` →
  `window.fmtLocalTime`, so local-time rendering is preserved. The **Template dropdown is untouched** —
  it stays in the provenance block below the card.

### Notes
- **Host is read from the card, not the source block.** The artifact's `source.commcell_name` is the
  *customer* name ("Default"); the CommCell host ("cs01" = `cc.hostName`) lives only in the collected
  identity card. So `_command_center_host` reads it from the card (graceful: absent → Host row omitted).
  The cleaner long-term home is populating `source.endpoint`/host at collect time, but that touches the
  stored artifact (out of scope here).
- **Slice-B readiness:** after this slice the generic CC source `meta` matches the live builder **exactly**
  (Endpoint + Host=cs01). The only remaining live-builder-unique output is **cosmetic** — `status` badge
  (Validated vs Available), the source `description` text, and the tile `subtitle` (`cs01 · 11 SP40.47`
  vs "Data available"). `_build_environment_subject` is now **fully replaceable**; source metadata was the
  last substantive thing it uniquely authored. (`_build_environment_subject` was NOT retired this slice.)
- Untouched: collect/extractor/auth logic, storage, artifact schema, CEL, the evaluate path, the report
  page, and the Template selector.
- **Reviewer browser check (needs `./start.sh` + cache-busted reload):** (i) environment — source card
  shows Endpoint + Host (not the placeholder), "Last collected" sits inside the card next to Collect in
  local time, Template unchanged below; (ii) a non-CC subject (e.g. License Summary / Client Growth) —
  panel still renders, "Last collected" relocated consistently, no regression. Final confirmation is the
  reviewer's browser.

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

## 2026-05-25 (unified-upload session 4 — old upload routes deleted)

<!-- date corrected from a future-typo "2026-06-05"; commits c06309d/b873431/6e0b1ed are 2026-05-25. Left in place within the consolidation tail (not reordered). -->

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
