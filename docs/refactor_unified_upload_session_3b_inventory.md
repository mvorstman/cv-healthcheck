# Session 3b inventory + architectural finding (STOP-and-report)

**Date:** 2026-06-03
**Branch:** `feature/basic-healthcheck-report-output`
**Status:** Stop-and-report. Steps 1 (inventory) and an architectural assessment done. Steps 2-4 (adapter + wiring + deletion) NOT executed because the brief's plan as described cannot preserve the snapshot.

---

## Summary

Session 3b's plan was Option γ from the 2026-06-02 HANDOVER: move legacy on-disk reads into a fallback inside `_load_from_canonical_store`, returning `CanonicalArtifact` so `_build_generic_subject` can render rich output. After that, `_legacy_builders` deletes cleanly.

The plan has a hidden assumption that doesn't hold: that `_build_generic_subject` + `artifact_to_view` (the generic view producer) can reproduce the subject-specific view shapes the legacy builders produce. They can't, because:

- The legacy view shapes include subject-specific section types (`counters`, `findings_grid`, `workload`, `chart_growth`) that `artifact_to_view` doesn't produce.
- The legacy view shapes include subject-specific subject-level fields (computed `subtitle`, `fullUrl` from per-subject route endpoints, source-level `meta` entries) that the generic path doesn't synthesise.
- The canonical schema is frozen, so we can't extend it to carry these shapes natively.

Per the brief's "STOP and report if you can't classify the diff confidently" rule, this session stops before writing the adapter. The inventory below is the useful work product. The architectural decision belongs to the user.

---

## Section A — Inventory of legacy on-disk read paths

Every file-based legacy read currently performed by `_legacy_builders` via its loaders (`_legacy_loaders` in `src/cvhealthcheck/quickhc/subject_data_service.py:286-294`).

### 1. `environment` — CommCell identity

- **Loader**: `_load_legacy_commcell` (subject_data_service.py:230)
- **File**: `data/catalog/rest/commserv.json`
- **Reader call**: `read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))`
- **Shape on disk** (real file from dev machine):
  ```
  {
    "collected_at": "2026-05-22T17:37:54.263799+00:00",
    "http_status": 200,
    "identity": {
      "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D",
      "csVersionInfo": "11 SP40.47",
      "hostName": "cs01",
      "osType": "Unix",
      "releaseId": 16,
      "timeZone": "0:0:America/Danmarkshavn"
    },
    "ok": true,
    "raw": {...},
    ...
  }
  ```
- **What the loader returns**: the `identity` sub-dict.
- **Used by**: `_build_environment_subject` (subject_data_service.py:400-476).
- **Tile output (from snapshot)**:
  - `subtitle: "cs01 · 11 SP40.47"` (computed)
  - `fullUrl: "/quick-hc/commcell"` (from `_try_url`)
  - `activeSource: "rest_command_center_api"` (with status `"v"`)
  - One `meta` section with rows: COMMCELL NAME, COMMCELL ID, VERSION, TIMEZONE
  - Source-level `meta` entries on `rest_command_center_api`: Endpoint, Host, Version

### 2. `security_assessment`

- **Loader**: `_load_legacy_security_assessment` (subject_data_service.py:244) → `security_assessment_quick_hc()`
- **File**: `data/catalog/security_assessment/latest.json` (read through the SA service layer, eventually).
- **Used by**: `_build_security_assessment_subject` (subject_data_service.py:479-732).
- **Tile output (from snapshot)**:
  - `subtitle: "2 critical · 18 info · 12 good"` (computed from counters)
  - `state: "issues"`
  - One `meta` section (Source metadata)
  - One **`counters` section** with `{"Critical": 2, "Warning": 0, "Info": 18, "Good": 12}` ← subject-specific shape
  - One **`findings_grid` section** with critical/warning highlights ← subject-specific shape
  - Six `findings_list` sections (Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, Hardening)

### 3. `license_summary`

- **Loader**: `_load_legacy_license_summary` (subject_data_service.py:252) → `LicenseSummaryService().get_current()`
- **File**: `data/catalog/license_summary/latest.json` (via the LS service layer).
- **Used by**: `_build_license_summary_subject` (subject_data_service.py:734).
- **Tile output (from snapshot)**:
  - `subtitle: "16 other licenses"`
  - One `meta` section (Summary metadata)
  - One **`workload` section** ← subject-specific shape
  - Two `table` sections (Other Licenses, Agent / Feature Licenses)

### 4. `client_growth`

- **Loader**: `_load_legacy_client_growth` (subject_data_service.py:262) → `get_client_growth_summary(live=False)`
- **Files**: `data/catalog/metrics/client_count_history.json`, `data/catalog/metrics/client_growth_summary.json`, `data/catalog/metrics/client_growth_details.json`
- **Used by**: `_build_client_growth_subject` (subject_data_service.py:967).
- **Tile output (from snapshot)**:
  - `subtitle: "5 clients"` (computed)
  - One `meta` section (Summary metrics)
  - One **`chart_growth` section** with months/totals/added/yoy_pct ← subject-specific shape
  - One `table` section (Monthly summary)

### 5. `capacity_license`

- **Loader**: `_load_legacy_capacity_license` (subject_data_service.py:272) → `get_capacity_license_usage(live=False)`
- **File**: `data/catalog/metrics/capacity_license_usage.json`
- **Used by**: `_build_capacity_license_subject` (subject_data_service.py:1102).
- **Tile output (from snapshot)**:
  - `subtitle: "Available"`
  - One `meta` section (Summary)
  - One `table` section (Usage/details)

### 6. `backup_job_summary`

- **Loader**: `_load_legacy_backup_job_summary` (subject_data_service.py:282) → `load_backup_job_summary_artifact()`
- **File**: `data/catalog/quickhc/backup_job_summary_latest.json`
- **Used by**: `_build_backup_job_summary_subject` (subject_data_service.py:1232).
- **Tile output (from snapshot)**:
  - `subtitle: "1 jobs"`
  - Two `meta` sections (Summary, Status breakdown)
  - One `findings_list` (Recent failures)
  - One `table` section (Recent jobs)

---

## Section B — Architectural finding

The brief assumed that an adapter producing a `CanonicalArtifact` from legacy on-disk data, fed to `_build_generic_subject` (which calls `artifact_to_view`), would reproduce the legacy builder's output. **This assumption does not hold.**

### Subject-specific view shapes the generic path can't produce

| Subject | Section type produced by legacy | Produced by `artifact_to_view`? |
|---|---|---|
| environment | `meta` | yes — but missing `meta` field value, subtitle, source-level meta |
| security_assessment | `counters` | NO |
| security_assessment | `findings_grid` | NO |
| license_summary | `workload` | NO |
| client_growth | `chart_growth` | NO |

The canonical schema has section types `findings`, `table`, `metric`, `chart` — not `counters`, `findings_grid`, `workload`, `chart_growth`. The generic view producer renders one shape per schema type; the legacy builders produced richer shapes via subject-specific synthesis.

### Subject-level fields the generic path doesn't synthesise

Even for the simplest subject (environment), `_build_generic_subject(tile, adapter_artifact)` would diff from the legacy snapshot in at least these fields:

- `subtitle`: legacy computes `"cs01 · 11 SP40.47"` from identity. Generic returns `"Data available"`.
- `fullUrl`: legacy sets `/quick-hc/commcell` via `_try_url`. Generic hardcodes `None`.
- `sources[].status`: legacy marks active source as `"v"` (verified). Generic produces `"a"` (available). And source-level `meta` entries (endpoint, host, version) aren't synthesised.

### Proof of concept

```python
# Simulated adapter output for environment + generic view:
{
  "activeSource": "rest_command_center_api",
  "fullUrl": null,
  "sections": [{"id": "environment.metadata", "meta": "", "rows": [...]}],
  "sources": [],          # _build_generic_subject overrides this, but per-source
                          # status/meta still don't match.
  "state": "ok",
  "subtitle": "Data available"
}

# Legacy snapshot for environment:
{
  "activeSource": "rest_command_center_api",
  "fullUrl": "/quick-hc/commcell",
  "sections": [{"id": "environment.metadata", "meta": "CommCell profile", "rows": [...]}],
  "sources": [..., {"status": "v", "meta": [{"k":"Endpoint","v":"GET /commandcenter/api/CommServ"},...]}],
  "state": "ok",
  "subtitle": "cs01 · 11 SP40.47"
}
```

For environment alone, there are 4+ field diffs. For SA/LS/CG with their subject-specific section types, the diffs are structural — entire sections missing or with wrong types.

---

## Section C — Why this STOP-and-report is appropriate

The brief said:

> Verify with the snapshot test from session 3 step 1. After this step, the snapshot should be UNCHANGED for subjects that have data (legacy or canonical) and unchanged for subjects with no data either way. If any snapshot diff appears, investigate — it's either a regression or evidence the adapter doesn't produce the right canonical shape.
>
> If diff appears: STOP and report. Do not regenerate the snapshot to make the test pass.

I'm stopping at the inventory + assessment stage rather than after writing the adapter and confirming the diff, because:

1. The architectural reasoning above is sufficient to predict the snapshot diff without writing code.
2. Writing the adapter without resolving the view-shape question first would produce throwaway code (the adapter is correct, but the consumer can't render it).
3. The brief's intent was clearly to land Option γ cleanly. If Option γ as briefed can't land cleanly, the user needs to redirect before more code is committed.

---

## Section D — Options forward (user picks)

**Option γ1 — Restore per-subject view producers in `canonical_view.py`.** Reintroduce `security_assessment_to_view`, `license_summary_to_view`, `client_growth_to_view`, and any others needed. Make `artifact_to_view` (or `_build_generic_subject`) dispatch to them based on `artifact.artifact_type`. This is essentially undoing session 2's `canonical_view._build_sources` deletion direction, but the view producers go in canonical_view.py rather than subject_data_service.py. Net effect: the canonical store grows subject-aware view dispatch; legacy builders can then be deleted cleanly because the new dispatch reproduces the legacy view shapes from a `CanonicalArtifact`.

- Pros: keeps the canonical store as the single read path; subject-specific knowledge lives in the view layer (a natural place for it).
- Cons: undoes some of session 2's deletion direction. The "unified source-building path" claim becomes "unified data source with subject-aware view rendering."

**Option γ2 — Accept the regression as deliberate sunset of subject-specific view shapes.** Delete `_legacy_builders`. The view becomes generic for all subjects. Tile look-and-feel changes for SA (no counters chips, no highlight grid), LS (no workload section), CG (no chart). Snapshot regenerates. Future work could re-add richer views as customisations on top of the unified pipeline.

- Pros: smallest end state. Achieves the architectural goal cleanly.
- Cons: significant visible UX change. The Quick HC product was designed around these subject-specific views; losing them would be a regression in the customer-facing report composition surface.

**Option γ3 — Extend the canonical schema.** Add new section types (`counters`, `findings_grid`, `workload`, `chart_growth`) to the canonical schema. Adapter produces these section types directly. Generic `artifact_to_view` learns to render them.

- Pros: the canonical schema becomes expressive enough to encode every Quick HC view shape. Future subjects with custom views fit naturally.
- Cons: violates "the canonical artifact schema is frozen" (project constraint stated multiple times). Schema-level changes have a large blast radius.

**Option γ4 — Hold position and don't unify.** Accept that `_legacy_builders` is the long-term home for subject-specific view shapes; rename it to something less pejorative; keep it alive. The unified upload route (session 2) still exists; the URL flip (session 3) still happened. Sessions 4+ proceed: delete the old routes, replace the FIXME branch dispatch with data-driven dispatch. But the source-building path stays as two paths (canonical hit → generic, canonical miss → legacy/subject-specific).

- Pros: zero further behavior change. Sessions 4-5 can proceed unblocked.
- Cons: doesn't actually unify source building. The architectural goal is partially abandoned.

### My read

**γ1 looks correct in shape but is sized like a real session of its own.** Restoring 3-4 per-subject view producers, wiring dispatch, validating against the snapshot, and only THEN deleting `_legacy_builders` and running step 4 — that's a session. Not session 3b's narrow scope.

**γ4 is the minimal action that lets the rest of the refactor proceed.** It accepts that "source-building unification" is harder than initially modelled and reframes the goal to "route + persist + URL unification, source-build stays split because the view shapes are real product surface area."

I do not have authority to pick between these. The user does.

---

## What I'm doing in this commit

Just landing this document. Working tree otherwise clean. No code changes. The 477 passing tests from after session 3 still pass.

Next: CHANGELOG entry pointing here. HANDOVER pointing the next session at this decision.
