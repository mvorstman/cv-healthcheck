# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-26 (ADR 0002 phase 1 wrap-up)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** the phase 1 wrap-up commit (see `git log -1`)
**Test status:** 482 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — the design spec being implemented. Required reading.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Orthogonal to ADR 0002 but constrains what you can refactor.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives. Phase 1 changed the schema; the audit still describes the storage paths as of pre-phase-2 reality.

---

## What was just completed

**ADR 0002 phase 1 — schema and storage foundation.** Two code commits — `4c69034` (migration `0005_customer_project_finalization.sql`) and `75ba4b9` (snapshot test deletion) — plus this session's wrap-up commit. The database now has `customers` (extended), `projects`, and `finalizations` tables, plus an auto-seeded "Default" customer. **No application code uses any of this yet** — phase 2 plumbs the active project through `ArtifactStore`. Existing canonical artifacts at `data/catalog/artifacts/{license_summary,security_assessment,storage_utilization}/` were deleted (throwaway dev data per ADR 0002).

Test count 483 → 482 (-1 from the deleted `test_subject_initial_data_snapshot.py`). The snapshot test pinned the single-customer architecture being replaced; deleted intentionally per the phase 1 brief.

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**Phase 2 — `ArtifactStore` project-scoping.**

Spec: `docs/adr/0002-customer-and-project-entities.md` (Storage paths and Data model sections in particular). The schema is in place; phase 2's job is to make the write/read paths actually use it.

### What phase 2 needs to do

1. **Thread an "active project" through the request lifecycle.** The route → service → store path currently has no notion of which customer/project the user is working on. Phase 2 picks a mechanism (server-side session, cookie, URL-scoped — analogous to but separate from the `#subject=<id>` fragment) and wires it through. The ADR's "active project lives in the user's session" decision is the constraint; the implementation chooses the carrier.
2. **Extend `ArtifactStore`** (`src/cvhealthcheck/artifacts/store.py`) with a `project_context` parameter (or equivalent) on `save_artifact` and `load_latest_artifact`. New on-disk paths:
   - Working state: `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject_id>/<timestamp>.json` + `.../latest.json`
   - Finalized snapshots: `data/catalog/artifacts/<customer_id>/<project_id>/finalized/<N>/<subject_id>/...` (phase 5 writes here; phase 2 just defines the layout)
3. **Update every `ArtifactStore` caller** to pass the active project. From the audit, that's the SA/LS service persist paths, the SA REST collect path, `_unified_dispatcher_upload`, and `execute_approval` in MCP staging. Each call site needs the project context routed in.
4. **Provide a default project for the Default customer.** Phase 2 needs *some* project to write artifacts under. Two options:
   - Auto-create a "Default" project under the Default customer the first time an artifact is saved with no project context, and use it as the implicit working project.
   - Require an explicit project before any artifact write succeeds; surface this as an error in the UI (degrades the empty-state experience).
   The first option is friendlier to the dev-machine flow; the second is cleaner architecturally. Pick based on whether the UI for project creation is landing in phase 2 or phase 4.

### Constraints

- **Read paths matter too.** The audit (Section 3) maps every read path; each one needs to know which project's artifact to load. Don't only patch writes.
- **Source-building fork is orthogonal.** ADR 0001's `_legacy_builders` continue to serve system subjects. Phase 2 changes *where* the artifact comes from, not *how* the tile data is shaped.
- **`_legacy_loaders` reads `data/catalog/rest/commserv.json`, the legacy SA/LS stores, and `data/catalog/metrics/*.json`.** Those paths are unscoped today. Phase 2 needs a story for them: either project-scope them too, or accept that they remain global "commcell-level" reads while the canonical artifacts go project-scoped. The ADR doesn't dictate; phase 2 picks.
- **Option A invariant.** `load_active_security_assessment_artifact` / `load_active_license_summary_artifact` (the legacy fallback reads) still need to function. They can be project-scoped or left global; phase 2 picks.
- **Don't pre-empt phases 3-5.** Phase 3 = customer page, phase 4 = project page, phase 5 = finalize/reload. Phase 2 stays at the store layer.

### Priority-ordered backlog (everything else)

1. **Phase 3 — customer page** (after phase 2). List, create (manual + CommCell-discovery), edit.
2. **Phase 4 — project page**. List per customer, create, switch active, view finalization history.
3. **Phase 5 — finalize + reload**. Copy `working/` → `finalized/<N>/`, write a finalizations row, application-layer immutability invariant.
4. **ADR 0003 — REST extractor with credentials.** Follows ADR 0002 implementation. Will use the active project's storage path.
5. **AI import workstream — staging UI, compliance rules.**
6. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
7. **Legacy-store accumulation, orphaned SQLite registries, labreadiness consumer audit.** Audit Section 6 #2, #5, #6.

Smaller cleanups still on the list:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch` for consistency.
- Deeper README staleness in the SA section.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **The new schema exists but is unused by application code as of end of phase 1.** Reads against `customers`, `projects`, `finalizations` will return either the Default customer (one row) or empty. Writes through the existing route → service → store path still land at unscoped `data/catalog/artifacts/<subject_id>/latest.json`. Phase 2's job is to change that.
- **The "Default" customer is auto-created via migration.** `customer_id='default'`, `customer_name='Default'`. Future code can assume at least one customer always exists.
- **The snapshot test from session 3 is gone.** Don't try to update it or recreate it. Phase 2 onward exercises new paths through targeted tests as those paths come online.
- **`engagements` is empty, untouched.** Migration 0001 created the table; nothing inserts into it. Phase 2 doesn't need to touch it. Future cleanup can retire it.
- **`data/catalog/artifacts/` has been wiped on the dev machine.** The directory exists; subdirectories under it are gone. New artifacts will appear under the customer/project-scoped paths once phase 2 lands.
- **ADR 0002 is orthogonal to ADR 0001.** Don't touch `_legacy_builders` while implementing phase 2.
- **`data/app.db` is gitignored.** On a fresh clone, app startup runs migrations (now five files) and seeds the six system subjects + the Default customer.
- **Unified upload route is the sole upload path.** `POST /quick-hc/<subject_id>/import` handles everything. Subject-specific behavior lives in `upload_dispatch.py`. Phase 2 will need to plumb the active project through this path.
- **Subject-specific redirects carry `#subject=<id>` fragments** via `_workspace_redirect(subject_id)` in `quick_hc.py`. The active-project mechanism phase 2 introduces is separate; the two can coexist.
- **`/logout` is POST-only**. No CSRF middleware.
- **localStorage surface is currently two keys**: `quickhc-theme-v1`, `quickhc-state-v1`. Phase 2's active-project mechanism may add a third (or use a different carrier); flag the choice in the CHANGELOG.
- **`execute_approval()` requires an injected `store` in tests.** Pattern in `tests/test_core_solidity.py::test_execute_approval_artifact`. Phase 2 will need to extend the injection pattern to include a project context.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 482 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"      # expect: default | Default
sqlite3 data/app.db "SELECT COUNT(*) FROM projects;"                        # expect: 0
sqlite3 data/app.db "SELECT COUNT(*) FROM finalizations;"                   # expect: 0
sqlite3 data/app.db "SELECT migration_id FROM schema_migrations ORDER BY 1;" # expect 0001-0005
ls data/catalog/artifacts/                         # expect empty
ls docs/adr/                                       # expect 0001, 0002, README
```
