# Changelog

All notable changes to cv-healthcheck are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
DEVLOG.md holds detailed in-session notes; this file is the curated session-by-session summary.
Past entries are never deleted or rewritten — corrections are made by adding a new entry.

## [Unreleased]

Working branch: `feature/basic-healthcheck-report-output`.
Not yet merged to `main`.

### Added

- `docs/HANDOVER.md` — always-current single-file handover for the next session.
- `CHANGELOG.md` (this file) — curated session-by-session summary.

## 2026-05-25

Commits: `9073f06`
Test status: 461 passing

### Added

- Versioned SQL migration runner at `src/cvhealthcheck/db/migrations/__init__.py`, with `0001_initial`, `0002_staged_artifacts`, `0003_report_inventory`, `0004_rest_instructions_and_constraints` migrations.
- `subjects` / `subject_sections` / `subject_sources` / `subject_section_sources` / `collector_schemas` tables seeded with the six system tiles.
- `src/cvhealthcheck/db/subjects.py` — CRUD for the subject catalog plus `create_subject_from_proposal()`.
- Generic extractor pipeline under `src/cvhealthcheck/extractors/` (`dispatcher`, `html`, `csv`, `rest`, `recognition`, `result_to_artifact`), driven by `subject_section_sources` instructions.
- `/quick-hc/import` generic upload endpoint routing through `extract_file()`.
- MCP staging workflow: `propose_new_subject` and `list_proposed_subjects` tools, plus subject-proposal handling in `execute_approval()`.
- Staging review UI at `/quick-hc/staging`.
- Quick HC standalone dark UI (`quick_hc.html` no longer extends `base.html`).
- `subject_data_service.build_subject_initial_data()` returning `{commcell, cats, report_url}`.
- ~14 new test modules: `core_solidity`, `db_staging`, `db_subjects`, `delete`, `extractor_csv`, `extractor_html`, `import_flow`, `mcp_tools`, `migrations`, `recognition`, `rest_extractor`, `staging_routes`.
- `docs/handover/HANDOVER_2026-05-25.md` — detailed session handover with documentation audit and open-issues list.

### Changed

- `create_app()` now runs `run_migrations()` instead of the deprecated `init_db()`.
- Quick HC sidebar reads subjects from the DB via `get_tiles(db)` instead of the static `QUICK_HC_TILES` tuple; AI-proposed subjects now appear alongside system tiles.
- Quick HC connection badge: always shows `Connect` when unauthenticated and `Connected` when authenticated (removed the "6 available" branch).
- Quick HC report action bar moved from the top of the main panel to the bottom; visible only when at least one subject is included.
- `canonical_view.artifact_to_view()` now uses `tile["title"]` from the registry for the sidebar display name, so stale `artifact.subject.title` provenance (e.g. "Test Subject") no longer leaks into the UI.
- HTML extractor section-title matching accepts both exact match and `"<title> -"` / `"<title>:"` prefix forms.
- Test count rose from 343 to 461.

### Fixed

- Test pollution: `execute_approval()` was writing test artifacts to the real `data/catalog/artifacts/security_assessment/latest.json` on every `pytest` run. Added an optional `store` parameter; `test_execute_approval_artifact` now injects its `tmp_path` store.
- License Summary "No data" state: `canonical_view.license_summary_to_view` now accepts both short and fully-qualified section IDs (`other_licenses` and `license_summary.other_licenses`).
- Table-only canonical artifacts with non-empty rows now resolve to `ArtifactStatus.good` instead of `unknown`, so the sidebar shows "ok" not "nodata".

### Known limitations carried forward

- Section IDs are double-prefixed in `canonical_view` (`security_assessment.security_assessment.access_security`). Display titles are correct; the ID mismatch leaks into localStorage keys.
- Legacy `data/catalog/<subject>/latest.json` still written alongside canonical `data/catalog/artifacts/<subject>/latest.json`.
- `data/app.db` is tracked by git; should be moved to `.gitignore` in a follow-up.
- Stale 955-byte test-pollution artifacts in `data/catalog/artifacts/security_assessment/` from before the `execute_approval` fix — inert, but worth cleaning with `find data/catalog/artifacts/security_assessment -size 955c -delete`.

## Earlier history

See `DEVLOG.md` for the in-session detail trail before 2026-05-25.
Key milestones:

- 2026-05-24 — `TileDefinition` gained `category`, `category_label`, `import_url`, `collect_url`; canonical-view wiring for Security Assessment and License Summary; `data/app.db` added for business state.
- 2026-05-23 — Retired `/quick-hc/security-assessment` and `/quick-hc/license-summary` detail pages; both now redirect to `/quick-hc`.
- 2026-05-22 — Registry made authoritative for Security Assessment detail sections; cross-tile regression guard added.
- 2026-05-19 — Quick HC promoted to the main customer-facing report-composition surface; `QuickHcReportService` introduced.
- 2026-05-18 — Basic Quick HC HTML report at `/quick-hc/report`.
