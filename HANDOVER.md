# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (init_db retirement interstitial)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `13c36ce` — init_db retirement wrap-up: CHANGELOG and HANDOVER updates
**Test status:** 503 passing

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

**Interstitial: retire `init_db()` and `schema.sql`.** One commit (`bd7b4a0`) plus this session's wrap-up. The `init_db()`/`schema.sql` bootstrap path was deleted in favour of `run_migrations()` as the sole entry. Phases 2 and 3 had both surfaced the same footgun (tests using `init_db` got a schema frozen at migration 0001 and broke when later migrations added tables/columns). This commit removes the foot — including the five `test_init_db_*` tests that exercised `init_db` itself (now redundant; covered by `tests/test_migrations.py`). Test count 508 → 503 (-5).

Prior recent work — **ADR 0002 phase 3 (customer page UI)** — landed in commits `226c1ab` / `9858bcc` / `b8877f4` / `e22da6f` / `ae8bc27`. Customers are now manageable through the web UI: list at `/customers`, create at `/customers/new`, edit at `/customers/<id>/edit`, delete at `/customers/<id>/delete`. Manual entry only — CommCell-discovery is deferred.

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**Phase 4 — project page UI + active project switcher.**

Spec: `docs/adr/0002-customer-and-project-entities.md` (Lifecycle and "UI shape" sections). The customer surface is in place; the missing piece is the project layer that sits underneath each customer.

### What phase 4 needs to do

1. **List projects per customer.** Likely surfaced from the customer detail page or as a nested route (`/customers/<id>/projects` or `/projects?customer_id=<id>`). Shows project_number, ticket_reference, assigned_consultant, created_at, working_state_modified_at, and finalization count for each project.
2. **Create a project under a customer.** Form fields per ADR 0002: project_number (required, unique within customer per the migration's UNIQUE constraint), ticket_reference (optional), assigned_consultant (optional). Inserts a row into `projects`.
3. **Switch the active project.** A UI affordance for changing which (customer, project) pair the workspace operates against. Wires through to `set_active_project(customer_id, project_id)` from `src/cvhealthcheck/web/active_project.py` (already in place from phase 2).
4. **Delete a project.** Strict guard mirroring the customer-delete pattern: a project with finalizations cannot be deleted from the UI — it would erase the audit trail. (Phase 5 introduces finalizations; until then, all projects are finalization-free and deletable.)
5. **View finalization history (read-only placeholder).** Phase 5 lands the finalize action; phase 4 should leave a clear hook for displaying a project's finalizations list. An empty list with "No finalizations yet" suffices for v1.

### Constraints

- **No finalize or reload UI.** That's phase 5. Phase 4 reads the empty `finalizations` table but doesn't write to it.
- **The active-customer concept.** Phase 3 wired the customer surface; phase 2 wired the `(customer_id, project_id)` session key. Phase 4 chooses how the user picks an *active customer* in the nav (or whether the active customer is implicit from the active project). The simplest design: switch the active project, and the customer is read from the project's row. The brief doesn't dictate; phase 4 picks.
- **Default-project protection.** Same as Default-customer: not specially protected, but can't be deleted while it has finalizations (when phase 5 lands).
- **Source-building fork unchanged.** ADR 0001 `_legacy_builders` continue to serve their subjects globally.

### Suggested first slice

"List projects per customer + create a project + switch active to a project" is the smallest demoable cut. Delete and finalization-list display can follow within phase 4.

### Priority-ordered backlog (everything else)

1. **Phase 5 — finalize + reload.** Copy `working/` → `finalized/<N>/`, write a `finalizations` row, application-layer immutability invariant. Closes out ADR 0002.
2. **ADR 0003 — REST extractor with credentials.** Follows ADR 0002 implementation. Will use the active project's storage path.
3. **CommCell-discovery flow for customer creation.** Convenience feature. Authenticate against a CommCell with provided credentials, populate identity fields, user reviews and saves. Shares plumbing with ADR 0003's REST extractor.
4. **Report-provenance verification.** When a user imports an HTML or CSV report, check that the report's embedded CommCell identity matches the active customer's stored CommCell identity. Catches "wrong customer's report uploaded by accident" mistakes.
5. **Left-nav structural review.** The sidebar has accumulated items (Overview, Reports, Customers, Settings, Staging, plus SUBJECTS). At some point grouping or visual hierarchy will help. Not urgent.
6. **AI import workstream — staging UI, compliance rules.**
7. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). Globally scoped today.
8. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
9. **Legacy-store accumulation, orphaned SQLite registries, labreadiness consumer audit.** Audit Section 6 #2, #5, #6.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **Customer CRUD is in place.** The `customers` table is user-managed via the UI under `/customers`. Routes live in `src/cvhealthcheck/web/routes/customers.py`. Templates: `customers_list.html`, `customer_form.html` (shared create/edit), `customer_delete.html`.
- **CommCell-discovery (auto-populating customer fields from a CommCell login) is deferred.** When implemented, it will be an addition to the existing customer form, not a replacement. The form has fields for `commcell_id`, `commcell_hostname`, `company_guid` — discovery would fill these.
- **Customer ID slug convention.** Lowercase, alphanumeric joined by underscores, collision-disambiguated with `_2`/`_3`/... See `_slugify_customer_id` in `routes/customers.py`. The migration-seeded `default` matches this convention.
- **Strict deletion guard.** A customer with projects can't be deleted. Same will apply to projects with finalizations in phase 5. Defense in depth: server-side re-check on POST returns 400 if the count is non-zero.
- **Default customer/project are not specially protected.** They can be deleted like any other once their dependents are removed.
- **Active project state.** Lives in the Flask session as `session['active_project'] = {'customer_id': ..., 'project_id': ...}`. Phase 4's project switcher writes here; ArtifactStore reads through it via `make_active_project_store()`.
- **`init_db()` and `schema.sql` are gone.** `run_migrations()` is the sole database-bootstrap path. Tests use the `migrated_db_path` fixture (or call `run_migrations(db_path=...)` directly).
- **Subject-specific redirects carry `#subject=<id>` fragments** via `_workspace_redirect(subject_id)`. The active-project mechanism is separate from the fragment.
- **localStorage surface is still two keys** (`quickhc-theme-v1`, `quickhc-state-v1`). Phase 3 did not add a third — the active-customer/active-project state lives in the Flask session, not localStorage.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 503 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT migration_id FROM schema_migrations ORDER BY 1;"     # expect 0001-0005
curl -s http://127.0.0.1:5001/customers | head -10  # if dev server is up
ls docs/adr/                                       # expect 0001, 0002, README
```
