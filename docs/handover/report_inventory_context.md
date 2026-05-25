# cv-healthcheck: Report Inventory Context

*Design session handover — 2026-05-24*

This document is a factual extraction of the cv-healthcheck codebase as it stands on the `feature/basic-healthcheck-report-output` branch. It is intended to give a design session full context on the existing canonical artifact pipeline so that the scope of a Report Inventory feature can be set without revisiting the code from scratch.

---

## 1. Project overview

`cv-healthcheck` is a Flask web application plus a Model Context Protocol (MCP) server. Its purpose is to produce customer-facing health-check snapshots for Commvault environments. Data is collected either live (via the Commvault Command Center REST API / Reports Plus) or imported offline (CSV, HTML, JSON). Collected data is normalised into a *canonical artifact* contract (Pydantic v2) and persisted to disk. A Quick HC workspace renders these artifacts as a single-page tile dashboard; a report builder turns selected tiles into a downloadable report.

Entry points:

```
cv-healthcheck          → cvhealthcheck.cli:main  (Flask dev server)
cv-healthcheck-mcp      → cvhealthcheck.mcp.server:main  (FastMCP server)
```

---

## 2. File and directory inventory

```
src/cvhealthcheck/
├── __init__.py
├── api_client.py               CommvaultApiClient (requests wrapper)
├── artifact_registry.py        Helper lookups over QUICK_HC_TILES
├── cli.py                      Click CLI entry point
├── config.py                   Settings dataclass, load_settings()
├── adapters/
│   ├── commcell_details.py     adapt_rest() → CanonicalArtifact (commcell)
│   ├── license_summary.py      adapt() → CanonicalArtifact (license_summary)
│   └── security_assessment.py  adapt_reportsplus_rest() → CanonicalArtifact (security_assessment)
├── artifacts/
│   ├── enums.py                SourceType, ArtifactStatus, FindingSeverity, FindingStatus, ChartType
│   ├── exceptions.py           ArtifactNotFoundError
│   ├── models.py               CanonicalArtifact, all section types (Pydantic v2)
│   └── store.py                ArtifactStore (disk persistence, latest.json + timestamped)
├── auth/
│   └── commvault_auth.py       login_to_commvault(), Flask session token management
├── db/
│   ├── database.py             get_db(), init_db(), DB_PATH (anchored to project root)
│   ├── schema.sql              DDL: customers, engagements, staged_artifacts
│   ├── staging.py              CRUD functions for staged_artifacts table
│   ├── customers.py            CRUD for customers table
│   └── engagements.py          CRUD for engagements table
├── health/                     health model (unused in main flow)
├── labreadiness/               Lab readiness evaluator
├── license_summary/
│   ├── artifact.py             Build CanonicalArtifact from LS service output
│   ├── collect_rest.py         Live Reports Plus collection for license summary
│   ├── import_csv.py           Parse CSV export
│   ├── import_html.py          Parse HTML export
│   ├── models.py               Internal LS domain models
│   ├── normalize.py            Normalise raw rows
│   ├── service.py              LicenseSummaryService (get_current, save_artifact)
│   └── validate.py             Validation helpers
├── mcp/
│   └── server.py               FastMCP server with 6 tools
├── metrics/
│   ├── capacity.py             get_capacity_license_usage()
│   ├── common.py
│   └── growth.py               get_client_growth_summary()
├── output/
│   └── json_report.py          JSON report serialisation
├── quickhc/
│   ├── canonical_view.py       CanonicalArtifact → frontend view dict
│   ├── commcell.py             normalize_commserv()
│   ├── description_service.py  resolve_tile_description()
│   ├── models.py               TileDefinition, SectionDefinition, SourceDefinition, CommCellIdentity
│   ├── overview_service.py     build_overview()
│   ├── registry.py             QUICK_HC_TILES tuple, all section ID constants
│   ├── report_service.py       QuickHcReportService.build_report()
│   ├── source_provenance.py    Build source provenance dicts for detail pages
│   └── subject_data_service.py build_subject_initial_data() → JSON for JS frontend
├── registry/
│   ├── catalog.py
│   ├── execution.py
│   └── tile.py
├── reportsplus/
│   ├── backup_job_summary.py   load_backup_job_summary_artifact()
│   ├── catalog.py              read_json() helper
│   ├── checklist.py            normalize_check(), normalize_status()
│   ├── client.py               ReportsPlusClient
│   ├── datasets.py
│   ├── discovery.py
│   ├── extract_report.py
│   ├── inventory.py
│   ├── metadata.py
│   ├── metric_inventory.py
│   ├── priority.py
│   ├── security_assessment.py  security_assessment_quick_hc()
│   └── validation.py
├── security_assessment/
│   ├── artifact.py
│   ├── import_csv.py
│   ├── import_html.py
│   ├── models.py
│   ├── normalize.py
│   ├── registry.py
│   ├── service.py              SecurityAssessmentService (get_current, save_artifact)
│   └── validate.py
└── web/
    ├── app.py                  create_app() — registers blueprint, calls init_db()
    ├── routes/
    │   ├── basic.py            Login/logout routes
    │   ├── development.py      Dev tools page
    │   ├── main.py             Blueprint aggregator (imports all route modules)
    │   ├── metrics.py          Metrics routes
    │   ├── quick_hc.py         /quick-hc, /quick-hc/report, import/collect routes
    │   ├── quick_hc_api.py     JSON API routes for Quick HC
    │   ├── reportsplus.py      Reports Plus exploration routes
    │   ├── security_assessment.py  SA detail routes
    │   ├── shared.py           Blueprint definition, shared imports
    │   └── staging.py          /quick-hc/staging, approve, reject routes
    └── templates/
        ├── base.html           Shared layout (extends for most pages)
        ├── quick_hc.html       Standalone SPA shell (does NOT extend base.html)
        ├── quick_hc_staging.html   Staging review page (extends base.html)
        └── ...                 (other templates)

tests/                          343 tests total (pytest)
data/
├── app.db                      SQLite database (WAL mode)
├── catalog/
│   ├── artifacts/
│   │   ├── security_assessment/latest.json (+ timestamped snapshots)
│   │   └── license_summary/latest.json     (+ timestamped snapshots)
│   └── rest/
│       └── commserv.json
└── imports/                    Raw import files (CSV, HTML)
```

---

## 3. Dependencies

From `pyproject.toml`:

```toml
[project]
name = "cv-healthcheck"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "beautifulsoup4>=4.12,<5",
    "Flask>=3.0,<4",
    "mcp>=1.0",
    "pydantic>=2.0,<3",
    "requests>=2.31,<3",
]

[project.scripts]
cv-healthcheck     = "cvhealthcheck.cli:main"
cv-healthcheck-mcp = "cvhealthcheck.mcp.server:main"
```

Dev dependencies (requirements-dev.txt): `pytest`, `pytest-cov`, standard tooling. No type-checker or linter is wired into CI.

---

## 4. Database schema

File: `src/cvhealthcheck/db/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagements (
    engagement_id TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    commcell_id   TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engagements_customer_id ON engagements (customer_id);

CREATE TABLE IF NOT EXISTS staged_artifacts (
    stage_id        TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL,
    source_file     TEXT,
    source_type     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    artifact_json   TEXT NOT NULL,
    ai_notes        TEXT,
    created_at      TEXT NOT NULL,
    reviewed_at     TEXT,
    reviewed_by     TEXT,
    engagement_id   TEXT,
    customer_id     TEXT,
    FOREIGN KEY (engagement_id) REFERENCES engagements (engagement_id),
    FOREIGN KEY (customer_id)   REFERENCES customers (customer_id)
);

CREATE INDEX IF NOT EXISTS idx_staged_artifacts_status  ON staged_artifacts (status);
CREATE INDEX IF NOT EXISTS idx_staged_artifacts_subject ON staged_artifacts (subject_id);
```

Key facts:
- SQLite, WAL journal mode, `busy_timeout = 5000 ms`, foreign keys ON.
- `DB_PATH` is anchored to the project root via `Path(__file__).resolve().parents[3] / "data" / "app.db"` to support both Flask and MCP server contexts.
- `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS`). Called from `create_app()` and from MCP server module body.
- `customers` and `engagements` exist in the schema but have no UI or MCP tools yet — they exist as FKs for future multi-tenancy.
- `staged_artifacts.status` is an unvalidated TEXT column; the application enforces the enum (`pending`, `approved`, `rejected`) in Python.

---

## 5. Canonical artifact model

File: `src/cvhealthcheck/artifacts/models.py`

```python
class CanonicalArtifact(BaseModel):
    schema_version: int = 1
    artifact_type:  str
    generated_at:   datetime
    source:         ArtifactSource
    subject:        ArtifactSubject
    summary:        ArtifactSummary
    sections:       list[Section]        = Field(default_factory=list)
    metadata:       dict[str, Any]       = Field(default_factory=dict)
```

`Section` is a discriminated union on the `type` field:

```python
Section = Annotated[
    Union[FindingsSection, TableSection, ChartSection, MetricSection],
    Field(discriminator="type"),
]
```

Supporting models:

```python
class ArtifactSource(BaseModel):
    type:         SourceType        # enum: reportsplus_rest | rest | rest_commserve | csv_import | html_import | json_import
    report_id:    int | None = None
    report_name:  str | None = None
    endpoint:     str | None = None
    collected_at: datetime | None = None
    imported_at:  datetime | None = None

class ArtifactSubject(BaseModel):
    id:    str
    title: str

class ArtifactSummary(BaseModel):
    status:  ArtifactStatus          # enum: good | warning | critical | unknown
    metrics: list[SummaryMetric] = []

class SummaryMetric(BaseModel):
    id:    str
    label: str
    value: int | float
    unit:  str | None = None

class Finding(BaseModel):
    id:             str
    severity:       FindingSeverity   # enum: critical | warning | good | info
    status:         FindingStatus     # enum: open | resolved | acknowledged
    category:       str
    title:          str
    description:    str | None = None
    recommendation: str | None = None
    references:     list[FindingReference] = []
    raw_ref:        Any | None = None

class FindingsSection(BaseModel):
    type:  Literal["findings"]
    id:    str
    title: str
    items: list[Finding] = []

class TableSection(BaseModel):
    type:    Literal["table"]
    id:      str
    title:   str
    columns: list[TableColumn] = []
    items:   list[dict[str, Any]] = []

class ChartSection(BaseModel):
    type:       Literal["chart"]
    id:         str
    title:      str
    chart_type: ChartType   # enum: line | bar | pie
    x_axis:     ChartAxis | None = None
    y_axis:     ChartAxis | None = None
    labels:     list[str] = []
    series:     list[ChartSeries] = []
    # validator: len(series[i].data) must equal len(labels)

class MetricSection(BaseModel):
    type:  Literal["metric"]
    id:    str
    title: str
    items: list[MetricItem] = []
```

**Disk persistence** (`src/cvhealthcheck/artifacts/store.py`):

```python
class ArtifactStore:
    def __init__(self, base_dir: Path = Path("data/catalog/artifacts")) -> None:
        self.base_dir = base_dir

    def save_artifact(self, artifact: CanonicalArtifact) -> Path:
        subject_dir = self.base_dir / artifact.artifact_type
        subject_dir.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True)
        (subject_dir / _ts_filename(artifact.generated_at.isoformat())).write_text(encoded)
        latest = subject_dir / "latest.json"
        latest.write_text(encoded)
        return latest

    def load_latest_artifact(self, artifact_type: str) -> CanonicalArtifact:
        path = self.base_dir / artifact_type / "latest.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return CanonicalArtifact.model_validate(json.loads(path.read_text()))
```

The default `base_dir` is relative (`Path("data/catalog/artifacts")`), which works when Flask is started from the project root. The MCP server uses `ArtifactStore()` with the same default (also works from project root). Tests patch module-level `_artifact_store` instances via `conftest.py` to isolated `tmp_path` directories.

---

## 6. Adapters

Three adapters translate raw collected/imported data into `CanonicalArtifact`:

### 6.1 Security Assessment

File: `src/cvhealthcheck/adapters/security_assessment.py`

- Entry point: `adapt_reportsplus_rest(extraction: dict) -> CanonicalArtifact`
- Input: the full extraction dict from the Reports Plus report pipeline (contains `summary`, `datasets`, `executions`, `report`)
- Output: one `FindingsSection` per dataset, severity counts in `ArtifactSummary.metrics`
- Severity mapping: `{"Critical": critical, "Warning": warning, "Good": good, "Info": info}`
- `artifact_type = "security_assessment"`, `subject.id = "security_assessment"`, `report_id = 336`
- Source type: `SourceType.reportsplus_rest`

### 6.2 License Summary

File: `src/cvhealthcheck/adapters/license_summary.py`

- Entry point: `adapt(artifact: dict) -> CanonicalArtifact`
- Input: the internal LicenseSummaryService `get_current()` dict
- Output:
  - `MetricSection(id="commcell_info")` — CommCell name, version, expiry, last collection
  - `TableSection(id="other_licenses")` — License, Available Total, Used, Unit
  - `TableSection(id="agent_feature_licenses")` — de-duplicated by license name; Permanent/Term columns
  - N × `TableSection` for each workload summary section (id = snake-cased section name)
- Summary: `SummaryMetric(other_license_count)` + `SummaryMetric(agent_feature_count)`
- Source type mapped from legacy string: `"csv"→csv_import`, `"html"→html_import`, `"rest"→rest`
- `artifact_type = "license_summary"`, `subject.id = "license_summary"`

### 6.3 CommCell Details

File: `src/cvhealthcheck/adapters/commcell_details.py`

- Entry point: `adapt_rest(payload: dict) -> CanonicalArtifact`
- Input: raw CommServ REST API response
- Output: `MetricSection` with identity fields
- Source type: `SourceType.rest_commserve`
- `artifact_type = "commcell"`, `subject.id = "environment"`

---

## 7. Quick HC tile registry

File: `src/cvhealthcheck/quickhc/registry.py`

`QUICK_HC_TILES` is a tuple of 6 `TileDefinition` frozen dataclasses:

| id | title | category | artifact_type | collect? | import? |
|----|-------|----------|---------------|----------|---------|
| `environment` | CommCell Details | identity | commcell | no | no |
| `security_assessment` | Security Assessment | security | security_assessment | yes | yes |
| `license_summary` | License Summary | licensing | license_summary | yes | yes |
| `client_growth` | Client Growth | performance | client_growth | no | no |
| `capacity_license` | Capacity Licenses | performance | capacity_license | no | no |
| `backup_job_summary` | Backup Job Summary | operations | backup_job_summary | no | no |

All tiles share the same five `SourceDefinition` entries: `rest_command_center_api`, `rest_reports_plus`, `json_import`, `csv_import`, `html_import`.

### Section IDs (constants in registry.py)

```
environment.metadata
security_assessment.metadata
security_assessment.summary
security_assessment.highlights
security_assessment.all_findings
security_assessment.access_security
security_assessment.auditing
security_assessment.platform_security
security_assessment.company_and_owners_security
security_assessment.capabilities
security_assessment.hardening
license_summary.metadata
license_summary.workload_sections
license_summary.other_licenses
license_summary.agent_feature_licenses
client_growth.summary
client_growth.chart
client_growth.monthly_table
capacity_license.summary
capacity_license.table
backup_job_summary.summary
backup_job_summary.status_breakdown
backup_job_summary.recent_failures
backup_job_summary.recent_jobs
```

### TileDefinition dataclass

```python
@dataclass(frozen=True)
class TileDefinition:
    id: str
    title: str
    subtitle: str
    source_type: str
    source_service: str
    artifact_type: str
    preview_renderer: str
    report_renderer: str
    sources: tuple[SourceDefinition, ...]
    sections: tuple[SectionDefinition, ...]
    category: str = ""
    category_label: str = ""
    report_label: str | None = None
    detail_endpoint: str | None = None
    status_behavior: str = "available_or_missing"
    collect_capable: bool = False
    import_capable: bool = False
    import_url: str | None = None
    collect_url: str | None = None
```

---

## 8. Subject data service (frontend data assembly)

File: `src/cvhealthcheck/quickhc/subject_data_service.py`

This is the single function that builds the JSON payload serialised into `window.QUICK_HC_INITIAL_DATA` in `quick_hc.html`.

```python
def build_subject_initial_data() -> dict[str, Any]:
    # Returns: {"commcell": {...}, "cats": [...], "report_url": "..."}
```

### Data loading

Six loaders, one per tile:

| Loader | Data source |
|--------|-------------|
| `_load_commcell()` | `data/catalog/rest/commserv.json` via `read_json()` |
| `_load_security_assessment()` | `security_assessment_quick_hc()` (internal SA pipeline) |
| `_load_license_summary()` | `LicenseSummaryService().get_current()` |
| `_load_client_growth()` | `get_client_growth_summary(live=False)` |
| `_load_capacity_license()` | `get_capacity_license_usage(live=False)` |
| `_load_backup_job_summary()` | `load_backup_job_summary_artifact()` |

All loaders return `None` on `FileNotFoundError`; the subject builder then produces a `"nodata"` tile.

### Canonical artifact preference

For `security_assessment` and `license_summary`, the subject builder first tries to load from the canonical store:

```python
def _build_security_assessment_subject(sa: dict | None) -> dict:
    try:
        artifact = _canonical_store.load_latest_artifact("security_assessment")
        view = _canonical_view.security_assessment_to_view(artifact)
        view["fullUrl"] = _try_url("main.quick_hc")
        return view
    except FileNotFoundError:
        pass
    # fall through to legacy sa dict
```

`_canonical_store = ArtifactStore()` is a module-level instance — this is the read-side store that tests must patch via `conftest.py`.

### Subject payload structure (per tile)

```python
{
    "id": "security_assessment",
    "name": "Security Assessment",
    "description": "...",
    "state": "ok" | "issues" | "nodata",
    "included": True,
    "subtitle": "3 critical · 12 warning · ...",
    "fullUrl": "/quick-hc" | None,
    "activeSource": "rest_reports_plus",
    "sources": [
        {
            "id": "rest_reports_plus",
            "name": "REST / Reports Plus",
            "desc": "...",
            "status": "v" | "a" | "n" | "ni",
            "meta": [{"k": "Report ID", "v": "336"}],
            "actions": [{"kind": "upload", "label": "Import", "importUrl": "...", "importField": "...", "accept": "..."}],
        },
        ...
    ],
    "sections": [...],
}
```

Source status codes: `v` = verified/active, `a` = available (not active), `n` = not collected, `ni` = not implemented.

---

## 9. Staging workflow

### 9.1 Database layer

File: `src/cvhealthcheck/db/staging.py`

Five public functions:

```python
create_staged_artifact(db, stage_id, subject_id, artifact_json, *, source_file, source_type, ai_notes, engagement_id, customer_id) -> dict
get_staged_artifact(db, stage_id) -> dict | None
list_staged_artifacts(db, *, status=None, subject_id=None) -> list[dict]
approve_staged_artifact(db, stage_id, *, reviewed_by=None) -> dict | None
reject_staged_artifact(db, stage_id, *, reviewed_by=None) -> dict | None
delete_staged_artifact(db, stage_id) -> bool
```

`approve_staged_artifact` and `reject_staged_artifact` raise `ValueError("artifact is not pending")` if the record is not in `pending` status — the web routes and MCP tools catch this and surface it to the caller.

### 9.2 MCP server tools

File: `src/cvhealthcheck/mcp/server.py`

Six tools exposed via FastMCP:

```python
get_canonical_schema()          # Returns the full JSON schema description for CanonicalArtifact
list_subjects()                 # Returns [{id, title, description}] from QUICK_HC_TILES
save_staged_artifact(subject_id, artifact_json, source_file, source_type, ai_notes, customer_id, engagement_id)
list_staged_artifacts(status=None, subject_id=None)
approve_staged_artifact(stage_id, reviewed_by=None)
reject_staged_artifact(stage_id, reviewed_by=None)
```

`save_staged_artifact` validates `artifact_json` against `CanonicalArtifact` via `model_validate_json` before writing to the DB. `stage_id` is generated as `f"stage_{uuid4().hex}"`.

The MCP server calls `init_db()` at module level (before `mcp = FastMCP(...)`) so the database is created if it doesn't exist when the server starts cold.

### 9.3 Web routes

File: `src/cvhealthcheck/web/routes/staging.py`

```python
GET  /quick-hc/staging                      → quick_hc_staging.html
POST /quick-hc/staging/<stage_id>/approve   → validates, saves via ArtifactStore, approves in DB, redirects
POST /quick-hc/staging/<stage_id>/reject    → rejects in DB, redirects
```

The approve route calls `ArtifactStore().save_artifact(artifact)` (default relative base_dir) before updating the DB status. Flash messages: `"Approved staged artifact for {subject_id}."` / `"Rejected staged artifact for {subject_id}."` / error messages on ValueError.

---

## 10. Web application structure

File: `src/cvhealthcheck/web/app.py`

```python
def create_app() -> Flask:
    init_db()
    app = Flask(__name__)
    app.secret_key = os.getenv("CV_SECRET_KEY") or secrets.token_hex(32)
    app.register_blueprint(main_bp)
    return app

app = create_app()  # module-level instance used by Flask dev server
```

Single blueprint `main_bp` (defined in `routes/shared.py`) with all routes registered via imports in `routes/main.py`:

```python
from . import basic        # Login/logout
from . import development  # Dev tools page
from . import quick_hc     # /quick-hc, /quick-hc/report, import/collect
from . import quick_hc_api # JSON API for Quick HC frontend
from . import staging      # /quick-hc/staging, approve, reject
```

### Route summary

| Route | Handler | Notes |
|-------|---------|-------|
| `GET /quick-hc` | `quick_hc()` | Renders `quick_hc.html` with `window.QUICK_HC_INITIAL_DATA` |
| `GET/POST /quick-hc/report` | `quick_hc_report()` | Builds report from selection_ids |
| `POST /quick-hc/security-assessment/import` | import route | HTML/CSV upload |
| `POST /quick-hc/license-summary/import` | import route | HTML/CSV/XLSX upload |
| `POST /quick-hc/security-assessment/collect` | collect route | Live REST collect |
| `POST /quick-hc/license-summary/collect` | collect route | Live REST collect |
| `GET /quick-hc/staging` | `quick_hc_staging()` | Staging review page |
| `POST /quick-hc/staging/<id>/approve` | `quick_hc_staging_approve()` | |
| `POST /quick-hc/staging/<id>/reject` | `quick_hc_staging_reject()` | |

### `quick_hc.html` (standalone SPA shell)

Does **not** extend `base.html`. Has its own header with:
- Logo (dark/light theme switch via `data-light-logo` / `data-dark-logo`)
- Theme toggle buttons (light/dark, persisted in `localStorage` key `quickhc-theme-v1`)
- "Connect" link → `main.login`
- "Staging" link → `main.quick_hc_staging` (in `left-footer`)
- "Dev tools" link → `main.development` (in `left-footer`)
- "Generate Customer Report" button → submits `#report-form`

`window.QUICK_HC_INITIAL_DATA` is injected as `{{ initial_data | tojson }}` in a `<script>` tag. The JS in `quick_hc.js` reads this on load.

---

## 11. Authentication and configuration

### Configuration

File: `src/cvhealthcheck/config.py`

```python
@dataclass(frozen=True)
class Settings:
    base_url:        str
    token_path:      Path
    verify_ssl:      bool  = True
    timeout_seconds: float = 30.0

def load_settings() -> Settings:
    base_url        = os.getenv("CV_BASE_URL", "").rstrip("/")
    token_path      = Path(os.getenv("CV_TOKEN_FILE") or os.getenv("CV_TOKEN_PATH", ".token"))
    verify_ssl      = _as_bool(os.getenv("CV_VERIFY_SSL"), default=True)
    timeout_seconds = float(os.getenv("CV_TIMEOUT") or os.getenv("CV_TIMEOUT_SECONDS", "30"))
    return Settings(base_url=base_url, token_path=token_path, verify_ssl=verify_ssl, timeout_seconds=timeout_seconds)
```

Environment variables: `CV_BASE_URL`, `CV_TOKEN_FILE` (alias `CV_TOKEN_PATH`), `CV_VERIFY_SSL`, `CV_TIMEOUT` (alias `CV_TIMEOUT_SECONDS`), `CV_SECRET_KEY`.

### Authentication

File: `src/cvhealthcheck/auth/commvault_auth.py`

- `login_to_commvault(base_url, username, password) -> str` — POST to `/commandcenter/api/Login`, returns token string
- Token stored in Flask session under key `"commvault_token"`
- `is_authenticated()` → checks `session.get("commvault_token")` inside a request context
- `get_current_token()` / `set_current_token(token)` / `clear_current_token()` — session helpers
- Token extraction tries keys: `"token"`, `"accessToken"`, `"access_token"` from login response JSON

---

## 12. Test suite overview

343 tests collected. Run with `pytest`.

### conftest.py (autouse fixture)

```python
@pytest.fixture(autouse=True)
def _isolate_canonical_stores(monkeypatch, tmp_path):
    import cvhealthcheck.security_assessment.service as sa_service
    import cvhealthcheck.license_summary.service as ls_service
    import cvhealthcheck.quickhc.subject_data_service as sds

    isolated = ArtifactStore(base_dir=tmp_path / "canonical_artifacts")
    monkeypatch.setattr(sa_service, "_artifact_store", isolated)
    monkeypatch.setattr(ls_service, "_artifact_store", isolated)
    monkeypatch.setattr(sds, "_canonical_store", isolated)
```

This prevents any test from reading or writing the production `data/catalog/artifacts/` directory.

### Key test files

| File | Coverage |
|------|----------|
| `test_adapter_security_assessment.py` | `adapters/security_assessment.adapt_reportsplus_rest()` |
| `test_adapter_license_summary.py` | `adapters/license_summary.adapt()`, section structure |
| `test_db_staging.py` | Full CRUD for `staged_artifacts` table |
| `test_staging_routes.py` | 6 integration tests for staging web routes |
| `test_mcp_server.py` | MCP tool integration (save, list, approve, reject) |
| `test_quick_hc_*.py` | Quick HC overview, selection, report builder |

### Staging route test pattern

```python
@pytest.fixture()
def client(monkeypatch, db_path):
    def open_db():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(staging_routes, "get_db", open_db)
    monkeypatch.setattr(staging_routes, "ArtifactStore", _FakeArtifactStore)
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c
```

---

## 13. Data directory layout

```
data/
├── app.db                               SQLite (WAL)
├── catalog/
│   ├── artifacts/
│   │   ├── security_assessment/
│   │   │   ├── latest.json              Latest canonical artifact
│   │   │   └── 2026-05-*_*.json         Timestamped snapshots
│   │   └── license_summary/
│   │       ├── latest.json
│   │       └── 2026-05-*_*.json
│   └── rest/
│       └── commserv.json               CommServ identity (raw REST response)
└── imports/                            Raw import files (not parsed, for reference)
```

`ArtifactStore.save_artifact()` writes both `latest.json` and a timestamped file. `load_latest_artifact()` reads only `latest.json`. Timestamped files accumulate with no cleanup — there is no rotation or pruning logic.

---

## 14. Known gaps and rough edges

1. **No Report Inventory model.** There is no table, model, or UI for tracking which canonical artifacts have been incorporated into a formal report for a specific customer/engagement. The `staged_artifacts` table captures AI-generated artifacts pending human review, but once approved they are only written to `latest.json` — no record of which engagement they belong to is persisted beyond the optional FKs on `staged_artifacts`.

2. **Relative `base_dir` in ArtifactStore.** The default `Path("data/catalog/artifacts")` is relative to CWD. Works when Flask is run from the project root. The MCP server also depends on CWD. No path anchoring in `ArtifactStore` itself.

3. **No timestamped artifact rotation.** Timestamped snapshots accumulate indefinitely. No pruning.

4. **`customers` and `engagements` tables unused.** The schema has them, staging FKs reference them, but there is no CRUD UI, no CLI commands, and no population of these tables in the current code paths.

5. **`staged_artifacts.status` is free-text.** The application enforces the `pending/approved/rejected` set in Python but the column has no CHECK constraint.

6. **Single `ArtifactStore` per `artifact_type` subdirectory.** There is no concept of per-customer or per-engagement isolation in the artifact store. `latest.json` is a single global file per artifact type.

7. **MCP server uses default `ArtifactStore()`.** The `approve_staged_artifact` MCP tool calls `ArtifactStore().save_artifact(artifact)` with the default relative path — will fail if the MCP server is started from a directory other than the project root.

8. **No audit trail on approved artifacts.** Once `approve_staged_artifact` is called, the `staged_artifacts` record captures `reviewed_by` and `reviewed_at`, but the `latest.json` file that was written carries no provenance linking it back to the `stage_id`.

9. **Backup Job Summary, Client Growth, Capacity License have no canonical adapter.** These tiles load data from their own non-canonical pipelines and have no `CanonicalArtifact` representation yet. They cannot participate in the staging workflow.

10. **No pagination on `list_staged_artifacts`.** The query returns all rows ordered by `created_at DESC` with no limit.
