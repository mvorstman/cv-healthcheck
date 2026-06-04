# ADR-0011: Version-aware comparison operators for rule evaluation

- **Status:** Accepted (2026-06-04 — shipped: `version_lt`/`version_gte` + the comparison primitive; Rule 2 authored and confirmed live)
- **Date:** 2026-06-04
- **Related:** builds the version-compare primitive named in ROADMAP item 1; prerequisite for the live-baseline vision (ROADMAP item 2). Unblocks the deferred "Rule 2" parked at the end of the `commserve_software_cache` rule session.

## Context

The row-scope rule engine compares a row's column value against a literal (or another column `ref`) using a flat operator vocabulary: `eq`, `ne`, `lt`, `gt`, `contains`, `not_contains`, `between`. `lt`/`gt` compare lexically or as plain scalars.

`commserve_software_cache.cache_contents` holds the per-platform cached service-pack versions (~3 rows — WinX64 and friends), expressed as dotted version strings of the form `release.FR.MR` (e.g. `11.40.51` = release 11, Feature Release 40, Maintenance Release 51). The deferred **Rule 2** needs to flag any platform whose cached version is **below a minimum** (the worked example: `WinX64 ≥ 11.40.51`).

The existing operators cannot express this correctly. Compared lexically, `"11.40.9"` sorts **above** `"11.40.51"` — the first differing character is `9` vs `5`, and `9 > 5`. So a naive `lt "11.40.51"` test reports that `11.40.9` is *not* below the minimum and lets an out-of-date row pass, when numerically MR 9 is older than MR 51. This is the exact inversion that makes the rule mis-fire.

This comparison is also the primitive the ROADMAP's live-baseline vision depends on (evaluate cache / clients / SP against the *current recommended release* instead of a hardcoded threshold). Building it once, correctly, as a reusable primitive avoids a second pass later.

Constraints carried in:
- **Separation of collection and evaluation** — comparison is an evaluation concern, not a collector concern.
- **No artifact churn** — `cache_contents` is byte-stable, and a fresh collection is currently token-gated (stale CommServe token 401s).
- **Authoring-time validation** — `save_rule` rejects unknown operators before persisting, so any new operator must be registered on the authoring side too, or Rule 2 can't be saved.
- **MCP module cache** — the running `cv-healthcheck-mcp` caches imported modules and must be restarted after engine changes, or it serves stale code (this masked Rule 1 last session).

## Decision

Introduce version-aware comparison as **evaluation-time operators backed by a single shared comparison primitive**.

### D1 — Comparison lives in the operator, at evaluation time (not in the extractor)

The operator normalizes both operands and compares them component-wise when a rule runs. The comparator is a standalone function (`compare_versions`-style, returning ordering) that the operators — and, later, the baseline evaluator — call.

Rejected alternative: precomputing a numeric comparison key in the artifact at extraction time. That smears an evaluation concern into collection, bloats the canonical artifact, forces a re-collection (token-blocked right now), and still leaves the rule's literal threshold to be parsed somewhere.

### D2 — Version normalization grammar (confirm against real data first)

A version is normalized by taking its maximal leading run of integer components separated by `.`, ignoring an optional leading non-digit token (`v`, `SP`, …). Compare as left-aligned integer tuples; missing trailing components are treated as `0`, so `11.40` == `11.40.0`.

- `"11.40.51"` → `(11, 40, 51)`
- `"11.40.9"`  → `(11, 40, 9)`
- `(11, 40, 9) < (11, 40, 51)` ✓ — the case lexical comparison gets wrong.

A string with no parseable leading numeric component (blank, `Unknown`, `Unlimited`, `N/A`) is **unparseable** — handled by D4. (`Unlimited` stays a string by project convention; here it is simply unparseable, not coerced.)

**Verify-first:** confirm the actual `cache_contents` version *field name* and *string form* against the **stored** canonical artifact before finalizing the parser — no live Connect required (the data is already in the canonical store). Design the parser against the real strings, not an assumed format.

### D3 — Operator surface: expose the two the rule needs; back them with a full-ordering comparator

Add `version_lt` and `version_gte` now — Rule 2 needs "below minimum" (the finding condition) and its complement. The underlying comparator yields full ordering, so `version_gt`, `version_lte`, `version_eq`, and `version_ne` are each a one-line addition the moment a future rule needs one — **not built now** (no current consumer). This avoids both unused surface and a rework when the next version rule appears.

### D4 — Unparseable operands: fail loud on the author side, degrade gracefully on the data side

- **Unparseable rule literal** (the threshold the author typed, e.g. `value: "eleven-forty"`): rejected at authoring time by `save_rule`, same class as an unknown operator. A typo in a rule should fail loudly, not silently grey every row.
- **Unparseable row value** (the data, e.g. a blank or `Unknown` cached version): that row evaluates to **not_evaluated** (grey), with the reason recorded — never a false `good` or false `critical`. Consistent with the existing `not_evaluated` legend entry and the `in_scope`/gating model.

### D5 — Discrete named operators, not a single parameterized `version_compare`

Matches the existing flat operator vocabulary that `save_rule` and rule authors already use, and keeps rule JSON uniform.

## Consequences

- **Rule 2 is NOT blocked by the stale token.** `evaluate_subject` runs the new operator over the already-stored `cache_contents` artifact, so impl → author → validate can all happen now. Only the eventual pretty live re-render of `/quick-hc` is token-gated.
- **Two registration points must stay in sync** — the evaluation-time operator registry and the `save_rule` authoring whitelist. If only the evaluator learns the operator, `save_rule` rejects the Rule 2 authoring; if only the whitelist learns it, evaluation breaks. Prefer a single source of truth consumed by both.
- **MCP restart required** after the engine/rules code change (`pkill -f cv-healthcheck-mcp` + reconnect), or it serves stale modules — the failure that masked Rule 1 last session.
- **No migration, no artifact change** — `cache_contents` is untouched.
- **Forward (vision):** the comparator is the reusable seam for the live-baseline feature — the operand becomes "current recommended/GA MR pulled from a Commvault baseline" evaluated through the same code path. This ADR builds the primitive; the baseline wiring is a later ADR.
- **Deferred to Michiel, not decided here:** Rule 2's severity (warning vs critical) and the actual minimum version are rule-authoring choices.

## Acceptance test

1. Read the **stored** `commserve_software_cache` artifact; confirm the `cache_contents` version column name and the real per-platform values (~3 rows).
2. Unit-test the comparator: `(11,40,9) < (11,40,51)`; padding `11.40` == `11.40.0`; equal strings; an ascending and a descending pair; unparseable → sentinel/None.
3. Add `version_lt` + `version_gte` to the evaluator **and** the authoring whitelist; restart the MCP server.
4. Author Rule 2 via `save_rule`: `row_match` on `cache_contents`, condition `{target: <version col>, operator: version_lt, value: <minimum>}`, severity per Michiel, `message` templated on `{row.<col>}`; bind to `cache_contents`.
5. `evaluate_subject commserve_software_cache` (dry-run, persists nothing): rows below the minimum flag, rows at/above stay `good`, any blank/`Unknown` version row reads `not_evaluated` — not mis-flagged. **Pick a minimum that splits the real rows** so ordering is actually exercised (not one all rows pass or all fail).
6. Explicitly confirm the lexical trap: a row that lexical `lt` would mis-order (an `x.y.9` value against an `x.y.51` minimum) gets the correct verdict.

## Alternatives considered

- **A — Eval-time version operators backed by a shared comparator.** *Chosen.* Keeps comparison in the evaluation layer, no artifact change, reusable primitive for the baseline vision.
- **B — Extract-time numeric coercion** (store a comparable key in the artifact, reuse existing `lt`/`gte`). Rejected: couples evaluation into collection, bloats and re-collects the artifact (token-gated now), still needs the literal parsed somewhere.
- **C — Lexical zero-pad hack** (pad each component to fixed width as strings). Rejected: brittle — it must guess a maximum component width and breaks the first time an MR exceeds the pad — and stays string-typed. A worse comparator.
- **D — Per-rule custom expression / scripting.** Rejected: far past current needs, opens a validation/injection surface, and contradicts the declarative-rule model.

## Out of scope / deferred

- The other four operators (`gt`/`lte`/`eq`/`ne`) until a rule needs them.
- `between` for versions (no consumer).
- Live Commvault baseline sourcing — separate ADR; this is its prerequisite.
- Token refresh / live re-collect — operational, unrelated to this primitive.
