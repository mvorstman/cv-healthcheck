# ADR-0016: Recipe transform layer — declarative shaping without code-in-data

**Status:** Proposed
**Date:** 2026-06-13
**Relations:** Extends ADR-0015 (the recipe is the template's extraction definition; this ADR defines how a recipe may *shape* extracted input). The transform registry becomes part of the ADR-0015 compile gate's validation contract. Builds on ADR-0010 (rules) and the Fix-3/Fix-4 identity/provenance work.

---

## Amendment (2026-06-13) — Open Item 1 resolved (`number_with_unit` return shape)

Grounded by a read-only probe over the real LS corpus. **Headline: no canonical
quantity appears with a differing unit.** Across the corpus = 38 license-bearing
exports, 0 `other_licenses` licenses show more than one real unit, and 0 workload
quantities vary unit across files (the per-section "variation" was different
*licenses* within a section — each individual quantity is unit-consistent). This
resolves Open Item 1 and updates the registry, Section 4, and Section 5 below.

**Amendment A — `number_with_unit` returns `{value, unit}` (parse-and-keep);
base-unit normalization is REJECTED.** Units are consistent per quantity across
the 38 exports, so the unit is parsed from the cell and kept verbatim; nothing is
ever converted to a base unit. (Normalization would only be needed to *equate*
differing units, which never arises: each row keeps its own value+unit, and a
parity comparison is same-file, same-cell → same unit on both sides.)

**Amendment B — `number_with_unit` is a CELL transform; header-encoded units are
out of scope (deferred).** 112 of 184 workload entitlement rows carry the unit in
the COLUMN HEADER (`Available Total (TB)`) with a plain-number cell; the bespoke
parser drops that header unit, and `number_with_unit` (a cell-value transform)
does the same — so parity holds. Capturing header units is a separate, deferred
capability, **`unit_from_coalesce_source_name`** (derive the unit from the chosen
coalesce source-column name); it is NOT part of `number_with_unit` and NOT
required for parity. Revisiting it would change the bespoke baseline and must be
re-grounded.

**Amendment C — `usage_percent` is a percentage, not unit-bearing; add
`to_float_percent` (spec'd, deferred).** `usage_percent` is reclassified OUT of
the unit / PENDING-UNIT set. When present it is `N%` → `to_float_percent`; in the
current corpus the `Used %` column is absent (0/184 rows populate it), so the
transform is specified but implementation-blocked-by-absence (no fixture to
validate against — confirm on a real export that populates it before building).

**Amendment D — the LS parity corpus is 38, not 41.** 3 of the 41 files under
`data/imports/license_summary/` are misfiled non-LS (two Security-Assessment HTML
exports + the `cv_redesign_option_a_refined` mock) and produce no license rows.
Parity coverage (Section 4) is the **corpus = 38** license-bearing exports;
fixture discovery still sees 41 files on disk.

---

## Context

The Piece-B recipe-feasibility inventory (2026-06-13) tested two real Commvault export specimens against the generic extractor recipe model:

- **client_growth (Growth-and-Trends):** fully expressible today. Its breakage was a mis-authored `section_label`, not a model gap — fixable by editing the recipe, no model change. Verdict **(a)**.
- **License Summary:** depends on four capabilities the recipe model fundamentally lacks — coalesce across candidate columns (report-version variance), scattered metadata-pair extraction, registration-code masking (a security control), and unit-aware number parsing — plus computed counts and dedup. Verdict **(c)**: model work must precede any LS conversion.

The two specimens diverging is itself the key finding: the generic model is **adequate for normal subjects** (client_growth needs none of these), and **LS is genuinely special**. This ADR therefore introduces a transform layer *deliberately, as a bet that License Summary justifies the platform capability* — not because the model is generally insufficient.

**The deliberate bet (recorded, not defaulted):** the strongest evidence for a transform layer today is a single subject (LS). This investment is justified iff (a) License Summary is important enough to warrant de-bespoking, and/or (b) future subjects will reuse these named transforms. If LS proves a one-off, this adds permanent recipe-model capability for one subject. The closed-registry design (below) bounds that cost. This is a conscious decision, made with the single-specimen evidence in view.

**The danger this ADR must avoid:** a transform layer is *power* in the recipe model, and ADR-0015 spent its effort *constraining* recipe power (no resolved values, no execution artifacts, transferable-by-construction). An open-ended transform capability ("run this code on this column") would reopen exactly what 0015 closed. The governing principle is therefore:

> **A recipe may describe transforms, but may never contain subject-specific code.**

Transforms are reusable, named, platform-owned capabilities selected from a closed registry — never expressions, lambdas, or logic authored into a recipe.

---

## Invariants (named, normative)

- **Closed Registry:** a recipe may invoke transforms only by name from a platform-owned closed registry. There is no arbitrary-expression escape hatch. (This is what keeps transforms data, not code.)
- **Compile-Validated:** every transform name in a recipe is validated at publish against the registry. An unknown transform name is a **compile error** — the template cannot publish. (Enforces Closed Registry; ties to the ADR-0015 compile gate.)
- **Security-by-Construction:** a canonical field tagged *sensitive* MUST carry its mandatory transform (per a closed, gate-enforced sensitive-field → required-transform mapping); the compile gate rejects a recipe where a sensitive field lacks it. The initial mapping requires `registration_code` → `mask_registration_code` — masking cannot be omitted by author oversight. Security is enforced at the gate, not left to author diligence. (Same shape as ADR-0015 D5: absence is an error, never a silent gap.)
- **Reusable, not subject-specific:** every transform is a general capability usable by any subject; none encodes LS-specific (or any-subject-specific) logic. If a needed shaping cannot be expressed as a reusable named transform, that is a signal to reconsider — not to add a one-off.

---

## Section 1 — The transform registry (closed, normative)

Recipes gain three model additions, all declarative:

**1a. `source: string | list[string]` — coalesce / first-present.**
A string keeps current 1:1 behavior. A list means "use the first present, non-empty source column among these" — for report-version / license-type column-name variance (`["Available Total", "Available Total (TB)", "Permanent Purchased", "Available Total (instances)"]`). First-present only; no merging, no arithmetic across candidates.

**1b. `transforms: list[string]` — named, ordered, from the closed registry.**
Applied in order to the (coalesced) source value. Initial registry — closed; additions require an ADR amendment:

| transform | input → output | notes |
|---|---|---|
| `trim` | str → str | whitespace strip |
| `null_if_empty` | str → str\|null | empty/placeholder → null |
| `to_integer` | str → int\|null | coercion; non-numeric → null + warning |
| `to_float` | str → float\|null | coercion |
| `to_float_percent` | str → float\|null | "80%" → 80.0. Spec'd, **deferred** — `Used %` absent in the corpus, no fixture to validate (Amendment C). |
| `number_with_unit` | str → **{value, unit}** | "500 VMs" → {500,"VMs"}. **Return shape RESOLVED: `{value, unit}`** (Amendment A). CELL transform — embedded units only; header-encoded units out of scope (Amendment B). |
| `mask_registration_code` | str → masked str | security transform; stores only `****`-masked form. Mandatory on `registration_code`. |

No `regex`, no `expression`, no `eval`, no user-supplied callable — those would violate Closed Registry. Adding a transform = adding a named, reviewed, platform-owned entry here.

**1c. `format: "metadata_pairs"` — scattered key:value section.**
For sections that are label/value rows rather than header+data tables (`"CommCell ID: 337f"`, `"License Expiry: ..."`). Declares a `label_map` (source label → canonical field). Each mapped field may carry `transforms` (e.g. `registration_code` → `["trim","mask_registration_code"]`).

**Constraint (normative):** `metadata_pairs` is for **deterministic exact-label → value** extraction only. It may NOT contain pattern matching, fuzzy/approximate label matching, regex extraction, hierarchical/nested parsing, or multi-line value assembly. A label either matches exactly (post-`trim`) or it does not. This is the boundary that keeps `metadata_pairs` from becoming a second, open-ended extraction model — a mini document parser — over time. `metadata_pairs` locates values by exact label; shaping happens only via the closed transform registry afterward. Any need beyond deterministic label→value is a signal to reconsider, not to extend this format.

**1d. Computed sections — minimal, enumerated.**
`row_count`, `distinct_count`, `grouped_count` only. No expressions, no arbitrary aggregation. (The ADR-0010 evaluative layer runs *after* extraction on shaped rows and computes verdicts; these computed sections are extraction-time row aggregates, a distinct and deliberately tiny set.)

---

## Section 2 — Decisions

**D1 — Closed registry only; no arbitrary expressions.** (Invariant: Closed Registry.) The registry above is the complete initial set. Expansion is an ADR amendment, reviewed — not a recipe-author act.

**D2 — Unknown transform = compile error.** (Invariant: Compile-Validated.) The ADR-0015 compile gate validates every transform name against the registry. The compile gate must therefore be **transform-aware from its first implementation** — this reorders the redesign: the transform-layer design (this ADR) precedes the compile gate, and the gate is built knowing the registry, rather than built simple and retrofitted.

**D3 — Sensitive fields declare mandatory transforms; the gate enforces them.** (Invariant: Security-by-Construction.) A canonical field may be tagged *sensitive*; sensitive fields carry a **mandatory-transform mapping**, and the compile gate rejects any recipe where a sensitive field lacks its required transform. The mapping is a closed, platform-owned table (extended only by ADR amendment), with the initial entry:

| sensitive field | mandatory transform |
|---|---|
| `registration_code` | `mask_registration_code` |

Defining it as a *mapping* (rather than hard-coding the single registration_code rule) leaves room for future sensitive fields without a model change, while keeping the set closed and gate-enforced. Security is enforced at the gate, not left to author diligence.

**D4 — `source: []` is first-present, never merge.** Coalesce picks one column; it does not combine, sum, or concatenate. Combining would be a computation the recipe model deliberately does not express.

**D5 — Transforms are platform capabilities.** Each is reusable by any subject, owned by the platform, tested independently of any subject. LS is the first consumer, not the owner.

**D6 — Parity harness precedes bespoke-LS deletion.** (See Section 4.) The bespoke LS parser is deleted only after byte/semantic parity is proven against the real-export corpus. Build order is fixed: ADR Proposed → parity harness → transform layer → LS conversion → delete bespoke LS.

---

## Section 3 — Build order (fixed)

1. **This ADR → Proposed** (reviewed). No code before the design is recorded — because the parity harness (next) silently encodes design decisions (what counts as parity, how masked fields compare, how units represent) that belong in the ADR, not in test code.
2. **Parity harness** — the acceptance gate, built before the transform layer so every capability is checked incrementally against real exports, not validated only at the end.
3. **Transform layer** — `source: []` coalesce → named-transform registry → `metadata_pairs` → minimal computed sections.
4. **LS conversion** — author LS's recipe using the new capabilities; the expressible parts (fixed-header `other_licenses` / `agent_feature_licenses` tables) and the now-expressible parts (coalesced workload summaries, metadata-pairs CommCell-Info, masked reg-code, unit-numbers).
5. **Delete bespoke LS** — only after parity proof.

---

## Section 4 — The parity harness (acceptance gate)

Proves a generic-recipe LS produces the same canonical artifact as the bespoke LS, across the **corpus = 38** license-bearing exports under `data/imports/license_summary/` (41 files on disk − 3 misfiled non-LS: two Security-Assessment exports + the `cv_redesign_option_a_refined` mock; Amendment D). Decisions the harness encodes (recorded here so they are design, not accident):

- **Equivalence basis:** semantic equivalence of the `CanonicalArtifact` per section — same sections, same items, same field values — NOT raw byte-equivalence of serialized JSON (key ordering, whitespace, and float formatting are not parity concerns).
- **Masked-field comparison:** `registration_code` is compared in its **masked** form on both sides (the bespoke path already masks; the generic path masks via transform). The harness never compares unmasked reg-codes — and asserts both sides are masked.
- **Unit fields:** compared as `{value, unit}` (Amendment A); header-encoded units are dropped on both sides (Amendment B). `usage_percent` is not a unit field (Amendment C).
- **Computed summaries:** compared semantically (the count values), not byte-wise.
- **Coverage:** all 38 exports (Amendment D) must pass; a single divergence blocks bespoke-LS deletion.

The harness is the gate for step 5, and the incremental check for steps 3–4.

---

## Section 5 — Open items

1. **`number_with_unit` return shape — RESOLVED (2026-06-13, Amendment A): `{value, unit}`.** The read-only grounding pass over the corpus = 38 LS exports found **no quantity with a differing unit** (`other_licenses`: 0 licenses with >1 real unit; workload: 0 quantities varying across files), so parse-and-keep suffices and base-unit normalization is rejected. Header-encoded units are out of `number_with_unit`'s scope — the deferred `unit_from_coalesce_source_name` capability (Amendment B). `usage_percent` is not unit-bearing → `to_float_percent`, deferred (Amendment C).
2. **The deliberate bet (recorded, not blocking).** Evidence for the transform layer is currently a single subject. Acceptance of this ADR is acceptance of that bet. If, during conversion, LS turns out to need capabilities *beyond* this registry, that is a signal to reconsider whether LS should stay bespoke — not to grow the registry open-endedly.
3. **`metadata_pairs` robustness** — confirm against the corpus = 38 exports (Amendment D) that the scattered-pair labels are stable enough for a `label_map` (vs. varying per report version), during the parity harness work.

---

## Consequences

- The ADR-0015 compile gate is built transform-aware (D2) — design sequence: this ADR → gate → conversion.
- The recipe model gains bounded, named shaping power; the Closed Registry + Compile-Validated invariants keep it from becoming code-in-data.
- License Summary becomes (mostly) recipe-driven; the bespoke parser is retired only behind parity proof.
- A `sensitive` field-tag concept enters the canonical/recipe model (D3) — small, but new.
- Acceptance criteria for this ADR reaching **Accepted**: the transform layer exists, the parity harness passes all 41 LS exports, and the bespoke LS parser is deleted with no regression — i.e. one full implementation cycle, same standard as ADR-0015.
