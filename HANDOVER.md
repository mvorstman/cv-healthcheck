# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-26 (ADR 0002 wrap-up)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `40f0ef1` — ADR 0002 wrap-up: HANDOVER points at implementation
**Test status:** 483 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Required reading if your work touches source-building, the canonical schema, or the unified upload route.
5. **`docs/adr/0002-customer-and-project-entities.md`** — the design spec for the next session. Required reading before implementation.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives on disk and which code paths read/write each location. The current state ADR 0002 replaces.

---

## What was just completed

**ADR 0002 — Customer and Project as first-class entities.** Design spec for the consulting-workflow features that take cv-healthcheck from "one dev machine, one CommCell" to "multiple customers, multiple projects, audit-traceable finalizations." The ADR settles twelve sub-decisions (identity, lifecycle, immutability model, customer-creation paths, auto-created Default customer, reload semantics, active-project session concept, data model in prose, storage paths, out-of-scope clarifications). No code, no SQL DDL.

Prior recent work (full thread in `CHANGELOG.md`):

- Housekeeping (this 2026-05-26): `data/app.db` gitignored; README test count and URL table refreshed.
- Data flow audit at `docs/data_flow_audit.md`.
- Workspace position preservation across full-page reloads (client-side fragment + server-side fragment-carrying redirects).
- Source-provenance dispatch wiring SA/LS provenance builders back into the workspace tile path.
- Unified-upload refactor (sessions 1 → 5b): one `POST /quick-hc/<subject_id>/import` route, subject-specific behavior in `upload_dispatch.py`.

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**Implement ADR 0002 — Customer and Project entities.**

Spec: `docs/adr/0002-customer-and-project-entities.md`. The ADR is the contract; read it before opening any code.

### Suggested implementation slicing (the user picks the actual slicing)

The ADR groups its decisions in a way that maps naturally to sequential implementation slices. A possible ordering:

1. **Schema migration.** Add `customers`, `projects`, `finalizations` tables via a new migration file under `src/cvhealthcheck/db/migrations/`. Migrate or replace the existing `customers` and `engagements` tables — the implementer decides whether to coexist, rename, or delete-and-recreate based on what's in them today. Auto-create the "Default" customer in the same migration. The migration also deletes existing dev artifacts under `data/catalog/artifacts/` (per the ADR's "existing data not preserved" decision).
2. **ArtifactStore project-scoping.** Add a `project_context` parameter (or equivalent) to `ArtifactStore.save_artifact` and `load_latest_artifact`. The new paths are `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject_id>/...` and `data/catalog/artifacts/<customer_id>/<project_id>/finalized/<N>/<subject_id>/...`. The change is local to the store layer; the canonical schema and source-building paths don't move.
3. **Active-project session state.** Pick a mechanism (cookie, server-side session, URL fragment — analogous to but separate from the `#subject=<id>` fragment) and wire it through the routes that today assume a single global artifact.
4. **Customer page** — list, create (manual + CommCell-discovery), edit. Auto-create-Default on first run is already covered by the migration; this slice is the UI for managing customers afterward.
5. **Project page** — list per customer, create, switch active project, view finalization history.
6. **Finalize action** — copies `working/` to `finalized/<N>/` and writes a `finalizations` row. Application-layer immutability: the code path that writes to `finalized/<N>/` exists once (the finalize handler) and is never invoked from a write-mutation path.
7. **Reload-finalized-for-editing** — copies `finalized/<latest>/` back into `working/`, with the UI confirmation when working state isn't already clean.

The ADR doesn't require this ordering. A vertical slice (one customer, one project, one subject all the way through finalize/reload) might be a better first cut to land something demoable end-to-end before broadening.

### Constraints from the ADR

- **No code, no SQL DDL belongs in the ADR.** If something feels ADR-shaped and isn't in the doc, surface it for a follow-up ADR rather than smuggling it into implementation.
- **Don't pre-empt ADR 0003.** REST extractor with credentials is the *next* next session. It builds on ADR 0002's storage paths. Don't design the credentials flow as part of this implementation.
- **Existing dev artifacts are deleted by the migration.** Verify with the user before running it on any machine that holds non-throwaway data.
- **Application-layer immutability.** The code path that writes to a finalized snapshot directory exists exactly once. Every other write path goes to working state.

### Priority-ordered backlog (everything else)

1. **ADR 0003 — REST extractor with credentials.** The session after the ADR 0002 implementation. Will build on ADR 0002's storage paths.
2. **AI import workstream — staging UI for proposal review, compliance rules.** Larger scope; the ADR 0002 implementation may surface architectural choices that simplify this work.
3. **2026-05-20 review backlog.** Older items parked when the unified-upload refactor took over. Review what's still relevant.
4. **Workflow tooling decisions** parked earlier — exact list lives in the older HANDOVER chain.
5. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3: 203 raw extraction files today, no retention policy.
6. **`data/catalog/{security_assessment,license_summary}/` legacy-store accumulation.** Audit Section 6 #2.
7. **Two orphaned SQLite registries** at `data/imports/{security_assessment,license_summary}/artifact_registry.sqlite3`. Audit Section 6 #6.
8. **`data/labreadiness/latest.json` consumer audit.** Audit Section 6 #5.

Smaller opportunistic cleanups still on the list:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly delete the legacy `/security-assessment` development page in `web/routes/development.py` if nobody uses it.
- Consider moving the no-canonical-artifact path for SA/LS onto `source_provenance_dispatch` so workspace-tile source statuses are consistent across both data-present and data-absent paths.
- Deeper README staleness: the SA section's "Latest persisted multi-source artifacts" paths at L260-268 no longer match the canonical-store layout.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **ADR 0002 is the spec for the next session.** Read it before opening code.
- **ADR 0002 is orthogonal to ADR 0001.** The source-building fork stays; customer/project work changes *where* artifacts are stored, not *how* tile data is shaped.
- **`data/app.db` is gitignored.** On a fresh clone, app startup runs migrations and seeds the six system subjects from `0003_report_inventory.sql`. The ADR 0002 migration will add the customer/project/finalization tables and auto-create the Default customer.
- **Unified upload route is the sole upload path.** `POST /quick-hc/<subject_id>/import` handles everything. Subject-specific behavior lives in `src/cvhealthcheck/web/routes/upload_dispatch.py`. The ADR 0002 implementation will need to plumb the active project through this path.
- **Subject-specific source-provenance lives in `src/cvhealthcheck/quickhc/source_provenance_dispatch.py`** (sibling pattern). Will also need to read project-scoped artifacts.
- **Subject-specific redirects carry `#subject=<id>` fragments** via `_workspace_redirect(subject_id)` in `quick_hc.py`. The active-project mechanism ADR 0002 introduces is separate; don't confuse the two.
- **Snapshot test (`tests/test_subject_initial_data_snapshot.py`)** is the behavior-preservation pin. Run it whenever you touch source-building or view-producing code. Expect it to diff substantially during ADR 0002 implementation as artifact paths change; regenerate intentionally with a CHANGELOG note.
- **Legacy artifact READS preserved.** Option A invariant; reads through `load_active_security_assessment_artifact` / `load_active_license_summary_artifact` still alive. ADR 0002 doesn't change this; the project-scoping happens above the legacy-store fallback.
- **`/logout` is POST-only**. No CSRF middleware.
- **localStorage surface is exactly two keys**: `quickhc-theme-v1`, `quickhc-state-v1`. URL fragment (`#subject=<id>`) is separate. The active-project mechanism may add a third surface depending on implementation choice — flag any addition in the CHANGELOG.
- **`execute_approval()` requires an injected `store` in tests.** Pattern in `tests/test_core_solidity.py::test_execute_approval_artifact`.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 483 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT subject_id,created_by,status FROM subjects;"
ls docs/adr/                                       # expect 0001, 0002, README
ls docs/data_flow_audit.md                         # expect present
```
