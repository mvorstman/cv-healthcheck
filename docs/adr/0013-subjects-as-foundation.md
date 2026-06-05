# ADR-0013 — Subjects-as-foundation: canonical evidence, intrinsic vs contextual evaluation, and the three-level visibility taxonomy

**Status:** Accepted — 2026-06-05
**Supersedes:** none
**Related:** ADR-0004 (evaluative face / rule overrides); ADR-0009 (MCP-authored catalog sources / canonical artifacts); ADR-0010 (row-scope verdict engine — the intrinsic-evaluation mechanism); ADR-0011 (version operators; its live-baseline vision is the first concrete *contextual* evaluation); ADR-0012 (domain labels — a *candidate*, not chosen, grouping for contextual-evaluation consumers).

---

## Context

The Report Output framework is next on the ROADMAP, and it needs a foundation decision made before docx/PDF work starts. The tempting framing is "reports are the foundation, everything hangs off a report definition." That is backwards. The system already authors **subjects**, not reports (`propose_new_subject`), and a single subject (e.g. CommCell version) legitimately feeds many report types with different interpretations of the same evidence.

This ADR locks the foundation as **subjects + evidence + evaluations**, with reports as read-only views over that foundation. It deliberately locks **principles only**. The lower-layer machinery — relevance engines, broad presentation-policy engines, override editors, full profile persistence, and the choice of which downstream consumer owns contextual evaluation — is left unresolved on purpose, because there is currently only one report path in flight (Quick HC, and the Customer Report which is the same evidence viewed differently). Designing those layers now would be guessing at a second consumer that does not exist yet, which the project's workflow explicitly avoids.

Two distinctions surfaced during design that the naive model collapses and must not:

1. **Intrinsic vs contextual evaluation.** "Version parses correctly / is supported by the parser" is intrinsic — a property of the evidence at collection time. "Version is affected by an advisory / is out of support / maps to a NIS2 concern" is contextual — it depends on external knowledge that changes over time. If Commvault publishes an advisory tomorrow, the canonical artifact must not need re-collection to surface that risk. The live-baseline vision in ADR-0011 (evaluate against the *current recommended release*) is exactly this contextual case.

2. **Visibility is three states, not a boolean.** A single "hidden/shown" flag cannot express "suppressed by default but a customer override may resurface it" *and* "must never reach a customer." Collapsing these makes overrides dangerous: an override that can punch through a soft suppression must not be able to punch through raw API payloads.

## Decision

Lock the following principles. Everything not stated here is deliberately left open.

1. **Subjects are the primary unit of information.** The catalog authors subjects; reports are downstream.
2. **Reports consume subjects. Subjects do not know about reports.** A subject definition never references a report type.
3. **Canonical artifacts are immutable evidence.** Once canonicalized, an artifact is the trustworthy record of what was collected and what it intrinsically means.
4. **Customer/report overrides never modify canonical artifacts.** Overrides are report-instance configuration only (hide/show/include/exclude, ordering, view-mode choices). They select and present; they never rewrite evidence.
5. **Intrinsic evaluation is baked at canonicalization.** Verdicts and findings that are properties of the evidence itself live in the artifact, produced by the row-scope verdict engine (ADR-0010). There is no separate intrinsic-evaluation store. (This is the existing D5 discipline, restated as a foundation principle — not a new mechanism.)
6. **Contextual evaluation is computed outside the canonical artifact, and can change without re-collecting the subject.** Advisory / lifecycle / supportability / compliance-mapping verdicts depend on external knowledge that changes over time. The falsifiable property: if discovering a new advisory or baseline shift ever forces a re-collect, this boundary has been violated. The live-baseline feature (ADR-0011) is the first consumer of this seam. A future explicit evaluated-artifact context may be designed, but report composition must not smuggle contextual evaluation into presentation code.
7. **Visibility has three levels:** `REPORTABLE` (normally available), `HIDDEN` (suppressed by default, *may* be resurfaced by an override), `INTERNAL` (never customer-visible — raw payloads, matching confidence, API response detail; an override can never resurface it). This is a **taxonomy lock, not a tagging exercise** — see Consequences.
8. **Relevance, visibility, and evaluation are separate concepts.** Relevance decides whether a subject or section belongs in a view. Visibility decides whether selected evidence may be shown to a customer. Evaluation decides what the evidence means. Do not collapse these into a generic "filter."
9. **Report output consumes canonical artifacts; it does not reshape or rewrite them.** Composition reads evidence and applies presentation; it has no write path back into the artifact and does not rewrite verdicts, provenance, source metadata, or canonical data.
10. **The first Report Profile is a thin view contract only.** It may declare selected subjects, selected sections, and view mode. It does not own evaluation logic, does not persist as a full report-profile schema, and does not introduce a profile engine.

### Deliberately left unresolved

The **consumer of contextual evaluation is undefined.** Lifecycle, vendor-advisory, supportability, NIS2, CIS, and customer-specific-standard evaluations may each turn out to belong to Health Domains, to compliance profiles, or to report profiles — and they may not all belong to the same place. ADR-0012's domain `labels` are a **candidate** grouping seam, explicitly **not chosen here**. Principle 6 commits only to *where contextual evaluation does not live* (the artifact); it does not commit to where it does. That choice waits for a second genuinely different report type.

### Constraint on ADR-0004 overrides

ADR-0004's rule-overrides model remains valid for evaluation-layer work, but this ADR constrains how it may be used by report composition:

- Customer/report presentation overrides are presentation/config only.
- They must not rewrite canonical artifacts, verdicts, provenance, source metadata, or collected values.
- Policy-specific or contextual evaluation must not be hidden inside report composition. If policy-specific evaluation is needed, it must be designed as an explicit evaluation context or evaluated artifact, not as a report-rendering side effect.

## Consequences

- **Principle 7 is a taxonomy, not a migration.** No field is tagged with a visibility level now. Everything is implicitly `REPORTABLE` until a real report needs something suppressed; a field acquires `HIDDEN` or `INTERNAL` the moment a concrete report requires it. Tag on demand, never retroactively — otherwise "lock the taxonomy" silently becomes "annotate the entire catalog," which is exactly the machinery this ADR defers.
- **Principle 5 keeps D5 intact.** The "is baked" wording (not "may be stored") forecloses re-opening the question of a separate evaluation store.
- **Principle 6 gives a test, not just a slogan.** "No re-collect on advisory change" is checkable. It also means the contextual layer needs its own (later) trigger/refresh story, owned by whichever consumer is eventually chosen — not by collection.
- **The thin Report Profile is the only profile machinery approved now.** It is a view input to report composition: selected subjects, selected sections, and view mode. It is not persisted as a full schema and does not become an evaluation owner.
- **No second taxonomy.** Contextual-evaluation grouping is left to read ADR-0012's labels (or domains, or profiles) later; this ADR does not introduce a competing classification.
- **Terminology discipline carried forward:** "scope" stays reserved for evaluation (ADR-0010); "Health Domain" (a management-level grouping of evidence across subjects) is **not** the same axis as a "domain label" (ADR-0012's subject-classification value), and this ADR does not merge them.
- **No code, no schema, no migration in this ADR.** It is a foundation principle set that the Report Output framework must respect. The first thing it constrains: report output reads canonical artifacts read-only.

## Non-goals (this ADR)

The following are explicitly deferred:

- full report-profile persistence/schema
- Health Domain consumer
- compliance / NIS2 profile machinery
- contextual advisory / lifecycle engine
- customer override editor
- broad visibility annotation sweep
- recommendation generation
- PDF/docx polish
- License Summary generic extractor migration

Also deferred: relevance engine, broad presentation-policy engine, override engine, profile engine, the contextual-evaluation consumer choice (domains vs profiles vs report profiles), any visibility-level tagging of existing fields, and any schema or collector change. All deferred until at least two genuinely different report types force the design.

## Open questions (deferred — non-blocking)

- **Which consumer owns contextual evaluation** — domains, compliance profiles, report profiles, or a mix. Resolved when the second report type exists.
- **Whether `HIDDEN`/`INTERNAL` are carried per-field, per-section, or per-source** — decided when the first suppression is actually needed, not before.

## Acceptance (for the principle set)

This ADR is satisfied when the Report Output framework, as designed, demonstrably: (a) reads canonical artifacts without a write path back to them; (b) keeps any customer/report override as report-instance config, with no mutation of the artifact; (c) introduces no contextual evaluation into the canonical artifact; and (d) keeps the first Report Profile to selected subjects, selected sections, and view mode. No build step is required to *accept* the ADR; it is a constraint on the work that follows.
