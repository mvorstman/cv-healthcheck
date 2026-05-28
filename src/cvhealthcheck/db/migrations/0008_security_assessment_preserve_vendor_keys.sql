-- =============================================================================
-- Migration 0008: preserve SA vendor-stable identifiers in column_map
-- =============================================================================
-- Extends migration 0007's column_map for all six Security Assessment
-- sections to PRESERVE attrName and PARAMID — Commvault's stable
-- identifiers for the finding — instead of dropping them as 0007 did.
--
-- Background
-- ----------
-- Migration 0007 (ADR 0003 phase 4) introduced column_map that renamed
-- Parameter/Status/Remarks/Action to canonical lowercase keys and dropped
-- everything else. The ADR 0004 survey surfaced that two vendor-stable
-- identifiers were being lost in that drop:
--
--   - attrName  -- text identifier, stable across releases
--                  (e.g. "2FAEnabled", "cleanupReport", "SecureMountPaths-Secure")
--   - PARAMID   -- numeric identifier, also stable
--                  (e.g. 25018, 2509, 25013, 25031, 2501, 25015)
--
-- Without these, rule overrides under ADR 0004's evaluative face have
-- nothing stable to match against — Commvault could rename the
-- human-readable Parameter label ("Two-factor authentication" →
-- "Two-Factor Authentication (2FA)") and any rule keyed on that label
-- would silently stop firing.
--
-- Per-row layout after this migration's column_map:
--   parameter   <- Parameter
--   status      <- Status
--   remarks     <- Remarks
--   action      <- Action
--   vendor_key  <- attrName      (NEW)
--   vendor_id   <- PARAMID       (NEW)
--
-- The Finding model gained vendor_key + vendor_id slots in the same
-- session. result_to_artifact._build_finding populates them from the
-- row dict; existing artifacts without those keys validate cleanly
-- because both fields default to None.
--
-- Other dropped raw columns (Data Source, ccid, sys_rowid, GROUP) are
-- intentionally still dropped:
--   - Data Source  : CommCell hostname — already on ArtifactSource
--   - ccid         : CommCell numeric id — already on ArtifactSource
--   - sys_rowid    : per-response row order, volatile across collections
--   - GROUP        : duplicates section_id
--
-- Idempotency
-- -----------
-- This migration UPDATEs the extraction_instructions JSON for each of the
-- six (security_assessment, rest, section_id) rows. The UPDATE replaces
-- the column_map portion only; report_id, dataset_name, dataset_guid,
-- status_to_severity, and output_as are preserved verbatim. Re-running
-- the migration is idempotent because the json() rebuild is deterministic.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Access Security
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Access Security",'
    || '"dataset_guid":"7bdc4b02-a846-431e-8f16-9e567c81cdc6",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.access_security'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );


-- -----------------------------------------------------------------------------
-- 2. Auditing
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Auditing",'
    || '"dataset_guid":"66cee133-ab35-46f8-e5b6-fb00937f3f76",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.auditing'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );


-- -----------------------------------------------------------------------------
-- 3. Platform Security
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Platform Security",'
    || '"dataset_guid":"673c6dbe-edaf-4fa7-bf81-50bfe693e24f",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.platform_security'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );


-- -----------------------------------------------------------------------------
-- 4. Company and Owners Security
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Company and Owners Security",'
    || '"dataset_guid":"f67af316-2aff-413c-d62f-c936e6c8cd65",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.company_and_owners_security'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );


-- -----------------------------------------------------------------------------
-- 5. Capabilities
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Capabilities",'
    || '"dataset_guid":"06a5b275-5cd8-40ba-a43a-0a7c3a737ac9",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.capabilities'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );


-- -----------------------------------------------------------------------------
-- 6. Hardening
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Hardening",'
    || '"dataset_guid":"6b274ec2-6f4b-4871-c1d6-defb7ea90649",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"},'
    ||   '{"source":"attrName","canonical":"vendor_key","type":"string"},'
    ||   '{"source":"PARAMID","canonical":"vendor_id","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
WHERE section_id = 'security_assessment.hardening'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'security_assessment' AND source_type = 'rest'
  );
