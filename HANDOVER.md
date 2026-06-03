# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (ADR-0010 Phase 1 — row-scope evaluation core landed; **Phase 2 next**)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *Add row-scope evaluation rules (ADR 0010 Phase 1)* — coerce + row_match + the result_to_artifact compliance pass (this commit).
**Test status:** **922 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md` — what the project is, how to run it.
2. `HANDOVER.md` (this file) — what to do next.
3. `ROADMAP.md` — direction.
4. **`docs/adr/0010-row-scope-evaluation-rules.md`** — the governing ADR for the current work (*Accepted*). The reconciliation that replaced the original Layer-5 spec.
5. **`docs/adr/0004-three-face-metadata-vocabulary.md`** (+ the ph8 rules registry) — the *existing* evaluative engine ADR-0010 extends; and **ADR 0006** (one canonicalization path), **ADR 0009** (the most recent complete arc).
6. The most recent CHANGELOG entries (2026-06-03 ADR-0010 Phase 1; 2026-06-02 ADR-0009 + the delete_subject fix).

---

## What was just completed

**ADR-0010 Phase 1 — the pure evaluation core + the canonicalization integration point.** Row-scope rules can now judge **table rows** (the gap the per-value engine couldn't reach):

- `evaluative/coerce.py` — centralized value coercion (units → number, `Unlimited`→+∞, `N/A`/absent, ISO + unix-epoch for `stale_days`).
- `evaluative/row_match.py` — `evaluate_row_rule(rule, rows)`: multi-condition **AND** predicates, field-to-field `{ref}`, `emit=per_row` (**`row_ref` = id, not name**) / `emit=count`, full operator set, `{value}/{target}/{count}/{row.<col>}` templating.
- `result_to_artifact` compliance pass — bound `row_match` rules → a derived **`<subject>.compliance` FindingsSection**, folded into the summary; read-only over the rows. `ExtractionResult.section_row_rules` carries the bindings.
- `tests/test_row_match_adr0010.py` (+37, incl. the `rommelgroep` duplicate-id correctness fixture).

**Prior on this branch (all committed):** ADR-0009 D1/D2 + Phase 1 staging consolidation (`f001339` / `5891076` / `1130baa`), and the `delete_subject` staging-reconciliation fix (`ae28dac`).

---

## Single recommended next action — ADR-0010 **Phase 2** (separate session)

Wire the core to the catalog + the MCP, and prove a real rule fires. **Three decisions are already settled — carry them in:**

1. **One `<subject>.compliance` FindingsSection per subject** (not per-rule) — already how Phase 1 emits.
2. **Build `evaluate_subject` (the dry-run) FIRST** — the rules-side parallel to `probe`: load the latest approved artifact, run enabled `row_match` rules, return the findings preview **without persisting**.
3. **`save_rule` rejects the malformed cases:** a row rule bound to a **non-table** section; a `{ref}` to a **missing column**; `emit=count` **without** `count_operator`/`count_value` (plus `between` without `value2`, unknown operators).

Then the rest of Phase 2: registry `kind:"row_match"` rows; the section binding (`extraction_instructions.evaluative.row_rules: [{"ref": rule_id}]`); the extractors resolving those refs into `section_row_rules` (so a catalog rule fires on collection); and `list_rules` / `save_rule` / `delete_rule`. Each phase ends `compileall` + `pytest` green.

---

## Other notes

- **Phase 1 boundary (important):** nothing populates `section_row_rules` from the catalog yet, so **no catalog-authored rule fires on a real collection** — the pass is a no-op until Phase 2 binds rules. The 37 tests drive it directly.
- **D5 (accepted):** findings are an **in-artifact** derived FindingsSection (re-derived on next collection / in the dry-run), **not** a separate store. Revisit a store only if persistent ack (surviving re-collection) or cross-engagement trend analysis becomes a goal.
- **Fixtures are real:** `clients`, `server_groups`, `users` are live AI table subjects; the row-scope test signals (server_groups empty group + duplicate `rommelgroep` ids 19/41; users never-logged-in epoch 0 + locked) come from their real shapes.
- `HEALTHCHECK_MATRIX.md` now carries the row-scope evaluation row (IMPLEMENTED, not yet data-verified).
- Possibly still operator-pending from ADR-0009: the in-browser acceptance test (re-propose a CC-API subject → approve → Collect hits `/v4/servergroup`, renders a table) — independent of Layer 5.
