# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (**ADR-0010 complete** — row-scope evaluation rules: core + binding + dry-run + MCP authoring)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *ADR 0010 Phase 2b — MCP authoring surface for row-scope rules* (this commit).
**Test status:** **939 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md` — what the project is, how to run it.
2. `HANDOVER.md` (this file) — what to do next.
3. **`docs/adr/0010-row-scope-evaluation-rules.md`** — the governing ADR (*Accepted*, now fully implemented).
4. The most recent CHANGELOG entries (2026-06-03 ADR-0010 Phase 2b / 2a / 1).
5. Context: ADR 0004 ph8 (the rules registry + evaluative engine ADR-0010 extends); ADR 0006 (one canonicalization path).

---

## What was just completed — ADR-0010 is complete end to end

Data-driven row-scope health rules over table subjects, authored via MCP, evaluated into the artifact:

- **Phase 1** — `evaluative/coerce.py` + `evaluative/row_match.py` (the row evaluator) + the `result_to_artifact` compliance pass (derived `<subject>.compliance` FindingsSection).
- **Phase 2a** — `db.rules.load_subject_row_rules` (resolve `evaluative.row_rules:[{ref}]`), `evaluative/subject_eval.evaluate_subject` (dry-run over the latest artifact, persists nothing), extractor wiring (rules fire on Collect).
- **Phase 2b (this)** — MCP tools `evaluate_subject` / `list_rules` / `save_rule` / `delete_rule`; `db.rules` helpers (`save_rule` with version-bump, idempotent `bind_rule`, `delete_rule` strips refs, `list_rules`); **authoring-time validation** (`validate_row_match_rule`); `load_subject_row_rules` skips disabled rules.

**Live (in-process):** `list_rules()` → the catalog rules; `evaluate_subject("server_groups")` → 12 findings. **The MCP client must reconnect (`pkill -f cv-healthcheck-mcp`) to see the 4 new tools.**

---

## Single recommended next action

ADR-0010 is done; **no forced next step.** Candidate directions, none blocking:

1. **Author real rules via `save_rule`** now that it exists — e.g. a `clients` rule (empty `hostname`, or missing `company`), a `users` locked/disabled check, a `server_groups` over-large-group `count` rule. Replace the two hand-authored Phase-2a rules (`sg_empty_group`, `users_never_logged_in`) through the tool so they carry `version`/`created_by`/`enabled`.
2. **Render the compliance findings** in the Quick HC report / UI (they're in the artifact as a `<subject>.compliance` FindingsSection; confirm the report surfaces them).
3. **Deferred ADR items** (only if needed): summary-scope rules (the validator carries the `scope=summary` TODO — must reject `emit != once`); a **count/aggregate kind** for cross-row duplicate *detection* (`row_match` is per-row); a **separate findings store** only on the D5 revisit trigger (persistent finding acknowledgement surviving re-collection, or cross-engagement trend analysis).
4. **Branch review/merge** — this branch is well ahead of `main` (ADR-0008/0009/0010 all complete); consider a review + merge.

---

## Other notes

- **Settled (do not relitigate):** one `<subject>.compliance` FindingsSection per subject; `row_ref = id, never name`; findings baked in at canonicalization, no separate store (D5); `row_match` is its own evaluator grain (D3).
- The live `data/app.db` carries the two Phase-2a rules (`sg_empty_group`, `users_never_logged_in`) + bindings — they fire on the next Collect of `server_groups`/`users`. Keep, or re-author via `save_rule`.
- `save_rule(rule, bind={subject_id, section_id})` is one call for author+fire; rule body and binding stay separable (one rule → several sections via repeated binds).
- Possibly still operator-pending from ADR-0009: the in-browser CC-API Collect acceptance test — independent of Layer 5.
