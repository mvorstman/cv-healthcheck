# Data Flow Audit

**Date:** 2026-05-27 (post-ADR-0002 refresh)
**Scope:** Where this project's data lives on disk, and which code paths read from / write to each location.
**Test status (unchanged):** 554 passing.

This audit reflects the **post-ADR-0002 architecture**: customer/project entities, project-scoped canonical artifacts under `working/<subject>/`, and immutable finalization snapshots under `finalized/<n>/<subject>/`. The legacy stores (SA, LS, ReportsPlus, metrics, CommCell cache, lab-readiness) remain globally scoped — that's an intentional carry-over, not drift. Project-scoping the SA/LS legacy stores is queued as HANDOVER backlog item #15.

This is a read-only audit. No code or data was modified.

---

## Section 1 — Directory tree of `data/`

```
data/
├── app.db                                       # Main project SQLite DB
│                                                  Post-ADR-0002 tables: customers, projects, finalizations
│                                                  Legacy tables retained: subjects, subject_*, staged_artifacts, engagements
├── catalog/
│   ├── datasets.json                             # Reports Plus dataset inventory (CLI extract output, global)
│   ├── datasets_summary.json                     # Compact summary derived from datasets.json (global)
│   ├── artifacts/                                # Project-scoped canonical artifacts (ADR 0002)
│   │   └── <customer_id>/
│   │       └── <project_id>/
│   │           ├── working/                      # Mutable. ArtifactStore writes here.
│   │           │   └── <subject_id>/
│   │           │       ├── latest.json           # Authoritative current state
│   │           │       └── <timestamp>.json...   # Append-only history per save
│   │           └── finalized/                    # Immutable snapshots. ONLY finalize_project writes here.
│   │               └── <n>/
│   │                   └── <subject_id>/
│   │                       ├── latest.json       # Frozen copy from working at finalize-time
│   │                       └── <timestamp>.json... # History as it stood at finalize-time
│   ├── license_summary/                          # Legacy global store (artifact_<uuid>.json + latest.json)
│   │                                              Still written by write_legacy=True paths; backlog #15
│   ├── security_assessment/                      # Legacy global store — same as above
│   ├── metrics/                                  # Per-CommCell metric snapshots (global)
│   │   ├── capacity_license_usage.json
│   │   ├── client_count_history.json
│   │   ├── client_growth_details.json
│   │   └── client_growth_summary.json
│   ├── quickhc/
│   │   ├── backup_job_summary_latest.json        # Per-CommCell (global)
│   │   └── descriptions/                         # {tile_id}.json overrides for tile descriptions
│   ├── reportsplus/                              # Raw Reports Plus extraction artefacts (global; backlog #16)
│   └── rest/
│       └── commserv.json                         # CommCell identity cache (per-deployment, global)
├── imports/                                      # Original uploaded files + per-subject SQLite registry
│   ├── license_summary/
│   │   ├── artifact_registry.sqlite3
│   │   └── {original-filename}-{import-id}.{html,csv,xlsx,...}
│   └── security_assessment/
│       ├── artifact_registry.sqlite3
│       └── {original-filename}-{import-id}.{html,csv,...}
└── labreadiness/
    └── latest.json                               # Lab-readiness assessment output (CLI-only, global)
```

**Three on-disk regions:**

1. **Project-scoped canonical artifacts** under `data/catalog/artifacts/<customer>/<project>/{working,finalized}/`. New as of ADR 0002 phase 2; the `finalized/` subtree as of phase 5.
2. **Globally-scoped legacy stores** for SA/LS (`data/catalog/security_assessment/`, `.../license_summary/`), Reports Plus extraction artefacts (`data/catalog/reportsplus/`), CommCell cache (`data/catalog/rest/commserv.json`), historical metrics (`data/catalog/metrics/`), and lab-readiness (`data/labreadiness/`). These pre-date customer/project scoping and remain global.
3. **SQLite catalog** at `data/app.db`. ADR-0002 added `customers`, `projects`, `finalizations` (migration 0005); the legacy `engagements` table from migration 0001 remains untouched (backlog item #14 covers its retirement).

### Filename patterns

| Directory | Pattern | Source |
|---|---|---|
| `data/catalog/artifacts/<customer>/<project>/working/<subject>/` | `<ISO-timestamp>.json` per save, plus `latest.json` mirror | `ArtifactStore.save_artifact` writes both (`store.py:58-71`) |
| `data/catalog/artifacts/<customer>/<project>/finalized/<n>/<subject>/` | Frozen copy of working at finalize-time (full subtree) | `db/finalizations.py:finalize_project` via `shutil.copytree` — application-layer-immutable thereafter; no other code path writes here |
| `data/catalog/{security_assessment,license_summary}/` | `artifact_<uuid>.json` per import, plus `latest.json` mirror | Legacy per-domain writers (see Section 4) |
| `data/catalog/reportsplus/` | `report_<id>_<role>.json` for typed snapshots; `report_<id>_raw_<dataset_guid>.json` for raw dataset dumps | `REPORTSPLUS_CATALOG_DIR` writers in `reportsplus/extract_report.py:14`, `reportsplus/metric_inventory.py:9` |
| `data/imports/<subject>/` | Uploaded filenames with `-<ULID-ish>-<hash>` suffix (preserved verbatim) | Per-subject import handlers via `_save_upload` |

---

## Section 2 — Per-subject data inventory

Subjects enumerated from `data/app.db`:

```sql
SELECT subject_id, created_by, status, category, version FROM subjects ORDER BY category, subject_id;
```

All canonical store paths are now project-scoped — the canonical store column below shows whether an artifact exists under the **active project** at the time of writing, at `data/catalog/artifacts/<customer>/<project>/working/<subject>/latest.json`. Legacy on-disk paths remain globally scoped per the carry-over noted in the header.

| subject_id | created_by | canonical store (project-scoped `working/<subject>/latest.json`) | legacy on-disk path(s) | REST collect handler | Upload handler |
|---|---|---|---|---|---|
| `environment` | system | ❌ (no canonical artifact) | `data/catalog/rest/commserv.json` (read via `_load_legacy_commcell`, `subject_data_service.py:309-320`) | Generic `/quick-hc/<subject_id>/collect` (`quick_hc.py:141`) — runs `RESTExtractor`; `has_section_instructions=0`, so no Collect button in UI today | None (system, no `UPLOAD_HANDLERS` entry) — returns 404 |
| `security_assessment` | system | ✅ (`latest.json` present today) | `data/catalog/security_assessment/{latest.json, artifact_<uuid>.json}` plus `data/imports/security_assessment/artifact_registry.sqlite3` + raw upload files | Dedicated `/quick-hc/security-assessment/collect` (`quick_hc.py:237`) → `SecurityAssessmentService.collect_from_rest` | Dispatched via `UPLOAD_HANDLERS["security_assessment"]` (`upload_dispatch.py:93`) → `import_security_assessment_upload` |
| `license_summary` | system | ✅ (`latest.json` present today) | `data/catalog/license_summary/{latest.json, artifact_<uuid>.json}` plus `data/imports/license_summary/artifact_registry.sqlite3` + raw upload files | Dedicated `/quick-hc/license-summary/collect` (`quick_hc.py:293`) → `LicenseSummaryService.collect_from_rest` | Dispatched via `UPLOAD_HANDLERS["license_summary"]` (`upload_dispatch.py:100`) → `import_license_summary_upload` |
| `backup_job_summary` | system | ❌ | `data/catalog/quickhc/backup_job_summary_latest.json` (read via `load_backup_job_summary_artifact`, `reportsplus/backup_job_summary.py:189`) | Generic `/quick-hc/<subject_id>/collect` — `has_section_instructions=1`, Collect button present | None |
| `capacity_license` | system | ❌ | `data/catalog/metrics/capacity_license_usage.json` (read via `get_capacity_license_usage`, `metrics/capacity.py:26`) | Generic `/quick-hc/<subject_id>/collect` — `has_section_instructions=1` | None |
| `client_growth` | system | ❌ | `data/catalog/metrics/client_count_history.json`, `client_growth_summary.json`, `client_growth_details.json` (read via `get_client_*` in `metrics/growth.py:40-73`) | Generic `/quick-hc/<subject_id>/collect` — `has_section_instructions=1` | None |
| `cloud_storage_egress_ingress` | ai | ❌ | None — AI subject, no legacy on-disk path | None (no REST collection) | Generic dispatcher (`_unified_dispatcher_upload` → `extract_file` → `ArtifactStore.save_artifact`) |
| `storage_utilization` | ai | ✅ (`latest.json` present today) | None | None | Generic dispatcher |

Subject IDs are underscored throughout (DB, code, fragment URLs). The hyphenated forms (`/quick-hc/security-assessment/collect`, `/quick-hc/license-summary/collect`) are URL aliases for two legacy routes only — see Section 5.

---

## Section 3 — Read paths

### Request → active project → ArtifactStore (resolver layer)
`src/cvhealthcheck/web/active_project.py`

Every read of a project-scoped artifact passes through this resolver. The flow:

1. **Session lookup.** `get_active_project()` reads `session['active_project']` (a `{'customer_id': ..., 'project_id': ...}` dict written by `set_active_project()` and the project-creation handler). Returns the pair if present.
2. **Default fallback.** If no session entry exists, `resolve_default_project(db)` queries `projects WHERE customer_id = 'default' ORDER BY created_at ASC LIMIT 1` and returns its `(customer_id, project_id)`. Migration 0005 guarantees this Default customer + project exist; the fallback raises `ActiveProjectMissingError` if either was deleted, but that path is not expected under normal operation.
3. **Store construction.** `make_active_project_store(db)` (and its sibling `make_default_project_store(db)` for non-request callers like MCP staging) calls the resolver and returns an `ArtifactStore(customer_id, project_id)`. The store is bound to that project for the lifetime of the call.
4. **Reads.** All canonical-store reads in the codebase now go through these helpers, never through a bare `ArtifactStore()` constructor (which would now raise — customer/project are required positional args).

`_canonical_store()` in `subject_data_service.py:14` is the wrapper that legacy callers use: it imports `make_active_project_store` lazily and returns a fresh store on every call (no module-level singleton, so per-request scoping is automatic).

### `build_subject_initial_data(db)` — workspace tile builder
`src/cvhealthcheck/quickhc/subject_data_service.py:70-134`

For each tile from `get_tiles(db)`:

1. **`_load_from_canonical_store(subject_id)`** → reads `data/catalog/artifacts/<customer>/<project>/working/<subject_id>/latest.json` via `make_active_project_store().load_latest_artifact()` (`subject_data_service.py:168-175`). The active project is resolved through the layer above; the read is project-scoped. Returns `CanonicalArtifact` or `None`.
2. If artifact exists → `_build_generic_subject(tile, artifact)`.
3. Else if a `_legacy_builders` entry exists for `subject_id` → run the legacy loader for that subject, then the legacy builder.
4. Else (AI subjects with no canonical artifact, when `db is not None`) → `_build_generic_subject(tile, None)`.
5. The commcell header always comes from `_load_legacy_commcell()` (reads `data/catalog/rest/commserv.json`, `subject_data_service.py:311-320`), independent of the per-subject branch and customer-agnostic.

### `_load_from_canonical_store(subject_id)`
`src/cvhealthcheck/quickhc/subject_data_service.py:168-175`

Constructs an active-project store on each call and reads its `latest.json` for the given subject. Catches `FileNotFoundError` → returns `None`. No legacy fallback inside this function — fallback is at the caller (see above).

### `_build_generic_subject` + `_build_generic_sources`
`src/cvhealthcheck/quickhc/subject_data_service.py:264-296` and `subject_data_service.py:194-262`

Builds the subject view from a `CanonicalArtifact` (passed in) by:

1. `artifact.model_dump(mode="json")` to a dict (`subject_data_service.py:295`), threaded to `_build_generic_sources` as `artifact_payload`.
2. `_build_generic_sources` consults `get_provenance_builder(subject_id)` from `source_provenance_dispatch.py` first. If a builder is registered (currently `security_assessment`, `license_summary`), the builder is called with the artifact payload and its output is adapted to the tile-source schema by `_provenance_to_tile_sources` (`subject_data_service.py:218-249`). Otherwise the existing catalog-table logic runs (consumes `tile["sources"]` rows from `get_tiles`, which itself reads `subject_sources` + derived `has_section_instructions` from `app.db`).
3. No on-disk reads inside `_build_generic_subject` beyond what the caller already did to obtain the artifact.

### `_legacy_loaders` and `_legacy_builders`
`src/cvhealthcheck/quickhc/subject_data_service.py:371-415`

Per-subject loaders (called only when `_load_from_canonical_store` returns `None`):

| Loader | Reads |
|---|---|
| `_load_legacy_commcell` | `data/catalog/rest/commserv.json` (`subject_data_service.py:311`) |
| `_load_legacy_security_assessment` | `data/catalog/security_assessment/latest.json` via `security_assessment_quick_hc()` (`reportsplus/security_assessment.py:106-124`, which calls `load_security_assessment_artifact()`) |
| `_load_legacy_license_summary` | `data/catalog/license_summary/<artifact-or-latest>.json` via `LicenseSummaryService().get_current()` → `load_active_license_summary_artifact` (`license_summary/service.py:71-88`, `service.py:311`) |
| `_load_legacy_client_growth` | `data/catalog/metrics/client_growth_summary.json` (and friends) via `get_client_growth_summary(live=False)` |
| `_load_legacy_capacity_license` | `data/catalog/metrics/capacity_license_usage.json` via `get_capacity_license_usage(live=False)` |
| `_load_legacy_backup_job_summary` | `data/catalog/quickhc/backup_job_summary_latest.json` via `load_backup_job_summary_artifact()` |

Each builder then composes its subject view from this legacy dict (these are the "custom view shapes" ADR 0001 documents).

### Provenance builders
`src/cvhealthcheck/quickhc/source_provenance.py`

These functions are pure transforms — they do not touch disk directly. Their input is the artifact dict already loaded by their caller.

| Builder | Caller(s) today |
|---|---|
| `build_security_assessment_provenance` (`source_provenance.py:168`) | `_provenance_to_tile_sources` via `get_provenance_builder("security_assessment")` (`subject_data_service.py:251`); receives `artifact.model_dump()` |
| `build_license_summary_provenance` (`source_provenance.py:109`) | Same path as above, keyed by `license_summary` |
| `build_backup_job_summary_provenance` (`source_provenance.py:70`) | `quick_hc.py:296` — the `/quick-hc/backup-job-summary` GET; receives `load_backup_job_summary_artifact()` output |
| `build_commcell_provenance` (`source_provenance.py:218`) | `quick_hc.py:235` — the `/quick-hc/commcell` GET; receives REST `get_commcell_identity(...)` or cached `read_json("commserv.json", ...)` |
| `build_metric_provenance` (`source_provenance.py:254`) | `web/routes/development.py:143, 169, 186` — internal metric detail pages |

### `/api/quick-hc/*` endpoints
`src/cvhealthcheck/web/routes/quick_hc_api.py:61-117`

| Endpoint | Reads |
|---|---|
| `GET /api/quick-hc/status` | `build_subject_initial_data()` (same read paths as above) |
| `GET /api/quick-hc/subject/<id>` | `build_subject_initial_data()` then filter |
| `POST /api/quick-hc/subject/<id>/description` | Writes `data/catalog/quickhc/descriptions/<id>.json` via `save_description_override` (`description_service.py:46-67`) |
| `GET /api/security-assessment/canonical` | `SecurityAssessmentService().get_canonical()` → `make_active_project_store().load_latest_artifact("security_assessment")` (project-scoped) |
| `GET /api/license-summary/canonical` | `LicenseSummaryService().get_canonical()` → `make_active_project_store().load_latest_artifact("license_summary")` (project-scoped) |

---

## Section 4 — Write paths

### `ArtifactStore.save_artifact`
`src/cvhealthcheck/artifacts/store.py:58-71`

The single canonical-store writer. **Writes only to `working/`** under the bound `(customer_id, project_id)`:
- `data/catalog/artifacts/<customer>/<project>/working/<T>/<timestamp>.json` (append-only snapshot)
- `data/catalog/artifacts/<customer>/<project>/working/<T>/latest.json` (mirror — atomically overwritten)

ArtifactStore deliberately exposes no write method for `finalized/<n>/`; that's a class-level invariant backing ADR 0002's application-layer immutability.

Callers (all go through `make_active_project_store()` or `make_default_project_store()` rather than constructing `ArtifactStore` directly — bare `ArtifactStore()` raises since customer/project are required):
- `persist_security_assessment_artifact` (when source_type is import-shaped; `security_assessment/service.py:378`)
- `persist_license_summary_artifact` (always — also `service.py:132, 192`)
- `SecurityAssessmentService.collect_from_rest` (`security_assessment/service.py:180`) — REST collection saves canonical directly via `adapt_reportsplus_rest`
- `_unified_dispatcher_upload` (`web/routes/quick_hc.py`) — AI/user uploads
- `execute_approval` in MCP staging (`db/staging.py:172`) — promotes a staged artifact; uses `make_default_project_store()` since MCP is not request-scoped

### `finalize_project` (writes `finalized/<n>/`)
`src/cvhealthcheck/db/finalizations.py:91-147`

**The only code path in the project that writes under `finalized/<n>/`.** Application-layer immutability is enforced by this being the sole writer; no `ArtifactStore` method nor any other module touches the finalized subtree.

For a `(customer_id, project_id)`:
1. Computes next `finalization_number` = `MAX(finalization_number) + 1` over existing rows for the project, starting at 1.
2. Copies every `working/<subject>/` subdirectory to `finalized/<n>/<subject>/` via `shutil.copytree`. Full subtree (timestamps + `latest.json`).
3. Inserts a `finalizations` row capturing the project's `assigned_consultant` (as `finalized_by`) and `ticket_reference` at finalize-time, so the audit row is stable even if the project row is later edited.

Raises `FinalizationError` if the project has no subjects in `working/` or doesn't exist in the DB.

### `reload_latest_finalization` (writes `working/`)
`src/cvhealthcheck/db/finalizations.py:149-201`

Restores the latest finalization back into `working/`. Clears `working/` (every subject directory), then copies every subject from `finalized/<max(n)>/` back. Bumps `projects.working_state_modified_at`. Returns the finalization number that was reloaded.

Raises `FinalizationError` if the project has no finalizations.

### `persist_security_assessment_artifact`
`src/cvhealthcheck/security_assessment/service.py:250-381`

Writes (when `write_legacy=True`, the default):
- `data/catalog/security_assessment/artifact_<uuid>.json` (snapshot)
- `data/catalog/security_assessment/<artifact-name>_latest.json` (source-type-specific latest)
- `data/catalog/security_assessment/latest.json` (subject latest)
- `data/imports/security_assessment/artifact_registry.sqlite3` (`artifacts` + `import_runs` rows) via `SecurityAssessmentArtifactRegistry`
- `data/catalog/artifacts/security_assessment/{timestamp,latest}.json` via `ArtifactStore.save_artifact` (only when `source_type ∈ {html, csv, json}`; see `service.py:374-379`)

When `write_legacy=False` (the path `import_security_assessment_upload` uses), only the canonical-store write happens.

### `persist_license_summary_artifact`
`src/cvhealthcheck/license_summary/service.py:196-?`

Same dual-store shape as SA. Writes legacy paths (`data/catalog/license_summary/...` + per-subject `data/imports/license_summary/artifact_registry.sqlite3`) when `write_legacy=True`; always writes the canonical store via `_artifact_store.save_artifact(_adapt_license_summary(persisted))` (`service.py:132, 192`).

### `SecurityAssessmentService.collect_from_rest`
`src/cvhealthcheck/security_assessment/service.py:160-181`

REST collection path. Calls `extract_security_assessment(...)` → `adapt_reportsplus_rest(...)` → `_artifact_store.save_artifact(canonical)`. Writes only to the canonical store. Note: the REST extraction itself (`reportsplus/security_assessment.py:57`) also calls `persist_security_assessment_artifact(normalized, write_legacy=False)` and `write_json` into `data/catalog/reportsplus/report_336_security_assessment_normalized.json`.

### `LicenseSummaryService.collect_from_rest`
`src/cvhealthcheck/license_summary/service.py:93-?`

REST collection. Calls `collect_license_summary_rest(...)` → `persist_license_summary_artifact(..., write_legacy=False)` → canonical store via the persist function's internal call.

### Metric collectors
`src/cvhealthcheck/metrics/`

- `get_capacity_license_usage(live=True)` writes `data/catalog/metrics/capacity_license_usage.json` via `metrics/common.py:57` (`write_json(f"{name}.json", payload, catalog_dir=METRICS_CATALOG_DIR)`).
- `get_client_count_history(live=True)`, `get_client_growth_summary(live=True)`, `get_client_growth_details(live=True)` write `data/catalog/metrics/{name}.json` analogously via `metrics/growth.py:40-73`.
- These are invoked from `web/routes/development.py:137-188` (the internal metric pages) with `live=True`. Quick HC's workspace tile loaders pass `live=False` and only read.

### Backup-job summary writer
`src/cvhealthcheck/reportsplus/backup_job_summary.py:182-187`

Writes `data/catalog/quickhc/backup_job_summary_latest.json` via `write_json(...)`. Callers are the Reports Plus collection paths (CLI + dev pages).

### CommCell REST cache writer
`src/cvhealthcheck/quickhc/commcell.py:42`

`write_json("commserv.json", payload, catalog_dir=catalog_dir)` — the only writer for `data/catalog/rest/commserv.json`. Triggered from the CommCell-identity refresh paths.

### MCP staging tools
`src/cvhealthcheck/mcp/server.py`

| Tool | Writes |
|---|---|
| `approve_staged_artifact` | Publishes a pending **subject_proposal** into the catalog: `subjects` row + sibling tables via `create_subject_from_proposal`, then marks the staging row approved. (Artifact approval was removed in the ADR-0015 redesign slice 1 — collection writes evidence directly to the scoped store, so `save_staged_artifact` and the artifact-approval branch no longer exist.) |
| `reject_staged_artifact` (`server.py:280`) | Marks staging row rejected (no canonical-store write) |
| `propose_new_subject` (`server.py:299`) | Creates a `staged_artifacts` row of type `subject_proposal` |

### Description-override writer
`src/cvhealthcheck/quickhc/description_service.py:46-67`

`POST /api/quick-hc/subject/<id>/description` writes `data/catalog/quickhc/descriptions/<tile_id>.json`.

### Lab-readiness writer
`src/cvhealthcheck/labreadiness/evaluator.py:15-31`

`assess_lab_readiness(write=True)` writes `data/labreadiness/latest.json`. Invoked from `web/routes/development.py:95` (internal page) and `cli.py`.

---

## Section 5 — The forks, named explicitly

### Source-building fork (ADR 0001)
**Where:** `src/cvhealthcheck/quickhc/subject_data_service.py:60-124` (the dispatch); `_legacy_builders` (`subject_data_service.py:401-415`); `_build_generic_subject` (`subject_data_service.py:264-296`).
**Why it exists:** the frozen `CanonicalArtifact` schema cannot represent the legacy-shape sections (`counters`, `findings_grid`, `workload`, `chart_growth`) the six system subjects render. Source: `docs/adr/0001-source-building-fork.md` (Decision section, lines 22-32). Full inventory of why each subject can't be unified: `docs/refactor_unified_upload_session_3b_inventory.md`.

### Provenance dispatch fork (recent)
**Where:** `src/cvhealthcheck/quickhc/source_provenance_dispatch.py` (the dispatch table); consumed by `_build_generic_sources` at `subject_data_service.py:251`.
**Why it exists:** SA and LS REST collection is implemented in dedicated Python services (`SecurityAssessmentService.collect_from_rest`, `LicenseSummaryService.collect_from_rest`) rather than described by `subject_section_sources` rows, so the catalog-data path that drives the generic tile-source builder can't tell their REST source is implemented. Source: `CHANGELOG.md` entry "2026-05-26 (post-5b regression fix — source-provenance dispatch)".

### Option A read fallback
**Where:** `src/cvhealthcheck/security_assessment/service.py:87, 384` (`load_active_security_assessment_artifact`); `src/cvhealthcheck/license_summary/service.py:80, 311` (`load_active_license_summary_artifact`).
**Why it exists:** legacy artifact-store reads were preserved even after production writes moved to canonical-only, because the legacy stores still hold historical artifacts that external readers (and the legacy builders) depend on. Source: `docs/adr/0001-source-building-fork.md:40` ("Legacy artifact-store reads continue to work (Option A invariant from 2026-05-27)"). Production callers pass `write_legacy=False` (`security_assessment/service.py:237`, `license_summary/service.py:130, 190`, `reportsplus/security_assessment.py:57`); the persist functions still accept the parameter for test fixtures.

### Upload-dispatch fork (session 5b)
**Where:** `src/cvhealthcheck/web/routes/upload_dispatch.py`; consumed at `quick_hc.py:357`.
**Why it exists:** SA and LS have subject-specific upload behavior (form field name, import function, success-message format) that doesn't fit into row-shaped catalog data without a schema migration. Source: `docs/refactor_unified_upload_session_5a_design.md` Section 7 (Option δ); `CHANGELOG.md` entries "2026-05-26 (session 5b)" and Section 6 of the design doc.

### Working/finalized split (ADR 0002 phase 5)
**Where:** `src/cvhealthcheck/artifacts/store.py` (write-only to `working/`); `src/cvhealthcheck/db/finalizations.py:finalize_project` (write-only to `finalized/<n>/`); `reload_latest_finalization` copies finalized → working.
**Why it exists:** delivered reports need to be auditable as immutable artifacts. The working subtree is mutable (the consultant edits freely); the finalized subtrees are frozen snapshots written exactly once at finalize-time. Immutability is application-layer (no filesystem chmod): the constraint is "ArtifactStore exposes no method that writes to `finalized/`" and "`finalize_project` is the only function in the codebase that writes there." This is an instance of the project-wide *writes converge to canonical / reads stay diverse* pattern documented in `docs/PATTERNS.md`. Source: `docs/adr/0002-customer-and-project-entities.md` (Immutability section); CHANGELOG entry "2026-05-27 (ADR 0002 phase 5)".

---

## Section 6 — Surprises and inconsistencies

These are observations from the audit. Nothing was changed.

### 1. AI-subject canonical artifacts live under the active project, same as system subjects

Pre-ADR-0002 there was exactly one canonical path per subject globally (`data/catalog/artifacts/<subject>/`). Post-phase-2 every subject's canonical artifact lives under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. The previous edition of this audit flagged `storage_utilization` (an AI subject) as the only one with a non-SA/LS canonical artifact at the old global path; that observation is moot now — the layout is uniform across created_by values. The interesting follow-on: an AI subject collected under one project is invisible from another project's workspace. Tests pin this contract in `tests/test_project_scoped_artifacts.py`.

### 2. The legacy SA/LS stores are still actively populated by `write_legacy=True` callers

Production callers (the unified upload route's import handlers, REST collection) pass `write_legacy=False` and skip the legacy-store writes — they only write the canonical store via `ArtifactStore.save_artifact` (now project-scoped). But the `persist_*_artifact` functions still accept `write_legacy=True` for tests and legacy callers, which means `data/catalog/security_assessment/` and `data/catalog/license_summary/` continue to accumulate `artifact_<uuid>.json` files across test runs and any legacy code path. The files are globally scoped (no customer/project segment) and never cleaned up. Backlog item #15 covers project-scoping these stores; backlog Section 6 #2 carry-over covers the accumulation.

### 3. `data/catalog/reportsplus/` has 203 entries today

Most are `report_<id>_raw_<dataset_guid>.json` files — raw extraction outputs kept per-dataset-execution. Written by `reportsplus/extract_report.py:546-558` and `reportsplus/metric_inventory.py:62`. Consumers I found: `data/catalog/datasets.json` builder, `labreadiness/collector.py:28`. No retention policy visible — the directory grows with every dataset extraction. Worth flagging because it can dominate disk usage on a long-running install. Not unread, but probably under-managed.

### 4. (Retracted)

This entry originally claimed `data/catalog/metrics/client_growth_summary.json` was absent from the working tree. That was an audit error — the `ls | head -3` invocation truncated the directory listing and hid the 4th entry. The file is present (2128 bytes, dated 2026-05-13) and the `client_growth` tile renders correctly: `state=ok`, subtitle "5 clients", 3 sections (summary, chart, monthly_table). All four metric files are present:

| File | Size | Reader |
|---|---|---|
| `capacity_license_usage.json` | 2647 B | `get_capacity_license_usage(live=False)` (`metrics/capacity.py:26`) |
| `client_count_history.json` | 2125 B | `get_client_count_history(live=False)` (`metrics/growth.py:40`) |
| `client_growth_details.json` | 900 B | `get_client_growth_details(live=False)` (`metrics/growth.py:73`) |
| `client_growth_summary.json` | 2128 B | `get_client_growth_summary(live=False)` (`metrics/growth.py:52`) |

Lesson for future audits: use `ls -1` or `find` for completeness checks, never `ls | head -N`.

### 5. `data/labreadiness/latest.json` is written but has no production reader visible

`assess_lab_readiness(write=True)` writes `data/labreadiness/latest.json` (`labreadiness/evaluator.py:30-32`). Callers: `cli.py:8` (CLI command) and `web/routes/development.py:95` (internal dev page). The Quick HC workspace doesn't read it; neither does any `/api/*` endpoint. The CLI also reads it back. So it functions as a CLI-only artifact; nothing in the web app depends on it. Worth knowing because the dev page advertises it as "lab readiness" but the workspace doesn't surface it.

### 6. Two separate SQLite registries alongside `data/app.db`

`data/imports/security_assessment/artifact_registry.sqlite3` and `data/imports/license_summary/artifact_registry.sqlite3` each carry their own `artifacts` + `import_runs` tables (schemas are SA/LS-specific). Production code in `import_*_upload` passes `write_legacy=False`, so these registries are only updated by test fixtures and legacy paths. They exist on disk (~few KB each) and are likely effectively read-only in production today. Not in `app.db`'s migration tracking; a different mental model.

### 7. The hyphenated route for `quick_hc_security_assessment` (`quick_hc.py:232-251`) and `quick_hc_license_summary` (`quick_hc.py:269-288`) GET handlers are now pure redirects with subject fragments

After today's fragment fix, these legacy GET handlers serve only as the indirection through which SA/LS upload/collect chains land on `/quick-hc#subject=<id>`. They no longer render any content. Deleting them would require all redirect-endpoint references in `upload_dispatch.py` (lines 98, 105) and within the collect handlers (`quick_hc.py:255, 258, 276, 311, 314, 327`) to point at `main.quick_hc` directly with the fragment — feasible cleanup, not done.

### 8. `data/catalog/datasets.json` is 84 KB and `data/catalog/datasets_summary.json` is 3 KB, but only the CLI writes them

`cli.py:138-242` reads and writes both. `labreadiness/collector.py:28` and `web/routes/development.py:422` read `datasets.json`. The Quick HC workspace doesn't touch either. So they exist as CLI-curated dataset inventory snapshots — not regenerated by the web app, only by explicit CLI invocation. If a fresh install ran the web app without ever running the CLI, neither file would exist; nothing in the web app would break (lab readiness page would 404-ish via `catalog_status`, but lab readiness is a dev page).
