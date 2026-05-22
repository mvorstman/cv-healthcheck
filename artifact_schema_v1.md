# Canonical Artifact Schema v1

## Status
Draft — approved direction, not yet final. Validate all current subjects before implementing migration.

---

## Top-level structure

```json
{
  "schema_version": 1,
  "artifact_type": "security_assessment",
  "generated_at": "2026-05-22T21:00:00Z",

  "source": {
    "type": "reportsplus_rest",
    "report_id": 336,
    "report_name": "Security Assessment",
    "collected_at": "2026-05-22T21:00:00Z"
  },

  "subject": {
    "id": "security_assessment",
    "title": "Security Assessment"
  },

  "summary": {
    "status": "warning",  // good | warning | critical | unknown
    "metrics": [
      {"id": "critical", "label": "Critical", "value": 2,    "unit": null},
      {"id": "warning",  "label": "Warning",  "value": 5,    "unit": null},
      {"id": "good",     "label": "Good",      "value": 12,  "unit": null}
    ]
  },

  "sections": [],

  "metadata": {}
}
```

### Field rules

| Field | Required | Notes |
|-------|----------|-------|
| `schema_version` | yes | Increment on breaking changes |
| `artifact_type` | yes | Stable snake_case subject ID |
| `generated_at` | yes | ISO 8601 UTC |
| `source` | yes | See source model below |
| `subject` | yes | Stable ID + display title |
| `summary` | yes | Status + top-level metrics |
| `sections` | yes | May be empty list |
| `metadata` | yes | May be empty dict |

`summary.status` values: `good / warning / critical / unknown`. Use `unknown` when no artifact has been loaded for a subject.

---

## Source model

```json
{
  "type": "reportsplus_rest | rest | csv_import | json_import | html_import",
  "report_id": 336,
  "report_name": "Security Assessment",
  "endpoint": "/v4/...",
  "collected_at": "2026-05-22T21:00:00Z",
  "imported_at": null
}
```

Use `collected_at` for adapter-collected data. Use `imported_at` for user-imported files.
Never mix source metadata into artifact data sections.

---

## Section types

Four canonical types cover all current Quick HC subjects.

```text
findings    Security Assessment, health findings
table       Job summary, client list, license table
chart       Capacity trend, client growth
metric      CommCell details, summary KPIs
```

Every section has a stable `id`, a display `title`, and a `type`.
The renderer selects behavior from `type` alone — no custom rendering logic per subject.

---

## findings section

```json
{
  "id": "access_security",
  "title": "Access Security",
  "type": "findings",
  "items": [
    {
      "id": "finding_001",
      "severity": "critical",
      "status": "open",
      "category": "Access Security",
      "title": "Anonymous access enabled",
      "description": "Anonymous access is enabled on the CommServe.",
      "recommendation": "Disable anonymous access in Security settings.",
      "references": [
        {"label": "How to disable anonymous access", "href": "https://documentation.commvault.com/..."}
      ],
      "raw_ref": null
    }
  ]
}
```

### Finding field rules

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Stable within artifact |
| `severity` | yes | `critical / warning / good / info` |
| `status` | yes | `open / resolved / acknowledged` |
| `category` | yes | Section or domain label |
| `title` | yes | Short display title |
| `description` | no | Detailed explanation |
| `recommendation` | no | Remediation guidance text |
| `references` | no | List of `FindingReference` objects |
| `raw_ref` | no | Reference to raw source record |

### FindingReference

```json
{"label": "How to disable anonymous access", "href": "https://documentation.commvault.com/..."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `label` | yes | Human-readable link text |
| `href` | yes | Absolute URL |

---

## table section

```json
{
  "id": "job_summary",
  "title": "Job Summary",
  "type": "table",
  "columns": [
    {"id": "client",   "label": "Client"},
    {"id": "status",   "label": "Status"},
    {"id": "duration", "label": "Duration", "unit": "h"}
  ],
  "items": [
    {"client": "srv01", "status": "Failed", "duration": 2.0}
  ]
}
```

### Table rules

- Column IDs are stable snake_case identifiers.
- Labels are display metadata only — never used as keys.
- Row items use column IDs as keys.
- `unit` is optional on columns.

---

## chart section

```json
{
  "id": "capacity_trend",
  "title": "Capacity Trend",
  "type": "chart",
  "chart_type": "line",
  "x_axis": {
    "label": "Month"
  },
  "y_axis": {
    "label": "Used",
    "unit": "TB"
  },
  "labels": ["Jan", "Feb", "Mar"],
  "series": [
    {
      "id": "used",
      "label": "Used TB",
      "data": [1.2, 1.4, 1.6]
    },
    {
      "id": "purchased",
      "label": "Purchased TB",
      "data": [5.0, 5.0, 5.0]
    }
  ]
}
```

### Chart rules

- `chart_type`: `line | bar | pie`
- `labels` length must match each `series.data` length.
- Multiple series are supported.
- x/y axis metadata is optional in v1 but recommended.

---

## metric section

```json
{
  "id": "commcell_details",
  "title": "CommCell Details",
  "type": "metric",
  "items": [
    {"id": "cs_version",  "label": "CS Version",  "value": "11.40.47", "unit": null},
    {"id": "cs_hostname", "label": "Hostname",     "value": "cs01.lab", "unit": null},
    {"id": "client_count","label": "Clients",      "value": 142,        "unit": null}
  ]
}
```

### Metric rules

- Each item has a stable `id`.
- `label` is display metadata.
- `value` may be string, int, or float.
- `unit` is optional.

---

## Subject coverage

| Subject | Section types |
|---------|--------------|
| Security Assessment | `findings` + `metric` summary |
| License Summary | `table` + `metric` |
| Capacity Licenses | `chart` + `table` / `metric` |
| Client Growth | `chart` + `table` / `metric` |
| CommCell Details | `metric` |
| Backup Job Summary | `table` + `metric` |

---

## Schema versioning

- `schema_version` is checked on artifact load.
- Source adapters always write the current version.
- A migration function upgrades stored artifacts on read.
- Breaking changes increment `schema_version`.
- Additive changes (new optional fields) do not require a version bump.

---

## What belongs in an artifact

| Belongs | Does not belong |
|---------|----------------|
| Normalized operational data | HTML fragments |
| Section structure | UI state |
| Findings and metrics | Flask rendering logic |
| Source provenance | Raw API response payloads |
| Timestamps | CSS or display metadata |
| Stable IDs | Source-specific field names |

---

## Separation principle

```text
source adapter    →    artifact    →    renderer / rules / report
```

- Adapters know source formats. Artifacts do not.
- Renderers know display. Artifacts do not.
- Rules engine knows evaluation. Artifacts do not.
- The artifact is the stable internal contract between all three layers.

---

## Using this document

When starting a Claude Code session to implement artifact migration:

```
Read docs/artifact_schema_v1.md first.
We are implementing the artifact layer for cv-healthcheck.
Start with the Security Assessment subject as the reference implementation.
```