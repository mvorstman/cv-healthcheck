-- =============================================================================
-- Migration 0007: Security Assessment REST section instructions (ADR 0003 phase 4)
-- =============================================================================
-- Seeds subject_section_sources rows for the six Security Assessment topic
-- sections under the existing security_assessment.rest source. This wires
-- the generic catalog-driven RESTExtractor up to collect SA via report 336.
--
-- Spec: docs/adr/0003-rest-extractor-with-credentials.md (Migration section).
--
-- Background
-- ----------
-- The `subject_sources` row for security_assessment/rest already exists
-- (seeded by migration 0003). Migration 0007 only adds the per-section
-- extraction_instructions linking each of the six SA topic sections to
-- that REST source.
--
-- The six datasets on report 336 are findings-shaped: every row carries
-- a Parameter (the finding's name), a Status (Commvault's status code
-- like "1_Good"/"2_Info"/"3_Warning"/"4_Critical"), Remarks (description,
-- sometimes with embedded HTML), and Action (recommendation text, often
-- with an embedded <a> documentation link).
--
-- column_map renames the raw response columns to the canonical keys
-- (parameter/status/remarks/action) result_to_artifact's findings path
-- expects. status_to_severity maps the prefixed status codes to the
-- four canonical severity strings. The extractor's findings post-
-- processing strips embedded HTML from string values so the workspace
-- renders plain text rather than escaped markup.
--
-- No parameters are declared. Probes confirmed all six datasets return
-- identical record counts with or without parameter.sys_commCellId=10000
-- on this lab; the bespoke flow passed it but the effect was nil. Multi-
-- CommCell labs may need parameter substitution in the future, but
-- that's an extractor capability extension out of phase 4 scope.
--
-- Six datasets / sections (verified via live GET /reports/336):
--
--   section_id                                       | dataset_name                | dataset_guid (cache hint)
--   -------------------------------------------------|-----------------------------|---------------------------------------
--   security_assessment.access_security              | Access Security             | 7bdc4b02-a846-431e-8f16-9e567c81cdc6
--   security_assessment.auditing                     | Auditing                    | 66cee133-ab35-46f8-e5b6-fb00937f3f76
--   security_assessment.platform_security            | Platform Security           | 673c6dbe-edaf-4fa7-bf81-50bfe693e24f
--   security_assessment.company_and_owners_security  | Company and Owners Security | f67af316-2aff-413c-d62f-c936e6c8cd65
--   security_assessment.capabilities                 | Capabilities                | 06a5b275-5cd8-40ba-a43a-0a7c3a737ac9
--   security_assessment.hardening                    | Hardening                   | 6b274ec2-6f4b-4871-c1d6-defb7ea90649
--
-- Idempotency
-- -----------
-- INSERT OR IGNORE relies on the UNIQUE(source_id, section_id) constraint
-- on subject_section_sources. The source_id resolves via a subquery to
-- subject_sources.id where (subject_id, source_type) = ('security_assessment',
-- 'rest'). A second run inserts zero rows.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Access Security
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.access_security',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Access Security",'
    || '"dataset_guid":"7bdc4b02-a846-431e-8f16-9e567c81cdc6",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';


-- -----------------------------------------------------------------------------
-- 2. Auditing
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.auditing',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Auditing",'
    || '"dataset_guid":"66cee133-ab35-46f8-e5b6-fb00937f3f76",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';


-- -----------------------------------------------------------------------------
-- 3. Platform Security
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.platform_security',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Platform Security",'
    || '"dataset_guid":"673c6dbe-edaf-4fa7-bf81-50bfe693e24f",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';


-- -----------------------------------------------------------------------------
-- 4. Company and Owners Security
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.company_and_owners_security',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Company and Owners Security",'
    || '"dataset_guid":"f67af316-2aff-413c-d62f-c936e6c8cd65",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';


-- -----------------------------------------------------------------------------
-- 5. Capabilities
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.capabilities',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Capabilities",'
    || '"dataset_guid":"06a5b275-5cd8-40ba-a43a-0a7c3a737ac9",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';


-- -----------------------------------------------------------------------------
-- 6. Hardening
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'security_assessment.hardening',
    '{'
    || '"report_id":"336",'
    || '"dataset_name":"Hardening",'
    || '"dataset_guid":"6b274ec2-6f4b-4871-c1d6-defb7ea90649",'
    || '"column_map":['
    ||   '{"source":"Parameter","canonical":"parameter","type":"string"},'
    ||   '{"source":"Status","canonical":"status","type":"string"},'
    ||   '{"source":"Remarks","canonical":"remarks","type":"string"},'
    ||   '{"source":"Action","canonical":"action","type":"string"}'
    || '],'
    || '"status_to_severity":{'
    ||   '"1_Good":"good",'
    ||   '"2_Info":"info",'
    ||   '"3_Warning":"warning",'
    ||   '"4_Critical":"critical"'
    || '},'
    || '"output_as":"findings"'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'security_assessment' AND ss.source_type = 'rest';
