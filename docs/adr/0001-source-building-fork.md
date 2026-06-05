# 0001 — Source-building fork is retained; upload routing is unified

**Status:** Accepted
**Date:** 2026-06-04

## Context

In May 2026 a multi-session refactor set out to unify two parallel paths for "upload a file for a subject":

- **Path A** (system subjects): per-subject route handlers like `POST /quick-hc/security-assessment/import`, per-subject persist functions, hand-written subject tile builders (`_legacy_builders` in `src/cvhealthcheck/quickhc/subject_data_service.py`).
- **Path B** (AI-created subjects): a single generic route `POST /quick-hc/import?subject_id=<id>` with a generic source builder `_build_generic_subject` that emits via `artifact_to_view` against the canonical artifact schema.

The original framing was "unify everything — system vs AI becomes a database fact (`subjects.created_by`), not a code-path distinction." That framing drove sessions 1-3 of the refactor.

Sessions 1, 2, and 3 (URL flip) landed cleanly. Session 3's attempt to delete `_legacy_builders` and route everything through `_build_generic_subject` was narrowed to URL changes only after the snapshot test failed with structural diffs.

Session 3b investigated the source-building unification more carefully and stopped before writing the proposed adapter. The investigation surfaced two facts:

1. **The canonical schema cannot represent the legacy-shape sections.** The frozen `CanonicalArtifact` schema has section types `findings`, `table`, `metric`, `chart`. The legacy tile data uses `counters` (Security Assessment), `findings_grid` (Security Assessment), `workload` (License Summary), and `chart_growth` (Client Growth). The generic `artifact_to_view` cannot produce these shapes; the canonical schema has no place to encode them.
2. **Even simple subjects' subject-level fields differ.** For the simplest subject (environment), the legacy builder computes `subtitle: "cs01 · 11 SP40.47"` from CommServe identity, sets `fullUrl: /quick-hc/commcell` from the per-subject route endpoint, and adds source-level `meta` entries (Endpoint, Host, Version). The generic path doesn't synthesise any of these from a `CanonicalArtifact`.

An adapter that reads legacy on-disk data into a `CanonicalArtifact` cannot losslessly reproduce `_legacy_builders` output, because the loss isn't in the read — it's in the schema. The full inventory is in `docs/refactor_unified_upload_session_3b_inventory.md`.

## Decision

**The upload routing path is unified. The source-building path is not unified.**

- `POST /quick-hc/<subject_id>/import` handles uploads for every subject — system or AI. This part of the refactor stands. (`quick_hc_subject_import` in `src/cvhealthcheck/web/routes/quick_hc.py`.)
- `_legacy_builders` continues to serve the six system subjects (`environment`, `security_assessment`, `license_summary`, `client_growth`, `capacity_license`, `backup_job_summary`). `_build_generic_subject` continues to serve everything else (AI-created subjects, and any subject whose canonical store has a fresh artifact).
- The dispatch in `build_subject_initial_data` keeps its current shape: try canonical store; on miss, fall back to the legacy builder for system subjects, otherwise fall back to the generic builder.

System vs AI remains a runtime fork in source-building — by necessity, not just a database fact.

## Amendment (2026-06-01, per ADR 0007)

`environment` has been migrated to the canonical path and removed from `_legacy_builders` (ADR 0007 Phase 3, slice B). This is the retirement this ADR anticipated as the *sanctioned* path — not a reopening of the decision below.

It needed **no schema unfreeze**. Environment's shape is a canonical **card** section, already representable — unlike the five legacy-shape subjects whose `counters` / `findings_grid` / `workload` / `chart_growth` views the frozen schema still cannot express. And the subject-level fields the Context's point 2 noted the generic path "doesn't synthesise" (subtitle `cs01 · 11 SP40.47`, source-level `meta` (Endpoint/Host), and the source status badge) are now derived generically by `_build_generic_subject` / `_build_generic_sources` from the canonical artifact, so environment renders identically through the uniform "canonical store wins" path with no live builder.

`_legacy_builders` therefore now serves **five** subjects, not six: `security_assessment`, `license_summary`, `client_growth`, `capacity_license`, `backup_job_summary`.

The core decision and its "don't delete `_legacy_builders` to feel cleaner" warning stand **unchanged** for those five: their legacy-shape views remain unrepresentable in the frozen schema. This amendment sanctions only the environment retirement — whose shape was always canonical — and is **not** a campaign to dissolve the fork. The two revisit triggers below are unchanged; environment qualified under neither (no schema unfreeze, no product redesign), because its shape never needed the schema extended in the first place.

## Consequences

### Preserved (the original goals that survive)

- Adding new AI-created subjects requires no code changes. The unified upload route + generic source builder handle them.
- The six system subjects retain their custom view shapes: `counters`, `findings_grid`, `workload`, `chart_growth`. The customer-facing Quick HC tile presentation is unchanged.
- Legacy artifact-store reads continue to work (Option A invariant from 2026-05-27).

### Accepted tradeoffs

- Two source-building paths remain in the codebase. This is an honest reflection of two genuinely different shapes of tile data, not technical debt.
- A future session that sees `_legacy_builders` may instinctively want to remove it. Code annotations at the dispatch site and at the function definition point at this ADR.

### Out of scope for this decision

- If the legacy-shape tile data is ever migrated to the canonical schema (which would require schema unfreeze + per-subject migrations + per-subject view producers), the fork can be retired then. That work is not on any current roadmap.
- Sessions 4 (delete old upload routes) and 5 (replace the unified route's branch dispatch with data-driven dispatch) can proceed unblocked. They are independent of source-building.

## Alternatives considered

- **γ1 — Restore per-subject view producers in `canonical_view.py`.** Reintroduce `security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view` (which were removed in session 2 alongside `_build_sources`). Make `artifact_to_view` dispatch by `artifact_type`. Then `_legacy_builders` can be deleted because the new dispatch reproduces the legacy view shapes. **Rejected** as speculative work without concrete motivation: the architecture is no cleaner than the current fork — subject-specific knowledge just moves from `_legacy_builders` to `canonical_view`. Future sessions can revisit if a clear motivation emerges.
- **γ2 — Accept the regression.** Delete `_legacy_builders`, let all subjects render via the generic view producer. **Rejected**: loses the customer-facing custom view shapes. The Quick HC product was designed around these shapes; removing them is a real UX regression.
- **γ3 — Extend the canonical schema** with new section types (`counters`, `findings_grid`, `workload`, `chart_growth`). **Rejected**: violates the frozen-schema constraint that has held for the duration of the project. Schema changes have a large blast radius.
- **γ4 — Hold position; document the fork** (this ADR). **Accepted.**

## References

- Investigation report: `docs/refactor_unified_upload_2026-05-31.md`
- Session 3b inventory and architectural finding: `docs/refactor_unified_upload_session_3b_inventory.md`
- Session 3 wrap-up CHANGELOG entry: `CHANGELOG.md` entry dated 2026-06-02
- Session 3b wrap-up CHANGELOG entry: `CHANGELOG.md` entry dated 2026-06-03
- Code annotations: `src/cvhealthcheck/quickhc/subject_data_service.py` — at the top of `build_subject_initial_data`'s dispatch (line ~91), at `_legacy_builders` (line ~317), and at `_legacy_loaders` (line ~292).
- Frozen canonical schema: `src/cvhealthcheck/artifacts/models.py` (do not modify).

## Revisit triggers

Reopen this decision if and only if:

- A schema unfreeze is independently motivated (a new subject type genuinely needs a new canonical section type), and the migration plan covers all six legacy-shape subjects too.
- The customer-facing Quick HC product is being redesigned in a way that removes the need for `counters` / `findings_grid` / `workload` / `chart_growth` shapes.

Don't reopen this for "the fork is ugly" or "I want to delete `_legacy_builders` to feel cleaner." The decision above already considered and rejected that motivation.
