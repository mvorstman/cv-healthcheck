---
name: Quick HC UI Rebuild
description: New standalone dark-panel UI for /quick-hc, implemented 2026-05-20
type: project
---

Replaced the quick_hc.html template (which extended base.html) with a standalone dark split-panel UI matching the `design/quick_hc_v7.html` prototype.

**Why:** Design required a full-page layout (fixed header + left nav + right panel) that doesn't fit inside the base.html sidebar structure.

**How to apply:** The new quick_hc.html is standalone — do not add `extends base.html`. All data comes from `window.QUICK_HC_INITIAL_DATA` injected by Flask.

## New files
- `src/cvhealthcheck/web/static/quick_hc.css` — dark design tokens, IBM Plex Sans/Mono
- `src/cvhealthcheck/web/static/quick_hc.js` — left nav render, config view, localStorage state, generate form POST
- `src/cvhealthcheck/web/templates/quick_hc.html` — standalone HTML, injects `initial_data | tojson`
- `src/cvhealthcheck/quickhc/subject_data_service.py` — `build_subject_initial_data()` builds CATS structure
- `src/cvhealthcheck/web/routes/quick_hc_api.py` — `GET /api/quick-hc/status`, `GET /api/quick-hc/subject/<id>`

## Data flow
- `quick_hc()` route calls `build_subject_initial_data()` → returns `{commcell, cats}` as `initial_data`
- JS reads `window.QUICK_HC_INITIAL_DATA.cats` for nav and config views
- Include/section state persisted in `localStorage` key `quickhc-state-v1`
- "Generate" button builds hidden form with `selection_ids` inputs and POSTs to `/quick-hc/report`

## Section types supported in JS secBody()
`meta`, `counters`, `findings_grid`, `findings_list`, `workload`, `table`, `chart_growth`, `chart_capacity`, `text`

## Known data quality notes
- Capacity license records use `-1.0` as sentinel for "no data" — treated as 0 in chart aggregation
- `workload_summary_sections` may be empty in some license summary artifacts (normal)
