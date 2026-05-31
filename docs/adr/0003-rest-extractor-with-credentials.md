# ADR 0003 — REST extractor with credentials

## Status

Implemented (with LS caveat). The catalog-driven REST extractor handles four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment). License Summary retains its bespoke `collect_from_rest` path — see the Migration and Out-of-scope sections for the rationale and the backlog item that records the future-expansion work.

## Context

ADR 0002 introduced customers and projects as first-class entities and ended with collected artifacts landing under `data/catalog/artifacts/<customer>/<project>/working/<subject>/`. The "collect" half of that flow — actually pulling data from a customer's CommCell — is still wired to the pre-0002 world: one `CV_BASE_URL` env var, one Flask-session token, no awareness of which customer is active.

ADR 0003 designs the live collection path: a REST extractor that takes credentials at collect time, hits the active customer's CommCell, and writes a canonical artifact to that customer's active project.

The survey (`docs/adr/0003-survey.md`) catalogued what's in the codebase today. The short version is that there are three REST collection paths in production, and they don't agree:

- **Generic** `RESTExtractor` driven by catalog rows in `subject_section_sources.extraction_instructions`. Uses `CommvaultSession`, which does a two-step pattern: POST `reportBuilder.do` to get a `cacheId`, then paginated GETs to `/datasets/<guid>/data?cacheId=…`. Used by `/quick-hc/<subject_id>/collect` for the three system subjects that currently have REST instructions.
- **Security Assessment** `SecurityAssessmentService.collect_from_rest`. Walks a report definition (report 336) at runtime, makes direct GETs to `/datasets/<guid>/data` with no `cacheId`, normalizes through `normalize_security_assessment`.
- **License Summary** `LicenseSummaryService.collect_from_rest`. Same shape as SA (report 206), more elaborate dataset discovery, normalizes through `normalize_license_summary_rest_extraction`.

Adding insult to fork, AI-proposed subjects that want REST collection currently can't have it without a Python edit to a one-entry `REPORT_DEFINITIONS` dict. That contradicts ADR 0002's spirit of catalog-driven subject addition.

Investigation of the License Summary report's actual API traffic showed two patterns in use against this CommCell. The browser's interactive rendering of the report POSTs `reportBuilder.do` once, gets a `cacheId`, and reuses it across 7+ dataset GETs to keep UI state coherent across drill-downs, sorting, and pagination cursors. The "direct GET, no cacheId" path that SA and LS use is the simpler programmatic shape: each dataset GET returns the data alongside an auto-generated `cacheId` in the response body, with no separate acquisition step. Each dataset row also comes back with display-ready `_formatted` siblings, meaning the per-subject "normalize" modules are mostly splitting datasets and labeling them, not transforming data.

That capture reframed the SA/LS services. They aren't structurally special — they're catalog rows that haven't been written yet. SA renders 1+ tables from report 336. LS renders 7 tables from report 206. Both fit the same shape as `client_growth.monthly_table`: one report, N sections, each section a dataset rendered as a table or card.

## Decision

ADR 0003 designs a single REST extractor that is catalog-driven, customer-scoped, and replaces all three current REST paths. The fork is not preserved.

### Authentication and customer scoping

Credentials are not stored at rest. The Flask session holds one CommCell token at a time, bound to the customer it was issued for. When a collect is initiated:

1. If the session has no token, or the token is bound to a different customer than the active one, the user is prompted for credentials.
2. The login POSTs to the **active customer's** CommCell (`commcell_hostname` from the customer row, not `CV_BASE_URL`). On success, the returned token is stored in the session along with the customer ID it was issued for.
3. The token is used for the collection. If the upstream returns 401, the session token is cleared and the user is redirected to re-authenticate. No auto-reauth.

`CV_BASE_URL` and the global `commserv.json` provenance file stop being authoritative. The active customer row is the single source of truth for both the CommCell URL and the artifact's provenance (`commcell_id`, `commcell_hostname`, `company_guid`).

The token's lifetime is the Flask session's lifetime. Switching the active customer mid-session invalidates the bound token; the next collect re-prompts.

### Catalog schema

`subject_section_sources.extraction_instructions` gains two concepts and loses one:

- **Gains** `report_id` (the Commvault report ID — `"206"`, `"336"`, `"318"`, etc.) and `dataset_name` (the dataset's display name within the report, e.g. `"GetLicenseSummaryCapacityV3"`).
- **Gains** `output_as: "card"` as a third option alongside `"table"` and `"findings"`. `"card"` renders the first row of the fetched dataset as a key-value block, used for report-header information like CommCell ID, last collection time, and license expiry.
- **Loses** `dataset_guid` as the canonical reference. Dataset GUIDs are CommCell-scoped (they vary across deployments) and are resolved at runtime, not stored in the catalog. A `dataset_guid` field may persist as an optional cache hint, but the canonical reference is `report_id` + `dataset_name`.

All sections within a single subject must reference the same `report_id`. The report definition fetch (`GET /reports/<report_id>`) happens once per subject collection, and the resolved `dataset_name` → `dataset_guid` map is reused across all section fetches for that subject.

### Extractor shape

The new extractor replaces the generic `RESTExtractor`, `SecurityAssessmentService.collect_from_rest`, and `LicenseSummaryService.collect_from_rest`. Per collection it:

1. Receives `(customer_id, project_id, subject_id, token, base_url)` as explicit constructor arguments — no Flask request context dependency. The route handler resolves these once and passes them in; non-route callers (CLI, MCP) construct them directly.
2. Opens a `CommvaultSession(base_url, token)` and GETs the report definition for the subject's `report_id`. Walks the definition to build a `dataset_name` → `dataset_guid` map for that report. The map is reused across all section fetches for the subject.
3. Loads the subject's section instructions from `subject_section_sources` filtered to `source_type='rest'`.
4. For each section: resolves `dataset_name` → `dataset_guid` from the map, GETs `/datasets/<guid>/data` with the section's `fields`, `orderby`, `limit`, and `parameters` from `extraction_instructions`, applies generic post-processing (timestamp parsing, null normalization, `_formatted`-sibling handling), and assigns the result to `result.sections[section_id]` with the section's `output_as` mode.
5. Returns an `ExtractionResult` that `result_to_artifact(...)` converts to a `CanonicalArtifact`, which is then written via `project_store.save_artifact(artifact)`.

Error handling is fail-whole. If any section's fetch fails, the run aborts with a clear error; partial artifacts are not written.

The current `output_as: "table" | "findings"` post-processing in `RESTExtractor._fetch_section` continues to apply. `output_as: "card"` is new: it takes `result.sections[section_id].rows[0]` and emits a key-value block keyed by `fields`. Non-TABLE components in the report definition (PANELs, custom HTML) are ignored by the extractor; if the consultant wants header information rendered, the catalog adds a `card` section pointing at the relevant dataset.

The browser's UI rendering of Reports Plus reports uses a `cacheId` acquisition step (POST `reportBuilder.do`, then GETs parameterized by the returned `cacheId`). That step is a UI-session concern — it keeps state coherent across drill-downs, sorting, and paginated views. Programmatic collection does not require it: the dataset GET endpoint accepts requests without a `cacheId` and returns one auto-generated in the response body. Including the POST step has been observed to fail (HTTP 419) on some CommCell deployments. ADR 0003's extractor follows the programmatic pattern — GET-only, no `cacheId` acquisition. The SA and LS bespoke `collect_from_rest` paths were already using this shape; ADR 0003 generalizes it as the catalog-driven extractor's protocol rather than replacing it.

### Invocation

For v1, only per-subject collection through `/quick-hc/<subject_id>/collect` is supported. The route resolves the active customer and project from the session, pulls the customer's `commcell_hostname` and the session token, constructs the extractor, runs it, and saves the artifact. Project-wide "Collect All" is out of scope for this ADR — it's a UX layer over the same per-subject extractor and can be added later without disturbing the design.

### Migration

Security Assessment migrates to the catalog-driven REST extractor (phase 4 of implementation). License Summary is deliberately left in its bespoke `collect_from_rest` path. Investigation during phase 5 surfaced that LS's report structure (47+ pages with name-ambiguous datasets, runtime dataset-result-to-parameter dependencies, and per-row value formulas like unit suffixing) does not fit the catalog model's expressiveness as defined in this ADR. Migrating LS would require extractor extensions (parameter substitution from prior dataset results, page-aware GUID resolution, value-formula transforms) whose cost exceeds the cleanup benefit for a single subject. A backlog item records the work needed to migrate LS in a future expansion; meanwhile LS continues to work through its existing bespoke flow, unchanged by this ADR.

For SA's migration: report 336 was walked during phase 4 implementation to seed rows in `subject_section_sources`, one section per topic table. After seeding, the following SA-specific modules were deleted:

- `src/cvhealthcheck/security_assessment/service.py::collect_from_rest` (method)
- `src/cvhealthcheck/reportsplus/security_assessment.py`'s REST-collection helpers (`extract_security_assessment`, `normalize_security_assessment`)
- `src/cvhealthcheck/adapters/security_assessment.py::adapt_reportsplus_rest`

`SecurityAssessmentService` itself stays (HTML/CSV import paths are unchanged). Equivalent LS deletions (`license_summary/collect_rest.py`, `license_summary/service.py::collect_from_rest`, `_adapt_license_summary`, `normalize_license_summary_rest_extraction`, `persist_license_summary_artifact`) and the shared `extract_report.py` are deliberately retained because LS continues to use them.

The pre-amendment cacheId machinery — `CommvaultSession.init_report`, the `REPORT_DEFINITIONS` dict at `src/cvhealthcheck/reportsplus/report_definitions.py`, and the display-only `_read_commcell_provenance` helper — are deleted as part of phase 5's cleanup since they had no remaining production callers after the GET-only protocol amendment.

Existing SA artifacts under `data/catalog/artifacts/<customer>/<project>/working/security_assessment/` are dev-only state, not real customer work. ADR 0002 set the precedent that throwaway dev artifacts are deleted cleanly during a migration rather than preserved through a compatibility layer. ADR 0003 follows the same rule for SA: existing SA artifact directories are deleted as part of phase 4, and subjects re-collect into the new canonical shape on first use of the new extractor. No forward-migration script, no dual-read compatibility, no shape-translation code. LS artifacts are not wiped because LS is not migrated.

### Active-project resolution

The new extractor takes `customer_id` and `project_id` as explicit arguments. The route handler at `/quick-hc/<subject_id>/collect` is responsible for resolving these via `make_active_project_store()`'s underlying helpers and passing them in. This makes the extractor portable to CLI and MCP contexts without faking a Flask request, while keeping the request-context resolution centralized in route handlers.

## Consequences

**Positive.** One extractor replaces three. AI-proposed subjects can use REST without a Python edit. The catalog becomes the single source of truth for what a REST collection does. One report definition GET per subject collection (instead of per-dataset metadata lookups) keeps the request count low for multi-section subjects like License Summary. CommCell URL and provenance derive from the active customer row, making multi-customer collection work correctly. Credentials remain unstored, preserving ADR 0002's decision.

**Negative.** SA's artifact shape changed. Existing SA dev artifacts under those subjects got deleted rather than migrated; consultants who had those artifacts around needed to re-collect after phase 4 landed. Out-of-tree code reading the old shape (none known to exist) would break. Switching active customers mid-session invalidates the token and forces re-authentication, which is friction the current single-CommCell model doesn't have. **LS was not migrated.** The bespoke LS REST code, including `extract_report.py` (which is no longer shared with SA), remains in place. ADR 0003's stated goal of one unified REST collection path is partially achieved — the generic path handles four of five REST subjects (client_growth, capacity_license, backup_job_summary, security_assessment); LS retains the bespoke path.

**Out of scope.** Multi-CommCell-per-customer collection (deferred per ADR 0002). Project-wide "Collect All" invocation. Credential storage of any form. Auto-reauthentication on 401. Live `commcell_id` discovery from the CommCell at collect time (the customer row's stored values are authoritative; if they're wrong, the customer page is the place to fix them). **LS catalog migration is out of scope for ADR 0003 as implemented.** Future expansion work documented in the backlog.

**Open questions.** Whether `subject_section_sources` needs a constraint enforcing "all REST sections in a subject share the same `report_id`," or whether that's a runtime check.

## Pointers for implementation

- Auth: `src/cvhealthcheck/auth/commvault_auth.py` (login, session token), `src/cvhealthcheck/web/routes/shared.py` (route-side token + client construction).
- Session: `src/cvhealthcheck/reportsplus/session.py::CommvaultSession` (the shared HTTP session for Reports Plus; the extractor uses its dataset GET helper).
- Current generic extractor: `src/cvhealthcheck/extractors/rest.py::RESTExtractor` (the starting point — replace with the ADR 0003 extractor, preserving `_fetch_section`'s timestamp and null-value post-processing).
- Catalog schema: `db/migrations/0003_report_inventory.sql` (current shape), `db/migrations/0004_rest_instructions_and_constraints.sql` (current seed rows). A new migration adds `report_id`, `dataset_name`, and `output_as: "card"` support.
- Customer record: the `commcell_hostname` / `commcell_id` / `company_guid` columns added in migration 0005 become load-bearing under ADR 0003.
- Active-project resolution: `src/cvhealthcheck/web/active_project.py`. The route handler uses this; the extractor does not.
- Test suite: `tests/test_rest_extractor*.py`, `tests/test_extract_report*.py`, `tests/test_security_assessment_*.py`, `tests/test_license_summary_*.py`. The deletions described above will remove most of `test_extract_report*` and the REST-collection portions of the SA/LS tests; the new extractor needs equivalent coverage with the schema-extended catalog rows.
