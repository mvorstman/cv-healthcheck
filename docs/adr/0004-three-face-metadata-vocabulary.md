# ADR 0004 — Three-face metadata vocabulary

## Status

Proposed.

> **Implementation note (2026-05-31):** the Status line above is left as written — its formal ratification is the user's call, not a doc-cleanup act. Factually, the vocabulary's plan has **largely shipped**: phases 1–7 are complete and phase 8 (the evaluative face) is largely built (per-field metric/card judging; threshold / presence / enum / format rule kinds). Only the phase-8 **Shapes** and the generative **recommend stage** remain. See `0004-phase-plan.md` §Implementation status and `0004-phase-8-design.md` §H.

## Context

ADR 0003 unified REST collection into a single catalog-driven extractor. Phase 4 migrated Security Assessment cleanly. Phase 5 deferred License Summary. Then a screenshot revealed that Capacity Licenses had lost its chart, and a blast-radius investigation showed that three of four migrated subjects had silently regressed: ADR 0003 modernized *how data gets collected* and accidentally downgraded *how data gets shown*, because the rendering intent lived in hand-written legacy builders rather than in the data itself.

The diagnosis is that catalog-driven extraction produced canonical artifacts the generic renderer didn't know how to display richly. The renderer fell back to a plain table. Charts, summary metrics, and multi-section structures — all real presentations the legacy builders produced — quietly disappeared.

The pre-ADR-0004 cleanup addressed two adjacent issues. It preserved vendor-stable identifiers (`attrName`, `PARAMID`) in Security Assessment findings so the future rule layer has something stable to match against. It made unsupported section types fail loudly at insert and collection time rather than silently render nothing. It documented as a backlog item that report IDs are not stable across CommCells — a finding that emerged from three CommCells' worth of API captures and shapes ADR 0004's design.

The ADR 0004 survey stress-tested a proposed three-face metadata vocabulary against five CommCells' worth of evidence: the six in-corpus subjects, License Summary in full, and supplementary captures from a different deployment. The survey actively tried to break the design rather than confirm it, surfaced approximately thirty distinct gaps, and identified the formula language, vendor-stable key preservation, and cross-CommCell calibration as the most consequential. Pre-cleanup addressed vendor-stable keys. ADR 0004 addresses the rest.

The architectural principle ADR 0004 commits to is simple and follows from the regression: **every section of every subject carries metadata describing what it is, how it should be shown, and how it should be judged**. The data is self-describing across three faces. Renderers consume metadata to draw; evaluators consume metadata to judge; AI authoring (a successor ADR) consumes metadata to propose new subjects. The same vocabulary serves all three readers.

## Decision

ADR 0004 defines a three-face metadata vocabulary, builds the renderers and evaluators that consume it, and validates the whole by restoring rich presentation and adding compliance to the three regressed subjects.

### The three faces

Every section of every subject declares metadata across three faces:

- **Semantic** — what is this data. Type, unit, time period, entity, derived quantities, vendor-stable identifiers.
- **Presentational** — how should it be shown. Render mode, layout hints, sort and limit rules.
- **Evaluative** — how should it be judged. Rule references, severity outputs, and an explicit precedence layering of vendor verdicts, template defaults, and per-report overrides.

The three faces are independent declarations attached to the same section. A section can carry all three (a metric with a chart and a threshold rule), or only some (an identity card carries only semantic and presentational). Faces compose; they don't depend on each other.

A fourth face — *predictive*, for recommendations like "at this growth rate, full in 47 days" — is deliberately out of scope. ADR 0004's evaluative face is designed not to paint predictive into a corner. Specifically, rules may carry a `recommendation_hook` forward-declared field that ADR 0004 itself ignores; a successor ADR introducing predictive will interpret it.

### Section types

Six section types form the initial vocabulary. Adding a new type is a deliberate code change; new instances of existing types are catalog data.

- **table** — rows-and-columns, plain.
- **findings** — severity-bearing rows with title, description, recommendation, and vendor-stable identifiers.
- **metric** — single or multi-field summary values, optionally with derived computations.
- **chart** — time-series or categorical visualisation, with explicit series and axis declarations.
- **card** — key-value identity block, typically one row.
- **multi_section** — a logical section containing N sub-sections of the same shape, where the sub-section names are discovered from the data rather than declared in the catalog. License Summary's workload sections are the canonical case.

The same names appear in the catalog SQL (`section_type` column), the canonical Python model (`SectionType` enum), the renderer's dispatch (`section.type` matching), and the workspace JS. ADR 0003 left three different vocabularies in use; ADR 0004 forces alignment. One source of truth, one set of names, used end to end.

### Formula language

Derived values, rule predicates, and field-source expressions use [CEL — Common Expression Language](https://github.com/google/cel-spec). CEL is statically typed, sandboxable, well-documented, and expressive enough for every derivation the survey identified. It's safe for AI authoring in the successor ADR. The cost is one Python dependency (`cel-python` or equivalent) and a thin evaluator wrapper.

Examples of CEL expressions in catalog rows:

```
records[size(records)-1].total_clients
sum(records.filter(r, r.month == latest_month).used_capacity)
latest_used / latest_purchased * 100.0
records.size() >= 13 && records[size(records)-13].total_clients > 0
```

The evaluator runs at collection time. Derived values are computed once, stored as part of the section's data, and treated as authoritative thereafter. Renderers display stored values; compliance evaluates against them; a future recommendations face will project from them. No re-derivation at render time.

### Catalog-vs-code boundary

The vocabulary supports a defined set of primitives in CEL expressions:

- Field-level transforms: `parse_number`, `parse_percent`, `strip_html`, lookup against a named table.
- Aggregations over named windows: `sum`, `count`, `avg`, `min`, `max`, `latest` over the section's `records`.
- Threshold predicates and comparisons.
- Lookup tables (e.g. LicUsageType integer → unit string) declared at the catalog level and referenced by CEL `lookup(table, key)`.

Anything that falls outside these primitives — multi-step state machines, network calls, per-customer dynamic computation, branching logic per row beyond conditional expressions — requires Python code. When implementation hits a case the primitives cannot express, the implementer **stops and the boundary returns to the steering chat for review**. No unilateral extension of the catalog vocabulary or the primitive set.

This rule is identical in shape to ADR 0003's STOP triggers, and exists for the same reason: every time the catalog model has been extended unilaterally during implementation, it has bitten us. The primitive set in ADR 0004 is deliberately broad enough to handle every derivation the survey identified; the stop rule exists for the cases the survey didn't.

### The evaluative face — three vendor-compliance shapes

The survey corpus established that Commvault expresses compliance in at least three structurally different shapes. ADR 0004's evaluative face supports all three:

**Shape 1: per-row severity codes.** Each row in the dataset carries a severity field with values like `1_Good / 2_Info / 3_Warning / 4_Critical`. Security Assessment uses this shape. The catalog row declares:

```yaml
evaluative:
  severity_source:
    kind: vendor_field
    field: vendor_status
    mapping:
      "1_Good": good
      "2_Info": info
      "3_Warning": warning
      "4_Critical": critical
```

**Shape 2: separate StatusRow with thresholds.** A separate dataset declares thresholds with templated good/warn/critical text; the metric dataset carries the measured values; the runtime joins them. Disk Library Growth uses this shape. The catalog row declares:

```yaml
evaluative:
  severity_source:
    kind: status_row
    threshold_source:
      dataset_name: StatusRow
      good_text_field: GoodText
      warn_text_field: WarnText
      critical_text_field: CriticalText
      warn_threshold_field: Warning
      critical_threshold_field: Critical
      threshold_label_field: Threshold
    metric_field: estimated_days_to_full
```

**Shape 3: per-row threshold inline with metric.** Each row carries both its measured value and the threshold it must meet. SLA reports use this shape. The catalog row declares:

```yaml
evaluative:
  severity_source:
    kind: inline_threshold
    metric_field: met_sla_perc
    threshold_field: threshold
    comparison: ">="
```

Each shape produces a severity per row (`good`, `info`, `warning`, `critical`, or `muted`). The three shapes are first-class enumerated variants in the catalog; the evaluator dispatches on the variant.

### Rules layering — vendor, template, override

Three layers of rules apply in order. Each later layer can modify, add, or override the previous.

**Layer 1: vendor.** Whatever the vendor severity-source produces. Always runs if declared.

**Layer 2: template default.** Rules attached to the subject template. Apply universally across all reports that use this template version.

**Layer 3: per-report override.** Rules attached to a specific report's use of this subject. Apply only within that report.

Rules within a layer are evaluated in catalog declaration order. Within a layer, if multiple rules fire on the same row, the highest severity wins. Across layers, the later layer wins for the same `rule_id`. A rule may set severity to `muted` to suppress a verdict from a previous layer (e.g. "we don't care about vendor's critical here for this customer").

Rules are **referenceable, not inlined.** A named rule lives once in a rules registry; templates and report-level overrides reference rules by id. The same rule definition can attach to multiple sections or subjects. Inlining a rule per template (the alternative) was rejected on the grounds we just lived through with dataset GUIDs: inlined catalog data ages badly and scales poorly.

Each finding or section verdict in the resulting artifact carries:

```yaml
severity: critical
verdict_chain:
  - layer: vendor
    severity: info
  - layer: template_default
    rule_id: yoy_critical_decline
    severity: critical
    reason: "Year-over-year decline >25%"
```

The chain records the full provenance of the verdict — every layer that fired, in order, with the rule that produced each verdict. Auditable, debuggable, and consumed by the workspace UI to show "verdict was set by rule X" tooltips.

Severity enumeration: `critical`, `warning`, `info`, `good`, `muted`. `muted` is the explicit suppression severity used by overrides to neutralize a previous layer's verdict without lying about the underlying value.

### Conformance failures and the AI-rebuild bridge

Conformance is checked per section at collection time. When incoming data fails conformance (missing required fields, type mismatches, unknown enum values, cardinality mismatches), **the failing section is marked as failed; other sections in the same subject continue to collect and render normally**. The artifact carries a structured failure record for the failed section.

The failure record contains:

```yaml
conformance_failure:
  reason: missing_required_field
  expected: {fields: [JobId, ClientName, Status, StartTime]}
  actual: {fields: [JobStatus, JobId, SizeofApplication, ...]}
  delta:
    missing: [ClientName, Status, StartTime]
    unexpected: [JobStatus, SizeofApplication, EstimatedMediaSize, ...]
  hint: "Schema appears to have drifted from the template's declaration."
```

This shape is consumed by a successor ADR (the AI authoring loop) to drive a "rebuild this subject with AI" action. When the workspace shows a conformance-failed section, it offers: *"This section's data has drifted from the template. Rebuild with AI?"* — and the structured delta is what the AI consumes to propose an updated template that lands as the next version of the subject.

ADR 0004 does not implement the AI rebuild flow. It implements the conformance check, the failure-record emission, and the section-grained failure handling. The structured-delta shape is fixed in ADR 0004 so the successor ADR can consume it without coordinating shape changes later.

### Subject versioning

Templates evolve. When a subject's template changes — whether through AI rebuild after conformance drift, or manual evolution — the new template lands as a **new subject with a version suffix**: `capacity_license_v2`, `license_summary_v3`. The previous version remains as its own subject row with its own artifacts. No migration, no version field in the schema, no resolution logic.

Conventions:

- v1 is implicit. The first version of a subject has no suffix: `capacity_license`.
- v2 and later are explicit: `capacity_license_v2`, `capacity_license_v3`.
- The "family" of a subject is derived by stripping the suffix. `capacity_license` and `capacity_license_v2` both belong to family `capacity_license`.
- The catalog's uniqueness constraint is on `subject_id` (unchanged). Two versions are simply two distinct rows.

Each artifact records the `template_version` it was collected under. The data source tile in the workspace displays:

```
DATA SOURCE
Endpoint:        GET /commandcenter/api/CommServ
Host:            cs01
Last collected:  2026-05-28 14:23 UTC
Template:        capacity_license_v2  [version dropdown ▼]
```

The version dropdown lists all versions in the subject's family. Changing the selection determines which template the *next* collection uses. Existing artifacts remain tagged with whatever version they were collected under; their data and rendering are unaffected.

When v2 supersedes v1 because of conformance drift, both subjects continue to exist. v1's next collection attempt will fail loudly (its template no longer matches reality, which is correct). Existing v1 artifacts continue to render. The consultant picks via the dropdown when to move forward.

### Provenance and freshness

Every artifact carries provenance fields recorded at collection time:

- `template_version` — the subject_id under which the collection ran (e.g. `capacity_license` or `capacity_license_v2`).
- `collected_at` — UTC timestamp of collection.
- `source` — endpoint, host, and authentication context (already present, formalized here).
- `commcell_id`, `commcell_name` — from the customer row (already present from ADR 0003 phase 3).

Freshness is a property of the artifact, displayed by the source tile, and **available to rules as a CEL expression**:

```
duration_since(collected_at) > duration("7d")
```

A template-default rule "warn if data older than 7 days" is expressed in the evaluative face using the same machinery as any other rule. Freshness is not a fourth face; it's an inherent provenance field that rules can read.

The CommCell server version (e.g. `11 SP40.47`) is **not** displayed on the source tile. It's a property of the deployment, not of this collection. It belongs on a customer or CommCell page if anywhere.

### Migration of the three regressed subjects

ADR 0004's validation is the restoration of rich presentation and the addition of compliance to the three regressed subjects, using the three-face vocabulary end to end.

**Capacity Licenses** gets two sections rebuilt: a `metric` section computing `utilisation_pct` from used and purchased capacity via CEL, with template-default rules `warn at 70%, critical at 90%`; and the existing `table` section restored with clean column names via `column_map`. Sentinel handling for `-1` ("license not active that month") is declared in the semantic face. The chart that the legacy builder computed and never emitted becomes a `chart` section, driven from the same records.

**Client Growth** gets three sections: a `metric` section with `total_clients`, `latest_added`, and `yoy_pct` derived via CEL; a `chart` section showing the 12-month trend; and a `table` section with clean column names. Template-default rules warn on year-over-year decline.

**Backup Job Summary** gets four sections matching the legacy builder's presentation: a `metric` section with totals; a `card`-shaped status breakdown (or a small categorical structure to be confirmed during implementation); a `findings` section for recent failures; and a `table` section for recent jobs.

For each subject, after ADR 0004 implementation lands, the workspace UI renders these subjects equivalently to or richer than the pre-ADR-0003 legacy builder, with compliance rules firing where applicable, and the source tile shows the cleaned provenance. The three regressions are not just patched — they are validated against the new vocabulary, with compliance proving the evaluative face works end to end.

### What this ADR explicitly does not do

- **License Summary migration.** LS's structural gaps (page-aware GUIDs, cross-dataset parameter substitution, per-row value formulas, multi-page structure) are unchanged by the three-face vocabulary. They remain documented in HANDOVER as future-expansion work. LS keeps its bespoke path.
- **AI authoring loop.** ADR 0005 (or later) builds the AI-proposes-subject flow that consumes the vocabulary, including the AI-rebuild path triggered by conformance failure. ADR 0004 emits the records that flow will consume; it does not implement the flow.
- **Recommendations / predictive face.** Deferred. The `recommendation_hook` field on rules is reserved but unused by ADR 0004.
- **Cross-CommCell report identification.** HANDOVER backlog #23 documents that numeric report IDs are not portable. ADR 0004 acknowledges this but does not solve it — subject catalog rows continue to reference report IDs as today. Solving it likely requires a separate ADR on cross-deployment subject portability.
- **Implementation phases.** Phase planning happens as a follow-on, not in the ADR. The expected shape (vocabulary plumbing, section types one by one, the three regressions, evaluative face, conformance) implies six to eight phases, but the slicing is decided as the work progresses.

## Consequences

**Positive.** Data becomes self-describing across the three faces. The renderer becomes dumb and consumes metadata. The same vocabulary serves rendering, evaluation, and (in the successor ADR) AI authoring. Charts, summaries, and multi-section structures rejoin the system as first-class catalog-driven shapes. Compliance becomes a real product feature, not a Security-Assessment-only quirk. Rule layering with vendor / template / override gives consultants a clean mental model for customizing engagements. Conformance failures fail loudly and produce structured records the AI flow can act on. Versioning lets templates evolve without breaking historical artifacts. The catalog vocabulary's primitive set is bounded by an explicit stop-and-steer rule, preventing the unilateral-extension pattern that caused the ADR 0003 regressions.

**Negative.** ADR 0004 is the largest ADR the project has produced. Implementation is six to eight phases. The CEL dependency is real and the wrapper has to be built. Three vendor-compliance ingestion patterns each need their own evaluator code path. Subject versioning adds UI work for the version dropdown and a small amount of artifact-shape work for the `template_version` field. The three regressed subjects' artifacts on disk will be wiped per the established rule and re-collected, costing a small amount of dev-only data and one round of manual workspace verification per subject.

**Risks.** The largest is implementation drift from the survey's findings. The survey identified roughly thirty gaps; ADR 0004 addresses the load-bearing ones. As implementation proceeds, smaller gaps may surface that the survey caught and the ADR text did not pull through fully. The stop-and-steer rule and the section-grained conformance failure model are both designed to surface this loudly when it happens. If the rule fires unusually often during implementation, that itself is a signal that the survey's coverage was thinner than expected and the ADR may need amending.

A second risk: the supplementary captures established three vendor-compliance shapes but evidence for shape 2 (StatusRow) and shape 3 (inline threshold) is single-instance each. If future captures reveal a Commvault report using a *fourth* shape, the evaluative face needs extension. The vocabulary is designed extensibly, but the implementation cost would be real.

A third risk: CEL is a deliberate choice over simpler alternatives. If catalog authoring proves frustrating in practice — consultants struggling to write CEL expressions for derivations — we may need to reconsider. The mitigation is that derivations are expected to be authored by AI (in the successor ADR) more often than by hand, and AI is well-suited to CEL.

## Open questions

A small set of questions are deliberately left for implementation. They are not architectural; their answers don't change ADR 0004's shape, but they do need to be settled as the work proceeds.

- The exact CEL Python library to adopt (`cel-python`, `celpy`, or another). Trade-offs in maturity, performance, and API ergonomics; investigated during the first implementation phase.
- The precise shape of the rules registry table. Whether rules live in a single global table or are namespaced per subject family.
- Whether the dropdown on the source tile should also support "create new version" as an action, or only select among existing versions. Lean toward select-only; new-version creation routes through AI rebuild in the successor ADR.
- Whether `multi_section` produces a single canonical artifact section with `sub_sections` field, or N separate canonical sections at the artifact level. The former is more faithful to the catalog declaration; the latter is closer to current rendering. Investigated during License Summary-relevant implementation work even though LS itself remains deferred.

## Pointers for implementation

- The three regressed subjects' legacy builders live in `src/cvhealthcheck/quickhc/subject_data_service.py` (`_build_capacity_license_subject`, `_build_client_growth_subject`, `_build_backup_job_summary_subject`). These contain the derivation logic that ADR 0004 reimplements in CEL.
- The canonical artifact model lives in `src/cvhealthcheck/artifacts/models.py`. ADR 0004 extends `SectionType`, the section models, and adds `template_version` to the artifact provenance.
- The catalog-driven REST extractor at `src/cvhealthcheck/extractors/rest.py` is the production-side consumer of the vocabulary; ADR 0004's section-type and conformance work hooks here.
- The workspace renderer dispatches in `src/cvhealthcheck/quickhc/canonical_view.py` (Python) and `src/cvhealthcheck/web/static/quick_hc.js` (JS). Both need extending to handle the full six section types and the structured conformance-failure record.
- The ADR 0004 survey at `docs/adr/0004-survey.md` is the evidence base. Implementation phases should consult its gap list and surprise list as the work proceeds.
- The pre-ADR cleanup landed three commits (`b871c46`, `4589409`, `0f939ae` plus pointer `1fe141c`). The vendor-stable key preservation and unsupported-section-type loud failure are already in place; ADR 0004 builds on them.
