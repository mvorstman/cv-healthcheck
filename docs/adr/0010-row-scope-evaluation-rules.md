# ADR 0010 — Row-scope evaluation rules as a registry extension (Layer 5 reconciliation)

- **Status:** Accepted
- **Date:** 2026-06-03
- **Deciders:** Michiel (sole maintainer)
- **Reconciles:** `layer5_rules_spec_v0.1` — whose framing ("Layer 5 is deferred / unbuilt", a standalone `rules`+`findings` store, migration `0005`) is wrong against this tree. This ADR keeps the spec's genuinely-new capabilities and drops the collisions.
- **Extends:** ADR 0004 phase 8 (the rules registry + the `evaluative/` engine + verdict chains).
- **Within:** ADR 0006 (declarative extraction boundary — D1 one canonicalization path; D2 structural surface).

---

## Context — what is already built (verified against HEAD `ae28dac`)

The "deferred Layer 5" is substantially built. Grounded facts:

- **Registry:** a single `rules` table (migration **0018**), flat `rule_id → definition_json`, referenced by `{"ref": rule_id, …binding}` from **section bindings** (`subject_section_sources.extraction_instructions`). It has **no** `subject_id`/`section_id` columns — a rule is subject-agnostic; the binding supplies the target. `db/rules.py` only loads it.
- **Engine** (`evaluative/engine.py`): `evaluate(value, template_rules, …) -> (severity, verdict_chain)` — a **per-VALUE** evaluator, kind-dispatched (`threshold` / `presence` / `enum` / `format`), composing **vendor → template → override**. Called **only** from `metric_section` / `card_section` per field, inside `result_to_artifact` — i.e. at **canonicalization time, never at approval**.
- **Findings today, two mechanisms:** (a) metric/card **verdicts** — engine-derived `severity` + `verdict_chain` written onto items/sections, in the artifact; (b) **FindingsSection** items **transcribed at extraction** (`output_as="findings"`, e.g. `security_assessment`). There is **no findings table** and **no rule-derived FindingsSection**.
- **Overrides** (migration 0019): keyed `(customer, project?, subject, version, section, rule_id)` — per **rule**.
- **MCP:** no rules tools exist; `probe` is the existing dry-run parallel.
- **Targets exist:** `clients`, `server_groups`, `users` are active AI table subjects.

**The genuine gap.** The engine judges a **single scalar field** on metric/card sections. It **cannot judge a table row at all.** The new table subjects need: row-scope predicates, multi-condition **AND**, **field-to-field** comparison (`used > available`), **emit modes** (`per_row` / `count`), and operators beyond numeric bands (`contains` / `between` / `stale_days` / `exists`). That is net-new and worth building — *through* the registry's extensibility, not by contorting the per-value evaluator.

---

## Decision

### D1 — No new table; a row-scope rule is a new **kind** in the existing registry.
Store it as a `rules` row whose `definition_json` is `{ "kind": "row_match", "conditions": [...], "emit": ..., "count_operator"?, "count_value"?, "severity", "title"/"message"/"recommendation" }`. This dissolves the `CREATE TABLE rules` collision, keeps **one** rules system, and needs no schema change.

### D2 — A row-scope rule is **bound from the table section**, not self-describing its subject.
Consistent with the existing ref-from-binding model: the table section's `extraction_instructions` gains `evaluative: { "row_rules": [ {"ref": rule_id} ] }`. Rules stay subject-agnostic; the binding supplies the `(subject, section)` association. → **no `subject_id`/`section_id` columns, no migration 0029.**

### D3 — A new evaluator at **row grain**, reusing vocabulary + primitives, **not** a branch in the per-value dispatcher.
Honest finding from the engine: `_evaluate_rule(rule, value)` is **value**-grained (scalar → one VerdictEntry). A row-match is **dict**-grained (AND of predicates over a row → a match boolean → a finding). So the row evaluator is a **new function** (e.g. `evaluative/row_match.py`) that reuses the `VerdictEntry` / `FindingSeverity` vocabulary, the comparison/coercion primitives, and the registry storage — but it is its own entry point. It does **not** slot into `_evaluate_rule`'s kind-dispatch, which only makes sense for scalar verdicts. *(This refines the steer's "new rule kind": new kind in the registry **definition**, new **evaluator** at a new grain.)*

### D4 — Findings attach as a **derived FindingsSection**, at **canonicalization time**.
Row-scope evaluation runs inside `result_to_artifact` (the one canonicalization path — ADR 0006 D1), after `TableSection`s are built; matching rows / counts produce a derived **FindingsSection** on the artifact (the existing findings shape + render path). Therefore evaluation is **auto-applied on every collection** — the original spec's approval-time hook (§7) is **unnecessary** — and re-derived by re-collection. The dry-run (`evaluate_subject`) re-runs the same evaluator over the **latest stored artifact without persisting**.

### D5 — The re-derivability tension, decided with eyes open.
The original spec's **locked** principle — "findings never modify the artifact; a separate store; change-a-threshold-and-re-derive without rewriting history" — conflicts with D4 (findings as an in-artifact FindingsSection). Grounded reality: the existing engine **already bakes verdicts into the artifact at collection**; D4 follows that established pattern rather than inventing a parallel store the codebase doesn't have. **Accepted consequence:** a row-scope rule change takes effect on the **next collection** (or immediately in the `evaluate_subject` dry-run preview), **not** by rewriting stored artifacts. We do **not** add a separate findings store now. *If* "persistently re-derive + store findings after a rule change without re-collecting" later becomes a hard requirement, that is a **separate, deferred** decision (a findings store keyed `(subject, artifact_ref)` reading stored artifact + current rules) — explicitly out of scope here.
**Revisit trigger:** revisit a separate findings store only if **persistent finding acknowledgement** (a finding's ack/`status` surviving re-collection) or **cross-engagement trend analysis** becomes a goal.

### D6 — Value coercion: one centralized, tested helper.
Carry forward original §4.1 (the existing `_coerce_number` / `_resolve_field_path` cover field access but **not** units/`Unlimited`/absent): parse leading-numeric from unit strings (`"0 TB"`→0, `"4 clients"`→4); `"Unlimited"`→+∞ (so `used > Unlimited` is always false); `"N/A" | "-" | "" | null` → **absent** (a comparison against absent is **false**, not an error; `exists`/`not_exists` test exactly absence). **Plus:** `lastLoggedIn` on `users` is **unix epoch** (`0` = never) — distinct from the ISO-date `stale_days` case; both noted in the helper. One module (`evaluative/coerce.py`), unit-tested, reused by the row evaluator.

### D7 — Override grain for row-scope.
`rule_overrides` is `(subject, section, rule_id)`-grained — per **rule**. A row-scope override therefore mutes / re-severities the **whole rule** for a `(subject, section)`; it does **not** target an individual matched row (rows are dynamic — no stable per-row override key). Per-row overrides are out of scope.

### D8 — MCP surface (new).
Add `list_rules` / `save_rule` / `delete_rule` / `evaluate_subject` (dry-run, the rules-side `probe`). `save_rule` validates the `row_match` kind: known operators only; `between` requires `value2`; `emit=count` requires `count_operator` + `count_value`; conditions reference resolvable targets; the bound section exists **and is a table**.

---

## Consequences
- **One** rules system, **one** canonicalization path (ADR 0006 D1 held) — the table-name collision and parallel-evaluator risk are gone.
- Row-scope is the **first non-scalar evaluator** in the engine package; the verdict-chain audit model extends to per-row / per-count findings.
- **No new migration** unless a future need (e.g. a row-rule lookup index) actually appears.
- Accepted limitation (D5): rule changes re-derive on next collection / via dry-run, not by rewriting stored artifacts; no separate findings store now.
- The original spec's **§9** (migrate environment, retire its Python) is **dropped** — already done (migration 0023 moved environment's card rules to data; the Python builder is gone, with a test asserting it). `security_assessment` stays pass-through (out of scope), as the spec said.

---

## Open questions (confirm at build time, not now)
- **FindingsSection identity** for derived findings: one synthetic section per subject (e.g. `<subject>.compliance`) vs per-rule. Lean: one per subject; items carry `rule_id` + `severity` (fits the FindingsSection render path).
- **Insertion point** in `result_to_artifact`: after all sections are built, read the bound `TableSection` by `section_id` and run the row pass. Confirm it composes cleanly with the existing metric/card verdict pass.
- **`stale_days` / epoch** home: `coerce.py` (value normalization) vs the predicate evaluator (time-relative compare needs "now").
- **Stable `row_ref`** for `emit=per_row`: requires the table artifact to carry a stable per-row id. `server_groups` (duplicate name `rommelgroep`, ids 19 & 41) confirms the **id**, not the name, is the stable key.

---

## Validation (for the implementation phase — phased after this ADR is Accepted)
- **Phase 1 (core, no MCP/hook):** `evaluative/coerce.py` + `evaluative/row_match.py` + the `result_to_artifact` row pass + tests — coercion (units / `Unlimited` / absent / epoch); AND (all-true vs one-false); field-to-field `{ref}` (`used > available`); `emit=per_row` (N findings, `row_ref` = id); `emit=count` threshold; operators `contains`/`between`/`stale_days`/`exists`. First real fixtures: `server_groups` empty group (`server_count` 0) + duplicate name; `users` never-logged-in (epoch 0) + locked/disabled.
- **Phase 2 (MCP):** `list_rules` / `save_rule` / `delete_rule` / `evaluate_subject`; `save_rule` validation rejections; dry-run persists nothing.
- Each phase ends `python -m compileall src` + `python -m pytest` green.

*Per Workflow.md, work stops at this ADR for review. On Accepted: implement Phase 1, then Phase 2; docs to CHANGELOG (append-only) + HANDOVER; record validated behaviour in `HEALTHCHECK_MATRIX.md`.*
