# cv-healthcheck — Project Context Report

Generated: 2026-05-23

---

## 1. Directory Structure

```
cv-healthcheck/
  API_MAPPING.md
  DATA_SOURCE_MAPPING.md
  DEVLOG.md
  HEALTHCHECK_MATRIX.md
  PROMPT.txt
  README.md
  ROADMAP.md
  artifact_schema_v1.md
  pyproject.toml
  data/
    catalog/
      datasets.json
      datasets_summary.json
      execution_validation.json
      health_candidate_priority.json
      health_candidates.json
      license_summary/         (artifact JSON files + latest.json symlinks)
      metrics/
        capacity_license_usage.json
        client_count_history.json
        client_growth_details.json
        client_growth_summary.json
      quickhc/
        backup_job_summary_latest.json
        descriptions/
          license_summary.json
      reports.json
      reports_summary.json
      reportsplus/             (report_NNN_*.json files for reports 206, 318, 336)
      rest/
        commserv.json
      security_assessment/     (artifact JSON files + latest.json)
    imports/
      license_summary/
        artifact_registry.sqlite3
      security_assessment/
        artifact_registry.sqlite3
  src/
    cvhealthcheck/
      __init__.py
      api_client.py
      artifact_registry.py
      cli.py
      config.py
      adapters/
        __init__.py
        commcell_details.py
        security_assessment.py
      artifacts/
        __init__.py
        enums.py
        exceptions.py
        models.py
        store.py
      auth/
        __init__.py
        commvault_auth.py
      health/
        __init__.py
        model.py
      labreadiness/
        __init__.py
        collector.py
        evaluator.py
        models.py
      license_summary/
        __init__.py
        artifact.py
        collect_rest.py
        import_csv.py
        import_html.py
        models.py
        normalize.py
        service.py
        validate.py
      metrics/
        __init__.py
        capacity.py
        common.py
        growth.py
      output/
        __init__.py
        json_report.py
      quickhc/
        __init__.py
        commcell.py
        description_service.py
        models.py
        overview_service.py
        registry.py
        report_service.py
        source_provenance.py
        subject_data_service.py
      registry/
        __init__.py
        catalog.py
        execution.py
        tile.py
      reportsplus/
        __init__.py
        backup_job_summary.py
        catalog.py
        checklist.py
        client.py
        datasets.py
        discovery.py
        extract_report.py
        inventory.py
        metadata.py
        metric_inventory.py
        priority.py
        security_assessment.py
        validation.py
      security_assessment/
        __init__.py
        artifact.py
        import_csv.py
        import_html.py
        models.py
        normalize.py
        registry.py
        service.py
        validate.py
      web/
        __init__.py
        app.py
        routes/
          __init__.py
          basic.py
          development.py
          main.py
          metrics.py
          quick_hc.py
          quick_hc_api.py
          reportsplus.py
          security_assessment.py
          shared.py
        static/
          quick_hc.css
          quick_hc.js
        templates/
          (Jinja2 HTML templates)
  tests/
    test_adapter_commcell_details.py
    test_backup_job_summary.py
    test_license_summary.py
    test_license_summary_web.py
    test_platform_foundation.py
    test_quickhc_description_service.py
    test_quickhc_overview_service.py
    test_quickhc_registry.py
    test_quick_hc_report.py
    test_quickhc_source_provenance.py
    test_registry_execution.py
    test_registry_helpers.py
    test_registry.py
    test_security_assessment_import.py
    test_security_assessment_registry.py
```

---

## 2. SQLite Schema

Both `data/imports/security_assessment/artifact_registry.sqlite3` and
`data/imports/license_summary/artifact_registry.sqlite3` share the same schema:

```sql
CREATE TABLE import_runs (
    import_run_id     TEXT PRIMARY KEY,
    customer_id       TEXT NOT NULL,
    commcell_id       TEXT NOT NULL,
    engagement_id     TEXT,
    report_stream_id  TEXT,
    report_run_id     TEXT,
    imported_at       TEXT NOT NULL,
    executed_at       TEXT,
    run_sequence      INTEGER,
    imported_by       TEXT,
    import_method     TEXT
);

CREATE TABLE artifacts (
    artifact_id       TEXT PRIMARY KEY,
    import_run_id     TEXT NOT NULL,
    artifact_type     TEXT NOT NULL,
    source_type       TEXT NOT NULL,
    source_file       TEXT,
    file_path         TEXT NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT,
    last_accessed_at  TEXT,
    retention_policy  TEXT,
    imported_by       TEXT,
    import_method     TEXT,
    source_metadata   TEXT,
    FOREIGN KEY (import_run_id) REFERENCES import_runs(import_run_id)
);

CREATE INDEX idx_artifacts_active
    ON artifacts (artifact_type, is_active);

CREATE INDEX idx_import_runs_stream_exec
    ON import_runs (report_stream_id, executed_at, run_sequence);

CREATE INDEX idx_import_runs_scope
    ON import_runs (customer_id, commcell_id, engagement_id, report_stream_id, imported_at);
```

---

## 3. Models

### `src/cvhealthcheck/artifacts/models.py` — Canonical Artifact (Pydantic v2)

```python
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

from .enums import ArtifactStatus, ChartType, FindingSeverity, FindingStatus, SourceType


class ArtifactSource(BaseModel):
    type:         SourceType
    report_id:    int | None      = None
    report_name:  str | None      = None
    endpoint:     str | None      = None
    collected_at: datetime | None = None
    imported_at:  datetime | None = None


class ArtifactSubject(BaseModel):
    id:    str
    title: str


class SummaryMetric(BaseModel):
    id:    str
    label: str
    value: int | float
    unit:  str | None = None


class ArtifactSummary(BaseModel):
    status:  ArtifactStatus
    metrics: list[SummaryMetric] = Field(default_factory=list)


class FindingReference(BaseModel):
    label: str
    href:  str


class Finding(BaseModel):
    id:             str
    severity:       FindingSeverity
    status:         FindingStatus
    category:       str
    title:          str
    description:    str | None             = None
    recommendation: str | None             = None
    references:     list[FindingReference] = Field(default_factory=list)
    raw_ref:        Any | None             = None


class TableColumn(BaseModel):
    id:    str
    label: str
    unit:  str | None = None


class ChartAxis(BaseModel):
    label: str
    unit:  str | None = None


class ChartSeries(BaseModel):
    id:    str
    label: str
    data:  list[float]


class MetricItem(BaseModel):
    id:    str
    label: str
    value: str | int | float
    unit:  str | None = None


class FindingsSection(BaseModel):
    type:  Literal["findings"]
    id:    str
    title: str
    items: list[Finding] = Field(default_factory=list)


class TableSection(BaseModel):
    type:    Literal["table"]
    id:      str
    title:   str
    columns: list[TableColumn]    = Field(default_factory=list)
    items:   list[dict[str, Any]] = Field(default_factory=list)


class ChartSection(BaseModel):
    type:       Literal["chart"]
    id:         str
    title:      str
    chart_type: ChartType
    x_axis:     ChartAxis | None  = None
    y_axis:     ChartAxis | None  = None
    labels:     list[str]         = Field(default_factory=list)
    series:     list[ChartSeries] = Field(default_factory=list)

    @model_validator(mode="after")
    def _labels_match_series(self) -> "ChartSection": ...


class MetricSection(BaseModel):
    type:  Literal["metric"]
    id:    str
    title: str
    items: list[MetricItem] = Field(default_factory=list)


Section = Annotated[
    Union[FindingsSection, TableSection, ChartSection, MetricSection],
    Field(discriminator="type"),
]


class CanonicalArtifact(BaseModel):
    schema_version: int = 1
    artifact_type:  str
    generated_at:   datetime
    source:         ArtifactSource
    subject:        ArtifactSubject
    summary:        ArtifactSummary
    sections:       list[Section]   = Field(default_factory=list)
    metadata:       dict[str, Any]  = Field(default_factory=dict)
```

### `src/cvhealthcheck/quickhc/models.py` — Quick HC UI Models (frozen dataclasses)

```python
from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QuickHcSource:
    mode: str; subject: str; endpoint: str; method: str; auth: str
    def to_dict(self) -> dict[str, str]: ...


@dataclass(frozen=True)
class CommCellIdentity:
    hostName: str | None = None
    csGUID: str | None = None
    csVersionInfo: str | None = None
    releaseId: str | int | None = None
    osType: str | None = None
    timeZone: str | None = None
    def to_dict(self) -> dict[str, str | int | None]: ...


@dataclass(frozen=True)
class SectionDefinition:
    id: str
    label: str
    default_selected: bool = True
    preview_renderer: str | None = None
    report_renderer: str | None = None


@dataclass(frozen=True)
class SourceDefinition:
    id: str; label: str; description: str


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
    report_label: str | None = None
    detail_endpoint: str | None = None
    status_behavior: str = "available_or_missing"
    collect_capable: bool = False
    import_capable: bool = False
    # properties: display_label, effective_report_label, description,
    #             section_ids, default_section_ids, source_ids
```

### `src/cvhealthcheck/security_assessment/models.py` — Security Assessment (frozen dataclasses)

Key classes:
- `CustomerContext(customer_id, customer_name)`
- `CommCellContext(commcell_id, customer_id, commcell_name)`
- `EngagementContext(engagement_id, customer_id, commcell_id)`
- `ReportStream(report_stream_id, customer_id, commcell_id, cadence)`
- `ReportRun(report_run_id, report_stream_id, executed_at, run_sequence)`
- `ImportRun(import_run_id, customer_id, commcell_id, imported_at, engagement_id?, report_stream_id?, report_run_id?, executed_at?, run_sequence?, imported_by?, import_method?)`
- `ArtifactRecord` — full registry row with all provenance fields
- `CanonicalFinding(section, parameter, status, remarks, action, source_type, source_file, imported_at)` — validated; status must be in DEFAULT_STATUS_KEYS
- `SecurityAssessmentArtifact` — full artifact with versioning (`schema_version=1`, `artifact_version="1.0"`, `collector_version="1.0"`), provenance fields, `findings: list[CanonicalFinding]`, `sections: list[str]`, `status_counts: dict[str, int]`, `source: dict`. Has `to_dict()` and `from_dict()` classmethods.

Schema version constants:
```python
SECURITY_ASSESSMENT_SCHEMA_VERSION = 1
SECURITY_ASSESSMENT_ARTIFACT_VERSION = "1.0"
SECURITY_ASSESSMENT_COLLECTOR_VERSION = "1.0"
```

### `src/cvhealthcheck/license_summary/models.py` — License Summary (frozen dataclasses)

Key classes:
- `OtherLicense(license, available_total, used, unit?, raw_available_total?, raw_used?)`
- `AgentFeatureLicense(license, permanent_total, permanent_used, term_total, term_used, client?, agent?, install_date?)`
- `WorkloadSummaryRow(license, entitlement_value, used, usage_percent?, status?)`
- `WorkloadSummarySection(section_name, rows: list[WorkloadSummaryRow])`
- `LicenseSummaryArtifact` — full artifact with versioning, provenance fields, and three license collections. Has `to_dict()` and `from_dict()`.

Schema version constants:
```python
LICENSE_SUMMARY_SCHEMA_VERSION = 1
LICENSE_SUMMARY_ARTIFACT_VERSION = "1.0"
LICENSE_SUMMARY_COLLECTOR_VERSION = "1.0"
```

### `src/cvhealthcheck/labreadiness/models.py`

```python
class ReadinessState(StrEnum):
    NOT_READY = "NOT_READY"
    READY_FOR_DISCOVERY = "READY_FOR_DISCOVERY"
    READY_FOR_DATA_EXECUTION = "READY_FOR_DATA_EXECUTION"
    READY_FOR_HEALTH_RULE_TESTING = "READY_FOR_HEALTH_RULE_TESTING"

@dataclass(frozen=True)
class Indicator:
    name: str; value: Any; status: str; notes: str = ""
    def as_dict(self) -> dict[str, Any]: ...
```

---

## 4. Flask Route Files

Blueprint name: `"main"` — defined in `shared.py`, all route modules register on it.

### `src/cvhealthcheck/web/routes/main.py` — Blueprint aggregator

```python
from .shared import bp, extract_security_assessment, is_authenticated
from . import basic, development, metrics, quick_hc, quick_hc_api, reportsplus, security_assessment
```

### `src/cvhealthcheck/web/routes/basic.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET/POST | `/login` | `main.login` |
| POST | `/logout` | `main.logout` |
| GET | `/` | `main.index` → redirects to `/quick-hc` |
| GET | `/lab-readiness` | `main.lab_readiness` (login required) |
| GET | `/api/test` | `main.api_test` (login required) |

### `src/cvhealthcheck/web/routes/quick_hc.py`

| Method | Path | Endpoint | Notes |
|--------|------|----------|-------|
| GET | `/quick-hc` | `main.quick_hc` | Main Quick HC page; renders `quick_hc.html` |
| GET/POST | `/quick-hc/report` | `main.quick_hc_report` | Report generation |
| GET | `/quick-hc/commcell` | `main.quick_hc_commcell` | CommCell identity |
| GET | `/quick-hc/security-assessment` | `main.quick_hc_security_assessment` | **302 → `/quick-hc`** (retired) |
| POST | `/quick-hc/security-assessment/import` | `main.quick_hc_security_assessment_import` | File upload |
| POST | `/quick-hc/security-assessment/collect` | `main.quick_hc_security_assessment_collect` | REST collect (login required) |
| GET | `/quick-hc/license-summary` | `main.quick_hc_license_summary` | **302 → `/quick-hc`** (retired) |
| GET | `/quick-hc/backup-job-summary` | `main.quick_hc_backup_job_summary` | Backup job summary |
| POST | `/quick-hc/license-summary/import` | `main.quick_hc_license_summary_import` | File upload |
| POST | `/quick-hc/license-summary/collect` | `main.quick_hc_license_summary_collect` | REST collect (login required) |

### `src/cvhealthcheck/web/routes/quick_hc_api.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET | `/api/quick-hc/status` | `main.api_quick_hc_status` |
| GET | `/api/quick-hc/subject/<subject_id>` | `main.api_quick_hc_subject` |
| POST | `/api/quick-hc/subject/<subject_id>/description` | `main.api_quick_hc_subject_description` |

### `src/cvhealthcheck/web/routes/metrics.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET | `/metrics/client-count` | `main.metrics_client_count` (login required) |
| GET | `/metrics/client-growth` | `main.metrics_client_growth` (login required) |
| GET | `/metrics/capacity-license` | `main.metrics_capacity_license` (login required) |

### `src/cvhealthcheck/web/routes/reportsplus.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET | `/reportsplus/reports` | `main.reportsplus_reports` (login required) |
| GET | `/reportsplus/reports/<report_id_or_guid>` | `main.reportsplus_report_detail` (login required) |
| GET | `/reportsplus/report/<report_id>` | `main.reportsplus_report_extract` (login required) |
| GET | `/reportsplus/report/<report_id>/metrics` | `main.reportsplus_report_metrics` |
| GET | `/reportsplus/datasets` | `main.reportsplus_datasets` (login required) |
| GET | `/reportsplus/health-candidates` | `main.reportsplus_health_candidates` (login required) |
| GET | `/reportsplus/execution-validation` | `main.reportsplus_execution_validation` (login required) |
| GET | `/reportsplus/dataset/<dataset_guid>` | `main.reportsplus_dataset` (login required) |
| GET | `/reportsplus/data/<dataset_guid>` | `main.reportsplus_data` (login required) |

### `src/cvhealthcheck/web/routes/security_assessment.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET | `/security-assessment` | `main.reportsplus_security_assessment` |
| GET | `/reportsplus/security-assessment` | `main.reportsplus_security_assessment_legacy` → legacy redirect |
| POST | `/security-assessment/import` | `main.security_assessment_import` |
| GET | `/security-assessment/history` | `main.security_assessment_history` (login required, JSON) |
| GET | `/security-assessment/registry-export` | `main.security_assessment_registry_export` (login required, JSON) |

### `src/cvhealthcheck/web/routes/development.py`

| Method | Path | Endpoint |
|--------|------|----------|
| GET | `/development` | `main.development` (login required) |
| GET | `/development/security-assessment-registry` | `main.security_assessment_registry_view` (login required) |

### `src/cvhealthcheck/web/routes/shared.py` — Helpers

- Blueprint `bp = Blueprint("main", __name__)`
- `login_required` decorator
- `_current_token()`, `_api_client()`, `_reportsplus_client()`
- `_auth_failure_redirect()`, `_safe_next()`, `_parameters_from_form()`, `_bool_filter()`
- `_diagnostics()`, `_inventory_message()`, `_security_assessment_registry_filters()`
- `_month_records()`, `_number_or_none()`
- Chart builders: `_client_count_chart()`, `_client_growth_chart()`, `_capacity_license_chart()`, `_client_growth_detail_chart()`

---

## 5. Test Count

```
215 tests collected in 0.15s
```

Test files:
- `test_adapter_commcell_details.py`
- `test_backup_job_summary.py`
- `test_license_summary.py`
- `test_license_summary_web.py`
- `test_platform_foundation.py`
- `test_quickhc_description_service.py`
- `test_quickhc_overview_service.py`
- `test_quickhc_registry.py`
- `test_quick_hc_report.py`
- `test_quickhc_source_provenance.py`
- `test_registry_execution.py`
- `test_registry_helpers.py`
- `test_registry.py`
- `test_security_assessment_import.py`
- `test_security_assessment_registry.py`

---

## 6. pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cv-healthcheck"
version = "0.1.0"
description = "Commvault HealthCheck and Reports Plus exploration tooling"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "beautifulsoup4>=4.12,<5",
    "Flask>=3.0,<4",
    "pydantic>=2.0,<3",
    "requests>=2.31,<3",
]

[project.scripts]
cv-healthcheck = "cvhealthcheck.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```
