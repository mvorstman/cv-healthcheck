# Roadmap

## Vision

The database-driven platform for Commvault operational health assessment & reporting: adding a new report type requires zero code — all subjects, sections, extraction, and compliance rules live in the database. Collect from any source (REST/HTML/CSV/JSON), normalize to canonical artifacts, evaluate against rules and live baselines, and compose customer-facing reports.

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

- **Rules & Evaluation maturity** — summary-scope evaluation; display coercions (byte/bool).
- **Quick HC canonical pipeline completion** — renderer orchestration; retire the legacy subject-shaping fallback once canonical parity is proven; the Security Assessment source-precedence fix.

## Initiatives — Next

*Status: Planned.*

- **Report Output framework** — docx/PDF composition and report profiles; de-bespoke the renderer-to-builder mapping.
- **Subject Inventory convergence** — migrate the system subjects into the database Report Inventory as seed data; grow subject coverage via MCP.

## Initiatives — Later

*Status: Proposed.*

- **Version Intelligence** — live Commvault release / maintenance-release / advisory baseline matching (builds on the shipped version-compare primitive).
- **Distributed Collection & Operating Modes** — Daily Reporting and Full HealthCheck modes; customer-side REST collectors → S3 evidence store → central analysis.
- **Evidence Confidence scoring** — source-quality/freshness weighting (the provenance metadata is already in place).
- **Report-Definition (XML) parser** — a generic Commvault report-definition parser.
- **Trend Analytics & Production Dashboard.**

## Sequencing & Dependencies

Platform Foundation [done] → Data Collection [done] → Rules/Evaluation [in progress] → Reporting → Analytics.

Cross-cutting: the version-compare primitive (done, ADR-0011) gates Version Intelligence.

## Known Risks

- Evaluation logic currently couples into `result_to_artifact` — this will strain as the rules engine grows.
- The project/context boundary leaks into non-web layers.

## Deferred Work

- **Evaluation-boundary extraction** — recorded debt; deliberate, not a defect (full reasoning in CHANGELOG / the prior debt note). This is the planned extraction point before the health/rules engine grows materially.
- **Registry-concept consolidation.**
- **S3 collector code** — blocked-by-design until the source/collector contracts stabilize.
- **Multi-tenancy** — one CommCell per customer for v1.
