# Codex Handover — Quick HC UI Rebuild
**Prototype:** `quick_hc_v7.html`  
**Project path:** `~/dev/cv-healthcheck`  
**Flask port:** 5001  
**Date:** 2026-05-20

---

## 0. Ground Rules

- Read each file before touching it
- No new business logic — all data comes from existing services
- No database changes — file-based artifacts only
- Preserve all existing routes
- The prototype (`quick_hc_v7.html`) is the visual contract — match it exactly

---

## 1. What the Prototype Does

Three views, same right panel:

### Overview (default, clicking "Quick HC" title)
- Title: "Quick HealthCheck" + `cs01 · SP40.47`
- **Report Sections** — list of included subjects by category, each clickable
- **Compliance Status** — placeholder tile (not yet implemented)

### Configure (clicking any subject in left nav)
- Title: subject name + Configure button (which is now the same page — no separate subject view)
- **Description** — editable textarea (placeholder, not persisted)
- **Data Source** — 3 buttons (Direct REST API / REST Report / Import File) + active source metadata panel
- **Report Sections** — CommCell identity tile with "Include in report" checkbox + section tiles each with "Include in report" checkbox
- **Compliance** — placeholder tile

### Left Nav
- Category headers (Identity, Security, Licensing, Performance & Growth, Operations)
- Subject rows: include checkbox + name + state badge

---

## 2. Mapping to Existing Code

### 2.1 Routes — `src/cvhealthcheck/web/routes/quick_hc.py`

| Prototype element | Existing route | Status |
|---|---|---|
| Overview page | `GET /quick-hc` → `quick_hc.html` | **Replace template** |
| CommCell configure | `GET /quick-hc/commcell` | **Replace with new pattern** |
| Security Assessment configure | `GET /quick-hc/security-assessment` | **Replace with new pattern** |
| License Summary configure | `GET /quick-hc/license-summary` | **Replace with new pattern** |
| SA import | `POST /quick-hc/security-assessment/import` | **Keep as-is** |
| License import | `POST /quick-hc/license-summary/import` | **Keep as-is** |
| License collect | `POST /quick-hc/license-summary/collect` | **Keep as-is** |

**New routes needed:**
```
GET  /api/quick-hc/status                    # badge states for all subjects
GET  /api/quick-hc/subject/<id>              # subject data as JSON
POST /api/quick-hc/subject/<id>/include      # toggle include_in_report
POST /api/quick-hc/subject/<id>/section/<sec_id>/include  # toggle section include
GET  /api/quick-hc/report-config             # current include state for all
```

### 2.2 Data Sources — what each subject calls

| Subject | Existing service call | File |
|---|---|---|
| CommCell Details | `get_commcell_identity()` / `catalog_status()` | `shared.py` → `quickhc/` |
| Security Assessment | `security_assessment_quick_hc()` | `reportsplus/security_assessment.py` |
| License Summary | `_license_summary_quick_hc()` | `shared.py` → `license_summary/` |
| Client Growth | `get_client_growth_summary(live=False)` | `metrics/growth.py` |
| Capacity License | `get_capacity_license_usage(live=False)` | `metrics/growth.py` |

### 2.3 Section tiles — what renders inside each

Read these files before implementing section content:
- `src/cvhealthcheck/reportsplus/checklist.py` — `STATUS_ORDER`, `normalize_check()`
- `src/cvhealthcheck/reportsplus/security_assessment.py` — `SECTION_ORDER`, `security_assessment_quick_hc()`
- `src/cvhealthcheck/license_summary/models.py` — `LicenseSummaryArtifact`
- `src/cvhealthcheck/metrics/growth.py` — `get_client_growth_summary()`, `get_capacity_license_usage()`

### 2.4 Templates to replace

| File | Action |
|---|---|
| `templates/quick_hc.html` | **Replace entirely** with split-panel layout |
| `templates/quick_hc_commcell.html` | **Keep** — "Open full details →" links here |
| `templates/quick_hc_security_assessment.html` | **Keep** |
| `templates/license_summary.html` | **Keep** |
| `templates/base.html` | **Do not touch** |

---

## 3. New Files to Create

```
src/cvhealthcheck/web/
  templates/
    quick_hc.html              ← replace with prototype layout
  static/
    quick_hc.css               ← all CSS from prototype (extract from <style> tag)
    quick_hc.js                ← all JS from prototype (extract from <script> tag)
  routes/
    quick_hc_api.py            ← new JSON API routes
```

---

## 4. Architecture: Static vs Dynamic

The prototype is fully static (hardcoded data). The real implementation needs:

**Option A — Server-rendered (simplest, matches existing pattern):**
- Flask renders the shell (`quick_hc.html`) with Jinja
- JS fetches `/api/quick-hc/subject/<id>` for each subject's data
- Flask routes call existing services and return JSON

**Option B — Full SPA:**
- Single HTML page, all data via fetch
- More complex, not recommended given existing Flask pattern

**Recommendation: Option A.** Matches project architecture.

---

## 5. Subject Registry

The prototype hardcodes 5 subjects across 5 categories. In the real implementation this should come from a config — read `shared.py` to understand what's currently available.

Current subjects and their data availability:

| Subject | Data available | Source type |
|---|---|---|
| CommCell Details | ✅ | Direct REST API |
| Security Assessment | ✅ | REST Report (336) + Import |
| License Summary | ✅ | REST Report (206) + Import |
| Client Growth | ✅ | REST Report (318) |
| Capacity License | ✅ | REST Report (318) |
| Job Failures | ❌ Not yet implemented | — |
| SLA Compliance | ❌ Not yet implemented | — |

---

## 6. Include in Report — Persistence

The prototype toggles include state in JS memory only. For persistence:

**Simplest approach:** JSON file at `data/quickhc/report_config.json`
```json
{
  "subjects": {
    "commcell": {
      "included": true,
      "sections": {
        "cc_id": true,
        "cc_f": true
      }
    }
  }
}
```

This matches the project's file-based pattern. No database needed.

---

## 7. Source Configuration — Persistence

Same pattern — `data/quickhc/source_config.json`:
```json
{
  "commcell": {"active_source": "rest_api"},
  "security_assessment": {"active_source": "rest_report"},
  "license_summary": {"active_source": "import"}
}
```

---

## 8. CSS/JS Extraction from Prototype

The prototype is a single HTML file. Before implementing:

```bash
# Extract CSS (everything between <style> and </style>)
# Save to: src/cvhealthcheck/web/static/quick_hc.css

# Extract JS (everything between <script> and </script>)  
# Save to: src/cvhealthcheck/web/static/quick_hc.js

# The JS will need to be adapted:
# - Replace hardcoded data with fetch() calls to /api/quick-hc/...
# - Keep all rendering functions (renderLeft, openConfig, secTile, secBody etc.)
# - Keep all CSS classes exactly as-is
```

---

## 9. Step-by-Step Implementation Order

1. **Extract CSS/JS** from `quick_hc_v7.html` into static files
2. **Create `quick_hc.html`** — shell template with left nav + right panel, loads CSS/JS
3. **Create `/api/quick-hc/status`** — returns badge states (cheap file-existence checks)
4. **Wire up left nav** — JS fetches status on load, renders category/subject list
5. **Create `/api/quick-hc/subject/<id>`** — returns subject data JSON, calls existing services
6. **Wire up openConfig** — JS fetches subject data, renders configure page
7. **Create persist endpoints** — include toggles, source config
8. **Test each subject** in order: CommCell → Security Assessment → License Summary → Client Growth → Capacity License

---

## 10. Files to Read First (in order)

```bash
cat src/cvhealthcheck/web/routes/quick_hc.py
cat src/cvhealthcheck/web/routes/shared.py
cat src/cvhealthcheck/web/templates/quick_hc.html
cat src/cvhealthcheck/reportsplus/security_assessment.py
cat src/cvhealthcheck/license_summary/__init__.py
cat src/cvhealthcheck/metrics/growth.py
cat src/cvhealthcheck/health/model.py
```

---

## 11. Do Not

- Do not modify `base.html`
- Do not modify existing import/collect POST routes
- Do not add a database
- Do not add new Python dependencies
- Do not commit `.token` or `.refresh_token`
- Do not hardcode the CommServ IP — read from `config.py` / `load_settings()`

---

*Prototype file: `quick_hc_v7.html` — open in browser to see the target UI*  
*All rendering logic is in the `<script>` tag of that file*
