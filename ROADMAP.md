# Roadmap

## Vision

The database-driven platform for Commvault operational health assessment and reporting.

The database is the primary source of truth for subject definitions, extraction instructions, report definitions, and evaluation rules.

New report types should be added through authoring rather than software development wherever practical.

The platform collects from multiple sources, normalizes to canonical artifacts, evaluates against rules and baselines, and composes customer-facing reports as read-only views over canonical subjects.

## Current State

Capability terms, not a feature log — the per-task history lives in `CHANGELOG.md`.

- Source-agnostic collection (REST/HTML/CSV/JSON) → canonical artifact model — proven
- Catalog-driven subject inventory; new subjects added via MCP without code
- Row-scope rules engine with version-aware comparison; live evaluation on `/quick-hc`
- Persistent artifact registry; customer/project scoping; application state in `app.db`
- Quick HC report-composition surface

## Strategic Themes

The stable "why" behind the work.

- Database as single source of truth (zero-code report-type addition)
- Separation of collection / evaluation / reporting
- Evidence integrity & provenance
- Reports as read-only views over canonical subjects (ADR-0013)
- Source-agnostic extensibility
- Verify-first / curl-first engineering discipline

## Initiatives — Now

*Status: In Progress.*

- **Customer/Project Context Isolation** — gating report-correctness item; precedes the Report Output framework (Next).
  - *Goal:* report generation never mixes data between customers or projects.
  - *Success:* every artifact read, write, report render, upload/import, evaluation, and composition selection is explicitly scoped to one (customer, project) or explicitly global by design; no cross-customer read fallback; environment/CommCell evidence is scoped, not a global single file; report-composition selections are scoped; operating on customer data requires an explicit active context (or "Default" is an unmistakable single-tenant lab mode).
- **Rules & Evaluation maturity**
  - *Goal:* increase rule expressiveness and consistency across all canonical section types.
  - *Success:* Rules can be authored, versioned, bound, evaluated, and surfaced without code changes. Evaluation supports row-scope and summary-scope rules across all canonical section types.
- **Quick HC canonical pipeline completion**
  - *Goal:* a single canonical render path across REST/HTML/CSV, with the legacy subject-shaping fallback retired once parity is validated.
- **Domain Labels** (catalog classification) — **v1 complete** (schema · MCP read · MCP author · sparse backfill; ADR-0012). The additive label axis alongside the single-valued `category` is in place; the first downstream consumer (report profiles / health domains / rule packs reading the labels) is future work.

## Initiatives — Next

*Status: Planned.*

- **Report Output framework** — docx/PDF composition and report profiles.
  - *Depends on:* Customer/Project Context Isolation (Now) — thin Report Profiles and docx/PDF output do not proceed until the HIGH cross-customer risks are closed.
  - *Direction:* ADR-0013 governs this work: canonical subjects are the foundation; reports are read-only views; canonical artifacts are never mutated by report/customer overrides.
  - *First slice:* introduce only a thin Report Profile view contract — selected subjects, selected sections, and view mode. Do not build full profile persistence/schema, contextual evaluation, health-domain consumers, or compliance profiles in this slice.
  - *Success:* Customer reports can be generated entirely from canonical artifacts and thin report definitions without subject-specific report builders, without rewriting verdicts, provenance, source metadata, or canonical artifact data.
- **Subject Inventory convergence** — migrate the system subjects into the database Report Inventory as seed data; grow subject coverage via MCP.
  - *Success:* A new report type can be added through catalog/MCP authoring without Python code changes. System subjects are represented in the same inventory model as user-authored subjects.

## Initiatives — Later

*Status: Proposed.*

- **Version Intelligence** — live Commvault release / maintenance-release / advisory baseline matching (builds on the shipped version-compare primitive).
- **Contextual Evaluation** — advisory, lifecycle, supportability, policy, and compliance-profile evaluation outside canonical artifacts; deferred until an explicit evaluation context is designed.
- **Health Domains and Compliance Profiles** — consumers over subjects / labels / evaluations, including possible NIS2 mapping; deferred until there is a second genuinely different report/profile need.
- **Distributed Collection & Operating Modes** — Daily Reporting and Full HealthCheck modes; customer-side REST collectors → S3 evidence store → central analysis.
- **Evidence Confidence scoring** — source-quality/freshness weighting (the provenance metadata is already in place).
- **Report-Definition (XML) parser** — a generic Commvault report-definition parser.
- **Trend Analytics & Production Dashboard.**

## Sequencing & Dependencies

Platform Foundation [done] → Data Collection [done] → Rules/Evaluation [in progress] → Reporting → Analytics.

- Reporting depends on stable evaluation outputs, so Rules/Evaluation precedes Reporting.
- Reporting must not mix customer/project data, so Customer/Project Context Isolation (Now) precedes the Report Output framework.
- The first Reporting slice is intentionally thin under ADR-0013: view selection over canonical subjects first; contextual evaluation, Health Domains, and compliance profiles later.
- Analytics depends on accumulated historical reporting data, so Reporting precedes Analytics.
- Cross-cutting: the version-compare primitive (shipped, ADR-0011) gates Version Intelligence.

## Known Risks

Genuine forward uncertainties.

- Version Intelligence depends on an external Commvault release/advisory data source whose format and access may change.
- Distributed collection (customer-side collectors → S3) may introduce tenant-isolation and evidence-integrity complexity.

## Known Architectural Debt

Deferred, deliberate — not defects.

- Evaluation logic currently couples into the artifact-construction stage; extract a separate evaluation stage before the rules engine grows materially.
- Project-context boundary leaks into non-web layers; introduce a non-web project/context service.
- Registry-concept consolidation.

## Deferred Work

- **S3 collector code** — blocked-by-design until the source/collector contracts stabilize.
- **Multi-tenancy** — one CommCell per customer for v1.
- **Full report-profile persistence/schema** — deferred; first Report Profile is an in-memory/view contract only.
- **Contextual advisory/lifecycle engine** — deferred; it must not be hidden inside report composition.
- **Health Domain / compliance profile consumers** — deferred; Domain Labels exist, but the first consumer is not designed yet.
