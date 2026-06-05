# Roadmap

## Vision

The database-driven platform for Commvault operational health assessment and reporting.

The database is the primary source of truth for subject definitions, extraction instructions, report definitions, and evaluation rules.

New report types should be added through authoring rather than software development wherever practical.

The platform collects from multiple sources, normalizes to canonical artifacts, evaluates against rules and baselines, and composes customer-facing reports.

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
- Source-agnostic extensibility
- Verify-first / curl-first engineering discipline

## Initiatives — Now

*Status: In Progress.*

- **Rules & Evaluation maturity**
  - *Goal:* increase rule expressiveness and consistency across all canonical section types.
  - *Success:* Rules can be authored, versioned, bound, evaluated, and surfaced without code changes. Evaluation supports row-scope and summary-scope rules across all canonical section types.
- **Quick HC canonical pipeline completion**
  - *Goal:* a single canonical render path across REST/HTML/CSV, with the legacy subject-shaping fallback retired once parity is validated.

## Initiatives — Next

*Status: Planned.*

- **Report Output framework** — docx/PDF composition and report profiles.
  - *Success:* Customer reports can be generated entirely from canonical artifacts and report definitions without subject-specific report builders.
- **Subject Inventory convergence** — migrate the system subjects into the database Report Inventory as seed data; grow subject coverage via MCP.
  - *Success:* A new report type can be added through catalog/MCP authoring without Python code changes. System subjects are represented in the same inventory model as user-authored subjects.

## Initiatives — Later

*Status: Proposed.*

- **Version Intelligence** — live Commvault release / maintenance-release / advisory baseline matching (builds on the shipped version-compare primitive).
- **Distributed Collection & Operating Modes** — Daily Reporting and Full HealthCheck modes; customer-side REST collectors → S3 evidence store → central analysis.
- **Evidence Confidence scoring** — source-quality/freshness weighting (the provenance metadata is already in place).
- **Report-Definition (XML) parser** — a generic Commvault report-definition parser.
- **Trend Analytics & Production Dashboard.**

## Sequencing & Dependencies

Platform Foundation [done] → Data Collection [done] → Rules/Evaluation [in progress] → Reporting → Analytics.

- Reporting depends on stable evaluation outputs, so Rules/Evaluation precedes Reporting.
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
