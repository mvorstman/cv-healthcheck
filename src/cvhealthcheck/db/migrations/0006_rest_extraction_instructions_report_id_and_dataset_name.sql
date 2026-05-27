-- =============================================================================
-- Migration 0006: REST extraction_instructions gains report_id + dataset_name
-- =============================================================================
-- Phase 1 of ADR 0003 (REST extractor with credentials).
-- See: docs/adr/0003-rest-extractor-with-credentials.md
--
-- ADR 0003 makes report_id + dataset_name the canonical reference for REST
-- collection, replacing the catalog-stored dataset_guid. Dataset GUIDs are
-- CommCell-scoped and will be resolved at runtime from the reportBuilder.do
-- response in phase 2. dataset_guid stays in the JSON for now as an optional
-- cache hint — not authoritative, not relied on.
--
-- Three existing REST rows are backfilled:
--
--   subject.section_id              | report_id | dataset_name
--   --------------------------------|-----------|---------------------------
--   client_growth.monthly_table     | "318"     | "Client Count"
--   capacity_license.table          | "318"     | "Capacity License Usage"
--   backup_job_summary.recent_jobs  | "194"     | "Job details"
--
-- One bug is also corrected in this migration:
--
--   backup_job_summary.recent_jobs's stored "dataset_guid" was 2638c3d3-...,
--   which is actually the REPORT-level GUID for report 194 — not a dataset
--   GUID. Migration 0004 stored the wrong identifier. The real dataset is
--   "Job details" with GUID a30bd278-c7d9-470f-9ae9-8b4922743330; this
--   migration corrects the stored value. Justification for fixing it here:
--   the migration is already touching this row's JSON, leaving a known-wrong
--   cache hint in place could mask bugs in phase 2's runtime resolution. The
--   scope expansion is tight (one field on one row).
--
-- This migration does NOT:
--   - Introduce output_as: "card" support (no existing row is card-shaped;
--     phase 4/5 seed SA and LS, which is where "card" first appears).
--   - Add a DB constraint enforcing "all REST sections in a subject share
--     the same report_id" — that's a phase 2 runtime check (see ADR 0003
--     "Open questions"). Implementing it in SQLite would require a TRIGGER
--     that JOINs across rows; the runtime check is clearer and easier to
--     debug.
--   - Touch any row other than the three listed.
--   - Modify dataset_guid for client_growth or capacity_license — their
--     stored values are real dataset GUIDs verified against
--     data/catalog/reportsplus/report_318_dataset_map.json.
--
-- Idempotency
-- -----------
-- Row-level idempotent via guard clauses. Each UPDATE filters on a field
-- that the first run sets (report_id) or changes (the wrong dataset_guid),
-- so a second execution matches zero rows and produces no writes. This is
-- in addition to the migration runner's own schema_migrations guard which
-- normally prevents re-execution.
--
-- The choice of json_set + guard (rather than rewriting each row's whole
-- JSON via json_object) preserves any unrelated keys the rows currently
-- carry (e.g. capacity_license's "note" field, client_growth's
-- timestamp_fields). json_set with the same value yields identical JSON,
-- but the guards make the no-op explicit and avoid touching updated_at on
-- a re-run.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. client_growth.monthly_table — backfill report_id + dataset_name.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_set(
        extraction_instructions,
        '$.report_id',    '318',
        '$.dataset_name', 'Client Count'
    ),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE section_id = 'client_growth.monthly_table'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'client_growth' AND source_type = 'rest'
  )
  AND json_extract(extraction_instructions, '$.report_id') IS NULL;


-- -----------------------------------------------------------------------------
-- 2. capacity_license.table — backfill report_id + dataset_name.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_set(
        extraction_instructions,
        '$.report_id',    '318',
        '$.dataset_name', 'Capacity License Usage'
    ),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE section_id = 'capacity_license.table'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'capacity_license' AND source_type = 'rest'
  )
  AND json_extract(extraction_instructions, '$.report_id') IS NULL;


-- -----------------------------------------------------------------------------
-- 3. backup_job_summary.recent_jobs — backfill report_id + dataset_name,
--    and correct the wrong-GUID dataset_guid.
--
-- Guard: matches only when dataset_guid is still the old report-level GUID
-- (2638c3d3-...). On a second run, the value is a30bd278-... and the WHERE
-- clause excludes the row. report_id-IS-NULL is also implied by the
-- guard since the first run also sets it.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_set(
        extraction_instructions,
        '$.report_id',    '194',
        '$.dataset_name', 'Job details',
        '$.dataset_guid', 'a30bd278-c7d9-470f-9ae9-8b4922743330'
    ),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE section_id = 'backup_job_summary.recent_jobs'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'backup_job_summary' AND source_type = 'rest'
  )
  AND json_extract(extraction_instructions, '$.dataset_guid')
        = '2638c3d3-adc7-4b61-bb24-2ba509229bf5';
