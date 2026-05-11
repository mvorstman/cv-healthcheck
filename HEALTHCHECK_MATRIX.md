# HealthCheck Matrix

Operational health evaluation matrix for cv-healthcheck.

This is not the API inventory. Source capabilities are tracked in [API_MAPPING.md](API_MAPPING.md). This matrix answers which health question is being asked, which collected data supports it, which evaluation rule should be applied, and how the result should be reported.

Status values:

- `TODO`: not designed yet
- `DESIGN`: evaluation shape identified, not implemented
- `IMPLEMENTED`: code exists
- `VERIFIED`: validated against real data

| Health Area | Health Question | Required Data | Source Reference | Evaluation Rule | Severity | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Client Growth | Can client growth trend data be queried and interpreted? | MonthStart, Added, Removed, Total | API_MAPPING.md -> Client Growth / Client Usage Trend | Initial rule not implemented. First validation checks whether records are returned and fields are present. | INFO | DESIGN | First healthcheck candidate based on proven Reports Plus dataset access. |
| Job failures | Which jobs are failing and how severe is the failure pattern? | TBD | API_MAPPING.md -> Failed jobs | TBD | TBD | TODO | Requires source mapping before rule design. |
| SLA | Are protected workloads meeting expected SLA targets? | TBD | TBD | TBD | TBD | TODO | Requires source mapping before rule design. |
| Storage capacity | Are storage resources approaching capacity limits? | TBD | API_MAPPING.md -> Capacity/free space | TBD | TBD | TODO | Requires source mapping before rule design. |
| MediaAgent health | Are MediaAgents online and healthy? | TBD | API_MAPPING.md -> MediaAgents | TBD | TBD | TODO | Requires source mapping before rule design. |
| Library health | Are libraries available and healthy? | TBD | API_MAPPING.md -> Libraries | TBD | TBD | TODO | Requires source mapping before rule design. |
| DDB health | Are deduplication databases healthy? | TBD | API_MAPPING.md -> Deduplication DB | TBD | TBD | TODO | Requires source mapping before rule design. |
| Index health | Are indexing components healthy? | TBD | API_MAPPING.md -> Index health | TBD | TBD | TODO | Requires source mapping before rule design. |
| Alert health | Are active alerts present that require attention? | TBD | API_MAPPING.md -> Alerts | TBD | TBD | TODO | Requires source mapping before rule design. |
| Schedule health | Are schedules configured and running as expected? | TBD | API_MAPPING.md -> Schedules | TBD | TBD | TODO | Requires source mapping before rule design. |
| Tenant/company reporting | Can tenant or company scoped health reporting be produced? | TBD | API_MAPPING.md -> Companies / tenants | TBD | TBD | TODO | Requires source mapping before rule design. |
| Security/user review | Are user and security settings ready for review? | TBD | API_MAPPING.md -> Users / security | TBD | TBD | TODO | Requires source mapping before rule design. |
| Network topology | Can topology data be collected for connectivity review? | TBD | API_MAPPING.md -> Network topology | TBD | TBD | TODO | Requires source mapping before rule design. |
| DR backup | Is CommServe DR backup configured and recent? | TBD | API_MAPPING.md -> CommServe DR backup | TBD | TBD | TODO | Requires source mapping before rule design. |
