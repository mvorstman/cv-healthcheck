# API Mapping

Technical source and capability catalog for cv-healthcheck collectors.

This document answers what data can be collected, where it comes from, which endpoint, dataset, or API provides it, what authentication and parameters are required, and whether the source is proven or still needs research.

Status values:

- `PROVEN`: verified in the lab or implemented code path
- `LIKELY`: plausible source, but not yet verified for this project
- `UNKNOWN`: research required
- `FALLBACK_ONLY`: usable only when preferred sources are unavailable

| Subject | Source Type | Endpoint / Dataset | Method | Auth | Parameters | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Client Growth / Client Usage Trend | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4/data` | GET | Authtoken | `fields=[MonthStart],[Added],[Removed],[Total]`; `format=object`; `orderby=[MonthStart] Asc`; `limit=15`; `includeOther=false`; `parameter.showDeconfigClients=0`; `parameter.includePsuedoClients=0` | PROVEN | Verified through Command Center Reports Plus internal REST API. Metadata exposes dataset fields, parameters, backend type, and SQL/stored procedure mapping. Auth matrix with the current `.token` later returned HTTP 401 for Reports Plus metadata using both `Authtoken` and `Authorization: Bearer`; retest with a fresh Login-issued Authtoken before relying on the current token source. |
| Reports Plus Report Inventory | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/reports` | GET | Login-issued Authtoken | None known | PROVEN | Endpoint proven with a token generated through `POST /commandcenter/api/Login` and sent as `Authtoken: <login_response.token>`. Current `.token` works for `/commandcenter/api` but returned HTTP 401 `Unauthenticated` for this Reports Plus inventory endpoint; Login-issued Authtoken returned HTTP 200 with JSON containing `reports` and `userHistory`. Expected records include reportId, userReportId, reportName, description, version, guid, revision, flags, engineVersion, deployed, deployedVersion, viewable, editable, content, type, and isMetrics. |
| Reports Plus Report 318 metadata | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/reports/318` | GET | Login-issued Authtoken or Flask session token | None known | LIKELY | Implemented focused extraction path for Report 318 without scraping the Command Center UI route. The extractor persists `data/catalog/reportsplus/report_318_metadata.json` and `report_318_definition.json`, parses the report `content` definition for widgets/sections and dataset references, and redirects to login on HTTP 401. Live validation still requires a fresh Commvault login token because the existing `.login_token` returned HTTP 401 during this work. |
| Reports Plus Report 318 dataset map | Local extraction artifact from ReportsPlus API responses | `data/catalog/reportsplus/report_318_dataset_map.json` | Local JSON | Derived from authenticated Reports Plus report and dataset metadata calls | Report definition dataset references | LIKELY | The reusable extractor maps discovered widgets/sections to backing datasets, including dataset GUID/id/name, required parameters, default parameters, available fields, selected/displayed fields, filters, sorting, limits, and execution endpoint. Backing dataset metadata is fetched with `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>`. |
| Reports Plus Report 318 dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/<datasetGuid>/data` | GET | Login-issued Authtoken or Flask session token | `format=object`; `includeOther=false`; `limit=<sample_limit>` plus discovered default `parameter.<name>` values | LIKELY | The extractor executes each discovered backing dataset when required parameters have safe/default values, writes raw results as `data/catalog/reportsplus/report_318_raw_<dataset>.json`, and writes a normalized summary to `report_318_execution_summary.json`. Dataset execution is data extraction only; no health scoring or interpretation is performed. |
| Reports Plus Dataset Inventory | ReportsPlus API | `/commandcenter/api/cr/reportsplusengine/datasets` | GET | Login-issued Authtoken | None known | PROVEN | Endpoint proven with a token generated through `POST /commandcenter/api/Login` and sent as `Authtoken: <login_response.token>`. Current `.token` works for `/commandcenter/api` but returned HTTP 401 `Unauthenticated` for this Reports Plus inventory endpoint; Login-issued Authtoken returned HTTP 200 with JSON containing `dataSet`. Response exposes rich dataset metadata including fields, GetOperation parameters, SQL text, database name, queryPlan, visibility flags, and builtIn/systemDataSet flags. |
| Audit trail dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/2b3e43c0-21fe-401d-ebf8-c485309262a7/data` | GET | Login-issued Authtoken | `format=object`; `includeOther=false`; `limit=10`; `parameter.playbackLevel=4` | PROVEN | Candidate execution validation returned HTTP 200 with 10 records and fields including ID, Severity Level, User, Time, Operation, and Details. Mapped health area: Users / security. |
| Company job status dataset execution | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/bb24f394-2260-4b04-a30b-de6acf7c5402/data` | GET | Login-issued Authtoken | `format=object`; `includeOther=false`; `limit=10` | PROVEN | Candidate execution validation returned HTTP 200 with returned fields including CompanyId, Company, RingId, Ring, failedBackupJobsLastNDays, and failedRestoreJobsLastNDays. Result set was valid and empty in the lab. Mapped health area: Failed jobs. |
| CommCell identity/version | Unknown | TBD | TBD | TBD | TBD | UNKNOWN | Research required. |
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
