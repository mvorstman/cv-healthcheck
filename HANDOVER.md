# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** `7b0b0c1` — Session 3b wrap-up: CHANGELOG entry, HANDOVER points at the decision
**Test status:** 477 passing

---

## Read this first

If you are a new chat / new session, read these files in order before doing anything else:

1. `README.md` — what the project is, how to run it, the stack
2. `HANDOVER.md` (this file) — what to do next
3. `ROADMAP.md` — where the project is heading
4. **`docs/refactor_unified_upload_session_3b_inventory.md`** — the session 3b architectural finding. This is required reading before continuing the refactor.
5. **`docs/refactor_unified_upload_2026-05-31.md`** — the original investigation report that drives the unified-upload refactor.

`CHANGELOG.md` is the dated history. The 2026-06-03 entry is the most relevant — session 3b stopped at the architectural assessment.

---

## What was just completed

**Session 3b — STOP-and-report at the inventory + architectural-assessment stage** (commit `11df86c`).

Before writing any adapter code, I traced the contract: `_build_generic_subject(tile, adapter_artifact)` cannot reproduce the legacy builder's tile output, because the legacy builders produce subject-specific view shapes (`counters`, `findings_grid`, `workload`, `chart_growth`) that `artifact_to_view` doesn't know how to produce. The canonical schema is frozen, so it can't carry those shapes natively either.

The session committed one docs file (`docs/refactor_unified_upload_session_3b_inventory.md`) containing:
- Section A: complete inventory of the 6 legacy on-disk read paths (file paths + return shapes).
- Section B: the architectural finding with concrete proof-of-concept showing the diff for environment (simplest case).
- Section D: four options forward (γ1 / γ2 / γ3 / γ4) for the user to pick between.

No code changed. 477 tests still pass. 3 `FIXME(refactor-unified-upload-session-5)` tags still in place.

---

## What is in-flight

The refactor is blocked on the architectural decision documented above. Working tree is clean.

---

## Single recommended next action

**Decide between options γ1, γ2, γ3, γ4** for completing the source-building unification, then execute the chosen path.

The four options are documented in detail in `docs/refactor_unified_upload_session_3b_inventory.md` Section D. Brief recap:

- **γ1 — Restore per-subject view producers in `canonical_view.py`.** Reintroduce `security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view`. Make `artifact_to_view` dispatch by `artifact_type`. Then delete `_legacy_builders` cleanly. Subject-specific knowledge lives in the view layer (a natural home for it).
- **γ2 — Accept the regression.** Delete `_legacy_builders`. All subjects render via generic view producer. Lose `counters`, `findings_grid`, `workload`, `chart_growth` shapes. Customer-facing UX regression.
- **γ3 — Extend the canonical schema.** Add new section types. Violates the "schema is frozen" rule — likely not the right choice.
- **γ4 — Hold position. Don't unify source building further.** Sessions 4-5 (route deletion + data-driven dispatch) proceed independently. The source-building stays split; `_legacy_builders` lives as the home for subject-specific view shapes.

### My read (not a decision)

**γ4 unblocks the rest of the refactor immediately.** Sessions 4 and 5 are independent of source-building unification:
- Session 4 deletes the old upload routes. The frontend already uses the new ones (session 3). Nothing in source-building blocks this.
- Session 5 replaces the branch-dispatch shim in `quick_hc_subject_import` with data-driven dispatch. Also independent of source-building.

After 4 and 5, the upload-route refactor is functionally complete. Source-building unification becomes a separate piece of work — perhaps best framed not as "delete `_legacy_builders`" but as "the view-shape question": where should `counters`/`findings_grid`/`workload`/`chart_growth` rendering live? `_legacy_builders` is one valid answer. γ1 (move them to `canonical_view.py`) is another. Either can land later; neither is on the critical path for the upload-route work.

**γ1 is the cleaner end state** if and when the user wants to invest in finishing source-building unification. The view producers reincarnate where they architecturally belong (the view layer), and `_legacy_builders` deletes cleanly. But it's a session of its own — restoring 3-4 view producers, wiring dispatch, validating against the snapshot.

If the user wants to proceed with the upload-route refactor without further source-building work, pick γ4 and move on to session 4. If the user wants to finish source-building too, pick γ1 and budget a session for it.

### What γ4 looks like operationally

1. Update HANDOVER (this file) to point at session 4 as the next recommended action.
2. The `_legacy_builders` keeps living; it's no longer flagged as a thing to delete. Add a CHANGELOG note that source-building unification is deferred.
3. Session 4 proceeds: delete old routes, delete `templates/quick_hc_import.html`, update tests.

### What γ1 looks like operationally

1. Restore `security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view` (and any others needed) in `canonical_view.py`. Use the legacy builders as reference for what each should produce.
2. Add dispatch in `artifact_to_view` (or `_build_generic_subject`) by `artifact.artifact_type` to the right view producer.
3. Run the snapshot. If it stays unchanged for the 3 subjects with rich views, the view producers are right. If not, iterate.
4. Build the legacy on-disk read adapter (session 3b step 2 as originally briefed) — now it can produce a `CanonicalArtifact` and downstream view rendering produces the right shape.
5. Wire the adapter into `_load_from_canonical_store`.
6. Delete `_legacy_builders` (session 3b step 4 as originally briefed).
7. Verify the snapshot stays unchanged.

This is a session-sized piece of work — probably more than session 3b's original scope.

### Verification

```bash
python -m compileall -q src
python -m pytest -q                                # expect 477 passing
grep -rn "FIXME(refactor-unified-upload-session-5)" src/  # expect 3 hits in quick_hc.py
```

---

## After the source-building question resolves, the queue resumes

1. **Session 4** — Delete the old `/quick-hc/security-assessment/import`, `/quick-hc/license-summary/import`, and `/quick-hc/import` routes plus `templates/quick_hc_import.html`. (Can happen NOW under γ4.)
2. **Session 5** — Replace the branch-dispatch shim in `quick_hc_subject_import` with data-driven dispatch. (Can happen NOW under γ4.)
3. **Session 6 (optional)** — Final cleanup.

After the refactor: `data/app.db` out of git, `README.md` refresh, 2026-05-20 review backlog, workflow tooling decisions.

---

## Context the next session needs that is not yet in README/ROADMAP/CHANGELOG

- **Source-building unification is blocked.** The two architectural walls hit so far are documented in the session 3 and 3b CHANGELOG entries plus `docs/refactor_unified_upload_session_3b_inventory.md`. Future sessions should not try to "just delete `_legacy_builders`" without addressing the view-shape question first.
- **The unified upload route from session 2 is live and tested.** Its 3 `FIXME(refactor-unified-upload-session-5)` tags are in place. The route handler's branch dispatch is a deliberate smell scheduled for session 5/6 replacement; do not refactor it before then.
- **The frontend uses the new underscored URLs** (`/quick-hc/<subject_id>/import`) since session 3 commit `389bc4d`. The old hyphenated routes still exist at the route layer; session 4 deletes them.
- **The snapshot test (`tests/test_subject_initial_data_snapshot.py`)** is the behavior-preservation pin. Run it whenever you touch source-building or view-producing code. Diffs must be classified before regenerating.
- **Legacy artifact READS are preserved.** The Option A invariant (write_legacy retired for new writes, legacy read fallback preserved) lives through both `_load_active_security_assessment_artifact` (legacy artifact files) and the legacy builders (file-based subject data). Future deletion of either must consider what readers depend on them.
- **`/logout` is POST-only**. No CSRF middleware in the app.
- **localStorage surface is exactly two keys**: `quickhc-theme-v1` and `quickhc-state-v1`. The Settings page (`/quick-hc/settings`) inspects and resets them.
- **Quick HC subject naming rule (load-bearing).** Sidebar display name must come from `tile["title"]`, not from `artifact.subject.title`. Override at `subject_data_service.py:213`.
- **`execute_approval()` requires an injected `store` in tests.** Pattern in `tests/test_core_solidity.py::test_execute_approval_artifact`.
- **Section ID prefix invariant** (landed 2026-05-26). `canonical_view` guards both prefix sites against re-prefixing.
- **Hyphen-vs-underscore URL convention.** The unified route is `/quick-hc/<subject_id>/import` with subject_id from the DB (underscored). The OLD per-subject routes used hyphens. Both are alive until session 4 deletes the old ones.

---

## Quick verification commands

```bash
cd /home/michiel/dev/cv-healthcheck
source venv/bin/activate
python -m compileall -q src
python -m pytest -q                                # expect 477 passing
git status --short                                 # expect clean
sqlite3 data/app.db "SELECT subject_id,created_by,status FROM subjects;"
grep -rn "FIXME(refactor-unified-upload-session-5)" src/  # expect 3 hits
```
