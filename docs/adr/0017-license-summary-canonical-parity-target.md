# ADR-0017: License Summary canonical parity target — what "parity" proves

**Status:** Proposed
**Date:** 2026-06-13
**Relations:** Closes the loop on ADR-0016 (the transform layer that makes the
generic LS recipe possible) and feeds the ADR-0016 build order's final steps (LS
conversion → parity proof → retire bespoke LS). Builds on the Fix-3/Fix-4
identity/provenance work (the enrichment seam, D2).

---

## Context

The License Summary de-bespoke conversion replaces the hand-written LS pipeline
(`license_summary/` + `adapters/license_summary.py`) with a generic recipe on the
ADR-0016 model. A parity harness (`tests/ls_parity_harness.py`) compares the
generic candidate against the bespoke baseline over the **38** real LS exports
(the corpus; 3 of the 41 files on disk are misfiled non-LS).

The bespoke output and a faithful generic output differ in ways that are NOT
errors:
- **representation** — bespoke flattens a number and its unit into separate
  fields; the generic `number_with_unit` returns a `{value, unit}` pair;
- **placement** — bespoke carries counts as `ArtifactSummary.metrics`; the
  generic carries them as computed sections;
- **fidelity** — bespoke *drops* data the file carries (it dedups agent rows, and
  omits `registration_code` from the canonical); the generic surfaces it.

So "parity" cannot mean byte-replication of bespoke output. **Parity proves the
generic produces the decided canonical TARGET — not replication of bespoke
omissions.** Where bespoke lost or dropped data the file carries, the generic path
is the more faithful one and parity accepts the difference rather than degrading
the generic path to match a bespoke gap.

This ADR records the equivalences (D1–D7) the parity comparator encodes, so that a
parity failure is a real difference, not a comparator artifact. The decisions were
settled across the deciding-reads and comparator slices; this is their record (the
comparator and CHANGELOG had them; the ADR is the source of truth).

---

## Decision

**D1 — value/unit equivalence.** A bespoke flat unit-bearing value (a number plus
a separate row `unit` field, or a `"N unit"` string) is EQUAL to the generic
nested `{value, unit}` when their (value, unit) pairs match. The standalone `unit`
field is subsumed into the pair (not compared on its own). Grounded by ADR-0016
Amendment A (units are consistent per quantity across the 38; `number_with_unit`
is parse-and-keep, no normalization). Applies to `available_total`, `used`,
`entitlement_value`.

**D2 — `commcell_info` is a MIXED-SOURCE enrichment section** (clarified
2026-06-13 — a strengthening, not a retreat). Two field categories, two
authorities:
  - **Identity** (`commcell_name`, `commcell_id`): authoritative source = the
    CUSTOMER CONTEXT (the declared active customer). `commcell_id` is stamped on
    `ArtifactSource` (Fix-3/4); `commcell_name` is a `commcell_info` item.
  - **Observational metadata** (`commcell_version`, `license_expiry`,
    `last_collection`): authoritative source = the REPORT EVIDENCE —
    transport-agnostic (the `ExtractionResult` is today's transport, NOT the
    authority; the field's truth lives in the report, reachable by whatever
    mechanism — today `metadata_pairs`-over-HTML/CSV, tomorrow possibly REST).

  The enrichment layer ASSEMBLES `commcell_info` from BOTH authorities at the
  `result_to_artifact` seam — identity from context, observational from report
  evidence — present only where each value exists (matching bespoke's per-file
  variation: 28 name-only / 8 full / 2 name+expiry). It is enrichment-ASSEMBLED,
  not a recipe section; the recipe MAY `metadata_pairs`-extract the observational
  labels (legitimate report evidence, NOT identity injection).

  **Identity precedence (`commcell_name`):** real declared context value > real
  report-evidence value > placeholder/default. "Unknown CommCell" is treated as
  NO authoritative value (absence of identity), so a real file-observed name
  ("CommServe A") beats the bare default — preserving Fix-3/4 (declared identity
  wins; the placeholder is not a declared identity).

**D3 — counts are computed sections, not summary metrics.** A bespoke
summary-metric `X` is EQUAL to a generic same-named computed-section `X` (same
name + same value). The metric vs section placement is not a parity concern —
nothing requires the metric placement (only a generic, gracefully-degrading tile
subtitle consumes `summary.metrics`; no rule, no report). A DIFFERENT value still
fails; a count present on only one side still fails. (`other_license_count` =
`row_count` over other_licenses; `agent_feature_count` = `distinct_count` over
agent_feature_licenses.license.)

**D4 — empty ≡ absent (F4); dedup tolerance (F3).** An empty section equals an
absent section (no rows of that type). Row-multiplicity differences are tolerated
where the DISTINCT set matches: bespoke dedups agent rows by license name, the
generic surfaces the real duplicates the file carries — the generic is more
faithful, and `distinct_count` parity holds regardless.

**D5 — `usage_percent` omitted.** It is a percentage, not unit-bearing; the
`Used %` column is absent across the corpus; `to_float_percent` is spec'd but
deferred (no fixture). The recipe omits `usage_percent`.

**D6 — sensitive fields: masked, not byte-identical.** A sensitive field is equal
iff BOTH sides are masked and NEITHER leaks raw — the mask FORMAT is not compared
(generic segment-mask `****-****-****-1234` ≡ bespoke first-4/last-4). A raw value
on either side fails (security preserved).

**D7 — `registration_code` is part of the canonical target when the source carries
it.** The generic recipe extracts and masks it (ADR-0016 Security-by-Construction).
Bespoke dropping `registration_code` was a historical omission, not a canonical
requirement. Parity ACCEPTS generic-present masked `registration_code` versus
bespoke-absent, provided the generic value is masked and no raw survives. Same
class of decision as D4/F3 — the generic is the more faithful path.

**D8 — the workload "Other Licenses" section-id collision is NOT preserved.**
Bespoke `_to_snake("Other Licenses")` gives the workload section the id
`other_licenses` — the SAME id as the `other_licenses` TABLE. Across the 38-file
corpus the two never co-occur (30 table / 8 workload / 0 both), so the shared id
never modeled a real relationship; it is a historical naming artifact. The recipe
CANNOT mirror the workload under `other_licenses` (`subject_sections` is unique on
section_id), and authoring it under a distinct id would double the fails rather
than clear them. The canonical target therefore does NOT preserve the bespoke
workload "Other Licenses" section. Parity ACCEPTS a bespoke-only workload
"Other Licenses" section (keyed `(other_licenses, workload)` by the B1 shape-tag)
as a non-preserved quirk. Same class as D7 — a deliberate, named drop. SCOPED to
this exact (id, shape-tag) pair: an unrelated bespoke-only section, the
bespoke-only `other_licenses` TABLE, and any other workload section id all still
FAIL (negative guards).

### Comparator bug-fixes (not decisions)

- **B1 — section-id collision.** The bespoke `_to_snake("Other Licenses")` workload
  section and the `other_licenses` TABLE collapse to the same id `other_licenses`;
  the comparator keys sections by `(id, shape-tag)` (a workload section carries the
  distinctive `entitlement_value` field) so a table is never cross-compared against
  workload fields.
- **B2 — unit-parse divergence (OPEN).** `number_with_unit` keeps everything after
  the number (`"0 source VMs"` → unit `"source VMs"`); bespoke `maybe_unit_from_value`
  keeps only the trailing word (`"VMs"`). One pattern, 28 rows. Resolution pending
  (number_with_unit → last-word unit, or comparator trailing-word normalization).

---

## Consequences

- The parity harness encodes D1, D3, D4, D6, D7, D8 as comparator equivalences and
  B1 as a section-identity fix; D2 and D5 are recipe omissions (the generic recipe
  does not extract them). A parity failure now denotes a real difference.
- The generic LS canonical SHAPE differs from the old bespoke shape (nested
  `{value, unit}`, counts as sections, `registration_code` present); this is the
  decided target, and downstream consumers read the target, not the old shape.
- D2 requires the enrichment seam to populate `commcell_info` from context before
  the conversion can fully close (it is not a recipe concern).
- Acceptance criteria (ADR → Accepted): the generic LS recipe converts, parity (by
  these definitions) holds over the 38, B2 and the "Other Licenses" title
  ambiguity (residual (b)) is resolved, the enrichment seam supplies
  `commcell_info`, and the bespoke LS path is retired with no regression.

## Open questions

- **B2** unit-parse: last-word unit vs trailing-word normalization.
- **"Other Licenses" — title-prefix ambiguity RESOLVED; two residuals remain.** The
  TABLE is now matched by its exact full title "Other Licenses - current usage
  details", so the recipe no longer grabs the bare-"Other Licenses" workload as a
  degenerate table. Residuals needing a decision: **(a) workload-vs-table id
  collision** — the bespoke workload "Other Licenses" has `_to_snake` id
  `other_licenses` (the table's id); the recipe CANNOT declare two `other_licenses`
  sections (`subject_sections` is unique on section_id), so the workload can't be
  mirrored under that id (authoring it under a distinct id would double the fails,
  not clear them). Decision needed: give the target workload a distinct id + a
  comparator mapping, or accept the bespoke collision as a quirk the target drops
  (D7-class). **(b) HTML-structure variation** — 6 files (lab-*, some
  License20summary, the sample) carry no `.reportstabletitle` element, so the
  selector-based recipe can't reach their tables (the bespoke custom DOM-walk can);
  this is the "HTML section not found" class, separate from "Other Licenses".
  Residual (a) — RESOLVED by D8: the workload-vs-table id collision is accepted as
  a non-preserved quirk (the target drops the bespoke workload "Other Licenses").
- **D2 enrichment seam**: the mechanism that attaches context identity onto the
  artifact at assembly.

## Alternatives considered

- **Byte/shape replication of bespoke output** — rejected: it would freeze
  bespoke's omissions (dropped registration_code, deduped rows, lost header units)
  into the canonical, and degrade the generic path to match gaps. Parity proves the
  decided target instead.
- **Counts as summary metrics in the generic path** — rejected (D3): nothing
  requires the placement, and the closed computed-section set is the model's count
  mechanism; equating the two in the comparator is cheaper than a model change.

## References

- ADR-0016 (recipe transform layer) + its Amendment A/B (number_with_unit) and the
  Piece-B recipe-feasibility inventory (F1–F6).
- ADR-0015 (compile gate) — the recipe publishes through it.
- `tests/ls_parity_harness.py` (comparator), `tests/ls_generic_recipe.py` (the
  recipe + signal runner), CHANGELOG 2026-06-13 entries (deciding-reads, comparator
  slices, B1, D7, D8, F5/D3).
