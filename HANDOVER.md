# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-05-26 (housekeeping wrap-up)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `a2f7e1d` — Housekeeping wrap-up: CHANGELOG entry, HANDOVER pivots to AI import
**Test status:** 483 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/adr/0001-source-building-fork.md`** — load-bearing architecture decision. Required reading if your work touches source-building, the canonical schema, or the unified upload route.
5. **`docs/data_flow_audit.md`** — read-only audit of where data lives on disk and which code paths read/write each location. Useful as a map before touching subject data flows.

`CHANGELOG.md` is the dated history. The 2026-05-26 housekeeping entry closes out the foundation backlog (gitignore, README refresh).

---

## What was just completed

**Foundation cleanup wrap-up.** Two small housekeeping items off the priority-ordered backlog: `data/app.db` is now gitignored (migrations recreate the schema and seed the six system subjects on a fresh clone; no separate bootstrap needed), and the README's test count + URL table are refreshed. Test count unchanged at 483. **The foundation work is complete.**

Prior recent work (full thread in `CHANGELOG.md`):

- Unified-upload refactor (sessions 1 → 5b): one `POST /quick-hc/<subject_id>/import` route, subject-specific behavior in `upload_dispatch.py`.
- Source-provenance dispatch: `source_provenance_dispatch.py` wires SA/LS provenance builders back into the workspace tile path.
- Workspace position preservation: client-side URL fragment (`fecf68c`) + server-side fragment-carrying redirects (`47c58b0`) — Collect/upload no longer drops the user back on CommCell Details.
- Data flow audit: `docs/data_flow_audit.md`.

---

## What is in-flight

Nothing. Working tree is clean.

---

## Single recommended next action

**The AI import workstream — scoping conversation, then implementation.**

The foundation work is complete. The next focus is the AI import flow: staging UI for proposal review, REST extractor with credentials, compliance rules. This is meaningfully larger than any single session in the recent thread and should not be started cold — **a scoping conversation should precede implementation**.

Shape of the scoping conversation the next session should drive:

- What does the AI import flow actually do end-to-end? The MCP tools (`save_staged_artifact`, `approve_staged_artifact`, `propose_new_subject` in `src/cvhealthcheck/mcp/server.py:210, 264, 299`) and the `staged_artifacts` table exist; what surfaces them to the user, and through what review affordances?
- What needs to be built first — the staging UI (probably highest user-visible value), the REST extractor with credentials (probably highest "is this even possible" risk), or the compliance rules engine (probably most design-heavy)?
- What's in scope for the first slice? "Approve/reject a staged artifact through a web UI" is one slice. "Run the full AI proposal → review → approval loop on a real subject" is a much bigger slice.
- What does success look like — both end-state and the first demo-able milestone?

This handover does not pick a sequence. The user picks after the scoping conversation. The aim of next session is *agree on the shape*, not *build*.

### Priority-ordered backlog (everything else)

1. **2026-05-20 review backlog.** Older items parked when the unified-upload refactor took over. Review what's still relevant; some items may have been overtaken by the refactor and the audit.
2. **Workflow tooling decisions** parked earlier — exact list lives in the older HANDOVER chain.
3. **`data/catalog/reportsplus/` retention.** Audit Section 6 #3: 203 raw extraction files today, no retention policy. Grows unbounded as datasets are re-extracted. Decision: keep all, prune by age, or move to a tiered store?
4. **`data/catalog/{security_assessment,license_summary}/` legacy-store accumulation.** Audit Section 6 #2: test fixtures still hit `write_legacy=True` and accumulate `artifact_<uuid>.json` files (33 and 47 today). Decision needed once Option A read fallback is retired.
5. **Two orphaned SQLite registries** (`data/imports/{security_assessment,license_summary}/artifact_registry.sqlite3`). Audit Section 6 #6: effectively read-only in production today (production callers pass `write_legacy=False`). Likely deletable; needs verification.
6. **`data/labreadiness/latest.json` consumer audit.** Audit Section 6 #5: written by CLI + dev page, no production reader. Decide whether to retire the write or surface the data somewhere.

Smaller, opportunistic cleanups still on the list:

- Delete `TileDefinition.import_url=` dead data at `registry.py:131, 205` (unread since session 2).
- Possibly delete the legacy `/security-assessment` development page in `web/routes/development.py` if nobody uses it.
- Consider moving the no-canonical-artifact path for SA/LS (the legacy `_build_security_assessment_subject` / `_build_license_summary_subject` source-list logic) onto `source_provenance_dispatch` so the workspace-tile source statuses are consistent across both data-present and data-absent paths. Not urgent — production has canonical artifacts; the snapshot test fixture is the only consumer of the legacy paths today.
- Deeper README staleness: the SA section's "Latest persisted multi-source artifacts" paths at L260-268 no longer match the canonical-store layout. Separate README session.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **Foundation work is done.** The unified upload route, the subject-data dispatch, the provenance dispatch, and the workspace-position-preservation fixes are all stable. Don't reopen them without a strong reason.
- **Source-building fork is intentional.** See `docs/adr/0001-source-building-fork.md`. The fork serves subject-specific view shapes (counters, findings_grid, workload, chart_growth) that the canonical schema can't represent. Do not "clean up" this fork without reading the ADR.
- **Unified upload route is the sole upload path** since session 4. `POST /quick-hc/<subject_id>/import` handles everything. Old URLs return 404 by design.
- **Subject-specific upload behavior lives in `src/cvhealthcheck/web/routes/upload_dispatch.py`.** Two entries today (`security_assessment`, `license_summary`). Adding a new system subject with custom upload behavior is one entry in the dict.
- **Subject-specific source-provenance lives in `src/cvhealthcheck/quickhc/source_provenance_dispatch.py`** (sibling pattern). Same two entries. Same δ → β migration path documented in `docs/refactor_unified_upload_session_5a_design.md` Section 6.
- **Subject-specific redirects carry `#subject=<id>` fragments** via `_workspace_redirect(subject_id)` in `quick_hc.py:65`. JS reads the fragment on init (`quick_hc.js:_readSubjectFromHash`). Don't add new subject-specific redirects without going through the helper.
- **`data/app.db` is gitignored.** On a fresh clone, app startup runs migrations and seeds the six system subjects from `0003_report_inventory.sql`. The two AI subjects in dev `app.db`s are dev-machine state.
- **Snapshot test (`tests/test_subject_initial_data_snapshot.py`)** is the behavior-preservation pin. Run it whenever you touch source-building or view-producing code.
- **Legacy artifact READS preserved.** The Option A invariant (write_legacy retired; reads through `load_active_security_assessment_artifact` / `load_active_license_summary_artifact` still alive) holds.
- **`/logout` is POST-only**. No CSRF middleware in the app.
- **localStorage surface is exactly two keys**: `quickhc-theme-v1`, `quickhc-state-v1`. Settings page (`/quick-hc/settings`) inspects and resets them. URL fragment (`#subject=<id>`) is a separate, non-localStorage mechanism.
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
grep -rn "FIXME(refactor-unified-upload-session-5)" src/  # expect 0 hits
ls docs/adr/                                       # expect 0001-source-building-fork.md + README.md
ls docs/data_flow_audit.md                         # expect present
```
