# ADR 0004 Phase 8 — Evaluative Face: Design Draft

**Status:** Ratified 2026-05-30 — ready for phased build (DP7 resolved to option (i), overruling the draft's (ii); see §3).
**Parent:** [0004-three-face-metadata-vocabulary.md](./0004-three-face-metadata-vocabulary.md) · [0004-phase-plan.md](./0004-phase-plan.md) · [0004-survey.md](./0004-survey.md)
**Honors:** [0006-declarative-extraction-boundary.md](./0006-declarative-extraction-boundary.md) (D1/D4 invariants)
**Date:** 2026-05-30

This is a design draft, not an implementation plan to execute. Every **DP-N** marker is a decision that needs ratification before any code. Scope is taken verbatim from the phase plan §Phase 8 + the `card_section.py` unification note; nothing here invents scope.

---

## 0. Where we are (grounding)

Current evaluative machinery (phases 2/4):

- `evaluative/threshold.py::evaluate_threshold_rule(rule, value, …) -> VerdictEntry` — a single threshold rule, **inline** in the catalog, producing **one** `VerdictEntry` at `layer="template_default"`. No vendor layer, no override, no registry.
- `metric_section.py` — per-`MetricItem` `severity` + `verdict_chain` (`verdict_chain = [verdict]`, one entry).
- `card_section.py` — section-level `CardSection.severity` + `verdict_chain` (one entry), reusing the exact metric shape. The docstring flags the duplication as "intentional and temporary; phase 8 unifies."
- `Finding` carries `severity` but **no `verdict_chain`**. Findings severity is set in the extractor today (`status_to_severity` in html/csv/rest), i.e. Shape 1 applied pre-canonicalization.
- `VerdictEntry{layer, severity, rule_id?, reason}`; `FindingSeverity = {critical, warning, info, good, muted}`.
- All section building (and therefore all current evaluation) runs inside `result_to_artifact` — the single canonicalization locus. ADR 0006 D1/D4: extraction ends at `ExtractionResult`; verdicts live downstream of it; one canonicalization path.

Phase-8 scope (phase plan): Shape 2 (StatusRow), Shape 3 (inline threshold), full vendor→template→override layering with the verdict chain, severity enum + `muted` suppression, `recommendation_hook` reserved — **plus** the metric/card unification.

---

## 1. Rules registry + reference-by-id

### Proposed approach
Introduce a **named rule registry**: each rule definition lives once, addressed by `rule_id`. Catalog sections stop inlining rule bodies and instead carry **references** (`rule_id` + a layer assignment). The evaluator resolves references against the registry at canonicalization time.

Reference shape on a section's `extraction_instructions.evaluative`:
```yaml
evaluative:
  vendor:                 # optional — the vendor severity_source (Shapes 1/2/3); see §4/§5
    severity_source: { kind: vendor_field | status_row | inline_threshold, … }
  rules:                  # template-layer rule references
    - { ref: utilisation_critical, target: utilisation_pct }
    - { ref: utilisation_warning,  target: utilisation_pct }
```
A rule definition in the registry:
```yaml
# registry entry, addressed by rule_id
utilisation_critical:
  kind: threshold
  comparison: ">="
  bands: [{at: 90, severity: critical}]
  default_severity: good
  mute_on_sentinel: true
  recommendation_hook: null   # §7
```

### Decision points
- **DP1 — registry storage.** Three candidates: (a) a new DB table `rules` (id, definition_json, …), seeded/extended by migrations; (b) a catalog JSON file (`data/catalog/rules/*.json`); (c) keep them in `subject_section_sources` but de-duplicated by a `rule_id` column. Recommendation: **(a) a `rules` table**, consistent with the catalog-in-DB pattern (subjects/sections/sources) and queryable; overrides (per-customer) then key naturally into the same store (§2). *Ratify the store.*
- **DP2 — backward compat for existing inline rules.** capacity_license (phase 5) and the `_card_test`/`_metric_test` subjects currently carry **inline** `evaluative.rules`. Options: (i) **registry-or-inline** — resolver accepts both; a section with an inline body uses it directly, a section with `ref` resolves from the registry (no migration, gentle); (ii) **migrate all inline → registry** in a migration, resolver only accepts `ref` (one-way, cleaner, but a MIGRATION-REVERSIBLE change touching seeded rows). Recommendation: **(i) registry-or-inline**, with inline treated as an anonymous template-layer rule — keeps phases 5/6/7 untouched and lets new work adopt refs incrementally. *Ratify whether inline keeps working or is migrated.*
  - **Authoring-time guard (load-time validation requirement).** When a section has **both** an inline rule **and** a registry `ref` targeting the **same `(section, target)`**, precedence must be **defined**, or the combination **rejected at catalog load** — otherwise a silent double-fire. Implement this as a load-time validation (fail loudly at insert/seed time, consistent with the `section_types` loud-failure pattern), not a runtime surprise.
- **DP3 — rule_id namespacing.** Flat global ids vs namespaced (`capacity_license.utilisation_critical`). Recommendation: flat global, since the whole point is cross-subject reuse; collisions are a catalog-authoring error caught at load. *Ratify.*

### Alternatives considered
- **Inline-only (status quo).** Rejected by the ADR already ("inlined catalog data ages badly and scales poorly", same lesson as dataset GUIDs).
- **Rules as code (Python registry).** Rejected: rules are catalog data (vendor primitives + thresholds), not logic; CEL/threshold primitives already cover them, and code-rules reintroduce the unilateral-extension risk ADR 0006 D3 guards.

### Schema / artifact impact
- New `rules` table (DP1) — additive migration, no artifact-shape change.
- Section `evaluative` blocks gain a `ref`-based form; **stored artifacts are unaffected** (rules live in the catalog, not in artifacts). The artifact only ever carries the *resolved* `verdict_chain`.

---

## 2. Layer resolution (vendor → template → override)

### Proposed approach
Three layers, evaluated in order: **vendor** (the `severity_source` — Shapes 1/2/3), **template_default** (registry rules attached to the subject template), **override** (registry rules attached to a specific customer/engagement's use of the subject+section). Each layer can fire zero or more rules; `muted` is the suppression severity.

**Resolution rule (proposed, per the ADR text):**
1. Within a layer, among rules that fire on the same target, **highest severity wins** (rank critical>warning>info>good; `muted` is rank −1, see §6).
2. Across layers, for the **same `rule_id`**, the **later layer wins** (override beats template beats vendor for that id). This is how an override neutralizes a specific prior verdict.
3. **Final section/item severity** = the most-severe **surviving** verdict after per-`rule_id` cross-layer resolution, with `muted` excluded from "most-severe" selection (a muted verdict suppresses, it does not become the headline). **DP4** governs whether an override can drop the headline below a vendor/template verdict.

### Decision points
- **DP4 — final-severity rule + can overrides lower?** Two coherent readings of the ADR:
  - **(A) most-severe-wins across surviving verdicts**, where an override only changes the *headline* if it (a) shares the `rule_id` it is overriding, or (b) `muted` suppresses that id. Under (A), an override **cannot** silently lower an unrelated higher verdict — it must target the specific rule_id (or mute it).
  - **(B) last-layer-wins absolutely** — the override layer's resolved severity is the final severity regardless of prior layers.
  Recommendation: **(A)**. It matches "later layer wins *for the same rule_id*" + "muted neutralizes a previous layer" literally, and prevents an override accidentally hiding an unrelated critical. **Overrides may lower severity only by targeting the rule_id (or muting it)** — not by introducing a lower verdict on a different id. *Ratify A vs B, and confirm overrides-may-lower-via-target.*
  - **Render requirement (build-time, not resolution logic).** A `muted` headline must render **distinctly from `good`** at tile/report level — "deliberately not assessed / waived" vs "passing." If `muted` and `good` render identically, an auditor cannot distinguish a **waiver** from a **pass**, which defeats the mute-with-reason chain. Carry this as a build-time render requirement (a distinct muted badge/affordance surfacing the waiver `reason`); it does not change resolution logic.
- **DP5 — what may an override change?** `severity` only, or `severity` + `reason`? Recommendation: **both** — an override that mutes a vendor critical should be able to say *why* ("waived for this customer per engagement X"); the `reason` is the audit value. *Ratify.*
- **DP6 — verdict_chain contents: all fired vs only-surviving.** ADR says "every layer that fired, in order." Recommendation: **record every fired verdict (including suppressed/muted ones), in layer order**, so the chain is a full audit trail; the resolved headline `severity` sits on the item/section, the chain shows how it got there (including "vendor said critical → override muted it"). *Ratify all-fired vs surviving-only.*

### Worked example (layers disagree)
capacity_license utilisation, customer Acme has waived the 90% critical for a known burst window:

```
vendor:           (no vendor severity_source for this metric)        → —
template_default: rule util_critical  (>=90 → critical) fires        → critical
override (Acme):  rule util_critical  severity: muted, reason:"…"    → muted (same rule_id)
```
Resolution: same `rule_id` (`util_critical`) → later layer (override) wins → that id resolves to `muted`. No other surviving non-muted verdict → **final severity = muted** (under DP4-A; muted suppresses, value still shown as n/a-for-judgment). `verdict_chain`:
```yaml
severity: muted
verdict_chain:
  - { layer: template_default, rule_id: util_critical, severity: critical, reason: "Utilisation 94% >= 90% threshold" }
  - { layer: override,         rule_id: util_critical, severity: muted,    reason: "Waived for Acme burst window (engagement E-1207)" }
```
Contrast — if Acme's override had instead been a *different* rule_id setting `warning`, under DP4-A the template's `critical` would still stand as the headline (most-severe surviving), and both verdicts appear in the chain. This is the crux DP4 ratifies.

### Where vendor & override rules are declared/stored
- **Vendor layer:** platform-shipped. The `severity_source` is declared on the section's catalog `evaluative.vendor` block (seeded by migrations); it is *not* per-customer.
- **Template layer:** registry rules referenced by the subject template (catalog, seeded by migrations).
- **Override layer:** per-customer / per-engagement. **DP10 — override storage + scope key.** Candidates: a table `rule_overrides(customer_id, engagement_id?, subject_id, subject_version, section_id, rule_id, severity, reason, …)`. The ADR calls layer 3 "a specific report's use of this subject" — needs pinning to our entity model: is the scope **customer**, **engagement**, or **project/finalization**? Recommendation: key on **(customer_id, engagement_id, subject_id, section_id, rule_id)** with engagement optional (customer-wide if null). *Ratify the override scope + storage.*
  - **Scope-semantics note (confirm before finalizing the null default).** "Engagement optional → customer-wide if null" is only correct if waivers are **standing customer policy**. If waivers are typically **per-engagement** (a waiver for this engagement's report should *not* leak to the customer's next engagement), then **engagement-scoped should be the norm and customer-wide the deliberate exception** — i.e. the null-semantics may be backwards. **Confirm against how waivers actually work before finalizing the null default.** The table shape `(customer_id, engagement_id?, subject_id, section_id, rule_id)` is fine either way; only the meaning of `engagement_id IS NULL` is in question.

### Schema / artifact impact
- New `rule_overrides` table (DP10) — additive migration.
- `VerdictEntry` already supports all three `layer` values — **no model change** for the chain itself. The headline `severity` field already exists on MetricItem/CardSection. So layering is largely *evaluator* work, not *schema* work — except the unification (§3) and findings-verdict-chain (DP9).

---

## 3. Metric/card evaluative-shape unification

### Proposed approach
This is **shared code at one evaluation locus**, plus a **shared artifact sub-structure** — but additive, not a breaking reshape.

- **Shared code:** replace the two call sites (`metric_section.evaluate_threshold_rule` per item; `card_section` per section) with a single **`evaluative/engine.py::evaluate(target_value | row_context, layered_rule_refs, vendor_source) -> (severity, verdict_chain)`**. `build_metric_section`, `build_card_section`, and (DP9) findings all call this one function. This is the "one evaluation locus" ADR 0006 requires — the unification must **not** spawn a second evaluator.
- **Shared artifact structure:** the `(severity: FindingSeverity|None, verdict_chain: list[VerdictEntry])` pair is already structurally identical on MetricItem and CardSection. Unification keeps that pair (optionally factored into a `Verdict`/`Evaluation` mixin used by both) — **the serialized JSON shape is unchanged**.

### Decision points
- **DP7 — vendor-layer locus. RATIFIED: option (i)** (overruling the draft's recommended (ii), 2026-05-30). **Leave findings' `status_to_severity` in the extractor.** Rationale: findings severity is **transcribed from the source report** (the source already judged it, e.g. `"4_Critical"`), not evaluated by thresholding a measurement. Metrics/cards are *evaluated*; findings are *reported*. Therefore findings **do not pass through the evaluation locus at all**, and ADR 0006 D4 ("one evaluation locus") is **not** violated by `status_to_severity` living in the extractor — it is a field-map producing a row value, sanctioned by ADR 0006 **D2**, not a verdict. Option (ii) was rejected because it trades a non-violation for churn on the SA findings path, which was only just stabilized (SA migration PRs `0c9920e`/`24523df`). **The engine owns the vendor layer for metric/card only; findings severity is transcribed at extraction.**
- **DP8 — mixin vs duplicated fields.** Factor `severity`/`verdict_chain` into a shared base model, or leave them duplicated on each section type (DRY-by-convention)? Recommendation: a small shared `Evaluation` mixin for code clarity, **only if** it serializes identically (Pydantic mixin → same JSON). *Ratify; if any risk to serialization, keep duplicated fields and share only the engine code.*
- **DP9 — findings gain `verdict_chain`?** The ADR's chain example says "each finding **or** section verdict." Findings currently have `severity` but no `verdict_chain`. Recommendation (ratified): **add `verdict_chain` to `Finding` (additive, default `[]`)** so findings are first-class under layering. This is an additive schema change.
  - **Clarifying note (DP7-(i) interaction).** A finding carries a **transcribed** severity (from the source, via the extractor) **plus** a `verdict_chain` that is populated **only when a template or override layer acts on the finding** — e.g. a customer mutes a specific finding. The chain on a finding therefore represents **layering applied to a transcribed severity**, not vendor-evaluation of the finding. **Warning:** do **not** wire findings into the vendor evaluator on the strength of DP9 alone — DP9 grants findings a chain for template/override layering, it does **not** route findings through the vendor evaluation locus (that stays extractor-transcribed per DP7-(i)).

### Stored / finalized artifact compatibility
- The unification is **additive** (same fields, optional new `Finding.verdict_chain` defaulting to `[]`). **Existing stored & finalized artifacts validate on reload unchanged** — `VerdictEntry`/`severity` shapes are untouched; a new optional field with a default is backward-compatible under Pydantic. **No artifact migration needed** *provided* DP8 keeps serialization identical and DP9 is additive-with-default. If DP8 reshapes JSON, that flips to needing a migration — so the recommendation is the additive path explicitly to avoid it.

---

## 4. Shape 2 — StatusRow dataset (DLG-style)

### Proposed approach
The StatusRow dataset (good/warn/critical text + thresholds) is **collected as ordinary rows** — a normal section/source binding producing rows into `ExtractionResult.sections[…]`, exactly like any table. **No join, no threshold logic in the extractor.**

The **join + threshold evaluation happens at canonicalization**, inside the engine (§3), which receives both row-sets from `ExtractionResult` via `result_to_artifact`:
- the metric section's rows (the measured `metric_field`),
- the StatusRow section's rows (the thresholds + templated text),
keyed/joined by the declared `threshold_label_field` (or positionally per the catalog `severity_source.status_row` block), then each metric value is graded against its matched warn/critical thresholds, emitting a vendor-layer verdict whose `reason` is the vendor's templated text.

**ADR 0006 D1 confirmation:** the two datasets are handed to `result_to_artifact` as separate `ExtractionResult` sections; the **join is performed in the evaluative engine, downstream of `ExtractionResult`** — never in the extractor. Joining inside the extractor would be the D1 violation; the design explicitly does not.

### Decision points
- **DP11 — how the StatusRow section reaches the engine.** Both the metric section and the StatusRow section are collected; the engine needs both. Options: (i) the metric section's `evaluative.vendor.status_row` names the StatusRow `dataset_name`/`section_id`, and `result_to_artifact` passes the named sibling section's rows into the engine; (ii) StatusRow is collected as a hidden/auxiliary section (not rendered) referenced by id. Recommendation: **(i)** — reference the sibling section by id; mark it non-rendered if it shouldn't appear as its own card/table. *Ratify how the auxiliary dataset is bound + whether it renders.*
  - **Conformance-interaction guard.** Confirm the conformance layer does **not** flag a non-rendered auxiliary StatusRow section as a coverage gap (a section that's collected-but-not-rendered is intentional, not a drift). **Add a test for this interaction** (non-rendered auxiliary section present + conformant ⇒ no conformance failure recorded for it).
- **DP12 — join key + missing-match behavior.** Exact join semantics (label match vs single-threshold-row broadcast) and what happens when a metric row has no matching StatusRow (mute? default? conformance failure?). Recommendation: no match → `muted` with an audit reason, not a silent good. *Ratify.*

### Schema / artifact impact
- No new artifact fields; the StatusRow data lands as a (possibly non-rendered) section. Catalog `severity_source.status_row` block (already sketched in the ADR) is the only new declaration. If the auxiliary section is non-rendered, that's a presentational flag — **DP11**.

---

## 5. Shape 3 — per-row inline threshold (SLA-style)

### Proposed approach
Each row carries both its measured value and its threshold (`metric_field`, `threshold_field`, `comparison`). Evaluation is **per row, within the single engine** — no second dataset, no join. The engine reads the two fields off the same row and applies the comparison, emitting a per-row vendor-layer verdict.

### Interaction with layering (§2)
Shape 3 (like Shapes 1/2) produces the **vendor layer**'s verdicts. Template and override rules then layer on top via the same resolution (§2): a template rule could, e.g., add a warning band the vendor row doesn't express; an override could mute the vendor SLA-miss for a specific customer. The engine treats all three shapes as **vendor severity_source variants** feeding layer 1, so layering composition is identical regardless of shape. *No new decision beyond confirming Shape-3 verdicts occupy the vendor layer (consistent with the ADR).*

### Schema / artifact impact
None beyond the catalog `severity_source.inline_threshold` block (already sketched in the ADR). Per-row verdicts attach to the row's evaluated unit (finding/metric item per the section type).

---

## 6. Muted suppression

### Proposed approach
- **Where it applies: evaluation, not render.** `muted` is a real resolved severity produced by the engine (sentinel n/a today via `mute_on_sentinel`; and by override/vendor rules in phase 8). The renderer simply shows no badge for a muted verdict (and "n/a" for a muted value) — it makes no suppression decision itself. This keeps the single evaluation locus authoritative.
- **Ranking:** `muted` ranks below `good` (−1) for "most-severe" selection, so a muted verdict never becomes a headline; it suppresses.

### Decision points
- **DP13 — who may mute.** The ADR's primary muting case is **override** ("we don't care about vendor's critical here for this customer"). May **vendor** or **template** also emit `muted`? `mute_on_sentinel` already lets a template/vendor threshold mute an n/a value — so muting is not override-exclusive. Recommendation: **any layer may produce `muted`** (sentinel-mute at vendor/template; deliberate-mute at override); cross-layer resolution (§2 / DP4) governs whether a later non-muted verdict re-raises. *Ratify.*

### Schema / artifact impact
None — `muted` already exists in `FindingSeverity` and is already produced by `mute_on_sentinel`. Phase 8 only extends *who* can emit it and how it composes across layers.

---

## 7. `recommendation_hook` reservation

### Proposed approach
Reserve a field on the **rule definition** (registry entry), forward-declared and ignored by the engine:
```yaml
# on a registry rule
recommendation_hook: null        # reserved; ADR 0004 does not interpret it
# future shape (illustrative, not implemented):
#   { kind: action, payload_ref: <playbook id> }
```
The engine **does not read it**; it is stored as opaque data on the rule. It is **not** placed on the artifact's `VerdictEntry` (rules are catalog data; the hook travels with the rule, not the verdict) — *unless* DP-below says otherwise.

### Decision point
- **DP14 — hook placement.** On the **rule definition only** (catalog), or also surfaced onto the emitted `VerdictEntry` (artifact) so a future consumer can act from the artifact without re-reading the catalog? Recommendation: **rule definition only** for now (minimal reservation; survey's stated intent); surfacing onto the verdict is the future ADR's call. *Ratify placement.*

### Consuming ADR
Interpreted by **a future predictive/recommendations ADR** (number unresolved — the 0005-vs-later assignment is open; do not bind to a number here).

### Schema / artifact impact
Catalog/registry-only field; **no artifact-shape change**. Reserve, don't implement.

---

## 8. ADR 0006 invariants — where phase 8 risks crossing them

| Invariant (ADR 0006) | Phase-8 risk | Mitigation in this design |
|---|---|---|
| **D1 — extraction ends at `ExtractionResult`; no joins/transforms in the extractor** | Shape 2 join of StatusRow ↔ metric | Both datasets collected as ordinary sections; **join happens in the engine inside `result_to_artifact`**, downstream of `ExtractionResult` (§4). Explicitly not in the extractor. |
| **One evaluation locus (unification must not create a second path)** | Two evaluation entry points today (metric per-item, card per-section) | A single `evaluative/engine.py::evaluate(...)` owns **metric/card** evaluation; all metric/card builders call it. **Resolved (DP7-(i)):** findings are **transcribed at extraction, not evaluated** — they do not pass through the engine, so there is no second evaluation path. `status_to_severity` in the extractor is a **sanctioned field-map (ADR 0006 D2)**, not a verdict producer. *(Not a risk under the ratified design.)* |
| **One canonicalization path** | A new "rules resolution" step could tempt a separate pass | Resolution runs *within* `result_to_artifact`'s section-build, not as a second pass over the finished artifact. No re-derivation at render (consistent with the ADR's "evaluator runs at collection time"). |
| **No new declarative transform operator at the boundary (ADR 0006 D3)** | StatusRow join might look like an `unpivot`/`group_rows` need | The join is *evaluative composition in code*, not a catalog transform operator — it does not add a declarative operator to the extraction DSL. Confirm no catalog-level join operator is introduced. |

---

## 9. Decision points to ratify (summary)

| # | Decision | Recommendation |
|---|---|---|
| **DP1** | Rules registry storage (DB table / JSON / column) | New `rules` DB table |
| **DP2** | Inline rules: keep working, or migrate to registry | Registry-or-inline (no migration) |
| **DP3** | `rule_id` namespacing (flat vs namespaced) | Flat global |
| **DP4** | Final-severity rule + can overrides lower? | Most-severe-of-surviving (A); overrides lower only by targeting/muting the rule_id |
| **DP5** | What an override may change (severity / +reason) | Both |
| **DP6** | verdict_chain: all-fired vs surviving-only | All fired, in layer order (full audit) |
| **DP7** | Vendor-layer locus (extractor vs engine) — **invariant-critical** | **Option (i)** — leave findings' `status_to_severity` in the extractor (transcribed, not evaluated); engine owns vendor layer for **metric/card only** *(overruled draft's (ii))* |
| **DP8** | Unification: shared mixin vs duplicated fields | Mixin only if serialization identical; else share engine code only |
| **DP9** | Add `verdict_chain` to `Finding`? | Yes, additive with default `[]` |
| **DP10** | Override storage + scope key (customer/engagement/…) | `rule_overrides` table keyed (customer, engagement?, subject, section, rule_id) |
| **DP11** | How StatusRow auxiliary section binds + whether it renders | Reference sibling section by id; non-rendered |
| **DP12** | StatusRow join key + no-match behavior | Label match; no match → muted + reason |
| **DP13** | Which layers may emit `muted` | Any layer |
| **DP14** | `recommendation_hook` placement (rule only / +verdict) | Rule definition only |

**Artifact-compat headline:** with DP8 (additive) + DP9 (additive-with-default), **existing stored & finalized artifacts validate on reload with no migration**. Catalog/DB migrations (rules table, overrides table) are additive and don't touch artifacts. The only path that would *require* an artifact migration is reshaping the `severity`/`verdict_chain` JSON — explicitly avoided.

### Ratification record (2026-05-30)

The table above is now **decided**, not "options + recommendations." Each DP is **Ratified as recommended**, except DP7:

- **DP1** — Ratified as recommended (new `rules` DB table).
- **DP2** — Ratified as recommended (registry-or-inline) **+ load-time validation guard** (inline ⨉ ref on same `(section, target)` → defined precedence or reject at load).
- **DP3** — Ratified as recommended (flat global `rule_id`).
- **DP4** — Ratified as recommended (most-severe-of-surviving; overrides lower only by targeting/muting the rule_id) **+ build-time render requirement** (muted ≠ good visually).
- **DP5** — Ratified as recommended (override may change severity **and** reason).
- **DP6** — Ratified as recommended (verdict_chain records all fired layers, in order).
- **DP7** — **Ratified option (i)** — leave findings' `status_to_severity` in the extractor (transcribed, not evaluated). **Overrules the draft's recommended (ii).** Engine owns the vendor layer for metric/card only. (2026-05-30; see §3.)
- **DP8** — Ratified as recommended (mixin only if serialization identical; else share engine code only).
- **DP9** — Ratified as recommended (add `Finding.verdict_chain`, additive, default `[]`) — for **template/override layering on a transcribed severity**, *not* a route into the vendor evaluator (see §3 warning).
- **DP10** — Ratified as recommended (table shape) **— pending confirmation of `engagement_id IS NULL` semantics** (customer-wide vs per-engagement default; confirm against real waiver behavior before finalizing).
- **DP11** — Ratified as recommended (reference sibling section by id, non-rendered) **+ conformance-interaction guard/test** (non-rendered auxiliary section ≠ coverage gap).
- **DP12** — Ratified as recommended (label match; no match → muted + reason).
- **DP13** — Ratified as recommended (any layer may emit `muted`).
- **DP14** — Ratified as recommended (`recommendation_hook` on the rule definition only).

---

## 10. Proposed build sequencing

**Foundation (gates everything):**
1. **Metric/card unification → `evaluative/engine.py` (single locus)** [DP7, DP8, DP9]. Refactor-only first: route existing template_default evaluation through the engine with no behavior change; prove byte-identical artifacts for capacity_license/the test subjects. This establishes the one locus *before* adding layers.
2. **Rules registry + reference-by-id** [DP1, DP2, DP3]. Independent of layering mechanics; needed before layering. Registry-or-inline keeps phases 5–7 green.

**Layering (gates on 1+2):**
3. **vendor → template → override resolution + verdict_chain** [DP4, DP5, DP6, DP10, DP13]. The core. Includes `rule_overrides` storage.

**Shapes (gate on 1; compose via 3):**
4. **Shape 3 (inline threshold)** — simplest vendor variant, single-row, no join. Good first shape.
5. **Shape 2 (StatusRow join)** [DP11, DP12] — needs the auxiliary-section binding + downstream join; do after Shape 3 proves the vendor-layer plumbing.
   *(Shape 1 / per-row severity codes is already in use for SA; phase 8 only formalizes it as the vendor layer per DP7.)*

**Independent / trivial (any time):**
6. **`recommendation_hook` reservation** [DP14] — a reserved field on the registry rule; no engine work.
7. **`muted` composition** [DP13] — falls out of step 3; no separate build.

**Independence map:** 1 and 2 are independent of each other and can land in either order; 3 gates on both. 4 and 5 gate on 1 (the engine) and compose through 3. 6 is fully independent. Each step is its own commit with parity/behavior tests; per ADR-0004 working discipline, validate against a real populated export (or the test subjects for Shapes 2/3, per the phase-plan gate) before flipping anything on.

 
---
 
# Addendum — Per-field judging, the measure→judge→recommend→store spine, and build status
 
**Added:** 2026-05-30 (post-ratification design evolution + build progress)
**Scope note:** This addendum records decisions made *after* the phase-8 DP ratification above. Some items extend **beyond** phase 8's original scope (per-field judging, the recommend stage, the project spine). Where flagged **→ future ADR**, the item is recorded here for continuity but will graduate to its own ADR (the predictive/recommendations ADR; number still open — see *Placement* in the seam contract).
 
## A. The project spine (context) → future ADR for the recommend half
 
The platform's real goal is a pipeline: **measure → judge → recommend → store**.
- **measure** — extraction → `ExtractionResult` (done; ADR 0006 governs the boundary).
- **judge** — deterministic, rule-driven evaluation → verdict (this is what phase 8 + per-field judging build out).
- **recommend** — *generative* (AI-assisted), consumes a **settled** verdict + history; produces the consultant-facing recommendation (e.g. "based on growth, expand in ~N months"). **Not built. → future ADR.**
- **store** — finalization chain (exists); the recommend stage reads across finalizations for trend ("since last delivery"). Substrate confirmed ready.
**Hard seam (ratified, committed separately):** the judge stage stays **deterministic**; AI lives **only** in the recommend stage, consuming a settled verdict — never in judging. The judge→recommend contract is defined in `recommend-seam-contract.md` (committed, ratified): a `recommendation` payload on the catalog rule, surfaced onto the emitted verdict as `recommendation_intent` (per evaluated-unit), kept **subject-agnostic** so it carries security-check / documentation verdicts too, not just capacity.
 
## B. Per-field judging model (extends phase 8)
 
**Unified rule switch — every field is rule-eligible.** A compliance rule attaches **per field** within a section. Each rule has a **global default (on/off)** that is **overridable per customer** (reusing the phase-8 vendor→template→override layering + `rule_overrides` storage). "Informational" is **not** a separate state — it is simply the **default-off** position of the same switch. Three states collapse to one axis:
- *measured by default* (e.g. CommCell Version),
- *not measured by default but rule-eligible* (e.g. CommCell Name — a customer override can switch it on),
- *informational* (e.g. CommCell ID) = default-off, nobody overrides it on.
The deliberate-vs-not-yet-judged distinction is **deferred** to an optional UI hint (catalog metadata), not modelled as engine state.
 
**Multiple rule kinds.** "Measurable" is broader than thresholds. `kind` now **dispatches** in `engine.evaluate` (it was a declared-but-ignored discriminator). Kinds: **threshold** and **presence** built; **enum** and **format/regex** deferred (each is "another evaluator behind the same dispatch"). The CommCell example needs presence (Version is set), enum (Timezone in allowed set), format (Name matches convention) — none are thresholds.
 
**Granularity asymmetry.** *Metrics are already per-item* (each `MetricItem` carries its own severity/verdict_chain) → per-field metric judging is rule-authoring only, no engine change. *Cards are section-level today* → per-field cards require `CardItem` to gain severity/verdict_chain, a per-field loop in `build_card_section`, and per-field render. **Per-field cards = next build.**
 
**The placeholder never existed.** `recommendation_hook` was always **doc-only** (zero code occurrences in history). Per-field judging is a *first build*, not a restore of lost capability.
 
## C. Verdict surfacing — decided
 
- **Metric/card verdicts are consultant-facing.** Surfaced on the **workspace tile**: headline severity badge + `verdict_chain[-1].reason` as a tooltip. **Deliberately NOT in the customer report.**
- **The customer report is a data + findings document by design.** It renders per-finding severity only; metric/card verdicts/reasons are consultant context the consultant translates into their own narrative. **Findings are the only customer-facing verdict in the deliverable.**
- **Full `verdict_chain` is stored-for-audit, not rendered** on any live surface. DP6's "record every fired verdict in layer order" stands; "render the full chain" is explicitly **not** a requirement (the tile shows the winning reason; the full layer provenance lives in the artifact JSON for audit/debug).
## D. Findings handling
 
- Findings carry a **transcribed** severity (from the source report's own assessment) + transcribed `recommendation` text — both pass through **unchanged** (consistent with DP7-(i): findings are transcribed, not evaluated through the engine).
- **"Copy" = faithful transcription** (Commvault says Info → stays Info; recommendation text verbatim). Needs **no build** — it is already the behavior.
- **Per-customer overrule of a finding** (keep the finding, substitute your own severity + reason) is a **future extension** of the override layer to findings: the transcribed severity is the base, an override sits on top — same mechanism as metric/card overrides. **Low priority, not built.** "copy" semantics are settled; overrule is deferred.
## E. Recommendation presentation
 
- Recommendations render **per evaluated-unit, inline with the judged item** (e.g. per finding in the Security Assessment), **not** collected into a single global summary card.
- Presentation is likely **per-report-type** (inline per finding here; could be inline-on-metric elsewhere). The **data** is uniform (recommendation attached per unit, per seam SC5); the **layout** can vary by subject. The recommend stage must **not** assume one global recommendations-section layout.
## F. Bespoke-track caveat (system subjects)
 
`environment` / "CommCell Details" is built by `_build_environment_subject` — one of the six **system subjects with custom view shapes** (ADR 0001 source-building fork), **not** the generic catalog-driven path. Consequence: it collects (Command Center API identity path, not Reports-Plus Collect), judges, and surfaces controls differently — e.g. it has **no Collect button by design** (the button gates on the Reports-Plus source type; the Command-Center-API source carries no collect action). **Per-field card judging must work against the bespoke builder, not only the generic path** — and CommCell Details is the worked example for per-field judging, so this track matters for that slice.
 
## G. Authoring model — deferred
 
How rules get created/edited is a **separate decision from the engine** (rules are rows in a table; the authoring surface can change without touching resolution). Direction (not yet built):
- **Template / global layer** → controlled **config** (version-controlled; authored by product, changes rarely). Likely permanent.
- **Per-customer override layer** → a **constrained in-app editor** (consultant picks a field + an action from a **fixed vocabulary** — mute / change severity / add a check of a known kind + reason). **Not free-form rule authoring** — keep overrides a constrained operation set so the editor stays safe, auditable, and small. Each rule *kind* being an enumerated, dispatched type (§B) is what makes such an editor a set of typed forms rather than a code box.
- **Decision deferred** — build when needed; nothing now forecloses it as long as overrides stay a constrained operation set (which they are).
## H. Build status (as of 2026-05-30)
 
**Committed:**
- Phase-8 steps 1–3: single evaluation locus (`engine.evaluate`), rules registry + reference-by-id, vendor→template→override layering + `rule_overrides`. Each gated (byte-identical parity on no-rule subjects + new-behavior tests + render verification).
- Per-field **metric** slice (per-field rules + per-field indicators) — committed, render-verified.
- Rule-**kind dispatch** + **presence** kind — committed, render-verified (threshold + presence rendering side-by-side, distinct severity tokens).
- The recommend **seam** exercised: a rule declares `recommendation_intent`, it surfaces onto the verdict, SC4 suppression holds (muted → no intent).
**Not yet built:**
- **Per-field cards** (`CardItem` verdict + per-field loop + render) — *next slice*; makes the CommCell Details example fully real (against the bespoke `_build_environment_subject` track, per §F).
- Additional rule **kinds**: enum, format/regex.
- Phase-8 **Shapes** (StatusRow / inline-threshold vendor sources) — deferred; slot in as additional vendor sources behind the existing layering.
- The **recommend stage** itself — → future ADR.
 


---

*End of draft. No code written; this file is placed untracked for review.*
