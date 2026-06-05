# Security Assessment subject

Security Assessment is integrated from Reports Plus report 336. It is a multi-source subject with a shared canonical artifact model, surfaced as a Quick HC subject (see [../architecture/quickhc.md](../architecture/quickhc.md)).

## Sources

Three sources feed the same `collect → normalize → persist → render` path:

- **REST** — Reports Plus report 336
- **HTML export import**
- **CSV export import**

The canonical artifact is the normalized evidence contract shared across REST, HTML, and CSV, so the UI and downstream health logic render one consistent structure regardless of acquisition method. HTML and CSV import support offline evidence ingestion and browser-driven upload when live REST access is unavailable or unsuitable.

REST endpoint pattern:

```text
/commandcenter/api/cr/reportsplusengine/reports/336
/commandcenter/api/cr/reportsplusengine/datasets/<guid>
/commandcenter/api/cr/reportsplusengine/datasets/<guid>/data
```

Normalized local artifact:

```text
data/catalog/reportsplus/report_336_security_assessment_normalized.json
```

## Module layout

```text
src/cvhealthcheck/security_assessment/
  models.py     — strict schema for customer / CommCell / import / artifact / finding models
  normalize.py  — field cleanup and canonical mapping only
  validate.py   — noise rejection, validity checks, deduplication
  artifact.py   — canonical artifact building, unique artifact persistence, latest.json compatibility writes
  registry.py   — SQLite artifact registry
  service.py    — orchestration used by Flask routes and non-UI collectors
```

Ingestion enforces canonical fields, rejects noise, deduplicates, filters header/footer rows, and parses HTML tables strictly (validated `thead` headers plus `tbody`/`tr`/`td` extraction only).

## Sections

Report 336 normalizes into these sections:

- Access Security
- Auditing
- Platform Security
- Company and Owners Security
- Capabilities
- Hardening

The reusable checklist normalizer lives in `src/cvhealthcheck/reportsplus/checklist.py`. It normalizes status values, strips unsafe HTML from remarks, extracts safe action links, and groups checks for Quick HC display.

## Persistence and registry model

Each import/refresh writes a unique artifact JSON file and registers it in SQLite; `latest.json` is retained as a compatibility pointer. The read path is:

```text
registry -> active artifact -> artifact file
```

Outputs:

```text
data/imports/security_assessment/latest.json
data/imports/security_assessment/latest_<source_type>.json
data/imports/security_assessment/artifact_registry.sqlite3
data/catalog/security_assessment/<artifact_id>.json
data/catalog/security_assessment/latest.json
data/catalog/security_assessment/latest_<source_type>.json
```

Registry behavior:

- The registry database path is deterministic: `data/imports/security_assessment/artifact_registry.sqlite3`.
- SQLite schema creation is idempotent and runs on demand.
- Reads prefer scoped active-artifact selection, then load the referenced artifact file; the `latest.json` compatibility fallback is used only when the scoped registry entry or artifact file is unavailable.
- Active selection is scoped, so different customers and CommCells do not overwrite or select each other's artifacts.
- The layer uses simple SQLite hardening (`foreign_keys`, `busy_timeout`, `WAL`); there is no migration framework.
- A registry export utility exists for audit/debugging; destructive cleanup is not implemented.

`SecurityAssessmentService` exposes current-state, history, and artifact-by-id/run retrieval; registry helpers list artifacts, fetch the latest/active artifact within scope, and list report/import runs. Service-layer reads prefer registry-backed loading over `latest.json`.

Metadata tracked per artifact/import run: `created_at`, `last_accessed_at`, `retention_policy`, `imported_by`, `import_method`, `source_metadata`.

Retention: all artifact files are kept by default; `latest.json` is a compatibility pointer, not the system of record; cleanup does not delete active artifacts without explicit operator action.

## Endpoints

Canonical JSON read endpoint (authenticated, read-only):

```text
GET /api/security-assessment/canonical
```

Internal history/registry tooling (authenticated, read-only; does not change the visible page flow):

```text
/security-assessment/history
/security-assessment/registry-export
/development/security-assessment-registry
```

Development/debug page:

```text
http://127.0.0.1:5001/reportsplus/security-assessment
```
