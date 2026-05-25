# Session 5a — Design proposal for data-driven dispatch

**Date:** 2026-05-26
**Branch:** `feature/basic-healthcheck-report-output`
**Status:** Proposal. Session 5b will implement whatever the user picks.
**Tests at start of session:** 472 passing. No code changes this session.

---

## Summary

The "dispatch smell" in `quick_hc_subject_import` is smaller than the FIXME tags imply. The handler branches on `(created_by, subject_id)` and calls one of three helpers. The only **true subject-specific** facts in the dispatch are: which form field the upload uses, which import function to call, and how to format the success flash. Everything else (extension whitelist, error-class catch-block, redirect target, persist-function-signature differences) is encapsulated inside the existing `import_security_assessment_upload` / `import_license_summary_upload` functions. **A small Python lookup table — a `dict[str, dict]` keyed by subject_id — is sufficient for session 5b. No schema migration, no new column, no MCP-tool contract change.** The "data-driven dispatch" framing was right; "data in the database" was an over-correction. Estimated session 5b: one session, +2 tests added, +1 modified, ~0 deleted, final count ≈ 475.

If the user wants the data to live in the database anyway (to enable future AI subjects with custom upload behavior without code changes), Option β (typed columns on `subjects`) is the next-cheapest after the lookup-table approach. Options α (JSON column) and γ (separate table) are over-engineered for the current set of two subject-specific handlers.

---

## Section 1 — What the dispatch actually does today

### The three FIXME sites

**Site 1** — `src/cvhealthcheck/web/routes/quick_hc.py:357-366`. The header FIXME explaining the smell:

```python
# FIXME(refactor-unified-upload-session-5): branch dispatch by
# subjects.created_by + sub-branch by subject_id is a deliberate
# migration shim. The two system subjects with upload paths are
# hard-coded here so session 2 can ship a small, obvious diff
# without committing to a data-model decision. Session 5/6 will
# replace this with data-driven dispatch — likely a new column on
# `subjects` describing import behavior (form-field name, allowed
# extensions, success-message format, persist function, etc.).
# Do not refactor this into a registry/plugin system in the
# meantime — the point of the FIXME is to defer that choice.
```

**Sites 2 and 3** — `quick_hc.py:370` and `:373`. The two hard-coded sub-branches:

```python
if created_by == "system":
    # FIXME(refactor-unified-upload-session-5): hard-coded subject IDs.
    if subject_id == "security_assessment":
        return _unified_security_assessment_upload()
    # FIXME(refactor-unified-upload-session-5): hard-coded subject IDs.
    if subject_id == "license_summary":
        return _unified_license_summary_upload()
    # The other four system subjects (environment, client_growth,
    # capacity_license, backup_job_summary) are REST/metrics-only.
    return ("Subject does not support uploads.", 404)

# 'ai', 'user', or any other created_by → dispatcher branch.
return _unified_dispatcher_upload(subject_id)
```

### What each branch does

**`_unified_security_assessment_upload`** (`quick_hc.py:384-413`):

1. Reads `request.files.get("assessment_file")`. **Form field: `assessment_file`.**
2. Empty-filename: flash + redirect to `main.quick_hc_security_assessment`.
3. Calls `import_security_assessment_upload(upload.stream, original_filename=filename)`. **Persist function with this exact signature.**
4. Catches `SecurityAssessmentImportError` → flash the message. **Subject-specific error class.**
5. Catches generic `Exception` → flash `f"Security Assessment import failed: {exc}"`. **Subject-specific prefix in error text.**
6. On success: flash `f"{source_type} import completed for {source_file} with {finding_count} findings."`. **Subject-specific success-message format counting `finding_count`.**
7. Always redirects to `main.quick_hc_security_assessment` (which itself redirects to `main.quick_hc`).

**`_unified_license_summary_upload`** (`quick_hc.py:416-450`):

1. Reads `request.files.get("license_summary_file")`. **Form field: `license_summary_file`.**
2. Empty-filename: flash + redirect to `main.quick_hc_license_summary`.
3. **Extra step**: validates `Path(filename).suffix.lower()` against `LICENSE_SUMMARY_UPLOAD_EXTENSIONS` from `web/routes/shared.py:71` (`{".csv", ".htm", ".html"}`). On reject: flash `"Unsupported file type. Upload a License Summary CSV or HTML export."`. **NOT a behavior the SA branch shares.**
4. Calls `import_license_summary_upload(upload.stream, original_filename=filename)`. **Persist function with the same signature shape as SA.**
5. Catches `LicenseSummaryImportError` → flash the message. **Subject-specific error class.**
6. Catches generic `Exception` → flash `f"License Summary import failed: {exc}"`.
7. On success: flash `f"{source_type} import completed for {source_file} with {other_count} other licenses and {agent_count} agent/feature licenses."`. **Subject-specific success-message format counting two row buckets.**
8. Always redirects to `main.quick_hc_license_summary` (also redirects to `main.quick_hc`).

**`_unified_dispatcher_upload`** (`quick_hc.py:453-537`):

1. Reads `X-Inline: 1` header → inline mode.
2. Reads `request.files.get("file")`. **Form field: `file`.**
3. Empty-filename: JSON 400 if inline, else flash + redirect to `main.quick_hc`.
4. Saves upload to `tempfile.NamedTemporaryFile`.
5. Calls `extract_file(tmp_path, db, subject_id=subject_id)`. **Different code path — dispatcher rather than persist function.**
6. Three error branches: `not recognized`, `not extractable`, `extraction_errors` — each renders a JSON 422 in inline mode or a flash.
7. `?stage=1` query routes the artifact to `_staging_db.create_staged_artifact(...)`; otherwise `ArtifactStore().save_artifact(artifact)`.
8. Always redirects to `main.quick_hc`.

### The contract table

This is the contract the data-driven dispatch must preserve.

| `(created_by, subject_id)` | Form field | Pre-check | Import call | Error class | Generic-error flash prefix | Success flash format | Redirect endpoint |
|---|---|---|---|---|---|---|---|
| `system, security_assessment` | `assessment_file` | none | `import_security_assessment_upload(stream, original_filename=fn)` | `SecurityAssessmentImportError` | `"Security Assessment import failed: "` | `"{source_type} import completed for {source_file} with {finding_count} findings."` | `main.quick_hc_security_assessment` |
| `system, license_summary` | `license_summary_file` | suffix in `{.csv, .htm, .html}` | `import_license_summary_upload(stream, original_filename=fn)` | `LicenseSummaryImportError` | `"License Summary import failed: "` | `"{source_type} import completed for {source_file} with {other_count} other licenses and {agent_count} agent/feature licenses."` | `main.quick_hc_license_summary` |
| `system, environment` | — | — | — | — | — | — | 404 |
| `system, client_growth` | — | — | — | — | — | — | 404 |
| `system, capacity_license` | — | — | — | — | — | — | 404 |
| `system, backup_job_summary` | — | — | — | — | — | — | 404 |
| `ai, *` and `user, *` | `file` | none (handled by `extract_file`) | `extract_file(tmp, db, subject_id=…)` + `ArtifactStore().save_artifact()` or `_staging_db.create_staged_artifact()` | none (generic `Exception` only) | `"Import failed: "` | `"Imported {title} successfully."` / `"Imported {title} — review in staging before approving."` | `main.quick_hc` |

**Notable observations:**

- The SA and LS rows have identical structural shape (form field + import function + error class + flash format + redirect). They differ only in the values inside that shape. **The two subject-specific helpers are duplicated structure with different constants.**
- The AI/user row is a different shape entirely: dispatcher instead of persist function, `extract_file` rather than `import_*_upload`, X-Inline and ?stage=1 modes that the SA/LS branches don't support. **The AI branch is genuinely different code; the SA/LS branches are structural duplicates.**
- The "no upload route" branch for the four system subjects (environment, client_growth, capacity_license, backup_job_summary) is just a 404. It's currently implicit — there's no per-subject row in any data structure that says "doesn't support uploads"; the dispatch falls through to the catch-all return because the subject_id matches neither `security_assessment` nor `license_summary`.

---

## Section 2 — What information the new dispatch needs

From Section 1's contract table, the SA and LS branches differ in five values:

| Field | SA value | LS value | Origin |
|---|---|---|---|
| `form_field` | `"assessment_file"` | `"license_summary_file"` | Inline string in the helper |
| `allowed_extensions` | none (the helper doesn't pre-check) | `{".csv", ".htm", ".html"}` | `LICENSE_SUMMARY_UPLOAD_EXTENSIONS` constant from `shared.py:71` |
| `import_fn` | `import_security_assessment_upload` | `import_license_summary_upload` | Imported into the route module |
| `error_class` | `SecurityAssessmentImportError` | `LicenseSummaryImportError` | Imported into the route module |
| `success_format` | template referencing `source_type`, `source_file`, `finding_count` | template referencing `source_type`, `source_file`, `other_count`, `agent_count` | Inline f-string |
| `redirect_endpoint` | `"main.quick_hc_security_assessment"` | `"main.quick_hc_license_summary"` | Inline string |

The success-format value is the most subject-specific because the field names it references (`finding_count` vs `other_count`/`agent_count`) live in the persist function's output and differ between subjects. Two ways to handle it:

- **Pre-compute summary counts in the dispatch** — the dispatch reads named fields from the persisted payload and passes them to a generic template. Forces a contract on what the persist functions return.
- **Subject-specific format function** — the dispatch holds a callable per subject that takes the persisted artifact and returns the success message text. More flexible; keeps the persist functions free.

### Candidate data dimensions, evaluated

| Candidate | Used by current dispatch? | Values across 8 subjects | Could be derived? |
|---|---|---|---|
| Form field name | Yes | `assessment_file`, `license_summary_file`, `file` | Could be derived from `(created_by, subject_id)`. AI uses `file`; system uses subject-specific. The default for AI subjects = `file`. |
| Allowed extensions | Yes (LS only — SA delegates to the importer's own check) | `{.csv, .htm, .html}` (LS); none (SA, AI) | The importers already do this check internally. The route's pre-check is **defensive duplication** for LS. Could be removed without a behavior change for SA-equivalent flow, but the LS error message ("Unsupported file type. Upload a License Summary CSV or HTML export.") is route-side and would need to come from the importer if removed. |
| Persist function reference | Yes | `import_security_assessment_upload`, `import_license_summary_upload`, `extract_file` (with downstream `save_artifact` or staging) | The system-subject set is small and stable. The AI-subject set always uses the dispatcher. A two-element lookup table keyed by `subject_id` covers SA and LS; AI is the default. |
| Error class | Yes | `SecurityAssessmentImportError`, `LicenseSummaryImportError`, `Exception` (AI) | Tied to the persist function. If the lookup table holds the persist function, it can also hold its specific exception class for nicer messages. |
| Success-flash template | Yes | Subject-specific f-string with subject-specific fields | Tied to the persist function's output shape. Most subject-specific value in the table. |
| Redirect endpoint | Yes | `main.quick_hc_security_assessment`, `main.quick_hc_license_summary`, `main.quick_hc` (AI) | Two of the three are subject-specific. The two SA/LS endpoints both immediately redirect to `main.quick_hc` (verified by reading `quick_hc.py:231-233` and `:268-270`), so changing them all to `main.quick_hc` would have an observable HTTP-302 chain change (one redirect instead of two) but no user-visible behavior change. The session-2 docstring on `_unified_security_assessment_upload` notes this. **Could be unified to `main.quick_hc` for all branches.** |
| Supports staging (`?stage=1`) | Yes (AI only) | True for AI, False for system | Can be derived from `created_by == "ai"`. Currently the system branches don't expose ?stage=1; preserving that. |
| Supports inline JSON (X-Inline) | Yes (AI only) | Same pattern | Same answer — derive from `created_by`. |

### What the dispatch genuinely needs

After this analysis, the smallest set of facts the dispatch genuinely needs to know per system subject is:

- The form field name.
- The persist function reference (and its associated error class).
- The success-flash template + the fields it references in the persist function's return value.

That's **three fields per system subject**. The other "candidates" (extensions, redirect endpoint, supports-staging, supports-inline) can either be derived from `created_by` or absorbed into the persist function's responsibility.

The dispatch never needs `created_by` for anything except "is this an AI subject? then use the dispatcher path." The hard-coded sub-branch can be replaced by a lookup: "do we have an entry in the system-subject upload table?" If yes, use it; if no and the subject is `created_by='system'`, return 404; if no and `created_by` is AI/user/other, use the dispatcher.

---

## Section 3 — Data model alternatives

### Option α — Single JSON column on `subjects`

```sql
ALTER TABLE subjects ADD COLUMN upload_config TEXT;  -- JSON, nullable
```

Each row's `upload_config` is a JSON string (Python dict) with the three fields:

```json
{
  "form_field": "assessment_file",
  "import_fn": "cvhealthcheck.security_assessment.service:import_security_assessment_upload",
  "success_format": "{source_type} import completed for {source_file} with {finding_count} findings."
}
```

Dispatch reads the JSON and looks up the function by import path.

**Pros:** No schema change for future extensions (e.g. if a third subject needs a different field). Stores everything in one place.

**Cons:** Function references by string path are fragile (renames break silently until run). JSON inside SQLite is opaque to query tools. Validation requires custom Python code. Migration for the two existing system subjects is a one-time INSERT, but every new AI subject needs `upload_config = NULL` (which means "use dispatcher") — and `propose_new_subject` needs to set NULL by default or accept the field as a parameter.

**Verdict:** Over-engineered for two subjects with three fields each.

### Option β — Typed columns on `subjects`

```sql
ALTER TABLE subjects ADD COLUMN upload_form_field TEXT;
ALTER TABLE subjects ADD COLUMN upload_import_fn TEXT;
ALTER TABLE subjects ADD COLUMN upload_success_format TEXT;
```

Each system subject with an upload path gets these three columns populated. Dispatch reads three columns from the row.

**Pros:** Queryable (`SELECT subject_id FROM subjects WHERE upload_form_field IS NOT NULL`). Easier to validate (NOT NULL constraints possible). Schema-level documentation of each field's purpose.

**Cons:** Three migrations for three fields. `upload_import_fn` is still a string-encoded callable reference. Each new dispatch dimension is another column. Adds three NULL-able columns to a table where only 2 of 8 rows use them.

**Verdict:** Cleaner than α but still string-encoded callable references. Worth it only if querying by these fields becomes valuable.

### Option γ — Separate table

```sql
CREATE TABLE subject_upload_configs (
    subject_id TEXT PRIMARY KEY REFERENCES subjects(subject_id),
    form_field TEXT NOT NULL,
    import_fn TEXT NOT NULL,
    success_format TEXT NOT NULL
);
```

Only the two SA/LS rows exist in this table. AI subjects have no row → dispatch falls back to the dispatcher path.

**Pros:** Cleanest separation. Easy to query "which subjects support custom uploads." NOT NULL constraints on every field. Adding a new dispatch dimension is a new column on a small table, not the main subjects table.

**Cons:** Adds a join (or a second SELECT) to the dispatch. Migration adds a table for two rows. Still string-encoded callable references.

**Verdict:** Architecturally cleanest if we believe more system subjects will get upload behavior. Today we have two. Probably the right move at scale; over-engineered now.

### Option δ — Python lookup table (no schema change at all)

```python
# In src/cvhealthcheck/web/routes/quick_hc.py (or a sibling module).
@dataclass(frozen=True)
class _UploadHandler:
    form_field: str
    import_fn: Callable[[Any, str], dict]
    error_class: type[Exception]
    success_format: Callable[[dict], str]  # takes the persisted dict, returns the flash text
    redirect_endpoint: str

_SYSTEM_UPLOAD_HANDLERS: dict[str, _UploadHandler] = {
    "security_assessment": _UploadHandler(
        form_field="assessment_file",
        import_fn=import_security_assessment_upload,
        error_class=SecurityAssessmentImportError,
        success_format=lambda art: (
            f"{str(art.get('source_type') or 'unknown').upper()} import completed "
            f"for {art.get('source_file')} with {int(art.get('finding_count') or 0)} findings."
        ),
        redirect_endpoint="main.quick_hc_security_assessment",
    ),
    "license_summary": _UploadHandler(
        form_field="license_summary_file",
        import_fn=import_license_summary_upload,
        error_class=LicenseSummaryImportError,
        success_format=lambda art: (
            f"{str(art.get('source_type') or 'unknown').upper()} import completed "
            f"for {art.get('source_file')} with "
            f"{len(art.get('other_licenses') or [])} other licenses and "
            f"{len(art.get('agent_feature_licenses') or [])} agent/feature licenses."
        ),
        redirect_endpoint="main.quick_hc_license_summary",
    ),
}
```

The dispatch becomes:

```python
def quick_hc_subject_import(subject_id: str):
    db = get_db()
    try:
        subject = get_subject(db, subject_id)
    finally:
        db.close()
    if subject is None:
        return ("Unknown subject.", 404)

    handler = _SYSTEM_UPLOAD_HANDLERS.get(subject_id)
    if handler is not None:
        return _handle_system_upload(handler)
    if (subject.get("created_by") or "ai") == "system":
        return ("Subject does not support uploads.", 404)
    return _unified_dispatcher_upload(subject_id)


def _handle_system_upload(handler: _UploadHandler):
    upload = request.files.get(handler.form_field)
    filename = (upload.filename if upload else "") or ""
    if not filename:
        flash("No file selected.", "error")
        return redirect(url_for(handler.redirect_endpoint))
    try:
        artifact = handler.import_fn(upload.stream, original_filename=filename)
    except handler.error_class as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"Import failed: {exc}", "error")
    else:
        flash(handler.success_format(artifact), "success")
    return redirect(url_for(handler.redirect_endpoint))
```

**Pros:**
- No schema change.
- No migration to write.
- No JSON-string-encoded callable references — `handler.import_fn` is a real Python callable, caught at import time if renamed.
- No `propose_new_subject` contract change — AI subjects fall through to the dispatcher branch as today, no config field needed.
- The "subject does not support uploads" 404 for environment/client_growth/capacity_license/backup_job_summary stays implicit (no entry in `_SYSTEM_UPLOAD_HANDLERS`).
- `_unified_security_assessment_upload` and `_unified_license_summary_upload` collapse into one `_handle_system_upload` function.
- Generic-error flash prefix can be normalised ("Import failed: " for all) without UX regression — the persist function's own error class already provides subject-specific messages via `str(exc)`.

**Cons:**
- The data lives in code, not in the database. A future AI-proposed subject can't override `form_field` from a CLI tool — would need a code change.
- Doesn't satisfy the literal text of the FIXME tag ("likely a new column on `subjects` describing import behavior").

**Verdict:** The smallest change that resolves the smell. The FIXME-tag text was suggestive ("likely a new column"), not prescriptive. The actual problem the tag flagged — subject-specific branching in route-handler code — is fully resolved by Option δ.

### Recommendation

**Option δ.** The two subject-specific helpers are duplicates of one structure with different constants; a single handler function reading from a typed dict resolves both the duplication and the dispatch branching in one move. No schema migration, no MCP-tool change, no AI-subject default question, no string-encoded callable references.

If the user wants the data in the database anyway (because future AI subjects with custom upload behavior need to override these fields without code changes — which is a real future need, just not today's), **Option β is the natural next step** when that motivation actually arrives. δ → β is a one-session migration when needed; α and γ are not on the path.

---

## Section 4 — Interaction with ADR 0001

ADR 0001 retains the source-building fork: six system subjects with legacy-shape tile data go through `_legacy_builders`; everything else goes through `_build_generic_subject`.

**Empirical check** — the two sets:

| Set | Members |
|---|---|
| Has upload behavior (this session's dispatch) | `security_assessment`, `license_summary` |
| Has source-building fork (ADR 0001's `_legacy_builders`) | `environment`, `security_assessment`, `license_summary`, `client_growth`, `capacity_license`, `backup_job_summary` |

**The upload-behavior set is a strict subset of the source-building-fork set.** The four source-building-special subjects without upload behavior (environment, client_growth, capacity_license, backup_job_summary) are REST/metrics-only.

**Question:** Should the data model treat these as related or independent?

Walking through what would go wrong if unified:

- If we had a single `subjects.legacy_handler` column or similar, it would have to express two unrelated facts about each row: "does this have legacy-shape source-building" AND "does this have an upload handler." For environment/client_growth/capacity_license/backup_job_summary the answer is (yes, no); for SA/LS it's (yes, yes); for AI subjects it's (no, no — they use the generic path for both source-building and uploads).
- A unified column would force a 2×2 matrix where 3 of 4 cells are populated. That doesn't simplify anything; it just adds a layer of indirection.
- The source-building fork is intentionally code per ADR 0001 — moving it into data would re-open the question that ADR 0001 closed. The fork exists because the canonical schema can't represent legacy view shapes; moving the fork into data doesn't change that, it just moves where the fork is encoded.

**Recommendation:** Treat them as independent concerns. The upload dispatch is the only one in scope for session 5b. ADR 0001's source-building fork stays as code. The `_SYSTEM_UPLOAD_HANDLERS` dict from Option δ contains only upload information; it makes no claim about source-building.

---

## Section 5 — AI-proposal workflow integration

`propose_new_subject` at `src/cvhealthcheck/mcp/server.py:298-378` accepts a JSON proposal describing a new subject (subject_id, title, category, sections, extraction_instructions, etc.), inserts it into `staged_artifacts` with `artifact_type='subject_proposal'`. The proposal is reviewed via the staging UI; once approved, `create_subject_from_proposal` in `db/subjects.py` writes it to the `subjects` table.

**Under Option δ:** `propose_new_subject`'s contract does not change. AI-proposed subjects don't have an entry in `_SYSTEM_UPLOAD_HANDLERS`, so they fall through to `_unified_dispatcher_upload` automatically — exactly the behavior `cloud_storage_egress_ingress` and `storage_utilization` have today. The dispatcher uses the file's recognition hints (from `extraction_instructions` in the proposal) to identify what to extract; the upload contract is uniform across all AI subjects.

If a future AI subject genuinely needed a custom form-field name, error class, or success-message format, **that's the motivation to migrate from δ to β**. Today there is no such subject; the AI flow is uniform.

**Under Option α/β/γ:** `propose_new_subject` would need to either accept upload-config parameters or set NULL defaults. The simplest contract: `upload_config = NULL` (or equivalent) means "use the dispatcher path," which is what every AI subject wants. The MCP tool can default to NULL without exposing a new parameter, so end users never see the field. The staging UI never needs to surface it either, because "NULL" is the answer 100% of the time for AI proposals.

**Verdict:** Either way (δ or α/β/γ), the AI workflow doesn't break. δ has the smallest contract — no fields touched at all in the proposal flow.

---

## Section 6 — Migration story

### Under Option δ (recommended)

**No migration.** The data lives in the `_SYSTEM_UPLOAD_HANDLERS` Python dict. The existing 8 subjects' upload behavior is derived at runtime by looking up `subject_id` in the dict. Rollback is `git revert`.

### Under Option α (JSON column)

```sql
ALTER TABLE subjects ADD COLUMN upload_config TEXT;
UPDATE subjects SET upload_config = '{"form_field":"assessment_file","import_fn":"cvhealthcheck.security_assessment.service:import_security_assessment_upload","success_format":"…"}' WHERE subject_id='security_assessment';
UPDATE subjects SET upload_config = '{"form_field":"license_summary_file",…}' WHERE subject_id='license_summary';
```

Existing migration framework at `src/cvhealthcheck/db/migrations/__init__.py` runs `.sql` files in lexicographic order from `src/cvhealthcheck/db/migrations/`. Migration `0005_subject_upload_config.sql` would fit the existing pattern. Idempotent re-run: `ALTER TABLE` is not idempotent in SQLite, but the migration framework tracks `schema_migrations` so each file runs once.

Rollback: a `0006_revert_subject_upload_config.sql` migration that drops the column. SQLite doesn't support `DROP COLUMN` natively until 3.35; if the project supports older SQLite, drop column requires recreate-table-and-copy.

### Under Option β (typed columns)

Same shape as α but three columns. Three `ALTER TABLE` statements. Rollback same caveat as α.

### Under Option γ (separate table)

```sql
CREATE TABLE subject_upload_configs (
    subject_id TEXT PRIMARY KEY REFERENCES subjects(subject_id),
    form_field TEXT NOT NULL,
    import_fn TEXT NOT NULL,
    success_format TEXT NOT NULL
);
INSERT INTO subject_upload_configs VALUES ('security_assessment', 'assessment_file', '…', '…');
INSERT INTO subject_upload_configs VALUES ('license_summary', 'license_summary_file', '…', '…');
```

Idempotent re-run is clean (the migration framework tracks applied files). Rollback: drop the table.

### Recommendation

**Under δ, no migration. Under α/β/γ, the migration pattern is straightforward and matches existing 0003/0004 file structure.** The "is this idempotent?" question is answered by the migration framework (each file runs exactly once), so a partially-populated database isn't a concern.

---

## Section 7 — Recommendation: shape of session 5b

### Concrete proposal

- **Data model: Option δ** (Python lookup table). No schema migration, no new column.
- **Where the table lives:** `src/cvhealthcheck/web/routes/quick_hc.py` next to the dispatch handler. If the file feels crowded, extract to `src/cvhealthcheck/web/routes/_upload_handlers.py` and import. The table is route-layer concern; doesn't belong in `quickhc/` or anywhere shared.
- **What it contains:** the `_UploadHandler` dataclass with five fields (`form_field`, `import_fn`, `error_class`, `success_format`, `redirect_endpoint`), one entry per system subject with upload behavior. Today's set: SA and LS.
- **The dispatch handler:** `quick_hc_subject_import` collapses to ~12 lines (lookup in `_SYSTEM_UPLOAD_HANDLERS`, dispatch to `_handle_system_upload` or `_unified_dispatcher_upload` accordingly). The three FIXME tags are removed.
- **The helpers:** `_unified_security_assessment_upload` and `_unified_license_summary_upload` are deleted. `_handle_system_upload` (single function taking an `_UploadHandler`) replaces them. `_unified_dispatcher_upload` stays as-is.
- **`propose_new_subject` contract:** unchanged.
- **Migration:** none.

### Estimated test count delta

| Change | Tests added | Modified | Deleted |
|---|---|---|---|
| New unit test on `_handle_system_upload` with each `_SYSTEM_UPLOAD_HANDLERS` entry (parametrised) | +1 (covers SA and LS via parametrisation) | 0 | 0 |
| New unit test confirming unknown subject_ids fall through correctly (already covered by existing `test_unified_route_returns_404_for_unknown_subject`?) | 0 (covered) | 0 | 0 |
| New unit test confirming AI/user subjects route to `_unified_dispatcher_upload` (covered by existing parity tests) | 0 (covered) | 0 | 0 |
| Existing SA/LS upload tests in `test_unified_upload_route.py` | 0 added | 1 modified (assert flow goes through `_handle_system_upload`, or simply unchanged if internals are opaque) | 0 |
| New test for "system subject with no upload handler returns 404" — covered by existing `test_unified_route_returns_404_for_system_subject_without_upload`? | 0 (covered) | 0 | 0 |
| Snapshot test | 0 added | 0 (no change to source-building) | 0 |

**Expected count after session 5b: 472 + 1 = 473.** Possibly +0 if the existing parametrised parity tests already cover both handlers and no new dispatch failure modes are introduced. Modest delta either way.

### Estimated session 5b size

**One session.** The change is:
- Define `_UploadHandler` dataclass (10 lines).
- Define `_SYSTEM_UPLOAD_HANDLERS` dict with 2 entries (~20 lines).
- Define `_handle_system_upload` function (~25 lines).
- Rewrite `quick_hc_subject_import` body (~12 lines).
- Delete `_unified_security_assessment_upload` and `_unified_license_summary_upload`.
- Remove the 3 FIXME tags.
- Add the parametrised test for `_handle_system_upload`.
- Update docstrings.
- Run snapshot + full test suite.

No migration, no schema change, no MCP-tool change. A short session.

### What session 5b should NOT do

- Touch ADR 0001's source-building fork. The upload-dispatch refactor is orthogonal.
- Touch `_unified_dispatcher_upload`. The AI/user branch is correct as-is.
- Reduce or change the persist-function call sites for SA and LS. The route just calls them via the handler dict; the persist functions themselves are unchanged.
- Add to or modify the canonical schema. Schema is frozen.

---

*Session 5a. Investigation only. Final test count 472, unchanged.*
