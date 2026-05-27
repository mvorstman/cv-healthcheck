# ADR 0003 Survey — REST extractor with credentials

## Scope

ADR 0003 will design a REST extractor (with credentials) that can collect from a customer's CommCell into the active project's working state. This survey grounds the design conversation in what already exists: the current auth surface, the two existing REST-collection patterns, the catalog-driven extraction-instructions schema, and the write path that lands collected data under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. The survey deliberately surfaces forks; it does not pick winners.

The ADR is design-only. No implementation in this session. The customer/project foundation it builds on is ADR 0002, fully implemented; the storage layout is documented in `docs/data_flow_audit.md` (freshly refreshed in the prior session).

## Existing code surface

### Authentication

**`src/cvhealthcheck/auth/commvault_auth.py`** — Flask-session-backed CommCell token management.

- `login_to_commvault(base_url, username, password)` (`commvault_auth.py:20-53`) — POSTs to `/commandcenter/api/Login` with `username` and base64-encoded password. Returns the token string. Does not touch session — caller decides what to do with the token.
- `set_current_token(token, username=None)` (`commvault_auth.py:56-65`) — writes `session[SESSION_TOKEN_KEY]` and optionally `session[SESSION_USERNAME_KEY]`. Quietly no-ops outside a request context.
- `get_current_token()` (`commvault_auth.py:68-72`) — reads from session; returns `None` outside a request context.
- `is_authenticated()` (`commvault_auth.py:94-95`) — `get_current_token() is not None`.
- `clear_current_token()` — removes both keys from session.

The token is the `Authtoken` header value. The session token has the same lifetime as the Flask session (cookie-backed). There is no token refresh mechanism; if the upstream returns 401, the route layer calls `clear_current_token()` and redirects to `/login`. The username is informational only (used by the connection badge in the UI); auth identity is purely the token.

There is no per-customer token storage. The Flask session holds one token for the whole app, regardless of which customer is active. The same token is used for whatever CommCell `CV_BASE_URL` points at.

**`src/cvhealthcheck/auth/__init__.py`** — `load_token(.token)` and `load_login_token(.login_token)` read tokens from local files. CLI and tests use these. `CommvaultApiClient`'s constructor falls back to `load_token(settings.token_path)` if no token is passed. `ReportsPlusClient` falls back to `load_login_token()` for inventory endpoints (Reports Plus uses a different token issued by the Login endpoint, distinct from a bearer token in `.token`).

### Commvault API client

**`src/cvhealthcheck/api_client.py::CommvaultApiClient`** — thin wrapper around `requests.Session` for GETs against the Commvault Command Center API.

- Constructor takes optional `settings`, `token`, and `session`. Pulls `settings` from env via `load_settings()` if not supplied; pulls `token` from `.token` file via `load_token(settings.token_path)` if not supplied. Token is held on the instance; never re-read.
- Methods: `get(path, params=None)` returns `ApiResult` (a dataclass with `ok`, `status_code`, `url`, `data`, `text`, `error`, `elapsed_seconds`). `ping()` returns `self.get("/commandcenter/api")`.
- Headers: `Accept: application/json` always; `Authtoken: <token>` if a token is present.
- The client is constructed per-route via `_api_client()` in `web/routes/shared.py:88-89` which passes `token=_current_token()`. Each request gets a fresh client with the current session's token.
- SSL: respects `settings.verify_ssl`; warns once if disabled.

### Reports Plus client

**`src/cvhealthcheck/reportsplus/client.py::ReportsPlusClient`** — wraps `CommvaultApiClient` with Reports-Plus-specific paths.

- Constructor takes optional `api_client`, `token`, and overridable `reports_path`/`datasets_path`. Builds its own `CommvaultApiClient(token=token)` if no client is passed.
- Inventory endpoints (`list_reports`, `get_report`, `list_datasets`, `get_dataset_metadata`) go through `_inventory_api_client()` which prefers the explicitly-passed token but **falls back to `load_login_token()`** — Reports Plus inventory historically needed a Login-issued token rather than a plain bearer token. If neither is available, falls through to the underlying client's token.
- Dataset data endpoint (`get_dataset_data(dataset_guid, fields, orderby, limit, parameters, format_, include_other)`) — single GET to `/datasets/<guid>/data`. No pagination. No caching. Direct fetch with all query-string params.
- All methods return `ApiResult`; callers check `.ok` / `.data`.
- Constructed per-route via `_reportsplus_client()` in `shared.py:92-93`.

### Reports Plus session (cacheId pattern)

**`src/cvhealthcheck/reportsplus/session.py::CommvaultSession`** — second, distinct Reports Plus client. Used only by the generic `RESTExtractor`.

- Constructor: `(base_url, token, *, verify_ssl=True, timeout=30.0)`. Owns a `requests.Session`. Holds `_cache_id`.
- Implements the two-step pattern: `init_report(report_definition)` POSTs to `/reportsplusengine/reportBuilder.do` and stores the returned `cacheId`. Subsequent `fetch_dataset(guid, ...)` calls pass that `cacheId` as a query parameter to `/datasets/<guid>/data`.
- `fetch_dataset` paginates: loops fetching `limit=1000, offset=N` until response total is reached, the page is short, or the caller's `limit` cap is hit.
- Context-manager friendly (`__enter__`/`__exit__`).
- Distinct from `ReportsPlusClient`. They share the underlying HTTP target (`/datasets/<guid>/data`) but differ on protocol: `ReportsPlusClient.get_dataset_data` is a single direct GET; `CommvaultSession.fetch_dataset` is paginated GETs with a `cacheId` (obtained via the reportBuilder POST).

### Extraction

**`src/cvhealthcheck/extractors/rest.py::RESTExtractor`** — the generic REST extractor driven by db-stored instructions. Used by AI / system subjects via `/quick-hc/<subject_id>/collect`.

- Constructor: `(db_conn, session)` — takes a `CommvaultSession` (or any duck-typed `fetch_dataset` + `init_report` provider).
- `extract(subject_id, version, report_definition=None)`:
  1. Loads section instructions via `_load_section_instructions` — SQL JOIN across `subject_section_sources`, `subject_sources`, `subject_sections` filtered to `source_type='rest'`.
  2. If `report_definition` was passed, calls `session.init_report(report_definition)` (stores cacheId for subsequent fetches).
  3. For each section: extracts `dataset_guid`, `fields`, `orderby`, `limit`, `parameters`, `timestamp_fields`, `timestamp_format`, `null_values` from the section's instructions JSON; calls `session.fetch_dataset(...)`; post-processes timestamps and null values; assigns to `result.sections[section_id]`.
- Returns `ExtractionResult` (a dataclass; same shape `html.py` returns). Caller (`web/routes/quick_hc.py:181`) converts via `result_to_artifact(result, subject_id, subject_title, commcell_id, commcell_name)` and then calls `make_active_project_store().save_artifact(artifact)`.
- No direct knowledge of customers, projects, or active session — receives a constructed `CommvaultSession` from the route handler.

### SecurityAssessmentService.collect_from_rest

**`src/cvhealthcheck/security_assessment/service.py:171-192`** — SA's REST collection. Distinct path from the generic extractor.

- Takes optional `client: ReportsPlusClient` (defaults to constructing one) and `execute: bool`.
- Calls `extract_security_assessment(client, execute)` (`reportsplus/security_assessment.py:34-68`), which in turn calls `extract_report("336", client=client, execute=execute, sample_limit=50)` (`reportsplus/extract_report.py:17-110`).
- `extract_report` does its own multi-step flow without `CommvaultSession.init_report`:
  1. `reports_client.get_report(report_id)` — fetches the report metadata.
  2. `parse_content_field(report_result.data)` — parses the report definition from the response payload.
  3. `discover_widgets(definition)` + `discover_dataset_references(definition)` — walks the definition to find datasets referenced by the report.
  4. `build_dataset_map(...)` — resolves each widget's datasets via additional `client.get_dataset_metadata(guid)` calls.
  5. `execute_mapping(...)` for each dataset — calls `client.get_dataset_data(guid, ...)` directly. **No `cacheId`. No `reportBuilder.do` POST.**
- Result is normalized via `normalize_security_assessment(extraction)`, persisted via `persist_security_assessment_artifact(normalized, write_legacy=False)`, adapted via `adapt_reportsplus_rest(extraction)`, written via `_active_project_store().save_artifact(canonical)`.
- The report_id `336` is hard-coded as `SECURITY_ASSESSMENT_REPORT_ID` in `reportsplus/security_assessment.py:21`.

### LicenseSummaryService.collect_from_rest

**`src/cvhealthcheck/license_summary/service.py:101-145`** — LS's REST collection. Structurally similar to SA but more elaborate.

- Takes optional `client: ReportsPlusClient` and several context kwargs (customer_context, commcell_context, engagement_context — these flow to `persist_license_summary_artifact`).
- Calls `collect_license_summary_rest(client, write_artifact=False)` (`license_summary/collect_rest.py:28-?`):
  - `reports_client.get_report(LICENSE_SUMMARY_REPORT_ID)` (report_id `"206"`, hardcoded at `collect_rest.py:23`).
  - Parses the definition, finds the License Summary detail page, extracts dataset specs (organization, other, agent, metadata) and summary specs.
  - Executes each spec via `_execute_dataset_spec(reports_client, spec, parameters, sample_limit)` and `_execute_with_guid_candidates(...)` — both ultimately call `reports_client.get_dataset_data(guid, ...)`. Again: **no `cacheId`, no `reportBuilder.do`.**
- Normalizes via `normalize_license_summary_rest_extraction(extraction)`, persists via `persist_license_summary_artifact(normalized, write_legacy=False, ...)`, adapts via `_adapt_license_summary(persisted)`, writes via `_active_project_store().save_artifact(canonical)`.

### Extraction instructions for AI subjects

**`subject_section_sources.extraction_instructions`** (defined in migration 0003, populated by migrations 0003 and 0004).

Schema doc-block at `db/migrations/0003_report_inventory.sql:178-235`. The `extraction_instructions` column is `TEXT NULL` holding a JSON object whose shape varies by `source_type`. For `source_type='rest'`:

```
{
  "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
  "fields":       ["MonthStart","Total","Removed","Added"],
  "orderby":      "MonthStart Asc",
  "parameters":   {"type": 2},
  "timestamp_fields":  ["MonthStart"],
  "timestamp_format":  "unix_seconds",
  "size_unit":    null,
  "null_values":  [null]
}
```

Plus `output_as: "table" | "findings"` (consumed by `RESTExtractor._fetch_section`).

**Current REST rows (3 today):**

| section_id | extraction_instructions (first 300 chars) |
|---|---|
| `backup_job_summary.recent_jobs` | `{"dataset_guid":"2638c3d3-...","fields":["JobId","ClientName","Status","StartTime","SizeKB"],"orderby":"StartTime Desc","limit":100,"output_as":"table"}` |
| `capacity_license.table` | `{"dataset_guid":"43c5c8f8-...","fields":["Month","Entity Name","Used Capacity"],"orderby":"Month Asc","parameters":{"type":2},"size_unit":"MB","null_values":[null],"note":"...","output_as":"table"}` |
| `client_growth.monthly_table` | `{"dataset_guid":"f2bfe9ce-...","fields":["MonthStart","Total","Removed","Added"],"orderby":"MonthStart Asc","limit":15,"timestamp_fields":["MonthStart"],"timestamp_format":"unix_seconds","null_values":[null],"output_as":"table"}` |

All three system subjects. No AI-proposed subjects have REST instructions today.

**Observed gaps:**
- The schema stores `dataset_guid` inline. Dataset GUIDs are CommCell-scoped (they vary between deployments); storing them in the catalog means the catalog is implicitly tied to a single CommCell. The user's three-layer identity model (catalog-portable / CommCell-scoped / collection-context) suggests dataset GUIDs belong in the CommCell-scoped layer, discovered at session start, not stored in the catalog.
- The schema has no `report_id`. `RESTExtractor.extract` takes an optional `report_definition` arg, populated externally from `REPORT_DEFINITIONS` (see next section). Without `report_id` in the instructions, the catalog can't say which report a dataset belongs to.

**`src/cvhealthcheck/reportsplus/report_definitions.py`** — Python dict mapping subject_id → reportBuilder.do payload. **Today the dict has exactly one entry: `client_growth`** (with hardcoded report ID `318` and dataset GUID `f2bfe9ce-...`). A new AI-proposed subject that uses REST would need both a row in `subject_section_sources` AND a Python edit to `REPORT_DEFINITIONS`. This conflicts with ADR 0002's spirit (AI proposals add subjects without code changes) and is an obvious target for ADR 0003.

### Write path to project storage

For the generic `/quick-hc/<subject_id>/collect` route:

1. `_current_token()` reads the Flask session token (`shared.py:84-85`).
2. `REPORT_DEFINITIONS.get(subject_id)` (`quick_hc.py:167`) — Python-dict lookup; returns `None` if no entry.
3. `get_subject(db, subject_id)` (`quick_hc.py:171`) — checks the subject exists. Returns its `title` and `version`.
4. `CommvaultSession(base_url, token, verify_ssl=...)` (`quick_hc.py:179`) — opens an HTTP session. Note: `base_url = settings.base_url` from env (`CV_BASE_URL`), NOT from the active customer's `commcell_hostname` field.
5. `RESTExtractor(db, cv_session).extract(subject_id, version, report_definition=report_definition)` (`quick_hc.py:181`) — runs the extraction (see RESTExtractor section above).
6. `_read_commcell_provenance()` (`quick_hc.py:77-86`) — reads `commcell_id` / `commcell_name` from **global** `data/catalog/rest/commserv.json`, NOT from the active customer's row. Used as artifact provenance metadata.
7. `result_to_artifact(result, subject_id, subject_title, commcell_id, commcell_name)` (`quick_hc.py:193`) — converts to `CanonicalArtifact`.
8. `make_active_project_store().save_artifact(artifact)` (`quick_hc.py:200`) — resolves active project from session, writes to `data/catalog/artifacts/<customer>/<project>/working/<subject_id>/{timestamp}.json + latest.json`.

For SA's `collect_from_rest`:

1. Caller (route handler at `quick_hc.py:267-`) constructs `ReportsPlusClient(token=_current_token())`.
2. `SecurityAssessmentService.collect_from_rest(client=...)` is called.
3. Internally: `extract_security_assessment(client, execute=True)` → `extract_report("336", client)` (the report ID lives in `reportsplus/security_assessment.py:21`, NOT in the catalog).
4. `extract_report` makes direct `client.get_dataset_data(guid, ...)` calls per dataset, no `cacheId`.
5. Normalization is SA-domain-specific.
6. `persist_security_assessment_artifact(normalized, write_legacy=False)` builds metadata.
7. `adapt_reportsplus_rest(...)` produces a `CanonicalArtifact`.
8. `_active_project_store().save_artifact(canonical)` — same project-scoped write as the generic path.

For LS's `collect_from_rest`: same shape as SA, with report ID `206` (`collect_rest.py:23`) and a more elaborate dataset discovery flow (organization, other, agent, metadata datasets with cross-dependent params via `_execute_with_guid_candidates`). Still: direct `client.get_dataset_data` calls; no `cacheId`.

### Notable divergences across the three REST paths

| Concern | Generic (RESTExtractor) | SA (extract_report) | LS (collect_license_summary_rest) |
|---|---|---|---|
| Auth-state class | `CommvaultSession` | `ReportsPlusClient` | `ReportsPlusClient` |
| Protocol | `reportBuilder.do` POST + `cacheId` + paginated GETs | Direct GETs, no `cacheId` | Direct GETs, no `cacheId` |
| Where the report ID lives | `REPORT_DEFINITIONS` Python dict | `SECURITY_ASSESSMENT_REPORT_ID = "336"` Python constant | `LICENSE_SUMMARY_REPORT_ID = "206"` Python constant |
| Where dataset GUIDs live | `subject_section_sources.extraction_instructions` (DB) | Discovered at runtime from the report definition | Discovered at runtime from the report definition |
| Where canonical-artifact assembly lives | `result_to_artifact` (generic) | `adapt_reportsplus_rest` + `persist_security_assessment_artifact` | `_adapt_license_summary` + `persist_license_summary_artifact` |
| Pagination | Yes — `CommvaultSession.fetch_dataset` loops | No — single GET per dataset | No — single GET per dataset |
| Customer-aware? | No (uses `CV_BASE_URL` + session token) | No | No |
| Project-aware? | Yes (resolves active project for save) | Yes (resolves active project for save) | Yes (resolves active project for save) |

## Design forks ADR 0003 will need to settle

Each fork is stated as a question with the realistic options and trade-offs. Items the user flagged explicitly come first.

### F1 — Credentials model: stored, session, or per-collection?

**Options:**
- **(a) Stored on the customer record.** Each customer row holds an encrypted token (or username + encrypted password). The extractor reads creds at collect-time, no prompt needed. *Trade-off:* encryption key management on the dev machine; ADR 0002 explicitly rejected storing credentials ("Credentials are used once for discovery and discarded — not stored"). Reopening that decision requires its own justification.
- **(b) Flask-session token (current behavior).** Whatever's in the session token is what gets used. The token is set once per login and reused for every customer. *Trade-off:* doesn't fit the consulting model where one consultant authenticates against many CommCells; the token is implicitly tied to the deployment that ran the login. Today this works only because `CV_BASE_URL` is also a single env var.
- **(c) Prompted per session.** When the user activates a customer, the UI prompts for credentials (or auto-prompts when a collect is initiated). The token lives in the session for the rest of the session, scoped to that customer. *Trade-off:* extra friction per session-customer switch; needs a way to bind the in-session token to the active customer.
- **(d) Supplied per-collection.** Each collect action takes a credentials payload (typed at collect-time or pulled from a per-session keyring). *Trade-off:* most secure, most friction.

Options (b) and (c) both keep ADR 0002's "credentials not stored" decision intact. Options (a) and the keyring variant of (d) reopen that decision.

### F2 — Routing to the active project: pulled or passed?

**Options:**
- **(a) Pull from session like routes do.** The new extractor calls `make_active_project_store()` internally; signature stays clean. *Trade-off:* tight coupling to Flask request context; non-route callers (CLI, MCP) need a different entry point or have to fake a request context.
- **(b) Take customer_id / project_id as explicit constructor args.** The route handler resolves the active project once and passes it in; the extractor is portable across contexts. *Trade-off:* every route handler has the same two-line preamble; testing is easier.

The phase 2 active-project helpers already split this way: `make_active_project_store()` for request context, `make_default_project_store()` for non-request. ADR 0003 picks which side of that split the new extractor lives on.

### F3 — Relationship to existing per-subject services

The user has settled this: ADR 0003 designs a new extractor that **coexists** with `SecurityAssessmentService.collect_from_rest` and `LicenseSummaryService.collect_from_rest`. Mirrors ADR 0001's fork-tolerance pattern.

**The remaining forks:**
- **(a) Boundary criterion.** What determines whether a subject goes through the new extractor vs an existing service? `created_by` (system vs ai)? Per-subject opt-in row in the catalog? A new flag on the subject? *Trade-off:* `created_by` is the natural axis but it doesn't generalize — system subjects can have catalog-driven REST too (the three current ones do). A per-subject flag is more explicit but more state.
- **(b) Do SA and LS get migrated later?** The fork-tolerance pattern from ADR 0001 was a permanent accommodation (the canonical schema couldn't represent the legacy shapes). Is ADR 0003's fork temporary (SA/LS migrate to the new extractor once it's proven) or permanent (SA/LS keep their custom services forever)? *Trade-off:* temporary means more work later; permanent means more code to maintain forever.
- **(c) Shared building blocks.** Both paths use `ReportsPlusClient` or `CommvaultSession`. Does the new extractor reuse one of those, or introduce a third? The cacheId pattern (`CommvaultSession.init_report` + `fetch_dataset`) is more efficient for many datasets per report; the direct-GET pattern (`ReportsPlusClient.get_dataset_data`) is simpler for one dataset or for parametrised executions. ADR 0003 could pick one, or it could let extraction_instructions specify which.

### F4 — CommCell URL: env var, customer row, or per-collection?

Currently the Commvault URL comes from `CV_BASE_URL` (env var), not from the active customer's `commcell_hostname` field. The customer record's CommCell-identity fields are display-only. ADR 0002 §"Out of scope for v1" said multi-CommCell-per-customer is out, but single-CommCell-per-customer with **different** CommCells per customer is in scope — and that requires reading `commcell_hostname` from the customer row at collect time.

**Options:**
- **(a) Keep `CV_BASE_URL` as the source of truth for v1.** Adequate for one-CommCell-on-one-deployment; doesn't fit multi-customer in practice.
- **(b) Read `commcell_hostname` from the active customer row.** The natural reading of ADR 0002. Each customer's collect hits that customer's CommCell.
- **(c) Per-collection override.** The user can override the URL at collect time. Useful for testing or edge cases.

This fork is downstream of F1: if credentials are per-session-per-customer, the URL has to be per-customer too.

### F5 — Dataset GUID storage: catalog or runtime?

The current catalog stores `dataset_guid` inline in `extraction_instructions`. Dataset GUIDs are CommCell-specific.

**Options:**
- **(a) Catalog-stored.** The current shape. Works fine when there's one CommCell. Breaks when the catalog needs to serve multiple CommCells (each has its own GUIDs).
- **(b) Runtime-discovered.** Each session starts with a discovery step (POST `reportBuilder.do` to get the report definition, walk it to find GUIDs). The catalog stores `report_id` + dataset names; the extractor resolves names → GUIDs at session start. Mirrors what SA/LS already do via `extract_report` + dataset discovery.
- **(c) Hybrid.** Catalog stores `report_id` + dataset names AND optionally dataset GUIDs as a cache hint. Runtime discovery validates and overrides the cache when it's stale.

The user's three-layer identity model (in the next-session brief context) treats (b) as the canonical answer. (a) is the current state; (c) is the migration shape.

### F6 — Pagination, field selection, error handling

The next-session prompt context noted these as open questions with recommended defaults:

- **F6a Field selection.** Explicit in extraction_instructions (current behavior) vs fetch-all-and-filter. Trade-off: explicit means catalog rows must list every needed field per section; fetch-all is wasteful on wide datasets.
- **F6b Pagination.** Paginate by default to fetch all rows (current `CommvaultSession.fetch_dataset` behavior with `limit=None`) vs honor `limit` from extraction_instructions. Trade-off: paginate-by-default catches data the catalog forgot to specify a limit for; honor-limit gives the catalog author control.
- **F6c Multi-dataset error handling.** Fail-whole (the current `RESTExtractor.extract` behavior — returns the result with `.errors` populated, the route surfaces and aborts) vs partial-success-with-warnings vs retry. Trade-off: fail-whole is simpler; partial means some sections render and the user has to manually re-collect missing ones.
- **F6d Auth failure mid-collection.** Auto-reauthenticate (try `login_to_commvault` if creds are available) vs surface to user (the current behavior — 401 → clear token → redirect to login). Trade-off: auto-reauth is friendlier but needs creds-on-hand (see F1); surface-to-user is the current `clear_current_token + redirect("/login", expired=1)` pattern.
- **F6e cacheId lifecycle.** One per collection run vs per-subject fetch. Trade-off: one-per-run is more efficient (fewer reportBuilder POSTs) but assumes the cacheId is good for the whole collection; per-subject is safer if cacheIds expire.

### F7 — Provenance: where does the artifact's commcell_id come from?

Today `_read_commcell_provenance()` reads from global `data/catalog/rest/commserv.json`. ADR 0002 added `commcell_id` and `commcell_hostname` fields on the customer row. The active customer's stored values aren't used in artifact provenance.

**Options:**
- **(a) Keep reading from `commserv.json`.** Doesn't fit multi-customer (collecting for two customers in sequence captures the same commcell_id for both artifacts, whichever CommCell was last cached).
- **(b) Read from the active customer's row.** Each artifact's provenance reflects the customer it was collected for. Natural reading of ADR 0002.
- **(c) Read live from the CommCell.** Hit `/commandcenter/api/CommServ` per collection to capture fresh identity.

(b) is the simplest fix; (c) is more accurate but adds a network round-trip per collection.

### F8 — How is the new extractor invoked?

Where does the user trigger it from?

**Options:**
- **(a) Per-subject Collect button (current generic flow).** The workspace tile has a Collect action that posts to `/quick-hc/<subject_id>/collect`. The new extractor handles the request; per-subject UX is unchanged.
- **(b) Per-project Collect All.** A project-level action that runs collection for every collectable subject in the project's subject set. Useful for "do the whole healthcheck."
- **(c) Both.**

(a) is the obvious carry-over. (b) is a UX win but introduces multi-subject concurrency and error-handling questions (relates to F6c).

## Surprises and observations

### S1 — Two completely different REST-collection patterns coexist today

The generic `RESTExtractor` (used by `/quick-hc/<subject_id>/collect` for AI/system subjects with catalog instructions) uses `CommvaultSession`'s `init_report` (POST `reportBuilder.do`) + `fetch_dataset` (paginated GETs with `cacheId`). The SA and LS `collect_from_rest` paths use `ReportsPlusClient.get_dataset_data` (single GET per dataset, no `cacheId`). The two patterns are not visibly described as alternatives in any doc I read — they evolved separately. ADR 0003 will have to make a deliberate choice about which becomes the new extractor's pattern, or whether both stay.

### S2 — `REPORT_DEFINITIONS` is a hard-coded one-entry Python dict

`src/cvhealthcheck/reportsplus/report_definitions.py:30-32` contains the entire mapping: `{"client_growth": CLIENT_GROWTH_REPORT_DEFINITION}`. Adding a new AI-proposed subject that uses REST requires editing this Python module. This contradicts ADR 0002's spirit of "AI proposals add subjects without code changes" — and the only existing system subject in the dict is one that the catalog also has REST instructions for, so the redundancy is real. ADR 0003 should design a path that moves this data into the catalog (or into the discovery-at-session-start flow per F5).

### S3 — `RESTExtractor`'s SQL hardcodes `source_type = 'rest'`

`extractors/rest.py:88-109` hardcodes the source_type filter. That's fine for v1; flagging because ADR 0003 might want a more general extractor selector (e.g. JSON sources, future source types).

### S4 — `RESTExtractor` has no concept of dataset discovery

The generic extractor reads `dataset_guid` from extraction_instructions and uses it directly. There's no path through `RESTExtractor` that walks a report definition to discover datasets — that lives in `extract_report` (`reportsplus/extract_report.py:17-110`), which the SA/LS paths use. If ADR 0003 picks runtime discovery (F5b/c), `RESTExtractor` will need extending or replacing.

### S5 — `commcell_id` on the customer row is currently display-only

The schema gained `commcell_id` / `commcell_hostname` / `company_guid` in migration 0005. The customer page form lets you set them. Nothing else reads them. The Commvault URL still comes from `CV_BASE_URL`; the artifact provenance still comes from `commserv.json`. This is not an architectural drift per se — the fields are there for ADR 0003 to wire up — but it does mean ADR 0003 has to address F4 and F7 to make the fields meaningful.

### S6 — `customer_context` / `commcell_context` / `engagement_context` already plumbed through LS

`LicenseSummaryService.collect_from_rest` accepts `customer_context`, `commcell_context`, `engagement_context` as kwargs (`service.py:104-110`) and threads them through `persist_license_summary_artifact`. The route handler at `quick_hc.py:295-318` does NOT pass any of these — they default to `None`. So the plumbing exists but isn't connected to the actual customer/project state. A pre-existing partial implementation that ADR 0003 can either complete or reroute.

### S7 — Two token sources still active for Reports Plus inventory

`ReportsPlusClient._inventory_api_client` falls back to `load_login_token()` (`.login_token` file or `$CV_LOGIN_TOKEN` env) when no token is passed. This was documented as a workaround for Reports Plus inventory endpoints returning 401 with the regular bearer token. Whether this is still needed under the new auth model is worth checking — if not, it's dead code.

### S8 — `extractors/rest.py` returns an `ExtractionResult` shape borrowed from `html.py`

`from cvhealthcheck.extractors.html import ExtractionResult`. The shape is shared across HTML and REST extractors. If the new ADR 0003 extractor is structured differently (e.g. async, streaming, multi-stage), it may want a richer result type — flagging the inheritance because the dataclass surface is part of the contract callers (like `result_to_artifact`) depend on.

## Pointers for the design conversation

- **Auth surface:** `src/cvhealthcheck/auth/commvault_auth.py` (login + session token), `src/cvhealthcheck/auth/__init__.py` (file-based fallbacks), `src/cvhealthcheck/web/routes/shared.py:84-93` (route-side helpers).
- **The two existing REST clients:** `src/cvhealthcheck/api_client.py` (the base; one class), `src/cvhealthcheck/reportsplus/client.py` (the per-domain wrapper), `src/cvhealthcheck/reportsplus/session.py` (the cacheId-aware session — used only by the generic extractor).
- **The two existing REST collection flows:** `src/cvhealthcheck/extractors/rest.py` (generic, catalog-driven), `src/cvhealthcheck/reportsplus/extract_report.py` (definition-walking, used by SA/LS), plus the per-subject services at `src/cvhealthcheck/security_assessment/service.py:171` and `src/cvhealthcheck/license_summary/service.py:101`.
- **Where catalog REST instructions live:** `db/migrations/0003_report_inventory.sql:178-235` (schema), `db/migrations/0003_report_inventory.sql:555-`/`0004_rest_instructions_and_constraints.sql` (seed rows). Current rows: query `SELECT sss.section_id, ss.source_type, sss.extraction_instructions FROM subject_section_sources sss JOIN subject_sources ss ON ss.id = sss.source_id WHERE ss.source_type = 'rest'`.
- **Report-definition python lookup:** `src/cvhealthcheck/reportsplus/report_definitions.py` (one entry today).
- **Hardcoded report IDs:** `SECURITY_ASSESSMENT_REPORT_ID = "336"` at `reportsplus/security_assessment.py:21`, `LICENSE_SUMMARY_REPORT_ID = "206"` at `license_summary/collect_rest.py:23`, `CLIENT_GROWTH_REPORT_DEFINITION` (report 318) at `reportsplus/report_definitions.py:22`.
- **Active-project resolver:** `src/cvhealthcheck/web/active_project.py` (see Section 3 of the data flow audit).
- **Where collected artifacts land:** `make_active_project_store().save_artifact(canonical)` → `data/catalog/artifacts/<customer>/<project>/working/<subject>/{timestamp}.json + latest.json`. Same final write across all three current REST paths.
- **Provenance gap:** `_read_commcell_provenance()` at `web/routes/quick_hc.py:77-86`. Reads global `commserv.json`, not the active customer's row.
- **Test suite:** 554 passing. Tests touching REST extraction: `tests/test_rest_extractor*.py`, `tests/test_extract_report*.py`, `tests/test_security_assessment_*.py`, `tests/test_license_summary_*.py`. Worth grepping if the ADR proposes a change that would break extraction-instruction shape or extractor signature.
