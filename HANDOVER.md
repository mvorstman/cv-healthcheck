# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (ADR 0002 phase 2 wrap-up)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** the phase 2 wrap-up commit (see `git log -1`)
**Test status:** 493 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — the design spec being implemented. Required reading.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Orthogonal to ADR 0002 but constrains what you can refactor.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives. Pre-phase-2 storage layout, still describes the legacy globally-scoped reads accurately.

---

## What was just completed

**ADR 0002 phase 2 — project-scoped storage + active-project session.** Four code commits (`d78e47c` Default project seed, `119e360` active-project helper, `f5c5946` ArtifactStore project-scoping, `a16942c` acceptance tests) plus this session's wrap-up commit. The workspace now reads/writes artifacts under `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject>/`, with the active project resolved from the Flask session (falling back to the Default project under the Default customer). The four module-level `_artifact_store` / `_canonical_store` singletons that pre-dated ADR 0002 are retired. Test count 482 → 493 (+6 active-project, +5 acceptance).

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**Phase 3 — customer page UI.**

Spec: `docs/adr/0002-customer-and-project-entities.md` (Identity and "UI shape" sections in particular). The schema is in place; phase 2 wired the active-project plumbing. Phase 3 builds the surface for managing customers.

### What phase 3 needs to do

1. **List customers.** A page that lists every customer in the catalog, with name, CommCell hostname, and whatever metadata makes them identifiable at a glance. The Default customer is one row; created customers are siblings.
2. **Create a customer (manual).** A form that accepts the ADR's required fields: name, CommCell ID, CommCell hostname, optional company GUID, free-form contact info and notes. Inserts into `customers` and is immediately visible in the list.
3. **Create a customer (CommCell-discovery).** A flow that takes CommCell credentials, authenticates against the CommCell, fetches identity fields (CommCell ID, version, hostname), and pre-populates the customer record. **Credentials are used once and discarded** per ADR 0002 — they are NOT stored. The existing CommCell login helper (see `auth/commvault_auth.py` and the `scripts/probe_*` scripts) is the starting point.
4. **Edit a customer.** Update the rich-config fields. The Default customer's record can be renamed; PK `customer_id='default'` should remain stable so existing project references don't break.
5. **Customer switcher in the nav.** A UI affordance for switching the active customer. This is the customer-level half of the active-project mechanism phase 2 introduced; the project-level switcher is phase 4.

### Constraints

- **Phase 3 does not introduce projects UI.** That's phase 4. The active project remains the customer's Default project until phase 4 ships project creation + switching.
- **Phase 3 does not touch the artifact storage paths.** Those are stable from phase 2.
- **Credentials policy.** CommCell credentials supplied for discovery are used exactly once. Don't persist them in the customer record, the session, or anywhere on disk. If discovery fails, the form falls back to manual entry — don't preserve the partial credential state.
- **Don't pre-empt phases 4-5.** No project creation, no finalize/reload.
- **Source-building fork is orthogonal.** ADR 0001's `_legacy_builders` continue to read globally-scoped legacy on-disk files; the customer/project work doesn't change those.

### Suggested first slice

If the session has appetite for less than the full phase 3 scope, "list customers + create customer (manual)" is the smallest demoable cut. Discovery and edit can follow.

### Priority-ordered backlog (everything else)

1. **Phase 4 — project page** (after phase 3). List per customer, create, switch active, view finalization history.
2. **Phase 5 — finalize + reload**. Copy `working/` → `finalized/<N>/`, write a finalizations row, application-layer immutability invariant.
3. **ADR 0003 — REST extractor with credentials.** Follows ADR 0002 implementation. Will use the active project's storage path.
4. **AI import workstream — staging UI, compliance rules.**
5. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). They're globally scoped today, used as the Option A read fallback. Eventually they need to live under a project too — out of phase 3 scope, not urgent.
6. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
7. **Legacy-store accumulation, orphaned SQLite registries, labreadiness consumer audit.** Audit Section 6 #2, #5, #6.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **ArtifactStore now requires customer_id and project_id at construction.** Production callers use `make_active_project_store()` from `src/cvhealthcheck/web/active_project.py` (request-context callers) or `make_default_project_store(db)` (non-request: MCP, CLI). Tests construct directly with explicit IDs.
- **The Default customer + Default project under it is the fallback** when no active project is set in the session. Phase 3 must let the user pick a different active *customer*; phase 4 will let them pick a different active *project*.
- **Session key for active project is `session['active_project']`** as a dict `{'customer_id': ..., 'project_id': ...}`. Don't collide with this namespace.
- **The retired module-level singletons** (`_artifact_store`, `_canonical_store`, `_store`) are now functions of the same name in their respective modules. Tests that historically monkeypatched the attribute as an ArtifactStore instance now monkeypatch as a callable (`lambda: store`). Or, simpler, monkeypatch `make_active_project_store` / `make_default_project_store` themselves.
- **Legacy globally-scoped reads stay global per ADR 0001.** `commserv.json`, `metrics/*.json`, `backup_job_summary_latest.json`, the legacy SA/LS stores. Phase 3 does not move these.
- **`data/app.db` is gitignored.** Migrations seed the six system subjects, one Default customer, one Default project. Phase 3 should be testable on a fresh clone.
- **Unified upload route** still goes through `upload_dispatch.py`. Phase 2's project-scoping flows into it transparently via the helper.
- **Subject-specific redirects carry `#subject=<id>` fragments** via `_workspace_redirect(subject_id)`. The active-project mechanism is separate from this fragment.
- **`/logout` is POST-only**. No CSRF middleware.
- **localStorage surface is still two keys**: `quickhc-theme-v1`, `quickhc-state-v1`. Phase 2's active-project state lives in the Flask session, not localStorage — keep it that way.
- **`execute_approval()` accepts an injected `store`.** Production paths get the Default project's store; tests inject fakes. The injection signature didn't change in phase 2.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 493 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"           # expect: default | Default
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT migration_id FROM schema_migrations ORDER BY 1;"     # expect 0001-0005
ls data/catalog/artifacts/                         # may be empty or hold one or more <customer_id>/<project_id>/working/ trees
ls docs/adr/                                       # expect 0001, 0002, README
```
