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
| Client Growth / Client Usage Trend | ReportsPlus Dataset | `/commandcenter/api/cr/reportsplusengine/datasets/979eba7f-8c67-420c-a27e-85ed82066514:8ac30a77-3de2-4968-86c1-ade4b02c85a4/data` | GET | Authtoken | `fields=[MonthStart],[Added],[Removed],[Total]`; `format=object`; `orderby=[MonthStart] Asc`; `limit=15`; `includeOther=false`; `parameter.showDeconfigClients=0`; `parameter.includePsuedoClients=0` | PROVEN | Verified through Command Center Reports Plus internal REST API. Metadata exposes dataset fields, parameters, backend type, and SQL/stored procedure mapping. |
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
