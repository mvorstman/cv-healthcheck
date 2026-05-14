# Data Source Mapping

Architecture-level source strategy for cv-healthcheck operating modes.

This document maps healthcheck subjects to practical data sources for:

- Daily Reporting
- Quick HC
- Full Healthcheck

It does not define health scoring, thresholds, severities, or implementation tasks. Those belong in later collector and health-rule design after source availability is clear.

## Source Strategy

Direct CommServe REST access is often best for current configuration and operational state. Reports Plus / Metrics is often best for trends, history, aggregation, and customer scenarios where direct CommServe access is unavailable. In many customer environments, Reports Plus / Metrics access may be the only realistic remote datasource for the central reporting platform.

In this project context, **Reports Plus == Metrics**. Use `Reports Plus / Metrics` to mean data available through the Command Center Reports Plus engine, private Metrics servers, Metrics reports, or related report/dataset execution paths.

Source exploration rule:

1. Where possible, explore both Command Center REST APIs and Reports Plus / Metrics datasets for every subject.
2. Do not treat either source as permanently exclusive.
3. When both sources exist, validate both and compare usefulness before choosing the operational pipeline.
4. Use email, import, uploaded snapshot, or manual export only as a last resort.

Important caveats:

- `reportId` values may be environment-specific. Prefer semantic report names, report GUIDs, dataset metadata, and validated field shapes where possible.
- `commUniId` identifies the CommCell instance in Metrics deep links and should be captured when mapping Metrics records back to a CommCell.
- Live APIs remain authoritative where available.
- Catalog files under `data/catalog/` are local artifacts and discovery outputs, not source of truth.
- Dataset GUIDs, report composition, and returned fields must be validated per environment before relying on them.

## Practical Mapping

| Subject | REST availability/usefulness | Reports Plus / Metrics availability/usefulness | Quick HC preferred source | Daily Reporting preferred source | Full HC preferred source | Fallback source | Caveats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CommCell identity/version | High. Best for current CommServe identity, version, OS, timezone, and GUID. | Useful if Metrics inventory exposes CommCell identity and `commUniId`. | REST | Reports Plus / Metrics if central REST is unavailable; otherwise REST snapshot | REST plus Metrics identity correlation | Import/manual export | Quick HC / Daily Reporting / Full HC subject. Live REST is authoritative for current version and identity. Capture `commUniId` when sourced from Metrics deep links. |
| Licensing | Likely useful for current license state where exposed. | Useful for licensing reports, summaries, and customer-provided report access. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics evidence | Manual license export | Quick HC / Daily Reporting / Full HC subject. Licensing data can be permission-sensitive and may be incomplete in either source. |
| Clients | High for current client inventory and properties. | High for inventory, history, growth, aggregation, and multi-CommCell summaries. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics trends | Import/export | Quick HC / Daily Reporting / Full HC subject. Validate both sources and compare field completeness before choosing pipeline. |
| Client groups | High for current groups and membership. | Useful if group inventory or scoped reports are available. | REST | Reports Plus / Metrics when available | REST plus report-derived group context | Manual export | Quick HC / Daily Reporting / Full HC subject. Membership freshness should be checked against REST when possible. |
| Plans | High for current plan configuration and relationships. | Useful for plan coverage and policy-style reports. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics coverage evidence | Export | Quick HC / Daily Reporting / Full HC subject. Plan-to-workload relationships may require multiple REST calls or report composition mapping. |
| Storage pools | High for current storage pool configuration and status. | High for capacity reporting, aggregation, and trends. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics capacity history | Import/export | Quick HC / Daily Reporting / Full HC subject. Metrics is useful for capacity reporting; REST is preferred for current configuration. |
| Disk libraries | High for current library configuration where exposed. | Useful for capacity/usage reports and historical usage. | REST | Reports Plus / Metrics | REST plus storage evidence and Metrics trends | Manual storage export | Quick HC / Daily Reporting / Full HC subject. Mount paths and free space may require customer-side collection when central access is limited. |
| Media agents | High for current MediaAgent list, roles, and status. | Useful for availability, capacity, and operational summaries. | REST | Reports Plus / Metrics | REST plus customer-side service snapshots and Metrics summaries | Import/export | Quick HC / Daily Reporting / Full HC subject. REST is preferred for current status; Metrics may lag but can provide history. |
| Deduplication / DDB | Useful for current DDB, storage pool, and DDB job state where exposed. | Useful for DDB reports, capacity trends, and operational history. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics history and uploaded evidence | Uploaded exports | Quick HC / Daily Reporting / Full HC subject. DDB details may be split across storage, job, and report sources. |
| Jobs | High for current/recent job controller and job history state. | High for recurring summaries, historical activity, and aggregation. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics trends | Email/import | Quick HC / Daily Reporting / Full HC subject. Compare recency, retention, and filter semantics across both sources. |
| Failed jobs | High for current/recent failure details and drill-down. | High for recurring failed-job reports and historical summaries. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics failure history | Email/import | Quick HC / Daily Reporting / Full HC subject. Daily Reporting can be Metrics-first when central REST is unavailable. |
| SLA | Variable; useful if SLA endpoints or workload status are exposed. | High. SLA is often report-native and trend-oriented. | Reports Plus / Metrics when available; REST for live workload context | Reports Plus / Metrics | Reports Plus / Metrics plus REST workload and policy context | Import/export | Daily Reporting / Quick HC / Full HC subject. Metrics may be the primary source even when REST exists. |
| Alerts | High for current active alerts and alert details. | Useful for alert summaries, history, and email/report-driven workflows. | REST | Reports Plus / Metrics or email digest when that is the established report path | REST plus Reports Plus / Metrics alert history | Email/import | Quick HC / Daily Reporting / Full HC subject. Email alerts are useful as last-resort evidence, not authoritative inventory. |
| Schedules | High for current schedule policy/list details. | Useful if schedule reports or plan coverage datasets exist. | REST | Reports Plus / Metrics when available | REST plus Reports Plus / Metrics coverage context | Export | Quick HC / Daily Reporting / Full HC subject. Current schedule configuration should come from live API when possible. |
| Tenants / companies | High for current company and tenant configuration. | High for tenant-scoped summaries and company reporting datasets. | REST | Reports Plus / Metrics | REST plus tenant-scoped Reports Plus / Metrics evidence | Export | Quick HC / Daily Reporting / Full HC subject. Metrics may expose tenant-scoped summaries without central CommServe REST. |
| Storage usage / capacity | High for current storage pool/library capacity and status. | High for capacity reports, trends, aggregation, and growth context. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics trends and storage evidence | Import/export/manual evidence | Quick HC / Daily Reporting / Full HC subject. Live APIs remain authoritative for current state; Metrics is preferred for history. |
| Growth trends | Limited unless REST exposes usable historical records. | High. Growth and Trends reports/datasets are expected primary candidates. | Reports Plus / Metrics sample when available | Reports Plus / Metrics | Reports Plus / Metrics plus imported historical artifacts | Imported reports/CSV/manual export | Daily Reporting / Full HC subject; optional Quick HC sample. `reportId` may vary by environment. |
| Backup activity trends | Limited unless REST history is sufficient and retained. | High for job/activity trend datasets and summaries. | Reports Plus / Metrics sample when available | Reports Plus / Metrics | Reports Plus / Metrics plus REST job context | Imported reports/CSV/email summaries | Daily Reporting / Full HC subject. Historical trend analysis is Metrics-native. |
| Restore activity | High for current/recent restore job history. | Useful for restore activity reports and historical summaries. | REST | Reports Plus / Metrics | REST plus Reports Plus / Metrics restore history | Import/export/email evidence | Quick HC / Daily Reporting / Full HC subject. Restore visibility may be sparse in small labs; validate dataset fields per environment. |
| Topology / network configuration | Variable. REST may expose limited topology, network, or firewall configuration. | Variable. Custom reports may expose topology summaries, but Metrics may not be complete. | REST or customer-side snapshot | Reports Plus / Metrics only if a useful report exists | REST plus customer-side topology snapshot and custom report evidence | Custom report, SQL/manual export as last resort | Full HC subject; optional Quick HC subject if reachable. Customer-side collection may be required. |
| Reports inventory | Not applicable except for API reachability/session context. | High. Reports Plus report inventory API is the source to explore. | Reports Plus / Metrics when checking reporting readiness | Reports Plus / Metrics | Reports Plus / Metrics inventory plus report definitions | Manual export of report catalog | Daily Reporting / Full HC subject. `reportId` may be environment-specific; catalog artifacts are discovery outputs, not source of truth. |
| Datasets inventory | Not applicable except for API reachability/session context. | High. Reports Plus dataset inventory and metadata APIs are the source to explore. | Reports Plus / Metrics when checking reporting readiness | Reports Plus / Metrics | Reports Plus / Metrics metadata plus execution validation | Manual export of dataset catalog | Daily Reporting / Full HC subject. Dataset GUIDs and fields can vary; validate execution per environment. |
| Lab readiness | High for probing configured REST access and authentication. | High for probing configured Reports Plus / Metrics access and executable datasets. | REST plus Reports Plus / Metrics probes | Not a customer Daily Reporting subject | REST plus Reports Plus / Metrics probes and environment notes | Manual notes/imported probe output | Quick HC / Full HC support subject. Readiness artifacts indicate lab/tool state only; they are not customer source of truth. |
| Security assessment | REST may expose individual security settings, but a complete current mapping has not been built. | High. Reports Plus report 336 provides checklist-style security assessment sections and normalized status rows. | Reports Plus / Metrics report 336 | Reports Plus / Metrics if recurring security posture reporting is needed | Reports Plus / Metrics plus REST validation for specific controls where useful | Manual report/export | Quick HC subject. Current artifact has 32 checks: 2 Critical, 0 Warning, 18 Info, 12 Good. Report IDs may vary by environment; validate report name and discovered datasets before relying on the pipeline outside the lab. |

## Operating Mode Guidance

Quick HC should stay fast, read-only, and minimally invasive. Prefer REST for current state when it is reachable, but also explore Reports Plus / Metrics-backed Quick HC tiles when that is the only remote datasource or when the subject is naturally trend/report-oriented.

Daily Reporting should be Reports Plus / Metrics-first for recurring reporting, historical trends, SLA, capacity, growth, backup activity, and multi-CommCell visibility. It should not assume direct CommServe REST access.

Full Healthcheck should combine live REST, Reports Plus / Metrics, uploaded customer-side snapshots, and manual evidence where required. REST remains authoritative for live state, while Reports Plus / Metrics remains authoritative for available historical reporting context. When both REST and Reports Plus / Metrics exist for the same subject, the project should validate both and compare freshness, completeness, permissions, field stability, and operational usefulness before selecting the pipeline used in production.
