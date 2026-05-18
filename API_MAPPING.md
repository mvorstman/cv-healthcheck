# API Mapping

Technical source and capability catalog for cv-healthcheck collectors.

This document answers what data can be collected, where it comes from, which endpoint, dataset, or API provides it, what authentication and parameters are required, and whether the source is proven or still needs research.

Status values:

- `PROVEN`: verified in the lab or implemented code path
- `LIKELY`: plausible source, but not yet verified for this project
- `UNKNOWN`: research required
- `FALLBACK_ONLY`: usable only when preferred sources are unavailable

## Source Strategy

API mappings describe source capabilities, not fixed health rules.

### Preferred Collection Order

Collection should prefer the most stable and supported acquisition methods first.

Preferred order:

1. REST APIs
2. Reports Plus / Metrics datasets
3. Existing reports
4. Uploaded exports/artifacts
5. SQL only as last resort

Rationale:

- REST APIs are the preferred authoritative operational source.
- Reports Plus / Metrics is the preferred historical and trend-analysis source.
- Existing reports may expose already-validated operational datasets.
- Uploaded artifacts and snapshots allow disconnected/offline analysis.
- SQL should only be used when no supported API/report source exists.

Important architectural notes:

- dataset GUIDs may vary between environments
- report IDs may vary between environments
- semantic report names are more stable than IDs
- field structures are often more stable than GUID references
- report composition mapping is important
- dataset execution validation is required
- private Metrics / Reports Plus servers are expected to become primary long-term reporting sources

The central reporting platform must NOT assume direct access to customer CommServe systems.

Expected long-term operating model:

- customer-side collectors gather operational data
- Metrics / Reports Plus provides trend and historical visibility
- uploaded snapshots/artifacts may be transported through S3
- analysis and reporting may happen centrally

### Source Capability Matrix

| Subject | Preferred Source | Details | Fallback |
| --- | --- | --- | --- |
| CommCell identity/version | REST API | CommCell / system / environment endpoints | OS / registry / install files |
| License status | REST API / Report | Licensing report/dataset | Command Center export |
| Clients | REST API | Client list / client details | Report dataset |
| Client groups | REST API | Client group endpoints | SQL/custom report |
| Agents installed | REST API | Client properties / agent list | Report dataset |
| Failed jobs | REST API | Job controller / job history | Reports API |
| Running jobs | REST API | Active jobs endpoint | Metrics |
| Job SLA | Reports API | SLA / Job summary datasets | Custom report |
| Long-running jobs | REST API / Metrics | Job list filtered by duration | Custom report |
| Alerts | REST API | Alert details / alert list | Metrics / report |
| Events | REST API | Event viewer endpoints | Custom report |
| MediaAgents | REST API | MediaAgent list/details | OS access for service checks |
| MediaAgent status | REST API | MediaAgent endpoints | Metrics |
| Libraries | REST API | Library / library details | OS/storage access |
| Disk libraries | REST API | Library details / mount paths | OS filesystem |
| Cloud libraries | REST API | Cloud library / storage pool details | S3/object API |
| Storage pools | REST API | Storage pool list/details | Reports API |
| Capacity/free space | REST API | Storage pool details: capacity/free/status | OS/storage API |
| Deduplication DB | REST API / Reports | DDB/storage pool details, DDB jobs | OS access |
| Storage policies | REST API | Storage policy endpoints | Reports API |
| Storage policy copies | REST API | Copy details / copy size | Reports API |
| Retention | REST API | Storage pool / storage policy copy details | Report/custom report |
| Auxiliary copy | REST API / Reports | Aux copy jobs/status | Report dataset |
| Data aging | REST API / Reports | Data aging jobs/events | Report dataset |
| Index Servers | REST API / Reports | Server/client role inventory | OS/service check |
| Index health | Metrics / Reports | Indexing related metrics/reports | OS access |
| CommServe DR backup | REST API / Reports | DR backup jobs/alerts | OS filesystem |
| Schedules | REST API | Schedule policy/list endpoints | Report dataset |
| Plans | REST API | Plan list/details | Report dataset |
| Companies / tenants | REST API | Company endpoints | Report dataset |
| Users / security | REST API | User/group/security endpoints | Export/report |
| Credential Manager | REST API / Workflow | Credential metadata only where exposed | Workflow/custom report |
| Network topology | REST API limited / SQL/custom report | Firewall topology custom report | SQL last resort |
| Web Server health | REST API / Metrics | API reachability, service metrics | OS service check |
| Command Center health | REST API / Metrics | Login/API probe, metrics | OS service check |
| Metrics reporting | Metrics / Reports API | Metrics datasets / reportsplusengine | OS only if unavailable |
| Custom report data | Reports API | reportsplusengine dataset execution | Manual export |

| Subject | Source Type | Endpoint / Dataset | Method | Auth | Parameters | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CommCell identity/version | Command Center REST API | `/commandcenter/api/CommServ` | GET | Login-issued Authtoken or Flask session token | None known | PROVEN | Live validated on 2026-05-14: endpoint returned HTTP 200 and exposed root fields `hostName`, `csVersionInfo`, `releaseId`, `osType`, and `timeZone`, with `csGUID` nested under `commcell`. Quick HC normalizes these fields and writes `data/catalog/rest/commserv.json`. |
| Client Growth / Client Usage Trend | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4/data` | GET | Authtoken | `fields=[MonthStart],[Added],[Removed],[Total]`; `format=object`; `orderby=[MonthStart] Asc`; `limit=15`; `includeOther=false`; `parameter.showDeconfigClients=0`; `parameter.includePsuedoClients=0` | PROVEN | Verified through Command Center Reports Plus internal REST API. Metadata exposes dataset fields, parameters, backend type, and SQL/stored procedure mapping. Auth matrix with the current `.token` later returned HTTP 401 for Reports Plus metadata using both `Authtoken` and `Authorization: Bearer`; retest with a fresh Login-issued Authtoken before relying on the current token source. |
| Reports Plus Report Inventory | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/reports` | GET | Login-issued Authtoken | None known | PROVEN | Endpoint proven with a token generated through `POST /commandcenter/api/Login` and sent as `Authtoken: <login_response.token>`. Current `.token` works for `/commandcenter/api` but returned HTTP 401 `Unauthenticated` for this Reports Plus inventory endpoint; Login-issued Authtoken returned HTTP 200 with JSON containing `reports` and `userHistory`. Expected records include reportId, userReportId, reportName, description, version, guid, revision, flags, engineVersion, deployed, deployedVersion, viewable, editable, content, type, and isMetrics. |
| Reports Plus Report 318 metadata | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/reports/318` | GET | Login-issued Authtoken or Flask session token | None known | PROVEN | Live validated on 2026-05-13: Login API token sent as `Authtoken` returned HTTP 200 for Report 318 (`Growth and Trends`). The extractor persists `data/catalog/reportsplus/report_318_metadata.json` and `report_318_definition.json`, parses report `pages[].body` JSON definitions, and redirects the Flask route to login on HTTP 401. |
| Reports Plus Report 318 dataset map | Local extraction artifact from ReportsPlus API responses | `data/catalog/reportsplus/report_318_dataset_map.json` | Local JSON | Derived from authenticated Reports Plus report and dataset metadata calls | Report definition dataset references | PROVEN | Live validation discovered 24 widgets and 30 backing datasets from Report 318. Dataset references use nested `dataSet.dataSetGuid` / id / name shapes, and backing dataset metadata calls to `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>` returned HTTP 200 for the discovered datasets using the same Login-issued/session token path. |
| Reports Plus Report 318 dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>/data` | GET | Login-issued Authtoken or Flask session token | `format=object`; `includeOther=false`; `limit=<sample_limit>` plus discovered default `parameter.<name>` values when present | PROVEN | Live validation executed all 30 discovered Report 318 backing datasets with `limit=25`; all returned HTTP 200 and wrote raw artifacts as `data/catalog/reportsplus/report_318_raw_<dataset>.json`. Some datasets returned valid empty result sets in the lab, while others returned sample rows. Dataset execution is data extraction only; no health scoring or interpretation is performed. |
| Reports Plus License Summary report 206 | ReportsPlus API / Datasets | `/commandcenter/api/cr/reportsplusengine/reports/206`; `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>`; `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>/data` | GET | Login-issued Authtoken or Flask session token | `format=object`; `includeOther=false`; bounded `limit`; discovered/default parameters if present | PROTOTYPED | Report 206 (`License summary`) now has two dataset families in active use: detail-table datasets (`Other Licenses - current usage details`, `Agent and Feature Licenses - current usage details`) and summary/category datasets (`Capacity Licenses`, `Operating Instance Licenses`, `Virtualization Licenses`, `User Licenses`, `Data Insights Licenses`, `Air Gap Protect Licenses`, and summary-page `Other Licenses`). Summary datasets may be partially unavailable depending on CommCell/report execution. The collector discovers and renders only datasets that return real rows and does not fabricate missing sections. |
| Reports Plus Security Assessment report 336 | ReportsPlus API / Datasets | `/commandcenter/api/cr/reportsplusengine/reports/336`; `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>`; `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>/data` | GET | Login-issued Authtoken or Flask session token | `format=object`; `includeOther=false`; bounded `limit`; discovered/default parameters if present | PROVEN | Report 336 (`Security Assessment`) is used for Quick HC security checklist output. Extraction discovers six datasets: Access Security, Auditing, Platform Security, Company and Owners Security, Capabilities, and Hardening. Returned fields include Parameter, Status, Remarks, Action, GROUP, attrName, Data Source, ccid, and PARAMID. Normalized artifact: `data/catalog/reportsplus/report_336_security_assessment_normalized.json`. Current artifact summary: 32 checks, 2 Critical, 0 Warning, 18 Info, 12 Good. |
| License Summary canonical artifact | Local canonical artifact shared by REST, XLSX-recorded REST, HTML, and CSV ingestion | `data/catalog/license_summary/latest.json` | Local JSON | Derived from normalized source artifact | Source-specific normalization output | PROTOTYPED | Canonical License Summary artifact with report metadata plus normalized detail collections `other_licenses[]` and `agent_feature_licenses[]`, and workload/category summary collections in `workload_summary_sections[]`. The schema is shared across CSV imports, HTML imports, XLSX API viewer recordings, and live REST extraction. Missing upstream metadata such as `license_expiry` remains unset rather than guessed. |
| License Summary artifact registry | Local registry / artifact metadata index | `data/imports/license_summary/artifact_registry.sqlite3` | SQLite | Derived from service-layer persistence | Import run context, artifact metadata, scoped active-selection state | PROTOTYPED | Registry-backed persistence mirrors the Security Assessment pattern. Unique artifact files are retained, scoped by customer and CommCell identity, and loaded through registry-first active selection with `latest.json` preserved as compatibility fallback. |
| Security Assessment canonical artifact | Local canonical artifact shared by REST, HTML, and CSV ingestion | `data/imports/security_assessment/latest.json` | Local JSON | Derived from normalized source artifact | Source-specific normalization output | PROVEN | Canonical Security Assessment artifact used by render paths regardless of acquisition source. This schema is shared across REST, HTML export imports, and CSV export imports. |
| Security Assessment artifact registry | Local registry / artifact metadata index | `data/imports/security_assessment/artifact_registry.sqlite3` | SQLite | Derived from service-layer persistence | Import run context, artifact metadata, scoped active-selection state | PROVEN | Persistent registry layer added beneath the current UI. Tracks customer_id, commcell_id, engagement_id, report_stream_id, report_run_id, import_run_id, artifact_id, source metadata, imported_at, executed_at, run_sequence, and active artifact state. The preferred read path is registry -> active artifact -> artifact file, with `latest.json` reserved for compatibility fallback only. |
| Security Assessment history/debug read API | Local service/read layer over registry and artifact files | `SecurityAssessmentService`; `/security-assessment/history`; `/security-assessment/registry-export` | Local service / Flask debug endpoints | None beyond local app access | Optional artifact_id, import_run_id, report_run_id, customer_id, commcell_id, source_type, engagement_id, report_stream_id | PROVEN | Historical retrieval layer for debug and future UI/reporting work. Supports current artifact lookup, scoped history, artifact-by-id/run retrieval, and registry export without changing the main page flow. |
| Security Assessment live REST latest artifact | Local persisted REST-derived artifact | `data/imports/security_assessment/latest_rest.json` | Local JSON | Derived from authenticated REST collection | None beyond source collection inputs | PROVEN | Online/live source variant for Security Assessment. Used to preserve REST-normalized evidence separately from imported artifacts for source comparison and debugging. |
| Security Assessment HTML export import | Offline import source | Browser upload / local import persisted to `data/imports/security_assessment/latest_html.json` | File import | No API auth after export is obtained | HTML export file | PROVEN | Offline import source. HTML exports are presentation-heavy and require strict table parsing with validated headers, `tbody`/`tr`/`td` extraction only, footer/header filtering, deduplication, and noise rejection. |
| Security Assessment CSV export import | Offline import source | Browser upload / local import persisted to `data/imports/security_assessment/latest_csv.json` | File import | No API auth after export is obtained | CSV export file | PROVEN | Offline import source. CSV exports are currently cleaner than HTML exports and normalize more directly into the canonical artifact schema. |
| Reports Plus Dataset Inventory | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/datasets` | GET | Login-issued Authtoken | None known | PROVEN | Endpoint proven with a token generated through `POST /commandcenter/api/Login` and sent as `Authtoken: <login_response.token>`. Current `.token` works for `/commandcenter/api` but returned HTTP 401 `Unauthenticated` for this Reports Plus inventory endpoint; Login-issued Authtoken returned HTTP 200 with JSON containing `dataSet`. Response exposes rich dataset metadata including fields, GetOperation parameters, SQL text, database name, queryPlan, visibility flags, and builtIn/systemDataSet flags. |
| Audit trail dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/2b3e43c0-21fe-401d-ebf8-c485309262a7/data` | GET | Login-issued Authtoken | `format=object`; `includeOther=false`; `limit=10`; `parameter.playbackLevel=4` | PROVEN | Candidate execution validation returned HTTP 200 with 10 records and fields including ID, Severity Level, User, Time, Operation, and Details. Mapped health area: Users / security. |
| Company job status dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/bb24f394-2260-4b04-a30b-de6acf7c5402/data` | GET | Login-issued Authtoken | `format=object`; `includeOther=false`; `limit=10` | PROVEN | Candidate execution validation returned HTTP 200 with returned fields including CompanyId, Company, RingId, Ring, failedBackupJobsLastNDays, and failedRestoreJobsLastNDays. Result set was valid and empty in the lab. Mapped health area: Failed jobs. |
| Clients | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Client groups | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Jobs | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Failed jobs | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Running jobs | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Alerts | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Events | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| MediaAgents | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Libraries | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Disk libraries | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Cloud libraries | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Storage pools | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Capacity/free space | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Deduplication DB | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Storage policies | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Storage policy copies | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Retention | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Auxiliary copy | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Data aging | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Index Servers | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Index health | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| CommServe DR backup | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Schedules | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Plans | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Companies / tenants | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Users / security | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Credential Manager | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Network topology | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Web Server health | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Command Center health | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Metrics reporting | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
| Custom report data | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
