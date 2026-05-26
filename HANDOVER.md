# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (ADR 0002 phase 4 wrap-up)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** the phase 4 wrap-up commit (see `git log -1`)
**Test status:** 527 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — the design spec being implemented. Required reading.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Orthogonal to ADR 0002.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives. Still accurate for the legacy globally-scoped reads.

---

## What was just completed

**ADR 0002 phase 4 — project page UI + active-project switcher.** Seven code commits plus this session's wrap-up. Project CRUD is in place (`/customers/<c>/projects/...`), the active-project selector is pinned to every workspace page, and the active-project JSON API (`/api/active-project`) lets the selector read and write the session. Test count 503 → 527 (+24).

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**Phase 5 — finalize and reload flows.** Closes out ADR 0002.

Spec: `docs/adr/0002-customer-and-project-entities.md` (Lifecycle and "Immutability" sections in particular). Phases 1-4 built the customer/project structure, the project-scoped storage, and the UI for managing both. Phase 5 lights up the audit-trail half — the finalize action that snapshots `working/` into `finalized/<N>/`, and the reload-latest-finalization action that brings a delivered project back into editable state for corrections.

### What phase 5 needs to do

1. **Finalize action on the project detail page.** A button/form that, when submitted, runs the finalize handler:
   - Determines the next `finalization_number` for the project (max + 1, starting from 1).
   - Copies every file under `data/catalog/artifacts/<customer>/<project>/working/<subject>/` to `data/catalog/artifacts/<customer>/<project>/finalized/<N>/<subject>/`. Treat the copy as an atomic unit at the application layer — if a copy fails mid-way, the finalization row is not written. (Filesystem-level atomicity is not a hard requirement per ADR 0002; the integrity guarantee is "the application never overwrites a finalized path once made.")
   - Optional inputs: `finalized_by` (free-form text), `ticket_reference` (string, often the same as the project's but can differ — the ticket that triggered THIS finalization), `notes` (free-form). Form fields on the finalize page.
   - Writes the `finalizations` row.
   - Redirects back to the project detail page with a flash confirming the finalization number.

2. **Reload-latest-finalization action.** Surface on the project detail page (probably next to the finalize button). When pressed:
   - Confirmation dialog warning that the current working state will be discarded.
   - On confirm, copy every file from `.../finalized/<max(N)>/...` into `.../working/...`, overwriting anything currently there.
   - Bump `projects.working_state_modified_at`.
   - Redirect to the project detail page with a flash.
   - The brief in ADR 0002 says "If working state has uncommitted changes from before, the UI warns and requires confirmation before discarding them." Phase 5 implements the warning + confirmation. Detecting "uncommitted changes" is tricky — easiest reliable signal is comparing `working_state_modified_at` to the latest finalization's `finalized_at`. If working is newer, working has unsaved changes.

3. **Finalizations history on the project detail page.** Replace the "No finalizations yet" placeholder with the real list. Each row shows `finalization_number`, `finalized_at`, `finalized_by`, `ticket_reference`, `notes`. Already wired into the route handler from phase 4; just remove the placeholder and let the existing table render.

4. **Application-layer immutability invariant.** The code path that writes to `finalized/<N>/<subject>/` exists exactly once (the finalize handler). Every other artifact write path goes to `working/<subject>/`. Phase 5 makes sure no other code is accidentally allowed to write to `finalized/<N>/`. The simplest enforcement: `ArtifactStore` exposes no method that writes to a finalized path; the finalize handler does its copy directly via `shutil.copytree` or equivalent without going through `ArtifactStore.save_artifact`.

### Constraints

- **Don't touch the active-project selector** from phase 4 unless something demonstrably needs adjustment when an active project gets reloaded.
- **Customer-routes are stable** from phase 3.
- **ADR 0002 source-building fork is orthogonal** to phase 5.
- **No new MCP tools.** Finalize is a UI-only action for v1.

### Suggested first slice

"Finalize action + finalizations history rendering" is the minimum demoable cut. The reload action is the natural second step.

### Priority-ordered backlog (everything else)

1. **ADR 0003 — REST extractor with credentials.** Follows ADR 0002 implementation. Will use the active project's storage path.
2. **CommCell-discovery flow for customer creation.** Convenience feature. Authenticate against a CommCell with provided credentials, populate identity fields. Shares plumbing with ADR 0003.
3. **Report-provenance verification.** Check that an uploaded report's embedded CommCell identity matches the active customer's stored CommCell identity. Catches "wrong customer's report" mistakes.
4. **Left-nav structural review.** The sidebar has accumulated items; visual hierarchy may help at some point.
5. **AI import workstream — staging UI, compliance rules.**
6. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). Globally scoped today.
7. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3.
8. **Legacy-store accumulation, orphaned SQLite registries, labreadiness consumer audit.** Audit Section 6 #2, #5, #6.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **Project CRUD is in place.** Routes live in `src/cvhealthcheck/web/routes/projects.py`. Templates: `customer_detail.html` (lists projects), `project_form.html` (shared create/edit), `project_detail.html`, `project_delete.html`.
- **Active-project selector is in `templates/partials/active_project_selector.html`.** Included from `base.html` and from every self-contained workspace template. It reads/writes via `/api/active-project`.
- **Project deletion is blocked once finalizations exist.** By design (audit trail safety). The strict-and-then-some pattern — UI disables the button, server-side returns 400 on a bypass attempt. Mirrors phase 3's customer-delete-with-projects guard.
- **Auto-activation on project create.** Creating a project sets it as active in the session, so the workspace renders against the new project's working state without an extra click.
- **Project ID is globally unique.** Slug from project_number, with `_2`/`_3` disambiguation across ALL projects (not just within the customer). The user-facing `UNIQUE(customer_id, project_number)` constraint is per-customer.
- **Phase 5 will write to finalizations.** Phase 4 only reads it (for delete-guard and the project detail page's history section). The `finalizations` table is empty in normal usage today.
- **No new localStorage keys.** Active project is session-only (Flask server session, not browser storage). The localStorage surface remains `quickhc-theme-v1` + `quickhc-state-v1`.
- **`init_db()` and `schema.sql` are gone.** `run_migrations()` is the sole bootstrap path. Tests use the `migrated_db_path` fixture.
- **ADR 0002 source-building fork is orthogonal.** `_legacy_builders` continue to serve their subjects globally; the customer/project work changes *where* canonical artifacts live, not *how* legacy tile data is shaped.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 527 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT migration_id FROM schema_migrations ORDER BY 1;"
ls docs/adr/                                       # expect 0001, 0002, README
```
