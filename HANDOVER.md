# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (ADR-0010 **Phase 2a** done — catalog binding + the `evaluate_subject` dry-run, proven live; **Phase 2b next**)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *ADR 0010 Phase 2a — catalog binding + evaluate_subject dry-run* (this commit).
**Test status:** **929 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md` — what the project is, how to run it.
2. `HANDOVER.md` (this file) — what to do next.
3. **`docs/adr/0010-row-scope-evaluation-rules.md`** — the governing ADR (*Accepted*). D2 (ref-from-binding), D3 (own grain), D5 (in-artifact findings).
4. The most recent CHANGELOG entries (2026-06-03 ADR-0010 Phase 2a and Phase 1).
5. Context: ADR 0004 ph8 (the rules registry + evaluative engine ADR-0010 extends); ADR 0006 (one canonicalization path).

---

## What was just completed — ADR-0010 Phase 2a

The Phase-1 evaluator is now **connected to the catalog and proven live**:

- **`db.rules.load_subject_row_rules(db, subject_id, version)`** — resolves a section's `extraction_instructions.evaluative.row_rules: [{"ref": rule_id}]` against the rules registry → `{section_id: [row_match defs]}`.
- **`evaluative/subject_eval.py:evaluate_subject(db, subject_id)`** — the dry-run (rules-side `probe`): runs the bound rules over the **latest stored artifact**, returns a findings preview, **persists nothing**.
- **Extractor wiring** — `RESTExtractor` + `CommandCenterExtractor` populate `result.section_row_rules`, so rules fire on a real collection (the canonicalization pass bakes a `<subject>.compliance` FindingsSection).
- **Live proof** (rules authored into `data/app.db`): `server_groups` → 12 empty-group findings incl. both `rommelgroep` (ids 19 & 41) distinct; `users` → 2 never-logged-in. +7 tests (929 total).

---

## Single recommended next action — ADR-0010 **Phase 2b** (the MCP authoring surface)

Build the MCP tools (none exist; `probe` is the read-only parallel). **`evaluate_subject` already exists as a service** — wrap it as the first/simplest tool.

1. **`evaluate_subject`** (MCP) — wrap `evaluative.subject_eval.evaluate_subject`; the dry-run preview.
2. **`list_rules`** (`subject_id?`, `enabled?`) — mirror `list_subjects` shape (read the `rules` registry; `db.rules.load_rules_registry` is the loader).
3. **`save_rule`** — upsert a `row_match` definition into the `rules` registry (a low-level `db.rules.save_rule` helper is intentionally NOT built yet — add it with the validation). **`save_rule` must reject** (the settled cases): a row rule bound to a **non-table** section; a `{ref}` to a column **not in the section's extraction columns**; `emit=count` **without** `count_operator`/`count_value` (plus `between` without `value2`, unknown operators). Fail at authoring time, not silently at collection.
4. **`delete_rule`** (`rule_id`) — delete from the registry.

Binding a rule to a section (writing `evaluative.row_rules`) is a related authoring action — decide whether `save_rule` also binds (it takes a subject/section), or binding is its own tool. The ADR keeps the rule body subject-agnostic; the binding is separate (today done by direct catalog writes — see the Phase-2a proof script pattern).

---

## Other notes

- **Settled (do not relitigate):** one `<subject>.compliance` FindingsSection per subject; `row_ref = id, never name`; findings baked in at canonicalization, no separate store (D5); `row_match` is its own evaluator grain (D3).
- **Live catalog now carries 2 real rules** (`sg_empty_group`, `users_never_logged_in`) + their bindings on the `rest_command_center_api` section sources of `server_groups`/`users`. They will fire on the next Collect of those subjects (extractor wiring). Keep or replace them via Phase-2b `save_rule` once it exists.
- Duplicate *detection* is cross-row → out of `row_match`'s per-row grain (a future `count`/aggregate kind if needed); the `rommelgroep` case is handled as distinct per-row findings.
- `clients` has a row rule target too (e.g. an empty-`hostname` or missing-company check) — a good third real rule once `save_rule` lands.
- Possibly still operator-pending from ADR-0009: the in-browser CC-API Collect acceptance test — independent of Layer 5.
