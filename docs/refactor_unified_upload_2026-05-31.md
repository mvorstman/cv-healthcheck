# Refactor: Unified upload route — Session 1 investigation report

**Date:** 2026-05-31
**Branch:** `feature/basic-healthcheck-report-output`
**Tests at start of session:** 469 passing.
**Code changes this session:** none. This is investigation only.

---

## Summary (read me first)

The codebase has **two** per-subject upload routes today, not the six the prior HANDOVER implied: `/quick-hc/security-assessment/import` and `/quick-hc/license-summary/import`. The other four "system" subjects (environment, client_growth, capacity_license, backup_job_summary) have **no upload path at all** — their sources are REST/metrics only, never user file upload. AI-created subjects route uploads through the generic `/quick-hc/import?subject_id=<id>` endpoint.

The per-subject routes are very thin — each is ~25 lines that delegate to `import_security_assessment_upload()` or `import_license_summary_upload()`. The generic route is **structurally richer**: it supports an `X-Inline: 1` JSON-response mode, a `?stage=1` query that routes uploads through the staging table, and reports recognition/extraction errors as distinct outcomes. A unified route needs to absorb all three structural features — none can be dropped without losing existing behavior.

The persist functions' `write_legacy=True` default is the only thing keeping ~30 test cases in `test_security_assessment_registry.py` and `test_license_summary.py` writing to the legacy per-domain store. Production code has been `write_legacy=False` everywhere since 2026-05-27 (the Option A commit). Flipping the default in session 2 or 3 is mechanical but requires touching every legacy-behavior test.

There are **three** source-building paths today (the prior HANDOVER only named two): `_build_generic_subject` + `_build_generic_sources` (handles AI subjects and any subject with a fresh canonical artifact), the per-subject legacy builders + `_build_tile_sources` (system subjects without a canonical artifact), and `canonical_view._build_sources` (a third path used by `security_assessment_to_view` and `license_summary_to_view` directly, though I could not confirm from a code-only reading whether the third path is reachable in production). The unified route's success depends on whichever source-building path actually feeds the frontend's `importUrl` — see section 3 for the divergence between the test fixtures and what production likely does.

Recommendation: session 2 should build `POST /quick-hc/import/<subject_id>` alongside the existing routes, dispatch by `subjects.created_by` rather than by hard-coded subject ID, and explicitly defer the source-building unification to session 3 so the new route can be added without a simultaneous JS-payload change. Estimated test-count delta: +6 / -0 in session 2 (new route tests added, old tests untouched).

---

## Section 1 — Per-subject route inventory

The HANDOVER claimed "all 6 system subjects have per-subject routes." That is **false**. Only two do. The other four have no upload route — they are REST/metrics-only sources.

### 1.1 `security_assessment`

```
POST /quick-hc/security-assessment/import
    src/cvhealthcheck/web/routes/quick_hc.py:236-260
    def quick_hc_security_assessment_import()
```

Operations, in order:

1. Reads `request.files.get("assessment_file")`. **Form field name is `assessment_file`** — subject-specific (not `file`).
2. Extracts `filename`. If empty: flash `"No file selected."` as error, redirect to `main.quick_hc_security_assessment` (which is itself a redirect to `main.quick_hc`).
3. Calls `import_security_assessment_upload(upload.stream, original_filename=filename)`.
4. Catches `SecurityAssessmentImportError` → flashes the exception message as `"error"`.
5. Catches generic `Exception` → flashes `f"Security Assessment import failed: {exc}"` as `"error"`.
6. On success: flashes `f"{source_type} import completed for {artifact.get('source_file')} with {finding_count} findings."` as `"success"`. **The success message format is subject-specific — it names "findings."**
7. Redirects to `main.quick_hc_security_assessment` regardless of outcome.

`import_security_assessment_upload` (`src/cvhealthcheck/security_assessment/service.py:187-247`) does the substantive work:

- `secure_filename()` + extension lookup against `ALLOWED_EXTENSIONS = {".html": "html", ".htm": "html", ".csv": "csv"}`. **Subject-specific extension whitelist.**
- Raises `SecurityAssessmentImportError("Unsupported file type. Upload a Commvault Security Assessment HTML or CSV export.")` for unknown extensions. **Subject-specific error message.**
- Saves the upload to `SECURITY_ASSESSMENT_IMPORTS_DIR` via `_save_upload()`.
- Dispatches to `import_security_assessment_html(saved_path, write_artifact=False)` or `import_security_assessment_csv(...)` based on source_type. **Subject-specific parser dispatch.**
- Raises `SecurityAssessmentImportError(f"{source_type.upper()} import produced no findings.")` if `finding_count == 0`. **Subject-specific empty-result guard (counts findings).**
- Calls `persist_security_assessment_artifact(artifact, ..., write_legacy=False)`.
- Logs an info line with `_finding_preview()` (a subject-specific debug formatter).

Tests covering this route:

```
tests/test_security_assessment_import.py:400-415
    def test_quick_hc_security_assessment_upload_imports_html_and_redirects()
    Hits /quick-hc/security-assessment/import with HTML_SAMPLE; asserts 200 after
    follow_redirects. URL-coupled.
```

The dev-page mirror route `/security-assessment/import` (in `web/routes/development.py:247`) calls the same `import_security_assessment_upload()`. It is NOT being refactored, but tests using the dev path also exercise the underlying function — they will continue to pass under the unified route since they bypass it entirely. (Lines 344, 370, 584, 610, 625, 642 of `test_security_assessment_import.py`.)

### 1.2 `license_summary`

```
POST /quick-hc/license-summary/import
    src/cvhealthcheck/web/routes/quick_hc.py:319-349
    def quick_hc_license_summary_import()
```

Operations, in order:

1. Reads `request.files.get("license_summary_file")`. **Form field name is `license_summary_file`** — different from security_assessment.
2. Empty-filename check → flash, redirect to `main.quick_hc_license_summary`.
3. **Extra step not in security_assessment**: validates `Path(filename).suffix.lower()` against `LICENSE_SUMMARY_UPLOAD_EXTENSIONS = {".csv", ".htm", ".html"}` (defined at `web/routes/shared.py:71`). On reject: flashes `"Unsupported file type. Upload a License Summary CSV or HTML export."` and redirects. **Pre-handler extension check, not just relying on the import function's own check.**
4. Calls `import_license_summary_upload(upload.stream, original_filename=filename)`.
5. Catches `LicenseSummaryImportError` → flashes the exception as `"error"`.
6. Catches generic `Exception` → flashes `f"License Summary import failed: {exc}"` as `"error"`.
7. On success: flashes `f"{source_type} import completed for {source_file} with {N} other licenses and {M} agent/feature licenses."` as `"success"`. **Subject-specific success-message format counts two row buckets.**
8. Redirects to `main.quick_hc_license_summary`.

`import_license_summary_upload` (`src/cvhealthcheck/license_summary/service.py:140-193`) substantive work:

- Same secure_filename + extension dispatch pattern, but `ALLOWED_EXTENSIONS = {".csv": "csv", ".html": "html", ".htm": "html", ".xlsx": "xlsx"}` — **includes `.xlsx` for "API viewer recording" import, which security_assessment does not support.**
- Three-way parser dispatch: `import_license_summary_html`, `import_license_summary_csv`, or `import_license_summary_xlsx_recording`. **Three formats vs two.**
- Empty-result check: `if not artifact.get("other_licenses") and not artifact.get("agent_feature_licenses")` → raises `LicenseSummaryImportError(f"{source_type.upper()} import produced no license rows.")`. **Subject-specific empty-result guard (different row buckets).**
- Calls `persist_license_summary_artifact(artifact, ..., write_legacy=False)`.
- **Extra step not in security_assessment**: calls `_artifact_store.save_artifact(_adapt_license_summary(persisted))` directly after persist — license_summary writes canonical at the caller, security_assessment writes canonical inside the persist function under a `source_type in {html, csv, json}` guard.

Tests covering this route:

```
tests/test_license_summary_web.py:106-146
    def test_quick_hc_license_summary_upload_imports_csv_and_redirects()
    URL-coupled.

tests/test_license_summary_web.py:149-185
    def test_quick_hc_license_summary_upload_rejects_unsupported_type()
    URL-coupled. Specifically exercises the pre-handler suffix check at quick_hc.py:328.
```

### 1.3 — 1.6 The other four system subjects

```
environment           — NO upload route.  Source: REST CommCell API only.
client_growth         — NO upload route.  Source: REST Reports Plus (metrics).
capacity_license      — NO upload route.  Source: REST Reports Plus (metrics).
backup_job_summary    — NO upload route.  Source: REST Reports Plus (collector).
```

Verified by reading each `_build_*_subject()` function in `subject_data_service.py`:

- `_build_client_growth_subject()` at `:967-1100` calls `_build_tile_sources()` with `statuses={CSV: "ni", HTML: "ni", JSON: "ni", ...}` and **no `actions` dict for any source**. The CSV/HTML/JSON sources render as "not implemented" badges with no upload button.
- Same pattern for `_build_capacity_license_subject()` (`:1102`), `_build_backup_job_summary_subject()` (`:1232`), and `_build_environment_subject()` (`:400-476`).

The four REST-only subjects have no behavior to migrate. Whatever shape the unified route takes, these four are unaffected.

### Subject-specific behavior summary (the parts a unified route must accommodate)

| Concern | security_assessment | license_summary |
|---|---|---|
| Form field name | `assessment_file` | `license_summary_file` |
| Extension whitelist | `.html .htm .csv` | `.csv .htm .html .xlsx` |
| Pre-handler suffix check | no (relies on import function) | yes (at route handler) |
| Empty-result guard | `finding_count == 0` | both row buckets empty |
| Empty-result message | "produced no findings" | "produced no license rows" |
| Success message format | counts "findings" | counts "other licenses and agent/feature licenses" |
| Canonical write site | inside persist, gated on `source_type ∈ {html,csv,json}` | at caller after persist |
| XLSX import | no | yes |
| Custom file save dir | `SECURITY_ASSESSMENT_IMPORTS_DIR` | `LICENSE_SUMMARY_IMPORTS_DIR` |
| Exception class | `SecurityAssessmentImportError` | `LicenseSummaryImportError` |
| Generic-exception flash text | "Security Assessment import failed" | "License Summary import failed" |

---

## Section 2 — Generic route deep-read

```
GET, POST /quick-hc/import
    src/cvhealthcheck/web/routes/quick_hc.py:379-454
    def quick_hc_generic_import()
```

Operations, in order:

1. Reads `X-Inline: 1` header into `inline` (boolean). **Inline mode switches every flash+redirect to a JSON response.**
2. **GET branch** (`:383-384`): renders `templates/quick_hc_import.html`. The template was a transitional UX for an in-app generic upload page; in current usage the GET branch may be effectively dead (no nav link points to it that I could find — the per-subject upload actions all POST directly), but the template exists.
3. **POST branch**:
   - Reads `request.files.get("file")` — form field name is `file` (different from both per-subject routes).
   - Empty-filename: returns `{"success": False, "error": "No file selected."}` with 400 in inline mode, otherwise flash + redirect to itself.
   - Saves the upload to a `tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".tmp", delete=False)` — **no per-subject imports-dir convention**. The temp file is deleted in the `finally` block (`:449-451`).
   - Reads `request.args.get("subject_id")` as `explicit_subject_id`. **This is what `subject_data_service._build_generic_sources` passes as the query string.**
   - Reads `request.args.get("stage") == "1"` as `stage_flag`.
   - Calls `dispatch = extract_file(tmp_path, db, subject_id=explicit_subject_id)`. This is `cvhealthcheck.extractors.dispatcher.extract_file()` — a generic dispatcher driven by `subject_section_sources` extraction instructions in the DB.
   - Three distinct error outcomes from `dispatch`:
     - `not dispatch.recognized` → "File not recognised — no matching report type found." (422 inline, flash "warning" otherwise).
     - `not dispatch.extractable` → "File recognised but not extractable: {reason}." (422 inline, "warning" otherwise).
     - `dispatch.extraction_errors` → "Extraction errors: {…}" (422 inline, "error" otherwise).
   - **No empty-result guard**. The generic route saves whatever the dispatcher produces.
   - On success:
     - If `stage_flag`: creates a row in `staged_artifacts` via `_staging_db.create_staged_artifact()` with status "pending". Message: `f"Imported {title} — review in staging before approving."`
     - Otherwise: `ArtifactStore().save_artifact(artifact)` and message `f"Imported {title} successfully."`
   - Generic `Exception` handler wraps the whole POST body (`:445-448`): JSON 500 in inline mode, `flash(f"Import failed: {exc}")` otherwise.
   - `finally` block deletes the temp file and closes the db connection.
4. Final redirect to `main.quick_hc_generic_import` (i.e. back to the same page).

### Differences vs per-subject routes

What the **generic route does that per-subject routes do not**:

- Supports GET (renders an upload page).
- Inline JSON response mode via `X-Inline: 1` header.
- Staging route via `?stage=1` query param.
- Three distinct error categories (recognition, extractability, extraction errors).
- Generic dispatcher (`extract_file`) driven by DB-stored extraction instructions; no per-subject parser dispatch.
- Uses Python `tempfile` for the upload, not a per-subject imports dir.
- Saves the artifact via `ArtifactStore().save_artifact(artifact)` directly — bypasses any `persist_*` function.
- Does not flash a success message that counts subject-specific buckets (no "N findings" or "M licenses") — just "Imported {title} successfully."

What **per-subject routes do that the generic route does not**:

- Subject-specific empty-result guards.
- Subject-specific success messages counting domain-specific things.
- Subject-specific extension whitelists with subject-specific error text.
- Per-subject imports dir for audit retention.
- Per-subject persist functions that maintain provenance (customer_id, commcell_id, import_run_id, etc. — see `persist_security_assessment_artifact` signature for the full list).
- Per-subject canonical-side-write timing (inside persist for SA; at caller for LS).

### Tests covering the generic route

```
tests/test_recognition.py:298-313
    def test_import_route_direct_save()
    POST /quick-hc/import with valid SA HTML; asserts artifact saved.
    Route-coupled (tests dispatcher integration through the route).

tests/test_recognition.py:316-340
    def test_import_route_staged()
    POST /quick-hc/import?stage=1; asserts staged_artifacts row created.
    Route-coupled — tests the ?stage=1 branch which is generic-only.

tests/test_recognition.py:343-363
    def test_import_route_unrecognized()
    POST /quick-hc/import with unrecognized HTML; asserts warning rendered.
    Route-coupled — tests the "not recognized" outcome which is generic-only.

tests/test_recognition.py:366-381
    def test_import_route_not_extractable()
    POST /quick-hc/import with charts-only HTML; asserts "not extractable" rendered.
    Route-coupled — tests the "not extractable" outcome which is generic-only.

tests/test_import_flow.py:105-140
    def test_import_route_passes_subject_id()
    POST /quick-hc/import?subject_id=my_report; asserts subject_id is forwarded
    to extract_file. URL-coupled (could trivially become path-coupled).
```

---

## Section 3 — Source-building path inventory

There are not two source-building paths today. There are **three**.

### 3.1 `_build_generic_subject` + `_build_generic_sources` (subject_data_service.py)

```
src/cvhealthcheck/quickhc/subject_data_service.py:191-218 (subject builder)
src/cvhealthcheck/quickhc/subject_data_service.py:158-188 (source builder)
```

Called from `build_subject_initial_data` at `:93-94`: **whenever `_load_from_canonical_store(subject_id)` returns a non-None artifact.** Also called at `:101` for AI subjects with no canonical artifact (when `db is not None`).

Source URL convention:

```python
import_url_base = f"/quick-hc/import?subject_id={subject_id}"
```

Output shape per subject (`_build_generic_subject` with artifact):

```python
{
    "id": str,
    "name": tile["title"],           # registry override (load-bearing — see CHANGELOG 2026-05-25)
    "description": str,              # from tile description/subtitle
    "state": str,                    # from artifact_to_view
    "included": True,
    "subtitle": str,                 # from artifact_to_view
    "fullUrl": None,                 # NB: hard None — see Section 3 differences
    "activeSource": str,
    "sources": [...],                # OVERRIDDEN with _build_generic_sources
    "sections": [...],               # from artifact_to_view
    "created_by": str,               # appended at :105 of build_subject_initial_data
    "status": str,
}
```

When artifact is None (AI subject, no canonical yet):

```python
{ ... "state": "nodata", "subtitle": "Not collected", "sections": [], ... }
```

Source-item shape (output of `_source_item`):

```python
{
    "id": source_id,
    "name": str,
    "desc": str,
    "status": str,            # "v" | "a" | "n" | "ni"
    "meta": [{"k": ..., "v": ...}, ...],
    "actions": [{"kind": "upload", "label": "Import", "importUrl": str, "importField": "file", "accept": str}, ...]
}
```

`importField` is **hard-coded to `"file"`** by `_build_generic_sources:172`.

Tests:

```
tests/test_import_flow.py:145+        test_artifact_to_view_generic
tests/test_quickhc_subject_data_service.py  (multiple tests — see file)
```

### 3.2 Per-subject legacy builders + `_build_tile_sources` (subject_data_service.py)

```
_build_environment_subject              :400-476
_build_security_assessment_subject      :479+  (large — handles SA-specific section mapping)
_build_license_summary_subject          :~700+ (large — handles LS-specific section mapping)
_build_client_growth_subject            :967-1100
_build_capacity_license_subject         :1102+
_build_backup_job_summary_subject       :1232+
_build_tile_sources                     :374-397 (shared source-list builder)
```

Called from `build_subject_initial_data` at `:97-99`: **only for system subjects, and only when no canonical artifact exists.**

Source URL convention:

```python
import_url=_SA_IMPORT_URL   # = "/quick-hc/security-assessment/import"
import_url=_LS_IMPORT_URL   # = "/quick-hc/license-summary/import"
```

`importField` is set per-subject (`assessment_file`, `license_summary_file`).

Output shape — mostly the same six top-level keys (`id`, `name`, `description`, `state`, `subtitle`, `fullUrl`, `activeSource`, `sources`, `sections`), but **populated independently** by each builder, with hand-written `sources` arrays per status condition (no-data vs has-data branches separately call `_build_tile_sources`).

`fullUrl` is `_try_url("main.quick_hc")` (a real URL) when present, NOT hard None. **Difference vs `_build_generic_subject`.**

`_build_tile_sources` always returns **all five `STANDARD_SOURCES`** in fixed order (`rest_command_center_api`, `rest_reports_plus`, `json_import`, `csv_import`, `html_import`). `_build_generic_sources` returns only the sources present in `tile.get("sources", [])` — for AI subjects from the DB, that may be fewer.

Tests:

```
tests/test_quickhc_subject_data_service.py — most likely covers all builders
tests/test_quick_hc_report.py:881-896 asserts shape and importUrl for SA/LS
```

### 3.3 `canonical_view._build_sources` (canonical_view.py)

```
src/cvhealthcheck/quickhc/canonical_view.py:441-470
```

Called from `security_assessment_to_view()` and `license_summary_to_view()` in `canonical_view.py`. Driven by `tile.import_url` from the registry (`/quick-hc/security-assessment/import` for SA, `/quick-hc/license-summary/import` for LS).

**Whether this is reachable in production is unclear from a code-only reading.** `_build_generic_subject` calls `artifact_to_view` (the generic one), not `security_assessment_to_view`. The subject-specific view functions are only used by the legacy builders. So `canonical_view._build_sources` only fires through the legacy builder path, which (in turn) only fires when no canonical artifact exists for the subject.

For security_assessment + license_summary specifically: after any production import (which writes both legacy and canonical for `source_type ∈ {html,csv,json}`, see Option A), the canonical artifact exists → `_build_generic_subject` is called → its `_build_generic_sources` produces `/quick-hc/import?subject_id=…` — **not** `/quick-hc/security-assessment/import`.

But the test at `tests/test_quick_hc_report.py:893-896` asserts the URL **is** `/quick-hc/security-assessment/import`. The test passes because it constructs the artifact with `source_type="rest"`, which does NOT trigger the canonical write inside `persist_security_assessment_artifact` (the canonical write at `service.py:374` is gated on `source_type ∈ {html,csv,json}`). So the test forces the no-canonical branch and exercises the legacy builder.

**This is a production-vs-test divergence worth flagging.** In real production, after an HTML/CSV import through the per-subject route, the frontend will render `importUrl="/quick-hc/import?subject_id=security_assessment"` for any subsequent upload — i.e. the per-subject route is not actually used as the importUrl after the first successful import. I could not confirm this end-to-end without running the app; it is a code-reading inference. **Flagging as something the user may want to verify before assuming session 4 (URL deletion) is risk-free.**

### Differences load-bearing? cosmetic? unknown?

| Field | Generic (`_build_generic_subject`) | Legacy (`_build_*_subject`) | Significance |
|---|---|---|---|
| `importUrl` for SA/LS | `/quick-hc/import?subject_id=…` | `/quick-hc/security-assessment/import` etc. | **Load-bearing.** The button POSTs to this. |
| `importField` | hard-coded `"file"` | `assessment_file` / `license_summary_file` | **Load-bearing.** The route reads this exact key from `request.files`. |
| `fullUrl` | `None` | `_try_url("main.quick_hc")` (string) | **Unknown** — frontend may or may not render based on this. |
| `sources` list size | only DB-listed sources (may be < 5) | always all 5 STANDARD_SOURCES | **Likely cosmetic** — extra "ni" sources just render as muted badges. |
| `description` source | tile description from DB | `resolve_tile_description(subject_id)` (file-based overrides) | **Possibly load-bearing** — user-edited descriptions persisted separately. |
| Source `meta` content | empty for AI subjects | hand-curated per source ("Report ID: 336" etc.) | **Cosmetic** but informative. |
| `state` for missing artifact | `"nodata"` | typically `"nodata"`, varies | matches. |

---

## Section 4 — Option A migration mechanics

`persist_security_assessment_artifact` and `persist_license_summary_artifact` both currently take `write_legacy: bool = True`. The Option A invariant has them at `write_legacy=False` for every production call.

### 4.1 Call sites of `persist_security_assessment_artifact`

```
src/cvhealthcheck/security_assessment/service.py:227-238 (inside import_security_assessment_upload)
    write_legacy=False ✅

src/cvhealthcheck/security_assessment/service.py:250 (definition)
    default write_legacy=True

src/cvhealthcheck/reportsplus/security_assessment.py:57 (inside extract_security_assessment)
    write_legacy=False ✅
```

Production passes `write_legacy=False` from both call sites. **No production caller relies on the True default.**

Test callers (all default to `write_legacy=True`, i.e. exercise the legacy path):

```
tests/test_security_assessment_registry.py — 22 separate calls (lines 136, 164, 171, 211, 254, 261, 301, 312, 355, 360, 396, 423, 456, 473, 529, 572, 579, 615, 649, 697, 740). The whole file exercises the legacy SQLite registry, which IS the legacy store. These are intentionally legacy-path tests.

tests/test_quick_hc_report.py — 11 calls (lines 291, 354, 491, 693, 833, 997, 1044, 1121, 1204, 1334, 1396, 1561, 1599) — none pass write_legacy explicitly. Likely don't care about the flag; rely on the side-effect canonical-write inside persist for source_type ∈ {html,csv,json}.

tests/test_security_assessment_import.py:555 — monkeypatches the function rather than calling it; doesn't care about the flag.
```

### 4.2 Call sites of `persist_license_summary_artifact`

```
src/cvhealthcheck/license_summary/service.py:119-131 (inside collect_from_rest)
    write_legacy=False ✅

src/cvhealthcheck/license_summary/service.py:180-191 (inside import_license_summary_upload)
    write_legacy=False ✅

src/cvhealthcheck/license_summary/service.py:196 (definition)
    default write_legacy=True
```

Production passes `write_legacy=False` from both call sites. **No production caller relies on the True default.**

Test callers (default):

```
tests/test_license_summary.py:456                       — 1 call
tests/test_license_summary_web.py:32, 68, 249           — 3 calls
tests/test_quickhc_description_service.py:108           — 1 call
tests/test_quickhc_source_provenance.py:137             — 1 call
tests/test_quick_hc_report.py — 9 calls (317, 363, 703, 843, 910, 1130, 1234, 1271, 1608)
```

### 4.3 The Option A regression test

```
tests/test_security_assessment_import.py:564-602
    def test_fresh_security_assessment_import_creates_no_legacy_artifact_files()
```

What it asserts:

1. POSTs HTML_SAMPLE to `/security-assessment/import` (the development.py mirror, not the Quick HC route — but both call `import_security_assessment_upload`).
2. Asserts `200` and `"HTML import completed"` in body.
3. Asserts `list((tmp_path / "catalog").rglob("*.json")) == []` — no legacy JSON files written anywhere under the patched catalog dir.
4. Asserts `list((tmp_path / "canonical_artifacts").rglob("*.json"))` is non-empty — the canonical store received the artifact.

**Will this hold when `write_legacy` is retired and non-legacy becomes the default?** Yes, comfortably. The test exercises `import_security_assessment_upload`, which passes `write_legacy=False` explicitly today. After retirement, the call site can drop the kwarg entirely and the behavior is unchanged.

The test does NOT distinguish between "the kwarg exists and is False" and "the kwarg doesn't exist and the default is False" — it only asserts the observable outcome. So removing the kwarg cleanly is safe.

**There is no equivalent regression test for license_summary.** The Option A invariant note in HANDOVER explicitly mentions this gap: "Add the License Summary equivalent of the security-assessment regression test if you touch that import flow." Session 2 or 3 should add it.

### 4.4 Recommendation: how to retire `write_legacy`

**Two options:**

**Option α — Remove entirely.** Drop the kwarg from both function signatures. Update every test that exercised the legacy path to either (a) opt in via a new explicit `legacy_store=...` parameter that takes the legacy paths, or (b) be deleted if it was testing the legacy SQLite registry behavior (which the project has decided to deprecate).

- Pros: clean signature. No deprecation noise. Forces every test author to face the choice.
- Cons: 30+ test cases would need touching across `test_security_assessment_registry.py` and `test_quick_hc_report.py`. Many of those tests appear to be **specifically** exercising the legacy registry — they aren't generic "test the persist function" tests. Deleting them might lose coverage of registry mechanics that are still in use for legacy reads.

**Option β — Flip default to False, keep kwarg with deprecation comment.**

```python
def persist_security_assessment_artifact(
    artifact,
    *,
    write_legacy: bool = False,   # DEPRECATED: retained only for legacy-registry tests
    ...
):
```

- Pros: every production call site can drop the kwarg. Legacy-behavior tests that currently rely on the True default need only update to `write_legacy=True` explicitly. Smaller blast radius.
- Cons: leaves a deprecation tail. The kwarg sticks around indefinitely.

**My read:** Option β is the right move for session 2 or 3. The 22 test cases in `test_security_assessment_registry.py` are testing the legacy registry's behavior (scoped active-artifact selection, import-run sequencing, recovery logic) — that machinery still runs for legacy reads, so the tests still have value. Flipping the default and adding `write_legacy=True` to each call is mechanical. Option α can be done as a separate cleanup pass after the unified route is live and the legacy-registry tests have been audited for whether they're still needed.

The decision belongs to the user; both are viable.

---

## Section 5 — Test coupling map

All test references to upload URLs and the generic-import function name.

### 5.1 By URL

**`/quick-hc/security-assessment/import`** (per-subject route under Quick HC):

```
tests/test_security_assessment_import.py:407
    test_quick_hc_security_assessment_upload_imports_html_and_redirects
    URL-coupled. Just asserts 200 after follow_redirects.

tests/test_quick_hc_report.py:893
tests/test_quick_hc_report.py:894
    test_quick_hc_overview_subject_sources_have_expected_shape (or similar)
    URL-coupled — asserts importUrl string equality against this exact URL.
```

**`/security-assessment/import`** (dev page mirror — NOT in scope for this refactor):

```
tests/test_security_assessment_import.py:344, 370, 584, 610, 625, 642
    Multiple tests. All exercise the dev-page route, which is independent of
    the Quick HC upload routing. Not affected by the refactor.
```

**`/quick-hc/license-summary/import`** (per-subject route):

```
tests/test_license_summary_web.py:135
    test_quick_hc_license_summary_upload_imports_csv_and_redirects
    URL-coupled.

tests/test_license_summary_web.py:173
    test_quick_hc_license_summary_upload_rejects_unsupported_type
    URL-coupled + Route-coupled — the pre-handler suffix check at
    quick_hc.py:328 is route-only. If the unified handler relocates this
    check (e.g. into the import function), this test needs updating, not just
    a URL bump.

tests/test_quick_hc_report.py:895
tests/test_quick_hc_report.py:896
    URL-coupled — asserts importUrl string equality.
```

**`/quick-hc/import`** (generic route):

```
tests/test_recognition.py:303 (test_import_route_direct_save)
tests/test_recognition.py:321 (test_import_route_staged) — ?stage=1
tests/test_recognition.py:348 (test_import_route_unrecognized)
tests/test_recognition.py:371 (test_import_route_not_extractable)
    Route-coupled — these test the generic dispatcher's three error outcomes
    and the ?stage=1 routing, both of which are generic-route-specific behaviors.

tests/test_import_flow.py:135 (test_import_route_passes_subject_id)
    URL-coupled. Asserts ?subject_id=... is forwarded to extract_file.
```

**Direct function reference (`quick_hc_generic_import`)**:

No tests reference the function by name. Only `quick_hc.py` self-references it via `url_for("main.quick_hc_generic_import")` at lines 392 and 454 (its own redirects), and `templates/quick_hc_import.html` at lines 30 and 38.

### 5.2 By category

| Category | Count | Notes |
|---|---|---|
| URL-coupled (just URL string assertion or POST target) | 9 | trivial s/old/new updates if URL changes |
| Route-coupled (tests behavior specific to a particular handler) | 5 | the 4 in test_recognition.py exercise generic-only outcomes; `test_quick_hc_license_summary_upload_rejects_unsupported_type` exercises a SA-specific pre-handler check |
| Behavior-coupled (asserts outcome, route-agnostic) | 0 | none — every test exists in one of the two categories above |

**Total:** 14 tests reference the upload URLs.

The 5 route-coupled tests are the interesting ones for session 2:

- The 4 generic-route tests (`?stage=1`, "not recognized", "not extractable", "?subject_id=" forwarding) test mechanics that **must survive in the unified route** — staging, three-way error reporting, subject_id forwarding via path component instead of query. They will need updating but the underlying behaviors must still be exercised.
- The license_summary unsupported-type test pins the pre-handler suffix check. If session 2 moves that check into the import function (recommended for unification), this test needs to either move with it or be replaced by a unit test on the import function directly.

---

## Section 6 — Recommendation: shape of session 2

### URL pattern

The user's working assumption was `/quick-hc/import/<subject_id>`. **I counter-propose `/quick-hc/<subject_id>/import`.**

Reasons:

1. **There is already a precedent for `/quick-hc/<subject_id>/<verb>` in the codebase** — `/quick-hc/<subject_id>/collect` and `/quick-hc/<subject_id>/delete` (at `quick_hc.py:140` and `:123` respectively). Both work today and both dispatch by `subject_id` from the URL path. The unified upload route should match this pattern, not invent a new one.
2. **`/quick-hc/security-assessment/import` matches this shape**, so renaming `security-assessment` → `<subject_id>` is the most local, most easily reviewed change. Session 4 (URL deletion) becomes a trivial deletion rather than a relocation.
3. The user's proposal `/quick-hc/import/<subject_id>` reverses the convention. The route would be the only `/quick-hc/<noun>/<id>` route in the file. Workable but inconsistent.

### Handler function name

`quick_hc_subject_import(subject_id: str)` — matches `quick_hc_generic_collect(subject_id: str)` at `:142`.

### How to accommodate subject-specific behavior (Section 1's findings)

Section 1 found nine subject-specific concerns. They split into three categories:

**(A) Mechanical — can be looked up by `subjects.created_by` or by a small registry of subject-id → adapter mapping:**

- Form field name, extension whitelist, parser dispatch, persist function, exception class, imports dir, success message format, empty-result guard.

**(B) Architectural — needs a deliberate choice:**

- Canonical write timing (inside persist for SA; at caller for LS).
- Generic-route-only features (X-Inline mode, ?stage=1, recognition/extractability/extraction error reporting).

**(C) Out of scope for the route refactor:**

- The pre-handler suffix check at `license_summary` is duplicate validation — the same check exists inside `import_license_summary_upload` at `:158-163`. Remove the pre-handler version when consolidating; the import function's own check covers it.

**Proposed handler shape:**

```python
@bp.route("/quick-hc/<subject_id>/import", methods=["POST"])
def quick_hc_subject_import(subject_id: str):
    # 1. Look up subject + its created_by from the DB.
    # 2. Dispatch by created_by:
    #      "system" + subject_id == "security_assessment" → import_security_assessment_upload
    #      "system" + subject_id == "license_summary"     → import_license_summary_upload
    #      "ai" / "user"                                  → extract_file (dispatcher)
    # 3. Render the response uniformly:
    #      - X-Inline support across all branches.
    #      - ?stage=1 support across all branches (currently only generic-route).
    #      - Success / error flashes with consistent formatting.
    return redirect(...)
```

Rationale: dispatching by `created_by` is the user's stated target architecture ("System vs AI becomes a database fact only — not a code-path distinction"). The system branch can still call the existing `import_*_upload` functions verbatim — those functions encode the per-subject behavior and don't need to change in session 2. The AI branch calls `extract_file` — also unchanged.

Adding X-Inline and ?stage=1 support across **all** branches (not just the AI branch) is technically a behavior expansion. The user should decide whether session 2 should:

- **(i)** Preserve the current asymmetry — system subjects don't get X-Inline / staging, AI subjects do. Simpler. Session 2 is smaller.
- **(ii)** Promote both features to all subjects from the start. Larger, but the "unified" goal is more fully met.

My read: **(i) for session 2, (ii) as a session 3 follow-up if anyone actually wants staging on system-subject imports.** The asymmetry is preexisting; preserving it keeps the diff smaller and the behavior changes more reviewable.

### Should session 2 also unify source-building?

**No, defer to session 3.**

The frontend reads `sources[].actions[].importUrl` and POSTs to it. Today's wiring:

- `_build_generic_sources` → `/quick-hc/import?subject_id=…`
- legacy `_build_security_assessment_subject` → `/quick-hc/security-assessment/import`
- `canonical_view._build_sources` → `tile.import_url` from registry

If session 2 ships the new route at `/quick-hc/<subject_id>/import` and leaves source-building alone, **the frontend will continue to POST to the old URLs** (which still exist). The new route is exercised only by tests and by manual smoke tests. That's the right safety boundary for session 2 — both old and new work, frontend uses old, tests prove new works.

Session 3 then flips source-building over to the new URL:

- `_build_generic_sources` → `/quick-hc/{subject_id}/import` (path component, not query).
- registry `import_url` → drop the hardcoded per-subject URLs; the registry can produce `f"/quick-hc/{tile.id}/import"` if it needs to produce a URL at all.
- legacy builders' direct `_SA_IMPORT_URL` / `_LS_IMPORT_URL` → same treatment.

After session 3, the frontend POSTs to the new route exclusively. Session 4 deletes the old routes safely.

**Argument for unifying in session 2 instead:** "Easier to test the new route if there's only one source-building path feeding it." I disagree — the new route can be tested directly with synthetic POSTs (as `test_recognition.py` already does), no source-building required. Source-building is a presentation concern, not a behavior concern.

### Test count estimate

| Action | Tests added | Tests modified | Tests deleted |
|---|---|---|---|
| Build new route at `/quick-hc/<subject_id>/import` | +6 (mirror the 6 existing import tests against the new URL, dispatching SA / LS / AI) | 0 | 0 |
| Add License Summary regression test (parity with SA's no-legacy-artifact test) | +1 | 0 | 0 |
| **Session 2 total** | **+7** | **0** | **0** |
| **Expected count after session 2:** | **476** | | |

Sessions 3–5 will involve modifying / deleting the 14 tests identified in section 5 (URL-coupled gets light updates, route-coupled needs rewriting), and possibly several from section 4's legacy-registry tests depending on the `write_legacy` retirement strategy. Total final count is harder to estimate without session 3's source-building changes scoped — best guess is 470–480 at the end of session 5.

### One concern worth flagging before session 2 starts

Section 3 surfaced that `_build_generic_subject` (called when a canonical artifact exists) calls `_build_generic_sources`, which uses the generic URL. This means **in production, after any HTML/CSV import for security_assessment, the next page render produces `importUrl="/quick-hc/import?subject_id=security_assessment"`** — not the per-subject URL. The per-subject URL only fires from the legacy builder, which only runs when no canonical artifact exists.

This is a production-vs-test divergence that the existing tests do not catch. It is not a blocker for session 2 (the new route will work regardless), but the user should know about it before session 4 deletes the per-subject routes — there may be edge cases where the legacy builder path is still active (e.g. session-level test pollution, or hand-deleted canonical artifacts) where the frontend still tries the per-subject URL.

I cannot rule out the possibility without running the app and exercising a real import end-to-end. Recommend running a manual smoke test before session 4: import a Security Assessment HTML through the Quick HC sidebar, inspect the resulting `window.QUICK_HC_INITIAL_DATA.cats[*].subjects[*].sources[*].actions[*].importUrl` in the browser's JS console, confirm which URL family is actually wired up post-import.

---

*Session 1 of 5. No code changed. Report committed for user review.*
