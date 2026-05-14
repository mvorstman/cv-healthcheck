# Data Source Mapping

Architecture-level source strategy for cv-healthcheck operating modes.

This document maps healthcheck subjects to practical data sources for:

- Daily Reporting
- Quick HC
- Full Healthcheck

It does not define health scoring, thresholds, severities, or implementation tasks. Those belong in later collector and health-rule design after source availability is clear.

## Source Strategy

Direct CommServe REST access is preferred when it is available because live APIs remain authoritative for current configuration and operational state. In many customer environments, however, direct CommServe REST access may not be available to the central reporting platform. Reports Plus / Metrics access may be the only realistic remote datasource.

In this project context, **Reports Plus == Metrics**. Use `Reports Plus / Metrics` to mean data available through the Command Center Reports Plus engine, private Metrics servers, Metrics reports, or related report/dataset execution paths.

Preferred collection order:

1. REST APIs for live CommServe configuration and operational state.
2. Reports Plus / Metrics when REST is unavailable, when historical/trend data is required, or when Metrics is the only reachable remote source.
3. Email, import, uploaded snapshot, or manual export as last resort.

Important caveats:

- `reportId` values may be environment-specific. Prefer semantic report names, report GUIDs, dataset metadata, and validated field shapes where possible.
- `commUniId` identifies the CommCell instance in Metrics deep links and should be captured when mapping Metrics records back to a CommCell.
- Live APIs remain authoritative where available.
- Catalog files under `data/catalog/` are local artifacts and discovery outputs, not source of truth.
- Dataset GUIDs, report composition, and returned fields must be validated per environment before relying on them.

## Practical Mapping

| Subject | Quick HC source | Daily Reporting source | Full HC source | Preferred datasource | Fallback datasource | Notes / caveats |
| --- | --- | --- | --- | --- | --- | --- |
| CommCell identity/version | REST `CommServ` snapshot | Reports Plus / Metrics CommCell inventory if available | REST plus uploaded customer snapshot | REST | Reports Plus / Metrics, import/manual export | Quick HC subject. Live REST is authoritative for current version and identity. Capture `commUniId` when sourced from Metrics deep links. |
| Licensing | REST licensing endpoint or export if available | Licensing report/dataset | REST plus license exports/evidence | REST | Reports Plus / Metrics, manual license export | Quick HC / Daily Reporting / Full HC subject. Licensing data can be permission-sensitive and may be incomplete in Metrics. |
| Clients | REST client list/details | Client inventory and trend datasets | REST client properties plus uploaded inventories | REST | Reports Plus / Metrics, import/export | Quick HC / Daily Reporting / Full HC subject. Metrics is useful for trend and multi-CommCell summaries; REST is better for current client properties. |
| Client groups | REST client group endpoints | Reports Plus / Metrics group inventory if available | REST group details plus exports | REST | Reports Plus / Metrics, manual export | Quick HC / Daily Reporting / Full HC subject. Group membership may need REST for authoritative current state. |
| Plans | REST plan list/details | Plan coverage reports/datasets | REST plan details plus policy evidence | REST | Reports Plus / Metrics, export | Quick HC / Daily Reporting / Full HC subject. Plan-to-workload relationships may require multiple REST calls or report composition mapping. |
| Storage pools | REST storage pool details | Storage pool capacity reports/datasets | REST plus capacity evidence and library detail | REST | Reports Plus / Metrics, import/export | Quick HC / Daily Reporting / Full HC subject. Metrics is useful for capacity reporting; REST is preferred for current configuration. |
| Disk libraries | REST library details | Library capacity/usage report datasets | REST plus OS/storage evidence where provided | REST | Reports Plus / Metrics, manual storage export | Quick HC / Daily Reporting / Full HC subject. Mount paths and free space may require customer-side collection when central access is limited. |
| Media agents | REST MediaAgent list/details | MediaAgent availability/capacity reports | REST plus customer-side service snapshots | REST | Reports Plus / Metrics, import/export | Quick HC / Daily Reporting / Full HC subject. REST is preferred for current status; Metrics may lag. |
| Deduplication / DDB | REST DDB/storage pool details and DDB job status | DDB reports/datasets and capacity trends | REST plus DDB evidence and job history | REST | Reports Plus / Metrics, uploaded exports | Quick HC / Daily Reporting / Full HC subject. DDB health details may be split across storage, job, and report sources. |
| Jobs | REST job controller/history endpoints | Job summary reports/datasets | REST history plus Metrics trends and exports | REST | Reports Plus / Metrics, email/import | Quick HC / Daily Reporting / Full HC subject. REST is preferred for current and recent jobs; Metrics is preferred for recurring reports and historical summaries. |
| Failed jobs | REST job history filtered by failure | Failed job reports/datasets | REST plus Metrics and evidence snapshots | REST | Reports Plus / Metrics, email/import | Quick HC / Daily Reporting / Full HC subject. Daily Reporting can be Metrics-first when central REST is unavailable. |
| SLA | REST where exposed, otherwise Metrics | SLA reports/datasets | Metrics plus REST workload and policy context | Reports Plus / Metrics | REST, import/export | Daily Reporting / Quick HC / Full HC subject. SLA is often report-native; Metrics may be the primary source even when REST exists. |
| Alerts | REST alert list/details | Alert reports/datasets or email digests | REST plus alert/event exports | REST | Reports Plus / Metrics, email/import | Quick HC / Daily Reporting / Full HC subject. Email alerts are useful as last-resort evidence, not authoritative inventory. |
| Schedules | REST schedule policy/list endpoints | Schedule reports/datasets if available | REST schedule details plus plan/policy context | REST | Reports Plus / Metrics, export | Quick HC / Daily Reporting / Full HC subject. Current schedule configuration should come from live API when possible. |
| Tenants / companies | REST company endpoints | Company/tenant report datasets | REST plus tenant-scoped report evidence | REST | Reports Plus / Metrics, export | Quick HC / Daily Reporting / Full HC subject. Metrics may expose tenant-scoped summaries without central CommServe REST. |
| Storage usage / capacity | REST storage pool/library capacity | Capacity reports/datasets | REST plus Metrics trends and storage evidence | Reports Plus / Metrics for trends; REST for current state | Import/export, manual capacity evidence | Quick HC / Daily Reporting / Full HC subject. Daily Reporting should usually be Metrics-first for history; live APIs remain authoritative for current state. |
| Growth trends | Not primary unless REST history is exposed | Growth and Trends report/datasets | Metrics trends plus uploaded historical artifacts | Reports Plus / Metrics | Imported reports/CSV/manual export | Daily Reporting / Full HC subject. Quick HC may include a small Metrics trend sample if available. `reportId` may vary by environment. |
| Backup activity trends | Not primary unless lightweight Metrics sample is available | Job/activity trend datasets | Metrics trends plus REST job context | Reports Plus / Metrics | Imported reports/CSV/email summaries | Daily Reporting / Full HC subject. Historical trend analysis is Metrics-native. |
| Restore activity | REST restore job history | Restore activity reports/datasets | REST history plus Metrics and evidence exports | REST for current/recent; Reports Plus / Metrics for reporting | Import/export, email/manual evidence | Quick HC / Daily Reporting / Full HC subject. Restore visibility may be sparse in small labs; validate dataset fields per environment. |
| Topology / network configuration | Limited REST topology or customer-side snapshot | Usually not Daily Reporting primary | REST, custom report, uploaded topology evidence | REST plus customer-side snapshot | Custom report, SQL/manual export as last resort | Full HC subject; optional Quick HC subject if reachable. Network topology may require customer-side collection because central Metrics may not hold complete configuration. |
| Reports inventory | Reports Plus report inventory API | Reports Plus report inventory API | Reports Plus inventory plus report definitions | Reports Plus / Metrics | Manual export of report catalog | Daily Reporting / Full HC subject. `reportId` may be environment-specific; catalog artifacts are discovery outputs, not source of truth. |
| Datasets inventory | Reports Plus dataset inventory API | Reports Plus dataset inventory API | Reports Plus dataset metadata plus execution validation | Reports Plus / Metrics | Manual export of dataset catalog | Daily Reporting / Full HC subject. Dataset GUIDs and fields can vary; validate execution per environment. |
| Lab readiness | Local readiness probe using configured REST and Reports Plus access | Not a customer Daily Reporting subject | Local readiness probe plus environment notes | Live probes against configured REST and Reports Plus / Metrics | Manual notes/imported probe output | Quick HC / Full HC support subject. Readiness artifacts indicate lab/tool state only; they are not customer source of truth. |

## Operating Mode Guidance

Quick HC should stay fast, read-only, and minimally invasive. Prefer REST for current state when it is reachable, but allow Reports Plus / Metrics-backed Quick HC tiles when that is the only remote datasource or when the subject is naturally trend/report-oriented.

Daily Reporting should be Reports Plus / Metrics-first for recurring reporting, historical trends, SLA, capacity, growth, backup activity, and multi-CommCell visibility. It should not assume direct CommServe REST access.

Full Healthcheck should combine live REST, Reports Plus / Metrics, uploaded customer-side snapshots, and manual evidence where required. REST remains authoritative for live state, while Reports Plus / Metrics remains authoritative for available historical reporting context.
