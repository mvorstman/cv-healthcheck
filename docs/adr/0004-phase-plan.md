# ADR 0004 Phase Plan

**Status:** Settled (phase planning conversation, 2026-05-29)
**Parent ADR:** [docs/adr/0004-three-face-metadata-vocabulary.md](./0004-three-face-metadata-vocabulary.md)
**Related:** [docs/adr/0004-survey.md](./0004-survey.md), HANDOVER backlog #24 (dev tools retirement), #25 (tile detail_endpoint decision)

This document records the phase slicing for ADR 0004 implementation. The ADR itself explicitly defers phase planning ("Implementation phases. Phase planning happens as a follow-on, not in the ADR."). This is that follow-on.

The plan is nine phases. Each phase has a narrow scope, a defined validation gate, and a single in-workspace verification moment. Phases 5–7 are the user-visible regression recovery; phase 8 is the architectural compliance work; phases 1–4 are infrastructure that lands without user-visible change.

## Implementation status (2026-05-31)

Factual build-tracking (the parent ADR's Status line is unchanged — ratification is the user's call; this records what has shipped against the plan):

- **Phases 1–4** (Foundation, `metric`, `chart`, `card` section types) — **shipped**.
- **Phase 5** capacity_license · **Phase 6** client_growth · **Phase 6.5** dev-tools retirement · **Phase 7** backup_job_summary — **shipped** (the regression-recovery arc is complete; all render canonically).
- **Phase 8** (evaluative face) — **largely shipped**: single evaluation locus (`engine.evaluate`), rules registry + reference-by-id, vendor→template→override layering + `rule_overrides`, severity enum + `muted`, per-field **metric** and **card** judging, rule-kind dispatch with **threshold / presence / enum / format** kinds, and the recommend **seam** (`recommendation_intent`). See `0004-phase-8-design.md` §H for the dated build status.
- **Still outstanding in Phase 8** (genuinely not built): the two compliance **Shapes** (StatusRow, inline-threshold vendor sources) and the generative **recommend stage** (a future ADR).

## Scope adjustments

Two adjustments to the ADR's stated scope, made during phase planning:

**`multi_section` is deferred.** The ADR documents six section types in its vocabulary. Five get built in ADR 0004. `multi_section` is the one type with no in-scope consumer (none of the three regressed subjects use it) and one open design question (single canonical section with sub_sections vs N separate canonical sections). It is deferred to whatever ADR addresses License Summary as a whole. The ADR's vocabulary documentation stands at six types; the implementation ships five. Future LS work brings `multi_section` with it.

**Dev tools retirement is included as phase 6.5.** HANDOVER backlog #24 specified dev tools retirement as natural cleanup post-ADR-0004. Phase planning placed it explicitly inside the sequence, between phase 6 (client_growth migration) and phase 7 (BJS migration), at the first moment LB-1 (production tile detail_endpoints depending on dev routes) is cleanly resolvable. Tile detail_endpoint decision (backlog #25) lands as part of phase 6.5.

## Phases

### Phase 1 — Foundation

**Scope.** CEL plumbing (Python library selection, evaluator wrapper, CEL expression evaluation at collection time). `template_version` field on artifact provenance. Family-derivation convention (subject_id suffix stripping). Source tile UI cleanup (drop CommCell version, add last-collected timestamp, add version dropdown infrastructure). Conformance mechanism: schema validation at collection time, structured failure record emission, section-grained failure handling.

**Rationale.** All foundational concepts the rest of the phases consume. Conformance lands here rather than at the end so each subsequent section-type phase is conformance-aware from birth, not retrofitted later.

**Validation gate.** Existing subjects (SA, LS, the three currently-degraded subjects) continue to work. No user-visible change. New artifacts carry `template_version` and conformance metadata. CEL evaluator works against test inputs.

### Phase 2 — `metric` section type

**Scope.** Catalog declaration for metric sections (semantic + presentational + evaluative metadata for single or multi-field summary values). Canonical model extension. CEL-driven derivations stored at collection time. Python renderer. JS renderer. Conformance applied per phase 1 mechanism.

**Validation gate.** A test subject (or partial migration of one regressed subject) exercises a metric section end-to-end. Browser verification: the metric renders in the workspace correctly against real data.

### Phase 3 — `chart` section type

**Scope.** Catalog declaration for chart sections (axis, series, render mode). Canonical model extension. Python renderer. JS renderer using **Chart.js**. Conformance applied.

Chart.js is the chosen chart library. The dev tools' `metric_detail.html` uses Chart.js today; the canonical workspace charts will too. Phase 6.5 (dev tools retirement) then removes Chart.js as a *dev-only* dependency but it stays in the project as a workspace dependency. The workspace's existing mini-chart code in `quick_hc.js` (raw HTML divs, not Chart.js) is unchanged by this phase — those mini-charts serve a different purpose (inline-on-tile preview) than the chart section type (full chart with axes and series).

**Validation gate.** A test subject exercises a chart section end-to-end. Browser verification: the chart renders in the workspace correctly against real data.

### Phase 4 — `card` section type

**Scope.** Catalog declaration for card sections (key-value identity blocks, typically one row). Canonical model extension. Python renderer. JS renderer. Conformance applied.

**Validation gate.** A test subject exercises a card section end-to-end. Browser verification: the card renders in the workspace correctly.

### Phase 5 — Migrate capacity_license

**Scope.** Capacity Licenses subject migrated end-to-end to the new vocabulary. Sections: `metric` (utilisation_pct computed via CEL with sentinel handling for -1), `chart` (the trend chart the legacy builder computed and never emitted), `table` (existing table restored with clean column names via column_map). Template-default rules: warn at 70%, critical at 90%. Minimum evaluative-face machinery to fire those rules — basically Shape 1 (per-row severity codes derived from threshold rules) or the simplest applicable evaluator. The other two shapes (StatusRow, inline threshold) and the full layered rules engine remain phase 8.

**Validation gate.** Capacity Licenses renders in the workspace correctly against real data. Metric shows utilisation. Chart shows the trend. Table shows clean column names. Compliance rules fire correctly (warn/critical badges visible against real values). Source tile shows cleaned provenance (no CommCell version, last-collected timestamp present, template version visible).

### Phase 6 — Migrate client_growth

**Scope.** Client Growth subject migrated end-to-end. Sections: `metric` (total_clients, latest_added, yoy_pct computed via CEL), `chart` (12-month trend), `table` (clean column names). Template-default rules: warn on year-over-year decline.

**Validation gate.** Client Growth renders correctly against real data. Metric shows totals and YoY. Chart shows 12-month trend. Compliance rules fire. Source tile clean.

### Phase 6.5 — Dev tools retirement

**Scope.** Retire `src/cvhealthcheck/web/routes/development.py` and its 14 dedicated templates, 7 orphan helpers in `shared.py`, 4 stale data files in `data/catalog/metrics/`. Update tile detail_endpoints (backlog #25) — either repoint at in-workspace canonical chart views (which now exist as of phase 6) or drop the detail_endpoints entirely. Update 4 affected test files. Update 4 README references.

The investigation already produced a three-tier removal plan (Tier A safe-to-delete, Tier B requires callsite updates, Tier C requires product decisions). At phase 6.5, the Tier C questions are answerable because the workspace has its own chart rendering surface, validated against real data in phases 5 and 6.

**Validation gate.** Workspace renders correctly with dev tools removed. Capacity Licenses and Client Growth tile detail links resolve correctly to in-workspace views (or are cleanly absent). No broken URLs, no template render errors, no test failures. Chart.js remains in the project as a workspace dependency (used by phase 3's chart section type renderer); the dev tools' use of it goes away with the dev pages.

### Phase 7 — Migrate backup_job_summary

**Scope.** Backup Job Summary subject migrated end-to-end. Sections: `metric` (totals), `card` (overall status), `findings` (recent failures), `table` (recent jobs). Card-or-categorical structure for status breakdown decided during this phase, per ADR. Template-default rules as applicable.

**Validation gate.** BJS renders correctly against real data. All four sections present and populated. Source tile clean.

### Phase 8 — Evaluative face

**Scope.** Complete the evaluative face. The two compliance shapes deferred from phase 5: Shape 2 (separate StatusRow with templated good/warn/critical text — Disk Library Growth-style), Shape 3 (per-row threshold inline with metric — SLA-style). Full rules layering: vendor → template → override, with the verdict chain recorded per finding/section verdict. Severity enum (`critical, warning, info, good, muted`) firmly in place; `muted` working as suppression. The `recommendation_hook` field reserved on rules (unused in ADR 0004, present for ADR 0005's predictive face).

**Validation gate.** All three regressed subjects continue to render correctly (phases 5–7 validation gates still pass). At least one subject that exercises Shape 2 or Shape 3 gets a catalog row demonstrating it (likely a small test subject or a stub for Disk Library Growth, since DLG itself isn't in the regression set). Verdict chain visible in artifacts. Rule layering tested with a template-default and a per-report override on the same rule_id.

## What this phase plan explicitly does not include

- **License Summary migration.** Bespoke path unchanged. Future ADR addresses LS holistically; that ADR brings `multi_section` with it.
- **AI authoring loop / AI rebuild from conformance failure.** ADR 0005 or later.
- **Recommendations / predictive face.** Deferred per ADR 0004.
- **Cross-CommCell report identification.** HANDOVER backlog #23, unsolved by ADR 0004.

## Phase ordering rationale

The order is not arbitrary. Three principles shape it:

**Infrastructure before consumers.** Phases 1–4 build the vocabulary and renderers. Phases 5–8 use them. No phase consumes machinery that hasn't already landed.

**Regression recovery before architectural completeness.** Phases 5–7 fix the three regressed subjects (the user-visible problem). Phase 8 adds the full evaluative face on a working baseline. This is deliberate: the workspace looks right again before the compliance machinery is fully built, so consultants see the recovery first.

**Dev tools retirement at the first clean moment.** Phase 6.5, after both chart-using regression subjects have canonical chart sections to which the tile detail_endpoints can be repointed. Earlier risks broken URLs; later adds nothing.

## Validation discipline

Every phase's validation gate involves *real-data browser verification*, not just programmatic tests. This is the central lesson of the chart regression incident: tests passing while rendered output is broken is the failure mode the whole workflow exists to prevent.

A phase is not "done" until:

1. Code is implemented and tests pass.
2. The relevant subject(s) render correctly in the workspace against real data.
3. The artifact on disk matches the canonical shape declared in the catalog.
4. Source tile shows the expected provenance.
5. Compliance rules (where applicable) fire correctly against real values.

Browser verification is the gate. Programmatic verification is necessary but insufficient.

## STOP triggers specific to ADR 0004 implementation

Per ADR 0004's catalog-vs-code boundary: any implementation phase that hits a derivation the CEL primitives cannot express stops and returns to steering. No unilateral extension of the catalog vocabulary or the primitive set.

Additional STOP triggers for this phase plan specifically:

- Any phase that touches a subject and discovers a vendor-compliance shape outside the three documented in the ADR (per-row severity, StatusRow, inline threshold).
- Any phase that surfaces a conformance failure pattern the structured drift record shape cannot express.
- Any phase where browser verification reveals a rendering quality regression relative to the legacy builder (rather than improvement).
- Any phase where `template_version` provenance or the version dropdown UI produces user-confusing behavior.

## Phase succession

Each phase ends with: implementation + tests + browser verification + commit + HANDOVER update + CHANGELOG entry + pointer commit. The next phase opens against a clean tree, fully on origin.
