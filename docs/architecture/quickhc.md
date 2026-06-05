# Quick HC architecture

Quick HC is the customer-facing report-composition surface. The operator opens `/quick-hc`, chooses which subjects and sections appear in the customer-facing report, and composes the result at `/quick-hc/report`.

## Product surface

The application is organized into four product areas:

- **HealthCheck** — the primary workspace; Quick HC is its customer-facing output.
- **Customers** — business/customer and engagement state.
- **Advanced** — deeper workflows outside the default HealthCheck path.
- **Development** — raw/debug/API/report exploration: lab readiness, Reports Plus inventory, report extraction, dataset execution, registry views, and validation tools.

Navigation is simple and product-oriented, and customer-facing pages stay visually separate from internal/development pages.

## Subjects

Quick HC subjects:

- CommCell Details
- Security Assessment (see [../subjects/security_assessment.md](../subjects/security_assessment.md))
- License Summary (see [../subjects/license_summary.md](../subjects/license_summary.md))
- Client Growth
- Capacity Licenses
- Backup Job Summary

Each subject provides an expandable tile on `/quick-hc`, customer-facing preview content in the tile body, a parent include/exclude control, nested section/table selection, and composition into `/quick-hc/report`.

CommCell Details collects CommCell identity/version from `GET /commandcenter/api/CommServ`, normalizing `hostName`, `csGUID`, `csVersionInfo`, `releaseId`, `osType`, and `timeZone` into `data/catalog/rest/commserv.json`.

## Routing model

Uploads and collection go through a unified routing layer:

- `POST /quick-hc/<subject_id>/import` — the sole upload route. Subject IDs are underscored (`security_assessment`, `license_summary`, …). System subjects with dedicated import functions are dispatched via `src/cvhealthcheck/web/routes/upload_dispatch.py`; AI subjects fall through to the generic dispatcher.
- `POST /quick-hc/<subject_id>/collect` — the generic REST-collection route (runs `RESTExtractor` against `subject_section_sources` rows in the catalog DB).
- `POST /quick-hc/security-assessment/collect` and `POST /quick-hc/license-summary/collect` — dedicated REST-collection endpoints for SA and LS (hyphenated; their collection is hardcoded in Python services rather than catalog-described).
- `GET /quick-hc/security-assessment` and `GET /quick-hc/license-summary` redirect to `/quick-hc#subject=<id>` so the JS workspace re-opens the right tile after a full-page reload.

Report-layout selection is remembered in the browser with `localStorage`. There is no server-side saved profile or database persistence for report layouts.

## Report composition

`/quick-hc/report` renders only the selected subjects and selected nested sections. The composition pipeline is assembled through `QuickHcReportService`, which keeps filtering logic out of Jinja templates.

Report output covers CommCell Details environment metadata; Security Assessment summary counters, critical/warning highlights, and an optional all-findings section; License Summary workload sections, other-license detail tables with compact usage summaries, and agent/feature detail tables; Client Growth summary metrics, Chart.js history, and monthly summary table; and Capacity Licenses summary and latest table.

Customer-facing report rules — the report carries no internal detail:

- no artifact paths
- no dataset GUIDs
- no HTTP status values
- no raw/debug extraction fields
- evidence and source metadata stay internal only

## UI shell

The Flask surface is a product shell, not isolated pages:

- app-shell layout with sidebar and topbar
- sidebar navigation (`Connect to CS`, `Quick HC`, `Development`) with active states
- global design tokens and a light/dark theme toggle with persisted preference
- a topbar Back action that prefers browser history and falls back to `/quick-hc`
- responsive shell behavior

Quick HC uses full-width expandable subject tiles, per-section cards, nested include/exclude controls, and theme-aware customer-facing previews. Detail pages use a standardized Source Provenance block so supported acquisition paths are visible consistently across tiles: available/validated sources render active; unavailable, not-implemented, not-tested, or not-applicable sources render muted rather than hidden.

## Framework

```text
src/cvhealthcheck/quickhc/
  models.py
  registry.py
  report_service.py
  overview_service.py
  canonical_view.py

src/cvhealthcheck/web/templates/
  quick_hc.html
  partials/
    quickhc_tile.html
    quickhc_section_card.html
    quickhc/previews/
      commcell.html
      security_assessment.html
      license_summary.html
      client_growth.html
      capacity_license.html
```

Tile and section metadata flow through shared dataclasses and a central registry, so a subject is described in one place rather than duplicated across routes, templates, and report composition:

- `TileDefinition` — subject-level metadata: tile ID, title, subtitle/description, source type, service name, artifact type, preview renderer name, report renderer name, category/category label, detail endpoint, import URL, collect URL, and registry-derived section/default-selection helpers.
- `SectionDefinition` — nested report-section metadata: stable section ID, label, default-selection flag, and logical renderer names.

Module boundaries:

- `quickhc/models.py` — shared Quick HC metadata models only.
- `quickhc/registry.py` — the single source of truth for tile IDs, section IDs, labels, subtitles, default selections, and logical renderer names. Initial subject data is registry-driven through `registry.list_tiles()`, with explicit tile-id loader and builder dispatch.
- `quickhc/report_service.py` — backend report composition and filtering only.
- `quickhc/canonical_view.py` — translation layer from canonical artifacts into the Quick HC JavaScript view-model contract.
- `quickhc/overview_service.py` — overview-only preview shaping for the `/quick-hc` dashboard, including the explicit preview-renderer mapping that turns tile metadata into preview payloads.
- `web/routes/quick_hc.py` — thin route layer that passes already-shaped data into templates.
- `web/templates/quick_hc.html` — top-level overview composition only.
- `web/templates/partials/quickhc_tile.html` — reusable outer tile shell.
- `web/templates/partials/quickhc_section_card.html` — reusable nested section-card shell.
- `web/templates/partials/quickhc/previews/*.html` — subject-specific preview bodies only.

Import and collect action URLs come from `TileDefinition.import_url` and `TileDefinition.collect_url`; frontend forms render through initial subject data rather than hardcoding URLs in the template. Renderer orchestration is explicit Python-side mapping, not dynamic resolution of Jinja templates from registry values.

### Adding a subject

1. Add or update `TileDefinition` and `SectionDefinition` entries in `quickhc/registry.py`.
2. Register a preview builder and a report builder that consume the tile metadata contract instead of duplicating tile IDs or labels elsewhere.
3. Keep `report_service.py` as the backend source of filtered report data.
4. Add a subject preview partial when a new overview subject needs one.
5. Keep renderer orchestration explicit rather than dynamically resolving Jinja templates from registry values.

## Business state and persistence

Application/business state is separate from import registries and canonical artifact storage:

- `data/app.db` holds business/application state.
- `src/cvhealthcheck/db/` supports customers and engagements using raw SQL and lightweight schema/migration files.
- Import registries and canonical artifact storage are separate from `data/app.db`.
- Canonical artifact persistence stays under the artifact/import storage paths and service layers, not the business DB.

## Scope & boundaries

- Report output is HTML; there is no PDF export.
- Report-layout selection is browser-local (`localStorage`); there are no persisted report profiles.
- Scoring is row-scope evaluation rules on table subjects ([ADR 0010](../adr/0010-row-scope-evaluation-rules.md)); the Reports Plus subjects are not scored, and there are no recommendations.
- Runtime artifacts live outside git.
- Evidence provenance stays out of customer-facing report output.
