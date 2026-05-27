# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-27 (workflow discipline: push to GitHub)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `fefff25` — Push-discipline wrap-up: CHANGELOG entry, HANDOVER header
**Test status:** 554 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0002-customer-and-project-entities.md`** — fully implemented. Read it as the spec for what's in place.
5. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Still active; orthogonal to ADR 0002.
6. **`docs/data_flow_audit.md`** — read-only audit of where data lives.

---

## What was just completed

**ADR 0002 phase 5 — finalize and reload flows. ADR 0002 implementation is complete.** Five code commits (`e4c582d` core logic + 15 unit tests, `8dfb0a3` finalize UI, `e86ce90` reload UI, `33c96fb` finalizations placeholder refresh, `158841c` 12 route tests) plus this session's wrap-up. The audit-trail promise of ADR 0002 is now operational: consultants can finalize a project's working state, see the immutable history on the project detail page, reload the latest finalization back into working for corrections, and re-finalize.

Test count 527 → 554 (+27 across phase 5). The full five-phase arc landed across 2026-05-26 → 2026-05-27.

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**ADR 0003 — REST extractor with credentials.** Design first; the customer/project foundation it builds on is now in place.

The REST extractor is the "live collection" half of the consulting workflow. Customers exist (phase 3); projects exist (phase 4); the workspace operates per-project (phase 2); finalization captures audit-trail snapshots (phase 5). What's still missing is a path from "the customer has a CommCell I can authenticate against" to "the project's working state holds real data collected from it." Today the workspace is empty unless someone manually drops files into a project's `working/` directory.

The session that lands next should write ADR 0003 as a design proposal — no implementation. The shape of the conversation: what authentication patterns work for the consulting-engagement model? Are credentials stored, prompted per session, or supplied per-collection? How does the extractor route collected data into the active project's storage? What's the relationship with the existing `RESTExtractor` (`src/cvhealthcheck/extractors/rest.py`) used by the generic collect route today, and the dedicated `SecurityAssessmentService.collect_from_rest` / `LicenseSummaryService.collect_from_rest` paths?

### Existing tooling worth surveying for ADR 0003

- `src/cvhealthcheck/auth/commvault_auth.py` — Flask session-backed CommCell token management.
- `src/cvhealthcheck/api_client.py` — Commvault API client.
- `src/cvhealthcheck/reportsplus/client.py` — Reports Plus client used by SA/LS collect paths.
- `src/cvhealthcheck/extractors/rest.py` — generic RESTExtractor used by `/quick-hc/<subject_id>/collect`.
- `src/cvhealthcheck/security_assessment/service.py::SecurityAssessmentService.collect_from_rest` and `license_summary/service.py::LicenseSummaryService.collect_from_rest` — dedicated REST collection per system subject.

ADR 0003 sits at the intersection of all of these. Its job is to design the unifying story — not implement it yet.

### Priority-ordered backlog

1. **ADR 0003 — REST extractor with credentials.** Design first, no implementation. Single recommended next action above repeats this; listed here as #1 for completeness.
2. **Refresh `docs/data_flow_audit.md`.** Currently stale after ADR 0002 implementation — the storage layout description still reflects pre-phase-2 reality. Do this BEFORE ADR 0003 so the design conversation has fresh visual ground (where data lives, how reads and writes flow).
3. **AI import workstream — staging UI for proposal review, REST extractor with credentials, compliance rules.** Larger scope; ADR 0002's implementation likely surfaced architectural choices that simplify some of this. Auth/extractor design will overlap with ADR 0003.
4. **CommCell-discovery flow for customer creation.** Falls out of ADR 0003's auth design — same plumbing, different destination (customer record's identity fields vs project's working state).
5. **Report-provenance verification.** When an HTML/CSV report is imported, check the embedded CommCell identity matches the active customer's stored CommCell identity. Catches "wrong customer's report uploaded by accident" mistakes.
6. **Read-only per-finalization view.** Deferred from phase 5 step 5. `GET /customers/<c>/projects/<p>/finalizations/<n>` would let consultants see a delivered report's contents alongside the current working state. Needs either an ArtifactStore read-mode that points at `finalized/<n>/` paths, or a sibling helper. Architectural decision left to that session.
7. **Customer panel on the right side of `quick_hc.html`.** Raised this session, not acted on. A right-side panel surfacing the active customer's context (customer name, CommCell hostname/ID, active project metadata) alongside the existing subject workspace. Pairs with the active-project selector at the top.
8. **`shared.py` split.** `src/cvhealthcheck/web/routes/shared.py` is a 413-line god-module with 60+ imports spanning auth, ReportsPlus, metrics, license_summary, security_assessment. Flagged in the 2026-05-20 review; still open. Split by concern.
9. **`SecurityAssessmentArtifactRegistry` rename.** Class at `src/cvhealthcheck/security_assessment/registry.py` is SA-specific in name but the registry pattern is also used by License Summary. Decide: rename to a generic `ArtifactRegistry` and unify, or clarify the per-domain naming as intentional. Flagged in the 2026-05-20 review.
10. **Hardcoded URLs in `report_service.py`.** Partial work landed (CHANGELOG 2026-05-20 says detail URLs were replaced with `TileDefinition.detail_endpoint` resolution through `url_for()`). Audit whether any hardcoded URLs remain.
11. **Left-nav structural review.** The sidebar has accumulated items (Overview, Reports, Customers, Settings, Staging, plus SUBJECTS). Grouping or visual hierarchy will help at some point.
12. **Two-CRUD-APIs investigation.** Customer routes use both inline SQL through `get_db()` AND `db/customers.py`'s module-level helpers — phase 3 surprise. Pick one, retire the other. Same review applies to projects.
13. **Template inheritance cleanup.** Some workspace templates extend `base.html`, others are self-contained — phase 4 surprise. Active-project selector is included in both ways, which is awkward. Consolidate.
14. **`engagements` table cleanup.** Empty since migration 0001; predates ADR 0002. No production writes. Retire if no future use surfaces (ADR 0002 explicitly replaced this concept with `projects`).
15. **Project-scope the legacy SA/LS stores** (`data/catalog/{security_assessment,license_summary}/`). Globally scoped today (Option A read fallback). Needs a project-scoping story eventually.
16. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3 — 200+ raw extraction files accumulating with no retention policy.
17. **Audit Section 6 #2, #5, #6** — legacy-store accumulation, orphaned SQLite registries, labreadiness unread.

Smaller cleanups:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205`.
- Possibly retire the legacy `/security-assessment` development page.
- Move SA/LS no-canonical-artifact path onto `source_provenance_dispatch`.
- Deeper README staleness in the SA section (still describes the pre-canonical artifact paths).

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **ADR 0002 is fully implemented.** Customers and projects are CRUD-managed through the UI under `/customers/...`. Each project has its own working state under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. Finalize captures an immutable snapshot under `.../finalized/<n>/<subject>/`. Reload restores the latest snapshot.
- **Finalize is the only code path that writes under `finalized/`.** `ArtifactStore` (the production write path used by every other artifact-saving code path) writes only to `working/`. This is the application-layer immutability invariant from ADR 0002.
- **Finalize/reload core logic lives in `src/cvhealthcheck/db/finalizations.py`.** Three functions: `finalize_project`, `reload_latest_finalization`, `diff_working_vs_latest`. Used by both the routes (`projects_finalize`, `projects_reload`) and by future automation (e.g. a CLI command if added later).
- **Finalize captures `ticket_reference` and `assigned_consultant` at the moment of finalization** and writes them into the `finalizations` row. Editing the project row later doesn't change earlier finalizations — this is the auditable history.
- **Diff is content-based on `latest.json`.** Timestamped snapshot files (the append-only history) are ignored. A no-op save (writing the same content) doesn't trigger a false "modified" signal.
- **Project deletion is blocked once any finalization exists.** Phase 4 introduced the guard with a direct-INSERT test fixture; phase 5 verified it still works with finalizations created via the new UI.
- **`init_db()` and `schema.sql` are gone.** `run_migrations()` is the sole bootstrap path.
- **ADR 0001 source-building fork is orthogonal.** `_legacy_builders` continue to serve their subjects globally; ADR 0002 changed *where* canonical artifacts live, not *how* legacy tile data is shaped.
- **Active-project session.** Lives in the Flask session as `session['active_project'] = {'customer_id': ..., 'project_id': ...}`. The active-project selector partial at `templates/partials/active_project_selector.html` is included on every workspace page (via `base.html` and the self-contained top-level templates).

---

## Session workflow disciplines

These apply to **every session**, not just ADR implementations or
multi-step refactors. Treat them as project workflow rules, not
suggestions.

### Push to GitHub regularly

- **Push to `origin` after each major task completes.** A "major task"
  is: a phase of an ADR implementation, an interstitial cleanup, an
  ADR write-up, a multi-commit refactor, a documentation pass that
  produces multiple commits.
- **Push at the end of every session**, regardless of whether a major
  task just completed. The session-end push is the *last* action
  before stopping — after updating HANDOVER's last-commit pointer, the
  very next thing to do is `git push origin <branch>`.
- This is the final step of the "single recommended next action"
  pointer. Don't treat it as optional.

**Why:** local-only commits are one disk failure away from gone. This
discipline was added after a session discovered 59 local commits had
accumulated unpushed — the work was only on the dev machine and
couldn't be pulled to a second machine. Pushing regularly puts the
commits behind GitHub's durability guarantees and makes the branch
available to any other machine.

If a push fails (auth issue, network), report it and stop — don't
push-force or work around it. Pushes should be append-only and
no-rebase under normal conditions.

### Verify before write

See `docs/PATTERNS.md` — HANDOVER claims are starting points, not
contracts. Grep first, then act.

### STOP-and-report

Many session briefs say "if X happens, STOP and report." Take that
literally — when a step surfaces a design question not covered by
the brief, ask the user rather than fabricating an answer. Better to
leave a gap than to document the wrong thing.

---

## Where work happens — Claude Code vs Claude.ai

This project's sessions run in two different tools. Knowing which is
which saves a fresh chat from trying work it can't do.

### Claude Code (agentic CLI, filesystem access)

Runs every session that touches the codebase. Every implementation
session in this project's history has been Claude Code. Use it for:

- ADR implementation phases
- Audit refreshes and documentation passes that verify against code
- Schema migrations
- Refactors and cleanups
- Anything that needs to read source files, run tests, commit, or push

If the work involves the filesystem at all, it belongs here.

### Claude.ai (chat interface, no filesystem)

Handles work that is pure conversation and prose. Use it for:

- Design conversations and strategic decisions
- Prompt drafting for Claude Code sessions
- Meta-discussions about the project's direction
- ADR drafting *when* the ADR doesn't need verification against
  current code (if it does, Claude Code is faster — it can grep
  while drafting)

### The handoff pattern

The user is the bridge between the two tools:

1. Claude.ai conversation produces a session brief (prompt) and any
   strategic decisions
2. User runs the brief in Claude Code at the dev machine
3. Claude Code executes, commits, pushes, reports back
4. User pastes the report into the next Claude.ai conversation if
   the work continues strategically

### Signal that a session needs Claude Code

Any of these in the brief means filesystem access is required:

- "read `<file>`", "update `<file>`", "edit `<file>`"
- "run the tests", "run pytest", "confirm test count"
- "commit", "push", "update CHANGELOG", "update HANDOVER"
- "verify against current code", "grep for", "check whether"
- "the audit", "the schema", "the migrations"

A Claude.ai chat seeing these signals should respond: *"this work
needs Claude Code — here's the prompt"*, then draft the prompt rather
than attempting the work.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 554 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT customer_id,customer_name FROM customers;"
sqlite3 data/app.db "SELECT project_id,customer_id,project_number FROM projects;"
sqlite3 data/app.db "SELECT finalization_number, project_id FROM finalizations ORDER BY project_id, finalization_number;"
ls docs/adr/                                       # expect 0001, 0002, README
```
