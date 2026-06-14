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
  bespoke parser could not import. Proves declarative **extraction** of
  report-shaped data (recipe transform layer, compile gate, parity); it does NOT
  prove declarative **collection** — LS REST collect stays bespoke (see Strategic
  Inflection).

## Strategic Inflection (recorded 2026-06-14; scope-corrected)

LS proved **declarative EXTRACTION for report-shaped, already-obtained data** —
the **upload** path (file → recipe → canonical, **no bespoke parser**), live and
browser-verified on a workload-heavy export the bespoke parser could not import.

It did **NOT** prove (correcting an earlier overclaim that the platform was
"proven end-to-end"):

- **declarative COLLECTION** — how to call / page / auth / correlate / merge an
  API. LS's own REST collect remains **bespoke** (`collect_rest.py`, deliberately
  retained).
- **declarative extraction for NON-table REST shapes** (nested-by-key; typed-rows
  needing a pivot). The recipe model HAS the vocabulary (`rest` /
  `rest_command_center_api` / `reportsplus_dataset`: `root_key`, field dot-paths,
  `parameters`), but **no live subject has proven it end-to-end**, and the
  pivot/partition case is an open expressiveness question.

**The next architectural test is therefore NOT another report.** It is a
**REST-primary subject driven through `rest_command_center_api` /
`reportsplus_dataset` WITHOUT a bespoke adapter** — exercising both COLLECTION
and non-table EXTRACTION. Candidate probes, easiest-shape-first:

1. **CommCell Details** (single-object card) — simplest collection + shape.
2. then a **list / typed-row REST subject** (Capacity License / Backup Job
   Summary) — to stress the extraction model (pivot / partition).

The outcome determines **how much bespoke collector code is needed long-term** —
the most valuable open architectural question in cv-healthcheck. This is still a
**platform-capability test, not yet pure product development**: LS answered
"declarative extraction of report data — yes"; the open question is "declarative
*collection* + non-table extraction — how far?"

## Strategic Themes

The stable "why" behind the work.

- Database as single source of truth (zero-code report-type addition)
- Separation of collection / evaluation / reporting
- Evidence integrity & provenance
- Reports as read-only views over canonical subjects (ADR-0013)
- Source-agnostic extensibility
- Verify-first / curl-first engineering discipline

## Initiatives — Now

*Status: CLOSED (browser-verified 2026-06-14). The next read-only investigation is
the D4 bindings/profile-ownership boundary check.*

**Customer/Project Context Integrity — CLOSED.** Scoped reads/writes on the
ADR-0002 customer+project entities are enforced on **both** sides: writes via D5
(`require_active_context`); reads via the `allow_default=False` no-fallback path on
the live web reads (Quick HC workspace + canonical APIs) — a no-context read
renders an honest empty state, never the Default customer's data. The two-customer
lab (`test_customer_1`/HomeLab REST + `test_customer_2` import, both populated) ran
a read-only isolation audit (2026-06-14): **cross-isolation PASSED**. Browser
verify (2026-06-14) confirmed: no-context → empty; HomeLab selected → only HomeLab
data; TC2 selected → only TC2 data; a TC2 License Summary HTML import landed under
the active TC2 context (scoped to the selection, not the file). **D4 (report-profile
/ bindings ownership) is now UNBLOCKED.**

Deferred (named, NOT blocking): moving active context out of the Flask session
into `app.db` — the narrow read-fix proved sufficient without it; revisit if the
session-scoped context becomes limiting. Report-identity / dataset-GUID
portability (#34) rides with the REST-primary subject probe (see Strategic
Inflection), not here. ADR-0015 §119 cross-environment id-variance is a separate
template-portability question (needs a live two-environment collect).

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
- **Generic table renderer value coercion (cosmetic)** — some generic table-render paths display structured `{value, unit}` objects raw (e.g. `{'unit': None, 'value': 100}`, observed in License Summary capacity/license rendering). Follow-up: generic display coercion → user-facing scalar text; likely the generic complement to bespoke LS formatting. Does NOT block Context Integrity, D4, or isolation.
- **Fix-4 per-source CommCell identifier precision** — the guard false-mismatches when the CommServ endpoint reports internal `commCellId=2` vs a declared licensed CCID `337f` (different identifier namespaces, not wrong-customer data). Resolver must distinguish identifier type; backlog, not blocking. (See HANDOVER register + CHANGELOG 2026-06-14.)
