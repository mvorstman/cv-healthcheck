# ADR-0015: Template / Profile / Runtime separation — the subject catalog lifecycle

**Status:** Proposed (2026-06-12) — reviewed by Michiel + external reviewer
**Date:** 2026-06-12
**Relations:** Amends ADR-0013 (subjects-as-foundation gains the draft→template→profile lifecycle). Tightens ADR-0010 (rules registry gains a template-vs-profile axis). Hardens ADR-0014 (typed RP source becomes the enforced authoring path). Builds on ADR-0002 (customer/project entities) and ADR-0003 (name-based dataset resolution).

---

## Context

An adversarial audit (2026-06-12) tested three hypotheses behind the planned staging/approval redesign. Results:

- **H1 (compile mapping): survived, refined.** Approval synthesizes fields no draft contains (category_label, status, FK identity, a status flip on the superseded predecessor). "Approval strips a draft" is falsified; approval **compiles** a derived artifact. Refinement: the compiled template is not stable — `bind_rule`/`delete_rule` mutate `extraction_instructions` in place after approval, so the reviewed object and the operating object diverge.
- **H2 (template transferability): broken as stated.** The flagship specimen (storage_policy_copy_jobs v2) bakes the authoring CommCell's custom-report GUIDs, datasource id, and an engagement timeframe into one opaque URL inside `recognition_hints`. This is not a template carrying customer metadata; it is **an execution binding masquerading as a template definition**. Nothing transfers by copying; transfer requires re-expression.
- **H3 (context integrity): survived.** No write path exists that cannot carry explicit context; writes funnel through few choke points; `staged_artifacts` already has (unpopulated) `customer_id`/`engagement_id` columns; `execute_approval` takes no context input.

A step-zero probe (2026-06-12) resolved the three remaining unknowns (metrics report_id, `{"type": 2}`, HTML DOM ids). All three resolutions converge on one shape: **names and shipped-definition constants are template material; environment-resolved ids are profile material; anything re-derivable live is runtime material.**

The architectural problem this ADR addresses is therefore not "remove customer data from templates." It is:

> **Separate definition from resolution from execution.**

---

## Section 1 — The allocation table (normative)

Every element that appears in a subject recipe today, allocated to exactly one layer. Evidence column cites the audit (AQ1/AQ2) or the step-zero probe (P1–P3).

| # | Element | Layer | Rationale / evidence |
|---|---------|-------|----------------------|
| 1 | Report **name**, dataset **name** | **Template** | Stable logical reference; repo doctrine (README: "ids vary, names are more stable"); ADR-0003 contract. (P1) |
| 2 | CC-API relative endpoint (e.g. `/v2/storagepolicy`) | **Template** | Product API surface, environment-independent. (AQ2) |
| 3 | Table spec, root_key, column field paths | **Template** | Report-shape-bound, not customer-bound. (AQ2) |
| 4 | column_map source headers (csv/html/rest) | **Template** | Report-shape-bound. (AQ2) |
| 5 | Dataset default parameters (IsJobAged, allJobs, appId, storagePoolId…) | **Template** | Shipped dataset defaults, identical everywhere. (AQ2) |
| 6 | Definition-default constants (e.g. `{"type": 2}` = Hidden input `capLicenseUsage` default) | **Template** | Report-definition constant; identical per definition; re-derivable at authoring time. Record provenance as "definition-default constant". (P2) |
| 7 | Parameter **declarations** + template-level defaults (e.g. timeframe default) | **Template** | The template declares what is bindable; defaults are policy. (AQ2/AQ3) |
| 8 | Evaluator binding refs (`{ref}`) | **Template** | Refs are ids into the rules registry. (AQ2) |
| 9 | **Policy-class** rule definitions (encrypted == "No", capacity bands) | **Template** | Reusable judgments about the product, not a customer. (AQ2) |
| 10 | Section definitions, layout, view-mode, domain labels | **Template** | Structure. (AQ1) |
| 11 | RP report **id** / custom-report composite GUIDs | **Profile** | Exist only per CommCell (#34); resolved binding of a logical name. (AQ2, P1) |
| 12 | Metrics report **id** (e.g. `318`) | **Profile** | Per-environment resolved binding; not even uniformly inventoriable (Metrics reports live outside the custom-report namespace — dereference-only). (P1) |
| 13 | `parameter.datasource[]` / CommServUniqueId | **Profile** | The shared-RP-server scoping id; natural home: customer identity columns; auto-resolved from CCID, confirmed by operator. (AQ2/AQ3; provenance session) |
| 14 | Parameter **overrides** (e.g. engagement timeframe `-P7D P0D`) | **Profile** | Engagement policy bound per project. (AQ2/AQ3) |
| 15 | **Customer-assertion** rules (`Company_1`, `rommelgroep`, named users) | **Profile** | One customer's objects; profile-owned rule packs. Today's flat registry has no axis to express this — see D4. (AQ2/AQ3) |
| 16 | Customer identity (CCID, CommServe hostname, reg code/GUID, optional RP server) | **Profile** (customer record) | The verification keys for the provenance guard. (Provenance session; F) |
| 17 | Dataset **GUIDs** | **Runtime** | Re-resolved live per collect via ADR-0003's name→GUID walk; a cached copy in the profile is permissible as a hint, never authoritative. (P1) |
| 18 | Resolved/assembled collect **URL** | **Runtime** | The execution artifact. Today's spcj failure is precisely this fossilized into a definition. Never persisted in template or profile. (AQ2; H2) |
| 19 | limit/offset/format mechanics | **Runtime (provisional)** | Classified from one specimen (baked into spcj's URL — extractor mechanics leaked into a recipe string, AQ2). Provisional because `format` may belong to the source *contract* (template-layer) rather than execution; settle at the first compile-gate implementation. |
| 20 | HTML `detail_table_dom_id` | **Runtime / informational** | Design-time component id minted in the report definition (epoch parse: 2018 ids in 2026 exports); inherits per-CommCell variance for custom reports; extraction already keys on structural/title matching and never reads it. Permissible as non-normative authoring prose; excluded from the extraction surface. (P3) |
| 21 | Extracted record values / canonical artifacts | **Runtime → evidence store** | Customer evidence, scoped to (customer, project); never template content. (AQ1) |
| 22 | `ArtifactSource` identity stamps (CCID/host/name as collected) | **Runtime → evidence store** | Provenance recorded with evidence, verified against the profile's declared identity (collection guard). (F; provenance session) |

**Allocation rule for future elements:** if it is a name or shipped-definition constant → template; if it is an environment- or engagement-resolved value → profile; if it is re-derivable live or assembled at collect time → runtime. An element that cannot be classified remains **unallocated and blocks publication of any template containing it** until investigated and classified — preserving the unknown → investigate → allocate discipline. (Runtime is not a safe default: a customer-specific element silently allocated to runtime would receive no profile binding and would hide the very transferability defect this table exists to catch. Blocking is per-template, not per-phase.)

---

## Section 2 — The model

```
TEMPLATE  (catalog, customer-independent, versioned, immutable once published)
   logical references + declared parameters + structure + policy rules
        │
PROFILE   (per customer/project: the composition + resolution layer)
   selected templates + resolved bindings + parameter overrides
   + customer-assertion rule packs + customer identity
        │
RUNTIME   (per collect: resolve, then execute)
   name→id resolution, URL assembly, extraction, evidence + provenance stamping
```

- Current model: `template → resolved address → execute`.
- Target model: `template → logical reference`; `profile → resolution binding`; `runtime → resolve → execute`.
- The resolved execution artifact exists **only** at runtime. Persisting it into a definition is the defect class this ADR eliminates.

**Lifecycle:** draft (authored via MCP from a real uploaded report, customer-laden, tunable) → **approval = compile + publish** (derived template, customer content excluded by construction, frozen version, moved to catalog; draft data discarded — reproducible by re-running the recipe against the original report) → profile binds templates to a customer/project → runtime collects.

---

## Section 3 — Decisions

**D1 — Approval is compile + publish.** A template is a derived artifact compiled from a draft, never "draft minus data." The compile step is explicit, owns the synthesized fields, and applies the allocation table: profile-layer and runtime-layer content must not survive into the template.

**D2 — Published templates are immutable.** What was reviewed is what operates. Rule bindings move out of the template's `extraction_instructions` blob into separate binding rows; any post-publish change to a template is a new version (supersession per existing mechanics). This is the **Publication Integrity** invariant — an auditability requirement independent of customer isolation: "what exactly was approved?" must always have one answer.

**D2a — Recipe immutability guard (shipped 2026-06-14; interim realization of D2 ahead of D4).** Until bindings physically move to their own rows (D4), the bindings still live co-located in `extraction_instructions.evaluative.row_rules`. Rather than leave the published template mutable in the meantime (the Findings divergence: `bind_rule`/`delete_rule` mutated the blob in place after approval), a guard makes approval **truthful for the recipe now**: any post-approval write to a section's `extraction_instructions` may change **only** `evaluative.row_rules` — every recipe key (known or future) and every other `evaluative` subkey is locked. The guard is an **allowlist** comparing PARSED structures (`assert_recipe_unchanged` / `RecipeImmutabilityError` in `db/rules.py`), so a recipe key nobody enumerated is protected by default and JSON key-reordering never trips it.

Scope of D2a (and what it intentionally is NOT):
- The **extraction recipe is locked at approval**; the **evaluative bindings are an intentionally-mutable layer**, co-located in the section blob today, to be physically separated into binding rows by D4 — at which point the template blob carries no bindings and is wholly immutable.
- D2a does **not** lock bindings (routine rule authoring via `save_rule(bind=…)` / `delete_rule` against an active subject stays a one-call operation; a per-rule version bump is explicitly avoided). Deciding whether *bindings themselves* must become immutable is the D4 question, not D2a.
- D2a does **not** change multi-version write scoping: `bind_rule` still writes every matching section row across versions (incl. superseded); the guard validates *what* changed (recipe vs bindings), never *which* rows are written. Any change to that scoping is a separate slice.

**D3 — Transferability by re-expression.** Templates hold logical names and declared parameters; profiles hold per-customer/per-environment resolutions (this is where backlog #34 lives and dies). Copying resolved values into templates is prohibited by the allocation table.

**D4 — Profiles own customer-specific configuration, bindings, and customer-assertion rule packs.** (Customer *evidence* does not live in profiles — it lives in the scoped evidence store; rows 21–22.) A profile is: selected templates (ordered) + resolved bindings + parameter overrides + customer-assertion rule packs, scoped (customer_id, project_id). Landing spot: a new per-(customer, project) bindings table (projects gains no JSON blob). The rules registry gains a template-vs-profile axis so policy rules and customer assertions stop sharing one undifferentiated namespace (tightens ADR-0010). The profile is the seed of the report builder: project creation selects a default profile, a custom profile, or starts blank; composition features grow on this object (per ADR-0013).

**D5 — Writes require proof of explicit context selection.** Staging rows populate their existing `customer_id`/`engagement_id` columns at creation (web staging has the request context available today and discards it). `execute_approval` requires explicit context as an input; absence of explicit selection is an error, never a silent default. The enforcement primitive lands first as its own change with a failing-then-passing test; call sites migrate onto it during the redesign.

**D6 — Publication requires structured parameterization.** A source type that cannot express address, identity, and parameters as separately declared elements may not be published as a reusable template. Current mechanism: the ADR-0014 typed `reportsplus_dataset` source for RP-sourced subjects; hand-built query strings via the generic endpoint are rejected at compile time for RP addresses. (The flagship specimen routed around the typed source after it shipped — capability without enforcement produced the defect. The principle outlives the class name: any future source type is held to the same bar.)

**Invariants (named, normative):**
- **Context Integrity:** a customer-data write may only occur against an explicitly selected context; absence of explicit selection is an error, never a silent default.
- **Publication Integrity:** the object approved by a reviewer must be the same object executed by the platform.
- **Template Catalog:** a template must transfer to a brand-new customer without modification; customer-specific information belongs in the project profile, not the template.
- **Catalog Purity (review criterion):** the catalog must not require access to any customer to be understood, reviewed, versioned, approved, or transported.

---

## Section 4 — Consequences

- **Publication becomes a validation boundary.** Compile validates, in one gate: allocation-table compliance (no profile- or runtime-layer content in the template), transferability (Template Catalog invariant), Catalog Purity, and structured parameterization (D6). The spcj class becomes a compile error, not a review burden.
- Existing templates require triage: spcj v2 (and any RP subject with baked addresses) must be re-expressed; customer-assertion rules migrate to profile rule packs; `{"type": 2}`-style constants get provenance annotations.
- `bind_rule`/`delete_rule` stop mutating published templates; bindings become separate rows (or force a version bump).
- The global catalog files under `data/catalog/` holding customer evidence (LS/SA) violate Catalog Purity and are retired by the independent Fix 2 plus the LS/SA conversion.
- Profile schema work lands with, not before, the staging redesign (same code region as the context gate).

## Section 5 — Open items (explicitly not resolved by this ADR)

1. **Cross-environment id variance is assumed but not yet demonstrated** — the repo holds one environment; verified the moment the Phase-1 two-customer lab runs the same template against a second environment. Until then the burden of proof stays open.
2. **Server-side name-based dataset addressing** — a live capture (API-viewer, 2026-06-12, in-session) shows the metrics server serving `datasets/Metrics CommCell Details/data` by name; no repo evidence exists. Commit the capture as evidence and/or verify live before any design relies on it. Until then, client-side name→GUID resolution (ADR-0003) is the only assumed mechanism.
3. **Semantic label of `{"type": 2}`** (which trend view it selects) — documentation TODO, not an allocation blocker.
4. **Multi-CommCell-per-customer** — explicitly deferred; identity stays on the customer record with the per-project split as the documented escape hatch.
