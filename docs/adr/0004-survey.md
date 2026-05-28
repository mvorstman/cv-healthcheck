# ADR 0004 Survey — Three-face metadata vocabulary

## 0. Real-data inventory (evidence basis)

What I can actually exercise the vocabulary against, before I claim anything:

| Subject / report | Evidence I have | Evidence I do NOT have |
|---|---|---|
| environment | `data/catalog/rest/commserv.json` (real CommServ identity, fresh) | — |
| security_assessment (report 336) | 6 raw REST dataset responses (`report_336_raw_*.json`, 32 findings total with vendor severity codes), canonical artifact, multiple legacy HTML+CSV exports | — |
| license_summary (report 206) | Report definition (48 pages, 169 dataset entries, 67 distinct dataset names, 20 duplicate names), 152 raw REST dataset extractions, legacy LS artifact, HTML/CSV exports | — |
| client_growth (from report 318) | Legacy `client_growth_summary.json` (May 13 — STALE, 13 records, latest=2026-05), canonical artifact (also from report 318) | Raw 318 datasets exist (in `report_318_raw_*.json`) but the legacy/canonical pre-aggregate from them |
| capacity_license (from report 318) | Same as client_growth — legacy file + canonical | `purchased_capacity` values are -1 sentinel or 0.0 throughout the file — **no non-degenerate utilisation values in real data** |
| backup_job_summary (report 194) | Legacy `data/catalog/quickhc/backup_job_summary_latest.json` (1 row: client-z, status=Completed), canonical artifact (empty), CHANGELOG note confirms the lab's report 194 dataset legitimately returns 0 rows | No 194 raw dataset file in `data/catalog/reportsplus/` |
| storage_utilization (AI subject, report 146) | Catalog rows: 4 sections (1 metric, 1 table, 2 chart); extraction wired only for `.detail_table` | No raw 146 data, no canonical artifact, no imports |
| cloud_storage_egress_ingress (AI subject, reports 56/300) | Catalog rows: 6 sections (2 table, 4 chart); extraction wired only for the 2 tables | No raw data, no canonical artifact, no imports |
| 17 other reports listed in `data/catalog/reports.json` | Report names + IDs only | No definitions, no datasets, no samples for: Cloud Storage Egress 56/300, Storage Usage 342, Restore Job Summary 235, SLA 252, CommCell Readiness 57, Audit Trail 27, Compliance lock 263, etc. |

**Blind spots I'm declaring up front, not papering over:**

1. The only reports with raw extraction samples are **3 of 20**: 206, 318, 336. Phase 2 step 3 ("a report that's neither in the six NOR LS") cannot be exercised against real data with conviction — only against the catalog rows for storage_utilization / cloud_storage_egress_ingress (AI subjects with declared schemas but no samples). The novel-report stress is therefore catalog-row-only, not data-driven. **That itself is a finding.**
2. Real capacity_license data has used=purchased=0 or -1 sentinels throughout. I can demonstrate the derivation **computes correctly** but cannot show the rules **firing on a real positive utilisation**. The threshold-rule layer is exercised only against fabricated values + hypotheticals.
3. Real client_growth has total_clients=0 in May 2025 and 5 in May 2026 — YoY mathematically undefined (division by zero). The derivation logic is verifiable; the realistic-YoY-value path isn't.
4. The lab's report 194 returns 0 rows for backup_job_summary — there is **no real production-shaped backup job data anywhere on disk to test against**. Legacy `backup_job_summary_latest.json` has 1 fabricated row ("client-z").
5. There is no real vendor severity report OTHER than SA. SA is the sole data point for vendor-severity ingestion. If Commvault's other compliance reports (Readiness, SLA, IntelliSnap) use a different severity convention, the survey wouldn't catch it.

The "rule of three" the steering chat noted — three subjects make a pattern — only one subject (SA) is exercised for vendor severity. The remaining stress on rule layering is hypothetical.

---

## 1. Phase 1 — six in-corpus subjects, three-face metadata against real data

I'll be terse on what doesn't strain and verbose where it does.

### 1.1 `environment` (CommCell identity)

**Legacy builder.** `_build_environment_subject` at `subject_data_service.py:520-597`. One section: `environment.metadata` of type `"meta"` with 4 fixed key/value rows pulled from `commserv.json`'s `identity` block (hostName, csVersionInfo, csGUID, timeZone).

**Proposed three-face metadata.**

```yaml
sections:
  - id: environment.metadata
    semantic:
      kind: identity
      entity: commcell
      fields:
        - { id: commcell_name,    source: identity.hostName,        type: string, label: "CommCell name" }
        - { id: commcell_id,      source: identity.csGUID,          type: string, label: "CommCell ID" }
        - { id: commcell_version, source: identity.csVersionInfo,   type: string, label: "Version" }
        - { id: timezone,         source: identity.timeZone,        type: string, label: "Timezone" }
    presentational:
      render_as: key_value_card
    evaluative:
      template_rules: []
```

**Real-data application.** Source: `data/catalog/rest/commserv.json:identity = {"csGUID":"C721DF1F-…","csVersionInfo":"11 SP40.47","hostName":"cs01","timeZone":"0:0:America/Danmarkshavn",…}`. The vocabulary maps cleanly: 4 declared fields → 4 source paths → 4 typed values → 4 key/value rows.

**Strain or forced fits.** None at this section level. But three thinly-veiled questions arose:

- **Identity-vs-metric distinction.** `environment` carries *identity facts* (the CommCell IS named `cs01`). Other subjects' metric sections carry *measured quantities* (capacity_license's *current* used). The proposed semantic `kind` vocabulary needs to distinguish them or it conflates "what this thing is" with "what was measured of it." This matters for rules: identity values don't have thresholds, but metrics do. The brief doesn't yet specify the `kind` enumeration. **Flagged as a gap below.**
- **`releaseId` and `osType` from the raw identity block are not exposed by the current legacy builder, but they're present in real data.** This is incidental, but it raises: the metadata declares what fields the section EXPOSES. Where in the vocabulary does "raw-but-unused" live? Either drop it (the legacy builder's choice) or expose it (broader). The vocabulary needs a stance.

### 1.2 `security_assessment` (report 336 — the vendor-severity case)

**Current canonical artifact.** 6 FindingsSection objects (one per dataset: Access Security / Auditing / Platform Security / Company and Owners Security / Capabilities / Hardening), 32 findings total, severities ingested via the phase-4 `status_to_severity` catalog mapping. Summary metrics on the artifact: critical=2, warning=0, good=12, info=18.

**Legacy SA shape (pre-phase-4, still on disk in `data/catalog/security_assessment/artifact_*.json`).** Top-level `findings` flat list[32], `status_counts={Critical:2, Good:12, Info:18, Warning:0}`, `sections=["Access Security","Auditing","Platform Security",…]` (just strings). The legacy bespoke `security_assessment_to_view` was a counters-chip + findings-grid view; phase 4 deliberately moved to canonical findings_list.

**Proposed three-face metadata (per section — applies uniformly to all 6 SA sections):**

```yaml
- id: security_assessment.access_security
  semantic:
    kind: findings
    entity: parameter
    fields:
      - { id: title,       source: Parameter, type: string }
      - { id: description, source: Remarks,   type: html_string, strip_html: true }
      - { id: action,      source: Action,    type: html_string, strip_html: true, extract: href }
      - { id: vendor_status, source: Status,  type: enum, values: [1_Good, 2_Info, 3_Warning, 4_Critical] }
    derived:
      - { id: category, value: "Access Security", type: string }
  presentational:
    render_as: findings_list
    group_by: derived.category
  evaluative:
    severity_source:
      kind: vendor_field
      field: vendor_status
      mapping: { 1_Good: good, 2_Info: info, 3_Warning: warning, 4_Critical: critical }
    template_rules: []
    overrides: {}
```

**Real-data application** (against the 6 raw REST extractions):

```
Total findings: 32
Severity distribution from vendor field: {info: 18, good: 12, critical: 2}
verdict_log[0] = {section: 'Capabilities', parameter: 'Users with master capabilities',
                  vendor_status: '2_Info', derived_severity: 'info', verdict_layer: 'vendor'}
```

This matches the canonical artifact exactly. The vocabulary fits this case cleanly.

**Strain or forced fits.**

- **`html_string` + `strip_html: true` + `extract: href` is doing a lot.** Real raw `Action` field: `'<a href="https://documentation.commvault.com/commvault/v11/article?p=7887.htm" target="_blank" >How to enable two factor authentication</a>'`. Phase 4 already invented this in code (catalog `status_to_severity` and HTML stripping). The three-face vocabulary inherits the question: **what's the canonical form of an "action" — a URL? a label? both? a hyperlink?** The current artifact stores just the link-text ("How to enable two factor authentication") with no URL. That's a data loss. If recommendations later want to surface "click here to remediate," the URL is gone. **Flagged: canonical action shape is undertheorised.**
- **`group_by: derived.category` is a soft cheat.** SA's section IS the category; each catalog row is one category. So the "group_by" is structural, not derived. The three-face model could instead make the *whole subject* a single semantic-`findings` block with one section per category — but then the per-section catalog row model breaks. **The grouping-cardinality tension is real:** SA's six sections are six findings groups, each rendered identically. Vocabulary needs to decide if "section per category" or "one section, group_by category" is the canonical shape. The current code is the first; the cleaner data model is arguably the second. **Flagged.**
- **`vendor_status` is the only field with a real type constraint** (`enum`). What does conformance failure mean when a vendor returns `5_Unknown`? Phase 4's code today silently downgrades unknown → `info`. The three-face vocabulary's "conformance failure must be LOUD" principle says it shouldn't — but the existing code does. **Flagged in Phase 3A below.**

### 1.3 `license_summary` (report 206 — the deliberate caveat)

**Current state.** LS is intentionally bespoke per phase-5 amendment. There ARE catalog rows for `license_summary.metadata`, `license_summary.other_licenses`, `license_summary.agent_feature_licenses`, `license_summary.workload_sections` — but `workload_sections` has NO extraction instructions wired (it's catalog-declared-only); the metadata section is also unwired; only `other_licenses` and `agent_feature_licenses` have CSV+HTML extraction rows.

**Legacy artifact shape (real data on disk):** flat top-level fields `workload_summary_sections: list[7]`, `other_licenses: list[N]`, `agent_feature_licenses: list[N]`, plus metadata fields (`commcell_id`, `license_expiry`, etc.). Workload sections carry `{section_name, rows[{license, entitlement_value, used, usage_percent, status, …}]}`.

**Proposed three-face metadata for LS workload section:**

```yaml
- id: license_summary.workload_sections
  semantic:
    kind: multi_section_table     # NEW kind vs ADR 0001 vocabulary
    entity: license_workload
    sections_field: workload_summary_sections
    section_name_field: section_name
    fields:
      - { id: license,           source: license,           type: string }
      - { id: entitlement_value, source: entitlement_value, type: string_with_unit }
      - { id: used,              source: used,              type: string_with_unit_optional_nullable }
      - { id: usage_percent,     source: usage_percent,     type: percent_string }
      - { id: status,            source: status,            type: string }
    derived:
      - { id: utilisation_numeric
          formula: "parse_percent(usage_percent) OR (parse_number(used) / parse_number(entitlement_value) * 100)"
          type: float
          nullable: true }
  presentational:
    render_as: workload_grid
  evaluative:
    severity_source:
      kind: derived_threshold
      field: utilisation_numeric
      thresholds: [{ warn_at: 70, critical_at: 90 }]
```

**Where it strains — these are the real phase-5 gaps revisited:**

1. **Page-aware GUID resolution.** Real measurement: `report_206_definition.json:pages` has 48 pages; `report_206_dataset_map.json:datasets` has 169 entries; 20 dataset names are duplicated; `'Get Last Collection Time'` appears **45 times** with 45 distinct GUIDs, one per page. The three-face vocabulary as proposed has no concept of "this dataset name is only valid inside this page" — it inherits ADR 0003's flat `dataset_name → guid` map. **The phase-5 gap is unchanged.** Adding semantic/presentational/evaluative faces doesn't address it. **Flagged.**

2. **Cross-dataset parameter substitution.** Real measurement: the LS 206 definition has 52 `"inputs"` blocks; one binds `id: orgGUID, fromDataSet: true, dataSetEntity: {dataSetName: GetOrganizationName, dataSetGuid: 0cbd2170-…}`. 130 parameter blocks reference `"=input.orgGUID"`. The vocabulary's metadata-only model has no slot for "this section's input parameter is the output of that section's primary key." **The phase-5 gap is unchanged.** Adding `evaluative` doesn't address this either; it's a collection-time prerequisite. **Flagged.**

3. **Per-row value formula (LicUsageType).** Real measurement: 78 references to `LicUsageType` in the 206 definition. This is the integer-code → unit-string dispatcher that phase 5 noted. The three-face semantic vocabulary as currently shaped supports `derived` formulas, but they're per-row, simple. A LookUpTable like `LicUsageType: {1: TB, 2: instances, 3: users, …}` is not the same as a numeric formula — it's a lookup. Could be modeled as `derived: { id: unit, lookup: LICENSE_USAGE_TYPE, key_field: LicUsageType }` — but the vocabulary as described doesn't define `lookup` yet. **Flagged: derived values need both `formula` AND `lookup` semantics.**

4. **The `string_with_unit` types are inelegant.** Real LS data has cells like `"500 VMs"`, `"0 sockets"`, `"25 TB"`, **plus** rows where the unit is in the column header `Available Total (TB)` and the cell is just the number, **plus** rows where Capacity Licenses' Used column is empty and the percentage lives in the Summary column as a styled status-bar div (HANDOVER backlog #22). The vocabulary needs to declare: "this field's value comes from cell text OR from column header OR from sibling-column status text." This is real complexity I encountered in three of the last four sessions. **Flagged: the unit-attachment and per-column-shape variations need to be in the vocabulary, not in code.**

5. **HTML-as-status (Capacity Licenses inside LS).** Real measurement: in the actual Commvault HTML export, the Capacity Licenses subsection of LS encodes utilisation as `<div class="status-bar complete-bar">0%</div>` in the Summary column with the Used column literally empty `<td></td>`. The semantic face needs to express "the utilisation value is HTML-encoded in this sibling cell" — a per-renderer fact that bleeds into the semantic layer. The clean three-face model gets muddy here. **Flagged: HTML-encoded measurement is real and recurring.**

### 1.4 `client_growth`

**Legacy builder.** `_build_client_growth_subject` at `subject_data_service.py:1087-1218`. Three sections: `summary` (meta — derived: total_clients, latest_month, added, YoY%), `chart` (chart_growth — months + totals + added arrays + latest_total + yoy_pct), `monthly_table` (table — Month, Total, Added, Removed).

**Proposed three-face metadata:**

```yaml
sections:
  - id: client_growth.summary
    semantic:
      kind: metric_aggregate
      entity: commcell
      derived:
        - { id: latest_total,  formula: "records[-1].total_clients",                                            type: int }
        - { id: latest_month,  formula: "records[-1].month",                                                    type: month }
        - { id: latest_added,  formula: "records[-1].added",                                                    type: int }
        - { id: yoy_pct,       formula: "(records[-1].total - records[-13].total) / records[-13].total * 100",  type: float, nullable: true }
    presentational: { render_as: metric_card }
    evaluative:
      template_rules:
        - { id: yoy_growth_warn,     field: yoy_pct, op: "<", value: -10, severity: warning,  label: "Year-over-year decline > 10%" }
        - { id: yoy_growth_critical, field: yoy_pct, op: "<", value: -25, severity: critical, label: "Year-over-year decline > 25%" }

  - id: client_growth.chart
    semantic:
      kind: timeseries
      entity: month
      series:
        - { id: total,  field: total_clients, type: int }
        - { id: added,  field: added,         type: int }
        - { id: removed, field: removed,      type: int }
      x_axis: month
      window: { points: 12, anchor: latest }
    presentational:
      render_as: bar_chart
      stack: [added, removed]
      line_overlay: [total]

  - id: client_growth.monthly_table
    semantic:
      kind: table
      entity: month
      fields:
        - { id: month,         source: month,         type: month }
        - { id: total_clients, source: total_clients, type: int }
        - { id: added,         source: added,         type: int }
        - { id: removed,       source: removed,       type: int }
    presentational:
      render_as: table
      sort: { field: month, direction: desc }
      limit: 24
```

**Real-data application.**

Source: `data/catalog/metrics/client_growth_summary.json:records[13]`. Latest record `{added: 0, month: 2026-05, total_clients: 5}`. `records[-13] = {month: 2025-05, total_clients: 0}`. Computed: `yoy_pct = (5-0)/0*100 → undefined (division by zero)`.

**Verbatim from real evaluation:**
```
records: 13
latest: {added: 0, data_source: 'cs01', month: '2026-05', removed: 0, total_clients: 5}
prev_year (12 months ago): {month: '2025-05', total_clients: 0}
YoY: cannot compute (prev_year total_clients=0)
```

**Strain or forced fits.**

- **YoY when baseline is zero.** The legacy builder returns `None` and hides the row. The proposed `template_rules` against a `nullable: true` derived value will never fire. What's the "correct" verdict? Vocabulary needs to decide: nullable inputs short-circuit to `unknown`? `info`? skipped silently? **The brief doesn't specify.** Flagged.
- **`formula` syntax.** I wrote `records[-13].total_clients` — but how is this expressed in catalog data, not code? JSON Path? Python expression strings? CEL? jq? Each has a different conformance shape and rule complexity. **The brief acknowledged "derived values are computed at collection time" but did not specify the formula language.** This is the same column_map-style question. Flagged loudly.
- **`window: { points: 12, anchor: latest }` is presentational AND collection-time.** The chart shows the last 12 months; the formula referencing `records[-13]` for YoY needs 13 months. If the source only has 11, what's the right behaviour? Vocabulary needs to declare: "this derived value requires N source records" so conformance catches it. **Flagged.**
- **Stale-data invisibility.** The legacy file is from May 13. The vocabulary has no temporal-freshness face. A renderer is "dumb" and draws stored truth — but the truth may be 16 days old. Where does freshness go? Source provenance? Evaluative ("stale > 7 days = warning")? **Flagged.** This is potentially a hidden fourth face: temporal / provenance.

### 1.5 `capacity_license`

**Legacy builder.** `_build_capacity_license_subject` at `subject_data_service.py:1222-1349`. Two sections (the chart-payload-but-never-emitted regression from the prior session): `summary` (meta — derived: latest_used, latest_purchased, utilisation_pct, period), `table` (table — Entity, Used, Purchased, Utilisation). Plus a computed-but-unused chart dict.

**Proposed three-face metadata:** structurally similar to client_growth. Add:

```yaml
- id: capacity_license.summary
  semantic:
    kind: metric_aggregate
    entity: commcell
    derived:
      - { id: latest_used_tb,      formula: "sum(records WHERE month=latest_month).used_capacity (after_sentinel_filter)",          type: float, unit: TB }
      - { id: latest_purchased_tb, formula: "sum(records WHERE month=latest_month).purchased_capacity (after_sentinel_filter)",    type: float, unit: TB }
      - { id: utilisation_pct,     formula: "latest_used_tb / latest_purchased_tb * 100",                                          type: float, unit: percent, nullable: true }
  presentational: { render_as: metric_card }
  evaluative:
    template_rules:
      - { id: util_warn,     field: utilisation_pct, op: ">=", value: 70, severity: warning,  label: "Capacity > 70%" }
      - { id: util_critical, field: utilisation_pct, op: ">=", value: 90, severity: critical, label: "Capacity > 90%" }
    sentinel_handling:
      sentinels: [-1]
      action: treat_as_null
      note: "License not active that month, not data error"
```

**Real-data application.**

Source: `data/catalog/metrics/capacity_license_usage.json:records[13]`. Verbatim from real evaluation:

```
2026-01 entity=CS01 - FFFFFFFF used=-1.0 purchased=-1.0 utilisation_pct=None
2026-02 entity=CS01 - FFFFFFFF used=-1.0 purchased=-1.0 utilisation_pct=None
2026-03 entity=CS01 - FFFFFFFF used=-1.0 purchased=-1.0 utilisation_pct=None
2026-04 entity=CS01 - FFFFFFFF used= 0.0 purchased= 0.0 utilisation_pct=None  (div by zero)
2026-05 entity=CS01 - FFFFFFFF used= 0.0 purchased= 0.0 utilisation_pct=None
Rules applied: warn>=70%, critical>=90%
Result: no rows trigger (all utilisation_pct=None)
```

The proposed model successfully expresses the computation against real data. The thresholds and sentinel handling are explicit. But:

**Strain or forced fits.**

- **Sentinel handling needs to be first-class.** `null_values` is already an ADR-0003 catalog key, but capacity_license's catalog row at `migrations/0003_report_inventory.sql:840-846` declares `null_values: [null]` — which doesn't catch the `-1` the REST API actually returns (HANDOVER backlog #22). The vocabulary needs to make sentinel handling LOUD enough that this can't slip through. The proposed `sentinel_handling` block is one shape; whether it belongs to `semantic` (the data has these sentinel values) or `evaluative` (we explicitly treat them as missing-not-zero) isn't obvious. **Flagged: sentinel handling is a real, recurring source of bugs. Where does it live in the three-face model?**
- **Division-by-zero (0/0) is conceptually different from sentinel-driven null.** "Customer hasn't purchased capacity yet" (0) is different from "license wasn't active that month" (-1). Both currently → `None`. The rules can't distinguish. **Flagged.**
- **The HTML-encoded percentage path (LS Capacity Licenses sub-section).** Real measurement, repeated from §1.3: Capacity Licenses' Used column in HTML is `<td></td>` and the Summary column holds `<div class="status-bar complete-bar">0%</div>`. The proposed formula `used / purchased * 100` doesn't apply — there IS no `used` to divide. Instead the percentage IS the source. So the semantic field-source map must support: "this metric's value is parsed from THIS column's HTML." **The three-face vocabulary doesn't yet have a clean way to say this.** Flagged.
- **Entity granularity is structural.** Real data has 1 row per (month, entity_name). Aggregating to (month) loses per-entity drill-down. The proposed metric_aggregate hides this. The legacy builder shows per-entity rows in a table; the metric_card aggregates. The vocabulary supports both forms (table section + metric section) but the data-coupling between them — they're computed from the same records — has no explicit declaration. If someone bumps one, the other silently de-syncs. **Flagged: cross-section data-source coupling.**

### 1.6 `backup_job_summary`

**Legacy builder.** `_build_backup_job_summary_subject` at `subject_data_service.py:1352-1490`. Four sections: `summary` (meta — total/completed/failed/running), `status_breakdown` (table — kv pairs from `bjs.status_breakdown`), `recent_failures` (findings — severity=crit hardcoded, title=client), `recent_jobs` (table).

**Proposed three-face metadata:** Four sections, each fitting cleanly into the vocabulary IF you accept that:

```yaml
- id: backup_job_summary.recent_failures
  semantic:
    kind: findings
    entity: job
    fields:
      - { id: title,       source: client,         type: string }
      - { id: description, source: failure_reason, type: string }
  presentational: { render_as: findings_list }
  evaluative:
    template_rules:
      - { id: any_failure, field: __presence__, op: exists, severity: critical, label: "Backup failure" }
```

**Real-data application.** Source: `data/catalog/quickhc/backup_job_summary_latest.json`. `recent_failures: list[0]` (the lab has no failures). `recent_jobs[0] = {job_id: "2001", client: "client-z", status: "Completed", start_time: "2026-05-20 09:00:00", duration: None, size: None, …}`. `status_breakdown: {Completed: 1}`.

**Strain or forced fits.**

- **`__presence__` is invented.** I made up `{ field: __presence__, op: exists }` to express "if any row is here, the section is critical." There's no such field in the data. This is the catalog model saying "this section's mere existence with rows is the verdict." The vocabulary as described doesn't have a clean syntax for "the existence of any row in this section is critical." **Flagged: not all rules evaluate per-row; some evaluate per-section. Vocabulary needs section-level rule support.**
- **`status_breakdown` is a KV map, not a table.** Real data: `{Completed: 1}`. The legacy builder rendered it as a tile-styled counter chips. The proposed `render_as: counters_chip` would work, but **the data shape (dict[str,int]) is fundamentally different from a tabular row-list.** It doesn't fit `semantic.kind: table`. Closer to `metric` but `metric` is usually scalar. The vocabulary needs another shape: `categorical_count_map` or similar. **Flagged: a real shape that doesn't fit the four section types in the canonical schema (findings/table/metric/chart).**
- **The empty-suite case.** `backup_job_summary` collection produces a canonical artifact with 1 section, 0 items, 0 columns. The workspace shows "Recent jobs: 0 rows" and nothing else — but the legacy builder would have shown a Summary stating "0 jobs · 0 failed" plus the status breakdown chip "Completed: 0." **The same regression as capacity_license: the catalog row is incomplete.** Vocabulary acceptance doesn't fix this — there's still an authoring question: did we declare all the sections this subject should have? The vocabulary needs to provide a way to detect this. **Flagged.**

---

## 2. Phase 2 — out-of-corpus stress

### 2.1 LS report 206 in full shape

Already addressed in §1.3 above. The three-face vocabulary inherits phase 5's gaps and adds nothing that closes them. Concretely:

| Phase-5 identified gap | Three-face vocabulary status |
|---|---|
| Page-aware GUID resolution (45× "Get Last Collection Time" with 45 GUIDs across 45 pages) | **Unchanged.** The semantic face declares fields per section but doesn't declare per-page context. |
| Cross-dataset parameter substitution (52 input blocks, 130 `=input.orgGUID` references binding to `GetOrganizationName`'s output) | **Unchanged.** No `inputs` declaration in the semantic face, no upstream-dataset reference shape. |
| Per-row value formulas (78 `LicUsageType` references — integer → unit-string lookup) | **Partially addressable** if `derived` supports `lookup` semantics with a referenced lookup table, but the vocabulary as described only mentions formulas, not lookups. |
| Multi-page structure (48 pages, only some of which produce surfaceable data) | **Not addressed.** The vocabulary is section-flat; pages are above the section level. Declaring "this subject reads pages 0, 4, 7" is structurally new. |

**Honest assessment:** the three-face vocabulary is orthogonal to the LS gaps. It doesn't worsen them but doesn't close them either. The same backlog item (#8 LS migration) remains regardless of ADR 0004.

### 2.2 Vendor compliance (report 336 = SA — the only one I have data for)

**Vendor verdict surface (measured).** 6 raw REST datasets, 32 rows total. Each row has a `Status` column with values from `{1_Good, 2_Info, 3_Warning, 4_Critical}`. Distribution: `{1_Good: 12, 2_Info: 18, 4_Critical: 2, 3_Warning: 0}` — the lab has no warnings.

**Apply three-face vocabulary's rule-layering precedence.** The brief specifies `vendor → template default → per-report override`. I exercised this against the real 32 rows:

```
Layer 1 (vendor only, no template/override rules):
  32 findings, severities {info: 18, good: 12, critical: 2}
  100% of verdicts attributed to layer='vendor'
  Matches phase 4's current behaviour exactly.

Layer 2 (template default rule overrides vendor):
  Rule: "if parameter=='Two-factor authentication' and vendor_status=='2_Info' → critical (org policy)"
  Hits: 1 row
    section='Access Security' parameter='Two-factor authentication'
    vendor='2_Info' → final_severity='critical' (verdict_layer='template_default')
  Aggregate: critical now = 3 (was 2), info now = 17 (was 18)
```

**Strain or forced fits.**

- **Override matching on free-text fields.** I matched `parameter == 'Two-factor authentication'`. But Commvault might rename that to "Two-Factor Authentication (2FA)" in a future release. Then the rule silently stops firing. Real rules need either (a) the stable vendor field `attrName` (in the raw data: `'2FAEnabled'`), or (b) a rule-condition language with fuzzy matching. **Flagged: rule identity vs vendor field stability is a real concern.**
- **`attrName` is hidden in the raw row.** Real measurement: each SA row has `attrName: '2FAEnabled'` / `'cleanupReport'` / `'SecureMountPaths-Secure'` etc. — Commvault's stable parameter identifier. **Phase 4's catalog `column_map` dropped this field** because the canonical Finding model has no slot for vendor-stable-key. So today's canonical artifact has NO way to reliably reference a finding for rule overrides. The semantic face needs to preserve a `vendor_key` or `stable_id` field. **Flagged: information that today's catalog drops is essential for the rules layer.**
- **Rule verdict layer attribution.** I added a `verdict_layer: 'template_default'` field to the artifact's finding. The brief says "the artifact records which layer produced the verdict." The vocabulary as proposed doesn't yet specify where this provenance attaches. Per-finding? Per-section? Per-subject? **Flagged.**
- **Vendor verdict CAN be wrong by design.** Commvault's `'Two-factor authentication = 2_Info'` is their judgement ("informational, not required"). A specific customer's policy says it's critical. The override is straightforwardly correct. But the inverse case — Commvault says `4_Critical`, customer policy says "we don't care about this" — needs a `severity: ignored` or `mute` verdict, OR the rule should output `severity: info` with a `muted: true` flag. The vocabulary doesn't have either. **Flagged: rule output enumeration must extend beyond {critical, warning, info, good} to {muted, deferred, n/a}.**
- **Vendor-provided "details" structure.** Real measurement: the `Remarks` field carries `'&#9679; 2 user groups without users<br>&#9679; 2 users without security associations<br>...'` for Auditing's "Security Cleanup report." That's structured data inside a string. A rule "warn if remarks contain more than N bullet points" is meaningful, but the vocabulary's `description: html_string, strip_html: true` deletes the structure. **Flagged: the strip-html-on-ingest decision is lossy in ways that matter for rules.**

### 2.3 A report that is neither in the six nor LS

**This is the explicit blind spot I declared in §0.**

What I CAN exercise: the catalog rows for two AI-created subjects in the DB:

| Subject | Catalog sections | Extraction wired |
|---|---|---|
| storage_utilization | kpi_metrics (metric), detail_table (table), health_chart (chart), usage_chart (chart) | only detail_table |
| cloud_storage_egress_ingress | by_storage_type (table), by_workload_operation (table), egress_pct_chart, ingress_pct_chart, egress_by_op_chart, ingress_by_op_chart (all 4 chart) | only the 2 tables |

**6 chart-typed catalog rows exist with NO extraction wiring.** Even if the AI proposed these subjects with chart sections, the system cannot collect data for them — and crucially, the existing canonical extractor cannot produce chart sections at all (the `ChartSection` model exists, no code instantiates it). The catalog is over-declaring; the runtime is under-capable.

**What I CANNOT exercise.** I have:
- No raw extracted data for storage_utilization (report 146) or cloud_storage_egress_ingress (reports 56 or 300).
- No HTML or CSV exports for either.
- No canonical artifacts on disk for either.
- 17 other reports listed in `reports.json` with NO datasets, NO definitions, NO samples.

**What this means for the survey.** Phase 2 step 3 was a stress test on novel structure. We don't have a novel report to stress against. Any claim that the vocabulary "handles" e.g. "Storage Usage" report 342 (which the catalog declares includes "predicted growth and date to be full") would be hand-waving. **Flagged: ADR 0004 will be designed against 3 of 20 reports. The other 17 are unverified.**

**Specifically:** the "Storage Usage" report's description says "predicted growth and date to be full" — that's a *fourth-face* (predictive) value computed by Commvault. The three-face vocabulary doesn't have a slot for "I have vendor-computed projections too." That's not just recommendations-deferred — that's "vendor MAY already be providing the prediction." The evaluative face was scoped to "rules"; vendor-prediction-fields don't fit. **Flagged: vendor predictions are a real surface.**

---

## 3. Phase 3 — adversarial questions

### A. Conformance failure

**Scenario:** capacity_license REST collection where the API drops the `Used Capacity` column from the response. (Plausible: Commvault renamed it in a release; or the dataset GUID resolved to a different version of the dataset.)

**Apply the proposed `semantic.fields` declaration:**
```yaml
fields:
  - { id: used,       source: Used Capacity,      type: integer }
  - { id: purchased,  source: Purchased Capacity, type: integer }
  - { id: month,      source: Month,              type: month }
  - { id: entity,     source: Entity Name,        type: string }
```

When the REST response omits `Used Capacity`:
- **Conformance check would catch it** at section-build time: "section capacity_license.table declares field 'used' sourced from 'Used Capacity'; column not present in dataset response → CONFORMANCE FAILURE." Consultant sees: "REST collection failed: required source field 'Used Capacity' missing from dataset f2bfe9ce-… on report 318."
- **The brief's "LOUD failure" principle is satisfied** for missing required columns.

**But conformance can succeed while output is still wrong:**

1. **Type widening.** API returns `"Used Capacity": "100 TB"` (string with unit) instead of integer. Type=integer conformance check: either fails (clean) OR silently parses "100" and drops the unit (bad). The vocabulary needs to make the choice explicit. Today's `parse_number` regex extraction (HANDOVER recent fix) is silently-tolerant. **Gap.**

2. **Semantic mismatch with same column name.** SA's `Status` column traditionally returns `1_Good`/`2_Info`/etc. Imagine Commvault adds a new health-pillar report with column ALSO named `Status` returning `Pass`/`Fail`/`Skip`. The catalog rule `status_to_severity: {1_Good: good, 2_Info: info, ...}` doesn't match `Pass`. Today's phase-4 code defaults unknown → `info`. **Conformance check would NOT catch this** unless the vocabulary declares `vendor_status: enum, values: [1_Good, 2_Info, 3_Warning, 4_Critical]` and the conformance check is strict. **The brief says "no silent degradation."** Today's code silently degrades. **Gap.**

3. **Cardinality mismatch.** LS workload sections declare 7 expected sections via `SUMMARY_SECTION_NAMES`. If a future Commvault release renames one ("Operating Instance Licenses" → "Operating Instances"), the parser produces 6 sections — silently. Conformance check would only catch this if it knows the expected section set. **Vocabulary as proposed doesn't declare expected cardinalities, only field-presence.** Gap.

4. **Pagination silently truncated.** Today's REST extractor uses `limit` from the catalog. If `totalRecordCount > limit`, the catalog row's `limit` is too low — extractor returns what it got, and the artifact has fewer rows than the source had. **Conformance doesn't catch "I asked for the first 100 and there were 500."** Gap.

5. **Section structure mismatch with backwards-compatible payload.** Commvault adds a new column (e.g. `MigrationStatus`) to an existing dataset. Catalog declares fields explicitly → new column dropped. That's OK. But if the new column is the AUTHORITATIVE source (e.g. Commvault deprecates `Status` in favor of `StatusV2`), the catalog continues reading the deprecated `Status` and conformance can't tell. **Vocabulary has no concept of "watch for deprecation" or "this field MAY be authoritative."** Gap, but possibly out of reasonable scope.

**Pinned gaps from A:** type tolerance, enum strictness, cardinality declaration, pagination conformance, field deprecation are all unaddressed.

### B. Derived values

#### B.1 capacity_license utilisation

**Legacy code (subject_data_service.py:1265):**
```python
utilisation_pct = round(latest_used / latest_purchased * 100, 1) if latest_purchased > 0 else 0.0
```

(Note: `else 0.0` — silently emits 0 when purchased is zero, which is wrong but won't fire any rules.)

**In the proposed model:**
```yaml
derived:
  - id: utilisation_pct
    formula: "latest_used / latest_purchased * 100"
    type: float
    nullable: true
    requires: [latest_used >= 0, latest_purchased > 0]
```

**Where does this live?** Brief says "computed once at collection time and stored." The collection-time computation runs after extraction, against `result.sections[section_id].rows`. So `result_to_artifact._build_finding` (or its TableSection equivalent) would invoke a formula evaluator BEFORE building the `CanonicalArtifact`. The derived value ends up as part of the section's data (which the brief specifies). Renderer reads stored truth.

**Catalog-expressibility boundary:** I need to declare a formula language. Candidates:
- **JSONPath + simple ops** — handles "records[-1].used", basic math. Can't handle "sum where month=X."
- **Python expression strings** — most expressive, but code execution is now catalog data. Conformance check against a Python eval is hard.
- **CEL (Common Expression Language)** — Google's choice. Statically-typed, sandboxable. Real implementation overhead.
- **jq** — well-defined, sandboxable, supports aggregation. Learning curve.
- **A hand-rolled mini-DSL** — every project I've seen do this regrets it within 18 months.

**The vocabulary as described doesn't pin a choice.** Each choice has different conformance shapes, evaluation costs, and authoring difficulty. **Flagged loudly: the formula language is the next column_map decision.**

**Catalog-expressible vs code-required boundary:** I think the realistic boundary is:
- **Catalog-expressible:** field-level transforms (parse_number, parse_percent, strip_html); aggregations (sum, count, min, max, latest) over named windows; threshold predicates; lookups against named tables.
- **Code-required:** anything that needs Python's `re` module beyond a simple pattern; multi-step state machines (e.g. LS's HTML status-bar parsing); anything that hits the network; anything that's per-customer dynamic.

**The brief says "new INSTANCES of known types add via data; new TYPES are code." This is the same boundary for formulas: known-shape formulas (sum, count, ratio, lookup) add via data; new transform types (HTML status-bar extraction, multi-cell pivot) are code.** Make this explicit in the ADR or it will be re-litigated per derivation. **Flagged.**

#### B.2 client_growth YoY

```yaml
derived:
  - id: yoy_pct
    formula: "(records[-1].total_clients - records[-13].total_clients) / records[-13].total_clients * 100"
    type: float
    nullable: true
    requires: [records.length >= 13, records[-13].total_clients > 0]
```

The `requires` clause prevents division-by-zero AND insufficient-data cases. The brief mentions "Conformance failure must be LOUD" — does insufficient history (only 10 records, can't compute YoY) qualify? **The vocabulary needs to declare:** is `requires` failure a conformance failure (loud) or a derived-value-is-null silent skip? **Real data:** client_growth has 13 records, but `records[-13].total_clients = 0`, so YoY is null. The legacy builder silently skips. The proposed model could be either way; the brief doesn't say. **Flagged.**

### C. Rules layering precedence — vendor, template, override

**Walked through with real SA data in §2.2 already.** Three additional concerns surface when I try to express this AS DATA:

**Catalog shape for rules:**
```yaml
# Per-template (subject) default rules
template_rules:
  - id: yoy_critical_decline
    field: yoy_pct
    op: "<"
    value: -25
    severity: critical
    label: "Year-over-year decline >25%"

# Per-report (project-scoped) overrides
overrides:
  - rule_id: yoy_critical_decline           # update existing template rule
    new_value: -15                           # tighter threshold for this customer
    reason: "Customer policy: any YoY <-15% is escalated"
  - rule_id: new_custom_rule                 # add a new rule
    field: latest_total
    op: "<"
    value: 100
    severity: warning
    label: "Total clients below baseline"
```

**Precedence:** the runtime evaluator should walk vendor → template_rules → overrides, with each layer modifying or shadowing the previous. The artifact stores the final verdict AND the chain that produced it: `verdict_chain: [{layer: vendor, severity: info}, {layer: override, severity: critical, rule_id: yoy_critical_decline, reason: …}]`.

**Concerns:**

1. **Rules-by-name vs rules-by-content.** The brief says "rules are REFERENCEABLE by name." But the example above has overrides keyed by `rule_id: yoy_critical_decline`. That id has to be unique, stable across template versions, and referenceable from the report-override layer. **The catalog needs a rules-registry with unique IDs.** Not declared by the vocabulary. **Gap.**

2. **Template default rules apply to many subjects.** A rule like "any backup with elapsed > 24h is warning" applies to backup_job_summary AND restore_job_summary AND DR validation reports. The vocabulary should let one rule attach to multiple subjects/sections. Today's proposed model attaches rules per-section. **Flagged: rule scope.**

3. **Order matters and is implicit.** vendor → template → override is the brief's stated order. But within a layer, multiple rules can fire. Whose wins? E.g. if template has "warn if value<10" and "critical if value<5", and value=3, both fire — does the artifact record both, or only the highest? **Today's SA code overwrites silently.** Vocabulary needs precedence-within-layer rule. **Gap.**

4. **Negation / mute.** Override = "I do not want vendor's critical here." Today's vocabulary can't express "set severity to good" because that's lying. The right verdict is `muted: true, original: critical`. Brief's evaluative face doesn't yet have `muted`. **Gap — same as §2.2 raised.**

### D. Vocabulary evolution

**The brief says: new instances of known types add via data; new TYPES require code.**

**Pick a plausible new type: sparkline.** The Commvault Storage Utilization report (146) has a per-storage-pool growth curve. A sparkline is a small inline chart, not the full chart_growth/chart_capacity treatment.

**Code changes required to add sparkline:**

1. **Schema (`artifacts/models.py`).** Add a `SparklineSection` or extend `ChartSection` with a `chart_type: sparkline` variant. The `ChartSection` model already has `chart_type: ChartType` — so extending the `ChartType` enum + adding renderer-specific fields (small width, no axes). Maybe 30 lines.

2. **Catalog vocabulary (`subject_sections.section_type`).** Add `sparkline` as a recognised section_type. Currently the SQL column is free-text. The catalog's `output_as` would extend: `table | findings | card | sparkline`. ~5 SQL lines in a migration.

3. **Renderer (`canonical_view.py`).** Add a sparkline branch in `artifact_to_view`. The current code has no chart branch at all — sparkline is the *first* chart-like canonical render. Maybe 20 lines.

4. **Workspace JS (`quick_hc.js`).** Add `sec.type === 'sparkline'` branch alongside `chart_growth`, `chart_capacity`. ~15 lines.

5. **Result-to-artifact (`extractors/result_to_artifact.py`).** If sparkline data is computed from the table extraction (e.g. last 12 months from a 36-month table), the result builder needs to either know to emit a sparkline alongside the table, OR the extractor needs to handle `output_as: sparkline` directly. The brief's "derived values computed at collection time" suggests sparkline could be a derived section computed from table data. Need to decide: section-or-derived? **Flagged: the vocabulary doesn't yet say.**

**Rough estimate:** ~100 lines of code + 1 migration + 1 test file (~5 test cases). Half a day's work for a new section TYPE.

**Forward-looking: new types I'd guess will be wanted within a year:**

1. **Heatmap.** Coverage matrix: clients × backup type, color = success rate. Real for compliance dashboards. Not expressible as table/chart/findings/metric.
2. **Geographic map.** Client locations vs status. Commvault deployments span multi-site customers; this surfaces in consultant pitches.
3. **Timeline / Gantt.** Backup window vs SLA. Same shape as Storage Usage's "predicted growth and date to be full."
4. **Diff card.** Before/after comparisons (e.g. finalisation N vs working state). Comes from the ADR 0002 finalization model.
5. **Threshold gauge.** Single-number with min/max/current — same as utilisation_pct but rendered as a gauge instead of text. Probably should be a render mode of metric, not a new type.
6. **Action ticket.** AI-recommendation surface: "do this thing, click here to execute" — half-render, half-action. Recommendations-driven.

**1, 2, 3, 4 are all real possibilities the brief's "new types are code" rule already covers.** 6 is interesting: the rec/action surface is a FOURTH face the brief deferred. Designing the section-type enum without considering "action-bearing sections exist" risks lock-in. **Flagged.**

**On the AI-author angle:** the catalog's two AI-proposed subjects already include chart sections the system can't yet collect. If AI proposes a heatmap section (because the report it's templating naturally is one), the vocabulary needs to either reject it (loud failure: "vocabulary doesn't include heatmap") or queue it for human-coded support. The brief doesn't specify this gate. **Flagged.**

### E. Recommendations deferral

**Does ADR 0004 paint recommendations into a corner?**

The brief's evaluative face produces severities {critical, warning, info, good}. Recommendations (predictive/prescriptive) are a fourth face deferred.

**Concrete adversarial probe:**

- A future rec face wants to say "based on current capacity utilisation trend, you will hit 90% in 47 days." This needs: historical data window, current value, trend slope, target threshold. The data exists in the same `records` list the evaluative face already consults.
- The CURRENT evaluative face is *snapshot-evaluative* — "is this value over threshold right now?" It doesn't carry a "tell me about the trajectory" shape.
- The proposed `derived` block COULD compute slope/projection and store it. Then the evaluative face could threshold against it: `derived: { id: days_until_full, formula: project_linear(records, target: latest_purchased * 0.9), type: int }` + `template_rules: [{ field: days_until_full, op: <, value: 30, severity: warning }]`. This is **already what the brief allows.**

**Where does the recommendations face actually need to attach?**

1. **Prescriptive action ("expand to 200 TB now").** This is not a value, it's an instruction. The evaluative face produces `severity: critical`; the rec face needs to produce a `recommended_action: {kind: expand_capacity, target_tb: 200, deadline: 2026-08-15, reason: …}`. Today's vocabulary has no slot for action-payloads attached to a verdict. **Flagged: actions don't fit the verdict enum.**

2. **Verdict-bearing prediction ("at this rate you'll hit 90% in 47 days").** The DERIVED VALUE can already express "days_until_full" today. The evaluative face can threshold it. **No retrofit needed.** Confirmed cleanly.

3. **What-if analysis ("if you delete inactive clients, projection becomes…").** Multi-state derivation. Not expressible in the proposed `derived` formula model — it needs branching, scenario inputs. **Flagged: scenario-bearing derivations don't fit.**

**Minimal change to evaluative face that leaves room without implementing it now:**

Add to each rule's output:
```yaml
template_rules:
  - id: util_critical
    field: utilisation_pct
    op: ">=" value: 90
    severity: critical
    recommendation_hook:        # FUTURE — not implemented in ADR 0004
      kind: action
      payload_ref: capacity_expansion_playbook
```

The `recommendation_hook` field is a forward-declaration. ADR 0004 ignores it; ADR 000N (later) interprets it. This way evaluative-face rules don't have to be refactored later. **Concrete minimal proposal.**

**Honest caveat:** I could only test this against the conceptual model. I have no real recommendation-bearing data to exercise it against.

---

## 4. Consolidated gaps

Each gap is something the survey actually surfaced against real data or against a specific phase-of-implementation gap. Steering chat decides scope.

### Vocabulary structure gaps

**V1. Section-type enumeration is undeclared.** Brief says "presentational face: chart, table, summary-metric, findings, multi-section, card; possibly others." But:
- The canonical schema today has `findings | table | metric | chart`. Catalog SQL has `metric | table | findings | chart`.
- JS today renders `findings_list | findings_grid | counters | workload | chart_growth | chart_capacity | table | meta | text`.
- Multi-section (LS workload) doesn't fit any existing model class — it's a category-of-tables.
- Vocabulary needs an explicit closed enumeration with mapping rules between section_type ↔ rendered shape ↔ artifact model class.

**V2. Identity-vs-metric semantic distinction.** Section semantic.kind must distinguish facts-about-the-thing (identity) from measurements-of-the-thing (metric). Environment is the only pure identity case. Mixing them confuses rules.

**V3. Multi-section / grouping cardinality.** SA has 6 sections each rendered identically (one per category). LS has 1 section holding 7 workload sub-sections. Two different shapes for the same logical pattern. Vocabulary needs to pin one or both.

**V4. Section data-source coupling.** capacity_license has a `summary` metric AND a `table` table, both derived from the same `records`. Their data coherence is implicit. Cross-section linkage (same source, different derivations) needs declaration so renames don't desync.

### Derived-value gaps

**D1. Formula language is undeclared.** The biggest gap in the vocabulary. JSONPath, CEL, Python expr strings, jq, hand-rolled DSL — each is a different conformance shape, evaluation cost, authoring difficulty. Without a choice, every derivation will be argued individually.

**D2. Catalog-expressible vs code-required boundary is implicit.** Same pattern as the `column_map` decision in ADR 0003 phase 4 — surfaces during implementation. Pin it now: aggregation primitives + threshold predicates + lookup tables = catalog; everything else = code.

**D3. Required-input declaration for derivations.** `requires: [records.length >= 13]` style precondition is needed for YoY and similar. Declaration shape + behaviour-when-missing not specified.

**D4. Lookup tables.** LS's `LicUsageType` integer → unit string is a lookup, not a formula. `derived` block doesn't yet have a `lookup` semantic.

**D5. Sentinel-value handling.** `-1 = "not active that month"` is real and recurring. Belongs to semantic? Evaluative? Currently flounders between them. Vocabulary needs to pin it.

**D6. Division-by-zero distinct from sentinel.** "Customer hasn't purchased" (0) and "license wasn't active that month" (-1) currently both → None. Rules can't distinguish. Vocabulary needs a way for the rule engine to see WHY a value is null.

### Evaluative-face gaps

**E1. Rule identity stability.** Override matching by free-text "parameter" name is fragile (Commvault may rename). Need stable vendor-keys preserved in the canonical artifact — and phase 4's column_map currently drops them (`attrName` is dropped today). **Today's catalog has a load-bearing data loss.**

**E2. Verdict attribution / layer provenance.** The artifact must record which layer (vendor / template / override) produced the final verdict. Brief mentions this but vocabulary doesn't yet specify the attachment point.

**E3. Severity enumeration extension.** Today: `{critical, warning, info, good}`. Need: `muted`, possibly `n/a`, possibly `deferred`. Override-to-mute is a real use case.

**E4. Section-level rules vs per-row rules.** "If any failure exists, this section is critical" is section-level, not row-level. Vocabulary as proposed is per-row-field only.

**E5. Rule scope across subjects.** A rule like "warn if backup elapsed > 24h" applies to many subjects. Today's vocabulary attaches rules per-section.

**E6. Precedence-within-layer.** If two template rules both fire (warn at 70% AND critical at 90%, value=95), behaviour undefined.

**E7. Rule registry / referenceability.** Brief says "rules are REFERENCEABLE by name." Catalog needs a registry table with stable IDs. Not declared by the vocabulary.

### Conformance gaps

**C1. Type tolerance.** `type: integer` with `"100 TB"` input — parse-and-warn, fail-loud, or silent-pass? Today's code is silent-pass (parse_number regex).

**C2. Enum strictness.** SA Status today: unknown values silently → info. Brief says "no silent degradation." Today's code degrades silently. Pick.

**C3. Section cardinality.** LS expects 7 workload sections. If 6 arrive, conformance doesn't catch it.

**C4. Pagination integrity.** REST's `limit` is a catalog field. Conformance doesn't check `received_count < totalRecordCount` and warn.

**C5. Field deprecation watch.** Vocabulary has no way to declare "this field is the authoritative source; if a `vN+1` variant appears, flag it."

### LS-specific gaps (phase 5 still open)

**LS1. Page-aware GUID resolution.** 45 distinct GUIDs share the dataset name "Get Last Collection Time" across 45 of 48 pages. The three-face vocabulary does not address this.

**LS2. Cross-dataset parameter substitution.** 52 inputs blocks, 130 `=input.orgGUID` references. The three-face vocabulary does not address this.

**LS3. Per-row value formulas via integer lookups.** 78 `LicUsageType` references — same as D4 above. Catalog `lookup` semantic needed.

**LS4. Multi-page structure as a first-class concept.** The vocabulary is section-flat. Pages above sections are not declarable.

**LS5. HTML-as-measurement.** Capacity Licenses inside LS encodes utilisation in a styled status-bar div in a sibling column. The semantic face has no slot for "this metric's value lives in cell text decoded from HTML."

### Recommendations-face hooks

**R1. Action-bearing verdicts.** Recommendations include playbook actions; the evaluative face produces severity strings only. Forward-declare an extension slot.

**R2. Scenario-bearing derivations.** What-if analyses need branching/scenario-input formulas. Out of scope for ADR 0004 but flagging shape.

**R3. Vendor-provided predictions.** Some Commvault reports (e.g. Storage Usage) provide "predicted growth" and "date to be full" already. The evaluative face was scoped to severity rules; vendor-prediction fields don't fit cleanly.

### Methodology gaps

**M1. Phase 2 step 3 is a real blind spot.** Only 3 of 20 reports in `reports.json` have any sample data. The two AI-proposed subjects (storage_utilization, cloud_storage_egress_ingress) have catalog rows but zero data. ADR 0004 will be designed against 15% of the report inventory.

**M2. Vendor-severity evidence is single-source.** SA is the only report with real vendor severity data. Rule-layering precedence is exercised only against SA. If Commvault's other compliance reports use different severity conventions, we won't catch it until implementation surfaces.

**M3. Stale-data freshness is not in the three-face model.** Legacy capacity_license file is 16 days old. ADR 0004 has no temporal face. Freshness might belong to a separate "provenance" face or to evaluative ("stale > N days = warning"). Undefined.

---

## 5. Surprises

**S1. The catalog already over-declares.** `storage_utilization` and `cloud_storage_egress_ingress` have 6 chart-type catalog rows with NO extraction wiring. The catalog SQL `section_type='chart'` value works (no constraint), but no extractor can produce a ChartSection. The catalog is currently aspirational beyond the runtime. ADR 0004 needs to decide: do catalog rows for features the runtime doesn't support fail loudly at insert, fail loudly at collection, or silently render nothing? **Today they silently render nothing.**

**S2. `_capacity_license_chart` in the legacy code path is unreachable.** From last session: the `_build_capacity_license_subject` builder computes a chart payload but never emits it as a section. ADR 0004 might delete this code (dead), but it's also evidence that the project already attempted this pattern. The chart-section data structure is not novel; it's been computed-but-discarded.

**S3. Phase 4 dropped `attrName`.** Real measurement: every SA REST row carries `attrName` (Commvault's stable vendor-key, e.g. `'2FAEnabled'`). The phase-4 catalog column_map drops it. This is a load-bearing data loss for the rules-layering future. Suggests ADR 0004 should mandate preserving vendor-stable IDs even when the canonical model "doesn't need them yet."

**S4. The system has 6 different render shapes for findings/tables/charts.** workspace JS handles: `findings_list`, `findings_grid`, `counters`, `workload`, `chart_growth`, `chart_capacity`, plus base `table` and `meta`. **The canonical schema knows about 4 (findings, table, metric, chart) and only emits 3 (findings, table, metric).** The legacy builders emit the others. ADR 0004's "presentational face" must reconcile these — it cannot just pick the canonical 4.

**S5. The cleaner three-face model arguably calls for redoing the section type enum.** When I tried to express SA's 6 sections (six rendered identically), the cleanest model was a single subject-level "findings collection" with category grouping. But the catalog as-shipped uses 6 separate sections. The three-face vocabulary could either rationalise this (one logical section, multi-group rendering) or accept the catalog shape (many sections, structural grouping). Both have implementation implications. Today's catalog reflects phase-4's choice; ADR 0004 might pick differently.

**S6. The "evaluative face is just rules" framing is narrower than the data suggests.** Real measurement: SA's `Status` field carries Commvault's verdict, but the `Remarks` field carries SUPPORTING EVIDENCE (`'2 user groups without users'`). A rule "warn if remarks contain >1 issue bullet" is meaningful; the brief's evaluative face as described is field-value-threshold focused. Vendor-evidence content might be a third evaluative-face variant. Not a gap exactly; just the brief's framing might be narrower than the data.

**S7. The system already has a "fourth face" pattern via source.collected_at and source.generated_on.** Legacy artifacts carry `collected_at`, `generated_on`, `last_collection_time`. These are provenance/freshness data. Today's vocabulary doesn't include them but every artifact carries them. The "fourth face" the brief hints at (predictive) might not be the only fourth face — provenance/freshness is also unaccounted. Calling it out so the brief's scoping is intentional, not accidental.

**S8. AI-authored subjects already exist in the catalog with chart sections.** This is a forcing function the brief hasn't reckoned with: the AI-proposal workflow generates catalog rows including section types that may not be supported. ADR 0004 needs to decide if AI proposals are validated against the section-type enum (loud failure for unsupported types) or if they queue for human review. Today neither path exists — the rows just sit there silently unsupported.

**S9. The "renderer is dumb" principle is good but the workspace template has accumulated complex per-type logic.** Real measurement: `quick_hc.js:155-260` has explicit branches for 8 section types, each with custom HTML generation. The "dumb renderer reading stored truth" principle requires either (a) the artifact already contains rendering-ready HTML/structure, or (b) the renderer is dumb for canonical primitives. The current code is in between. ADR 0004 should pick: do renderers consume primitive section-type + serialized data (current), or pre-rendered viewmodels (more lossy, less dumb)?

**S10. Phase 4's deliberate redesign of SA's rendering (findings_grid → findings_list) is a precedent.** Phase 4 explicitly accepted "consultants who had those artifacts around needed to re-collect." If ADR 0004 is going to extend the canonical schema with more section types, the same re-collection cost applies. Not novel news, but: ADR 0004's blast radius extends to wipe-and-recreate for every existing subject. The HANDOVER's wipe-and-recreate methodology marker (#17) is directly relevant.

---

That's the survey. The gap that most worries me is **D1 (formula language)** — it's a column_map-shaped decision that will reappear at implementation time and force a Path A/B fork. The gap most likely to undermine the rules layer is **E1 (vendor-stable IDs being dropped at ingest)** — it's a load-bearing data loss in TODAY'S catalog that the ADR needs to fix before rules can be reliable. The deepest unverified-design risk is **M1 (only 3 of 20 reports exercised)** — by the same lesson as phase 5, the easy cases don't calibrate the design.