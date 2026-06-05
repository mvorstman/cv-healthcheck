# ADR 0006 — Declarative Extraction Boundary & Transform Stop-Rule

## Status

Accepted (2026-06-01).

## Date

2026-05-30

## Context

A proposal circulated to introduce a generic source-importer framework — per-subject importer classes behind a `SourceImporter` protocol. Investigation established that the generic, declarative framework **already exists**:

```
source bytes
  → recognition            (recognition_hints match subject_id + version)
  → extraction             (extraction_instructions → generic HTML/CSV/REST extractor)
  → ExtractionResult       (raw rows per section + carried specs + section_failures)
  → result_to_artifact     (builds CanonicalArtifact; evaluates verdicts; sets summary)
  → ArtifactStore          (Pydantic-validated canonical artifact)
  → render                 (source-independent view of canonical sections)
```

A second importer framework would be redundant, and per-subject importer classes would reintroduce exactly the coupling the proposal aimed to remove. The real, ongoing risks are not "missing framework"; they are:

1. **Uncontrolled growth of the declarative surface** — `extraction_instructions` drifting into an untyped programming language one operator at a time (the inner-platform trap).
2. **Parallel / divergent canonicalization** — more than one path producing a `CanonicalArtifact`, with semantics kept in sync by hand.

This ADR bounds both. It is a **judgment artifact**: where it draws a line, that line is a deliberate decision, not a default to be widened under delivery pressure.

## Decision

### D1 — The pipeline boundary is fixed

**Extraction ends at `ExtractionResult`.** Everything after — canonical section construction, Pydantic validation, severity/`verdict_chain` population, summary status, conformance metadata, rendering — happens at or after `result_to_artifact` and is owned by it.

Any code that produces a `CanonicalArtifact` outside `result_to_artifact` is **out of bounds**. (This is the defect the Security Assessment migration removed: a bespoke path emitting its own parallel artifact with hand-rolled IDs, severities, and summary status.)

### D2 — What the declarative model is allowed to express

The declarative `extraction_instructions` surface is **bounded to stable source selection plus structural projection into rows/sections.** Sanctioned vocabulary:

- source/section recognition (`recognition_hints`, `title_contains`, selectors)
- table/section selection (`table_selector`, `section_title_selector`, `section_title_match`)
- column mapping (`column_map`: source → canonical name + type)
- null coercion (`null_values`); type coercion (string/int/float/timestamp/hex)
- static parameters
- findings severity via the existing declarative `status_to_severity` mapping
- the existing evaluative primitives: CEL-derived values and threshold verdicts evaluated inside `build_metric_section` / `build_card_section`

`hex` (integer → lowercase hex string) was admitted to the coercion set via the D3 gate (ADR 0007): it is a pure, fixed-shape, source-agnostic, unit-tested transform. Coercion values are added to this list **only after individually clearing D3** — the list grows one gated transform at a time, never by category.

A bounded "formula" surface **already exists** (CEL-derived values, threshold rules). The rule is therefore *not* "config must never contain formulas." It is: **keep expressiveness bounded to these existing, named, unit-tested primitives. Do not add a second formula mechanism or an arbitrary transform language.**

### D3 — The per-operator gate (the enforceable test)

A proposed declarative transform/operator is admissible **only if it satisfies all four**:

1. **Pure function** over already-selected rows — no side effects, no I/O, no statefulness.
2. **Fixed-shape** — operates on a column/section set known at authoring time. **No runtime data discovery** (e.g. columns whose identity is discovered per-export).
3. **No source-specific knowledge** — no per-report heuristics, no vendor quirks baked in.
4. **Unit-tested at the operator level** — ships with its own tests, independent of any subject.

Fail any one → it is **not** declarative; it stays bespoke Python (see D5). This checklist replaces prose judgement with a mechanical check a reviewer applies without relitigating the philosophy each time.

**Fixed-vs-runtime distinction (worked example).** Operators are judged on fixed vs. runtime-dependent shape, not on whether they *feel* structural:

- transpose/unpivot over a **known** column set → admissible (fixed shape).
- unpivot over **dynamic pivot columns** discovered per-export (e.g. `agent_dedupe_savings` weekly date-range columns matched by `header_pattern`) → **not** admissible (runtime discovery → bespoke).

"It's just an unpivot" is not sufficient; *which* columns, known when, decides it.

### D4 — Hard invariants

1. **One canonicalization path.** Only `result_to_artifact` builds a `CanonicalArtifact`.
2. **One evaluation locus.** Severity/verdicts computed in the evaluative layer at canonicalization time; never duplicated in extractors, services, or renderers.
3. **No source leakage into the canonical model.** Source-specific concepts (Highcharts payloads, Reports Plus widget shapes, CommCell dataset quirks) are flattened to canonical rows/sections at the extractor; they do not appear as canonical fields, and renderers do not learn to understand them.
4. **Renderers consume canonical sections; they do not compensate for extractor limitations.** If a render path needs data the extractor didn't produce, fix the extractor.
5. **Pydantic validates at the boundary** (construction + reload); conformance shape-checks remain non-fatal metadata.

### D5 — Where bespoke Python begins (sanctioned boundaries)

The declarative model has boundaries, and that is **healthy**. Bespoke Python is correct when logic needs any of: stateful interpretation; runtime discovery; cross-table semantics / multi-step joins; source-specific heuristics; fallback strategies; domain normalization needing unit tests as code (section inference, header classification, name-ambiguous dataset disambiguation). Forcing such logic into config produces a worse, untyped, untested bespoke language.

**Sanctioned bespoke boundaries register**

| Boundary | Status | Notes |
|---|---|---|
| **License Summary** (`license_summary/`) | Sanctioned bespoke, indefinite | ADR 0003 caveat: name-ambiguous datasets, runtime param-substitution, per-row value-formula transforms. No "reduce LS surface area" campaign — only a *specific, fixed-shape* transform closing a *specific* gap, evaluated one at a time against D3. |
| **Security Assessment dev unit** (`security_assessment/` parsers + per-domain store + registry) | Held, production-dead | Production SA flows fully through the generic path (SA migration, PRs `0c9920e` / `24523df`). Bespoke parsers/registry survive only as held dev-cluster machinery; confirmed production-dead. Retire under backlog #36. |

### Adding a new source or subject — the default in-bounds path

1. Define subject + section catalog rows.
2. Author `extraction_instructions` (recognition + selectors + `column_map` + coercion). **No code.**
3. If a needed operation fails the D3 gate → bespoke Python, registered as a named boundary in D5 — never silent drift.
4. Prove parity against a real populated export before flipping `extractable` (per-source, never blanket).
5. Tests + sample fixtures.

## Consequences

- New report onboarding stays catalog-only for the common case; bespoke code is the explicit, registered exception rather than the default.
- The "one canonicalization path" invariant means future evaluative work (e.g. ADR 0004 phase 8: vendor/override layering, rules registry, metric/card unification) lands inside `result_to_artifact`, not in extractors. Datasets a future feature needs may be *collected* as ordinary rows, but any *join/threshold against other values* stays at canonicalization — joining two datasets inside the extractor is a D1 violation.
- Reviewers gain a mechanical gate (D3) instead of case-by-case argument, reducing the surface for "just one more operator" drift.
- Cost: some reports remain bespoke Python (LS) rather than forced into config — accepted deliberately as a healthy boundary, not treated as debt.

## Alternatives considered

- **Generic source-importer framework with per-subject importer classes** (the original proposal). Rejected: the declarative generic extractor already provides this; per-subject classes reintroduce the coupling the proposal sought to remove.
- **Grow the declarative DSL until it can express License Summary** (param-substitution, row formulas, dynamic-pivot unpivot). Rejected: inner-platform trap — recreates a general-purpose language in YAML/JSON, worse than the bespoke Python it replaces.
- **Permanent read-time compatibility shims for scheme/ID changes.** Rejected as a default in favour of one-time migration (a shim keeps the old scheme alive and recreates a two-scheme split-brain); shim reserved for genuinely immutable history only.

## Open questions

- **Scope of admissible structural operators.** D2–D3 sanction the *current* vocabulary plus fixed-shape projection. Whether to pre-approve `unpivot` / `group_rows` for fixed-shape cases, or require each to clear the gate individually at proposal time, is a deliberate choice. *Recommendation: require each individually — do not pre-bless a category.*
- **Migration-over-shim as standing default.** Recommended; confirm.

## Revisit triggers

- A proposed report genuinely cannot be expressed within D2 *and* fails D3, yet recurs often enough that a bespoke boundary feels disproportionate → revisit the admissible-operator scope (not the invariants).
- Any future ADR introducing a new artifact producer → re-affirm D1/D4 against it before it ships.

## References

- ADR 0001 — Source-building fork retained; upload routing unified.
- ADR 0003 — REST extractor with credentials (License Summary bespoke caveat).
- ADR 0004 — Three-face metadata vocabulary (evaluative layer; phase 8 outstanding).
- ADR 0007 — Declarative single-object source + environment migration: the worked example that exercised the D3 gate. Nested-path field selection and `hex` coercion each cleared D3 individually; the boundary extends to single-object Command Center API sources without widening CEL.
- Security Assessment migration — PRs `0c9920e` (report re-author onto `get_canonical()`), `24523df` (bespoke-path removal).
- Backlog #36 — retirement of the held SA dev-cluster unit.
- Superseded proposal — "Standardized Source Import Framework" (see *Context*).
