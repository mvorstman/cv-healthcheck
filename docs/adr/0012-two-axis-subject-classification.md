# ADR 0012 — Two-axis subject classification: `category` (primary) + domain `labels` (additive)

**Status:** Accepted — 2026-06-05
**Supersedes:** none
**Related:** ADR-0009 (MCP-authored catalog sources / `propose_new_subject` lifecycle); ADR-0010 (row-scope evaluation rules — *distinct* from this; see "Naming" below).

---

## Context

Discovery for the initiative originally called "Scope Labels" found that the catalog **already** had a subject-classification mechanism: a single-valued `category` (controlled vocabulary `identity | security | licensing | performance | operations | storage`) with a derived `category_label`, authored via `propose_new_subject`, surfaced through `list_subjects`, and driving the workspace nav grouping (`TileDefinition.category`).

The initiative's real goal was **multi-valued** classification — a subject can belong to more than one operational domain (e.g. Security Assessment → security *and* compliance). So the genuine gap was **cardinality, not existence**.

Two problems with the initiative as originally framed:

1. **Taxonomy conflict.** Its proposed vocabulary and backfill, taken literally, would have created a *second* taxonomy disagreeing with the live `category` (e.g. "CommCell Details → infrastructure" vs live `identity`; "Backup Job Summary → backup" vs live `operations`). Two competing classifications violate the database-as-single-source-of-truth principle.
2. **Terminology collision.** "Scope" is already load-bearing in evaluation (section/rule scope, ADR-0010; `_scope_phrases`). A catalog "scope label" would reuse the most overloaded word in the codebase for an unrelated concept.

## Decision

1. **Naming.** Rename the initiative to **Domain Labels**. "Scope" stays reserved for evaluation; this axis never uses it.
2. **`category` is unchanged** — single-valued, primary, mutually-exclusive. All existing consumers (MCP, workspace nav) keep working untouched. Zero regression is the acceptance bar.
3. **Add `labels`** — a catalog-owned, **many-to-many** axis over subjects (0..N labels per subject).
4. **Vocabularies are separate *and disjoint*** — no term appears in both `category` and `labels`.
5. **Additive-only semantics** — a label never restates a category. This is guaranteed **structurally** by disjointness: a category term cannot be expressed as a label because it is not in the label set. (Not a runtime `if label == category: reject` rule that could rot.)
6. **Labels attach to the versioned subject row** (`subjects.id`), consistent with how `category` is carried per version and with the supersede model. A new version authored via `propose_new_subject` carries its own labels; superseding does not silently inherit them. (Verified in Phase 2: `list_subjects` does not collapse/dedup versions, so per-version labels are unambiguous.)
7. **Vocabulary storage** — a DB seed table (`domain_label`), catalog-owned and growable without code, per the zero-code-extension north star.
8. **Authoring (v1)** — an optional `labels` argument on `propose_new_subject`, validated against the vocabulary and **rejected loud** on an unknown term (mirroring `category` / rule-operator validation). No dedicated assignment tool in v1.
9. **First consumer** — MCP read filtering, `list_subjects(label=…)`. The read filter is **graceful-empty** (a member-less or non-vocabulary label returns `[]`, never raises). The loud reject-unknown lives **only** on the authoring path — read and write are deliberately asymmetric.

### Vocabulary (v1, disjoint)

- **`category`** (unchanged): `identity, security, licensing, performance, operations, storage`
- **domain `labels`** (new): `compliance, governance, backup, reporting`

## Consequences

**Positive**
- One taxonomy, two cardinalities — no parallel/competing classification system.
- Additive-only is enforced by construction, not by a rule that must be remembered and maintained.
- `category` and every consumer of it are untouched; the change is strictly additive.
- The catalog can answer report-domain questions ("what subjects belong to compliance?") and later feed downstream consumers (report profiles, health domains, rule packs) from the same labels.

**Accepted trade-offs**
- A subject cannot carry a label that coincides with a `category` term — e.g. `capacity_license` (category `performance`) cannot be labelled `licensing`. Accepted: "also belongs to a primary domain X" is a statement about primary classification, which is `category`'s job. (Whether `capacity_license`'s category *should* be `licensing` is category-correctness work, out of scope here.)
- Two controlled vocabularies to maintain. Mitigated by keeping the label set deliberately small and growing it by authoring.

## Known issue / follow-up (surfaced during implementation)

The `category` vocabulary is currently a **function-local `_LABELS` constant** against a **free-text `category` column** — not an importable single source of truth. The disjointness invariant test therefore *mirrors* those terms plus a data-driven cross-check against live subjects' categories. This is safe today (the data-driven check catches a real collision) but the mirror can drift if a colliding category term is added with no subject yet using it. **Backlog:** export `_LABELS` to a shared importable location so the disjointness invariant references one source of truth.

## Open questions (deliberately deferred — non-blocking)

- **Vocabulary composition.** The v1 set mixes cross-cutting concerns (`compliance`, `governance`) with finer operational domains (`backup`, `reporting`). Whether these are the same conceptual type, and whether the label vocabulary later wants internal structure, is left to a future review. The schema is vocabulary-agnostic, so this blocks nothing.

## Non-goals (v1)

Hierarchical/nested labels, colors, icons, dashboard redesign, scoring/rule changes, section-level or source-level labels, multi-dimensional taxonomy, a dedicated label-assignment tool, and the downstream consumers (report profiles, health domains, rule packs) — those read the same labels later but are not built now.

## Implementation (for traceability)

- **Phase 1** — schema: `domain_label` vocabulary + `subject_domain_labels` association + seed + disjointness test. Committed `36d9d41`.
- **Phase 2** — MCP read: `labels` in `list_subjects` output + `label` filter. Committed `fe9e111`.
- **Phase 3** — MCP authoring: `labels` arg on `propose_new_subject` + reject-unknown wired to the accessor. Planned.
- **Phase 4** — sparse backfill of subject→label assignments. Planned.
