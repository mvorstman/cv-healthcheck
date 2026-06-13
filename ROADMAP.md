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
- **License Summary CSV/HTML upload promoted to the generic declarative path
  (ADR-0017) — live, browser-verified** on a real workload-heavy export the
  bespoke parser could not import. First end-to-end de-bespoking of a real,
  structurally complex subject (recipe transform layer, compile gate, parity).

## Strategic Inflection (recorded 2026-06-14)

The platform is now **proven to represent a real, complex subject end-to-end** —
License Summary, fully declarative, live, and browser-verified (the
workload-heavy export the bespoke parser *could not* import succeeded via the
generic path). The question *"can the platform represent a real subject without
bespoke code?"* is answered: **yes**.

The next high-value move is therefore a **NEW SUBJECT on the proven foundation —
product development on the platform, not more platform-building** — rather than
further License-Summary edge-polish. The remaining LS work (REST-collect
migration) is a contained product decision, not a prerequisite for building new
subjects.

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

**Customer/Project Context Integrity (gating).** Enforce scoped
reads/writes/storage/reporting on the existing ADR-0002 customer+project
entities. First move active context out of the Flask session into app.db
(today `get_active_project` silently falls back to the Default customer's
earliest project when the session key is absent or there's no request
context — a wrong-customer hazard). Stand up the two-customer lab (one REST,
one JSON import with multiple report versions); run a read-only isolation
audit across collection/storage/evaluation/reporting before any fix. Couple
report-identity / dataset-GUID portability (#34) here.

## Initiatives — Next

*Status: Planned.*

- **Finish ADR-0004 phase 8** (Shapes + recommend stage) and ratify ADR-0004.
- **Build the thin Report Profile** (ADR-0013: selected subjects/sections/view-mode).
- **Report Output framework** — HTML master → PDF/DOCX via docxtpl+python-docx /
  WeasyPrint or LibreOffice; matplotlib on the shared severity palette.

## Initiatives — Later

*Status: Proposed.*

- **LS declarative conversion — CSV/HTML upload COMPLETE (ADR-0017).** Remaining
  LS work is the **REST-collect migration** (its own slice / product decision:
  migrate + prove a generic REST path, or retire LS REST-collect). LS REST collect
  is still bespoke and shares the retained `normalize`/`models`/adapter/`persist`/
  `collect_rest`; `import_html.py` is kept only as a parity/test reference.
- **#36 SA-module retirement** — still gated on the LS REST-collect migration: LS
  REST is structurally welded to the SA module (runs on the SA `ArtifactRegistry`
  alias; shares SA model classes), so the SA module can't be retired until LS REST
  is migrated or retired. The SA canonical read + SA upload are already generic.
- **Growth & Trends (report 318)** as the first composite-address subject.
- **Probe oversized-response handling** (1MB Desktop cap).
- **Set-CVJobRetention.ps1 un-retain opType capture.**
- **Health Domains, version intelligence, distributed/air-gapped collection.**

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
