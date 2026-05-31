# Recommend Seam Contract

**Status:** Ratified 2026-05-30. Standalone draft (not yet a numbered ADR — see *Placement*).
**Date:** 2026-05-30
**Honors:** ADR 0006 (one canonicalization path; verdicts settled at canonicalization, read at render) · builds on phase-8 steps 1–3 (single evaluation locus, rules registry, vendor→template→override layering).

This document defines **only the seam** between the deterministic *judge* stage and the future generative *recommend* stage. It does **not** design the recommend stage itself (AI generation, prompting, history traversal, prose). It defines the contract a settled verdict must carry so that a future recommender — for Quick HC or any other application — can consume it without re-reading the catalog and without subject-specific special-casing.

---

## 1. Why a contract, and why now

The project spine is **measure → judge → recommend → store**. The judge stage is deterministic and rule-driven; the recommend stage is generative and consumes a *settled* verdict. The seam between them is the one piece that is expensive to change after the per-field judge stage is built on top of it: if rules and verdicts don't carry what a recommender needs, wiring it later is a retrofit across every rule. So the seam is settled **before** the per-field judge build; everything downstream of it is iterative.

Investigation findings this contract responds to:
- A settled verdict already carries **value, severity, reason, rule_id, layer** — enough to *detect and explain* a judgment, not enough to know *what was intended to be recommended*.
- **Recommendation intent exists nowhere**: not on the verdict, not on the catalog rule (the rules-table `definition_json` has no recommendation payload). `rule_id` is the only artifact→catalog join-key, but there is nothing behind it to find.
- `recommendation_hook` was always **doc-only** — never implemented. This is a first build, not a restore.

## 2. Design principles (the constraints this contract is held to)

1. **Judge stays deterministic.** The seam carries a *settled* verdict. No generative step runs inside judging. The recommender is strictly downstream of a resolved verdict.
2. **Subject-agnostic.** The contract must carry a capacity-utilisation verdict, a security-check verdict, and a documentation judgment identically. Nothing in the seam may be shaped around disk/capacity specifics. **Litmus test for any field added here:** *would this same shape carry a security-check or documentation verdict without special-casing?* If no, it does not belong in the seam.
3. **No re-reading the catalog at recommend time.** A recommender consumes the artifact. Whatever intent a rule declares is **surfaced onto the emitted verdict**, not left only on the catalog rule.
4. **Reserve, don't generate.** This contract adds the *carrying* fields. It does not implement generation. The fields are populated with declared intent at judge time; interpretation is the recommend stage's job, later.
5. **Additive only.** New optional fields with defaults. Existing stored/finalized artifacts must validate on reload unchanged (the ADR-0006 / phase-8 discipline). No reshaping of `severity`/`verdict_chain`.

## 3. The contract

### 3a. On the catalog rule (the declared intent)
A rule definition gains an optional **recommendation intent** payload — the rule's *declaration* of what a recommender should consider when this rule fires. Shape (illustrative, subject-agnostic):

```
recommendation:                 # optional; absent = no declared intent
  intent_kind: <enum>           # trend_projection | remediation | attention | informational  (SC1)
  signal: <string>              # generic namespaced handle the recommender dispatches on (SC2)
                                 #   e.g. "capacity.trend", "naming.convention" — NOT a domain phrase
  inputs: [<field refs>]        # which measured values feed the recommendation (value, history, …)
  note: <string|null>           # optional human seed / template hint
```

Per principle 2: `intent_kind` and `signal` are **generic categories and handles**, not domain phrases. "Project a trend and flag when a threshold will be crossed" is an `intent_kind`; "disk fills in N months" is the recommend stage's *output*, never encoded here.

### 3b. On the emitted verdict (surfaced onto the artifact)
When a rule with a `recommendation` payload fires, the resolved verdict carries the intent **onto the artifact** so the recommender needs no catalog round-trip (SC3). Added to the emitted unit at the **evaluated-unit level** — metric item / card field / finding (SC5):

```
# alongside existing: value, severity, verdict_chain[{layer, severity, rule_id, reason}]
recommendation_intent:          # optional; present iff a fired, surviving rule declared one
  intent_kind: <enum>
  signal: <string>
  inputs_resolved: { <field>: <value> }   # the measured values, resolved at judge time
  note: <string|null>
```

A recommender reading one artifact then has, per judged unit: **what was measured** (value), **how it was judged** (severity + reason + layer provenance), and **what was intended to be recommended** (intent_kind + signal + resolved inputs) — with no catalog access and nothing subject-specific.

### 3c. What the recommender adds later (NOT in this contract)
The generative output — the recommendation text, the trend projection, "expand in ~N months" — is produced by the recommend stage, stored as its own artifact/field, and is out of scope here. The seam only guarantees the recommender has clean, sufficient, subject-agnostic input.

## 4. Interaction with existing stages

- **Layering (phase-8 step 3):** intent travels with the *winning* rule. A muted/waived unit carries **no** `recommendation_intent` (SC4) — a deliberately-waived item produces no recommendation, consistent with "muted = deliberately not assessed." (Revisitable: see Ratification record.)
- **Per-field judge (next build):** once cards judge per field, each field's verdict can carry its own `recommendation_intent`. Defined at the evaluated-unit level (SC5) so it works for metric items, card fields, and findings uniformly.
- **Temporal / store:** `inputs` may reference history; the recommender reads the finalization chain (substrate confirmed ready). The seam names *which* inputs feed a recommendation; reading across finalizations is the recommend stage's mechanism, not the contract's.
- **ADR 0006:** intent is resolved and surfaced **at canonicalization** (judge time), read at render/recommend — same invariant as verdicts. Finalized artifacts carry the intent as-stored; never re-resolved.

## 5. Ratified decisions

| # | Decision | Ratified |
|---|---|---|
| **SC1** | `intent_kind` starter enum | `trend_projection`, `remediation`, `attention`, `informational` — small, extensible |
| **SC2** | `signal` shape | Generic namespaced handle (e.g. `capacity.trend`), dispatched on by the recommender — **not** free prose |
| **SC3** | Surface intent onto the verdict (3b) vs. rule-only | **Surface onto the verdict** — no catalog round-trip at recommend time (small additive schema cost) |
| **SC4** | Muted/waived unit and recommendations | **Muted suppresses** — a waived unit carries no `recommendation_intent` |
| **SC5** | Placement granularity | **Evaluated-unit level** (metric item / card field / finding), not section level — composes with per-field judging |

### Consequential decisions flagged for later revisit (cheap until the recommend stage is built)
- **SC3** is the load-bearing one: it's the field-shape that makes the seam clean rather than coupled. Adopted as surface-onto-verdict. Changing it after the per-field judge build is the expensive retrofit — which is why it was settled here.
- **SC4 (suppress-on-mute) is a genuine semantic choice, not a mechanical default.** Adopted as suppress-by-default (a waived item produces no recommendation). The known alternative: emit a recommendation even on a muted item (e.g. "waived this time, but trending toward unwaivable"). Suppress-by-default is the safer first behavior; this remains cheap to flip until the recommend stage exists, and should be reconsidered when that stage is designed against real judged output.

## 6. Placement (ADR numbering — deferred)

This is the substance the survey always pointed `recommendation_hook` toward — the predictive/recommendations ADR that was forward-declared and never written. It stays a standalone ratified seam-contract for now; it graduates to a numbered ADR when the **recommend stage** design begins, so the number reserves the *stage*, not just the seam. The 0005-vs-later assignment remains open and is **not** bound here.

---

*Defines the judge→recommend seam only. No code; no recommend-stage design. Ratified for build — the per-field judge stage is built seam-aware on top of this.*
