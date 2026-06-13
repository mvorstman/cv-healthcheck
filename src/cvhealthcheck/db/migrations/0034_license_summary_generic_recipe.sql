-- 0034_license_summary_generic_recipe.sql
--
-- GENERATED FILE — do NOT edit by hand. Regenerate with:
--   python -m cvhealthcheck.license_summary.generic_recipe \
--     > src/cvhealthcheck/db/migrations/0034_license_summary_generic_recipe.sql
-- Source of truth: cvhealthcheck.license_summary.generic_recipe.LS_RECIPE_PROPOSAL
-- (the drift-guard test asserts this file is byte-identical to the render).
--
-- ADR-0017 promotion, commit 1: replace the 0003-era bespoke-shaped
-- license_summary recipe (sections + extraction instructions) with the generic recipe
-- under the SAME subject_id. The subjects row is NOT touched (created_by=
-- 'system' preserved); csv/html recognition_hints are NOT touched (commit 3);
-- the 'rest' source row is NOT touched (REST collect is out of scope).

-- Teardown the prior recipe content: every license_summary source's
-- section_sources, then all of its sections. Source ROWS are preserved.
DELETE FROM subject_section_sources WHERE source_id IN (
    SELECT id FROM subject_sources WHERE subject_id = 'license_summary'
);
DELETE FROM subject_sections WHERE subject_id = 'license_summary';

-- Ensure the csv/html sources exist and are extractable. INSERT OR IGNORE
-- leaves an existing row (with its recognition_hints) untouched.
INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('license_summary', 1, 'csv', 1, NULL, NULL),
    ('license_summary', 1, 'html', 1, NULL, NULL);

-- Sections (generic recipe).
INSERT INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type,
     default_selected, sort_order)
VALUES
    ('license_summary', 1, 'other_licenses', 'other_licenses', 'table', 1, 0),
    ('license_summary', 1, 'agent_feature_licenses', 'agent_feature_licenses', 'table', 1, 1),
    ('license_summary', 1, 'other_license_count', 'other_license_count', 'metric', 1, 2),
    ('license_summary', 1, 'agent_feature_count', 'agent_feature_count', 'metric', 1, 3),
    ('license_summary', 1, 'commcell_meta', 'commcell_meta', 'metric', 1, 4),
    ('license_summary', 1, '_commcell_observed', '_commcell_observed', 'metric', 1, 5),
    ('license_summary', 1, 'capacity_licenses', 'capacity_licenses', 'table', 1, 6),
    ('license_summary', 1, 'operating_instance_licenses', 'operating_instance_licenses', 'table', 1, 7),
    ('license_summary', 1, 'virtualization_licenses', 'virtualization_licenses', 'table', 1, 8),
    ('license_summary', 1, 'user_licenses', 'user_licenses', 'table', 1, 9),
    ('license_summary', 1, 'data_insights_licenses', 'data_insights_licenses', 'table', 1, 10),
    ('license_summary', 1, 'air_gap_protect_licenses', 'air_gap_protect_licenses', 'table', 1, 11);

-- Extraction instructions, per (source_type, section).
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'other_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "available_total", "source": "Available Total", "transforms": ["number_with_unit"]}, {"canonical": "used", "source": "Used", "transforms": ["number_with_unit"]}], "format": "single_table", "null_values": ["N/A", "-", ""], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'agent_feature_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "permanent_total", "source": "Permanent Total", "transforms": ["to_integer"]}, {"canonical": "permanent_used", "source": "Permanent Used", "transforms": ["to_integer"]}, {"canonical": "term_total", "source": "Term Total", "transforms": ["to_integer"]}, {"canonical": "term_used", "source": "Term Used", "transforms": ["to_integer"]}], "format": "single_table", "null_values": ["N/A", "-", ""], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'other_license_count', json('{"computed_type": "row_count", "format": "computed", "output_as": "table", "source_section": "other_licenses"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'agent_feature_count', json('{"computed_type": "distinct_count", "field": "license", "format": "computed", "output_as": "table", "source_section": "agent_feature_licenses"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'commcell_meta', json('{"format": "metadata_pairs", "label_map": [{"canonical": "registration_code", "source": "Registration code", "transforms": ["trim", "mask_registration_code"]}], "null_values": ["N/A", "-", ""], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, '_commcell_observed', json('{"format": "metadata_pairs", "label_map": [{"canonical": "commcell_name", "source": ["CommCell Name"]}, {"canonical": "commcell_version", "source": ["Version", "CommCell Version"]}, {"canonical": "license_expiry", "source": ["License expiration", "License Expiry", "License expiry"]}, {"canonical": "last_collection", "source": ["Usage collection time", "Last collection time", "Last Collection Time", "Usage Collection Time"]}], "null_values": [], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'csv';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'other_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "available_total", "source": "Available Total", "transforms": ["number_with_unit"]}, {"canonical": "used", "source": "Used", "transforms": ["number_with_unit"]}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Other Licenses - current usage details", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'agent_feature_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "permanent_total", "source": "Permanent Total", "transforms": ["to_integer"]}, {"canonical": "permanent_used", "source": "Permanent Used", "transforms": ["to_integer"]}, {"canonical": "term_total", "source": "Term Total", "transforms": ["to_integer"]}, {"canonical": "term_used", "source": "Term Used", "transforms": ["to_integer"]}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Agent and Feature Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'other_license_count', json('{"computed_type": "row_count", "format": "computed", "output_as": "table", "source_section": "other_licenses"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'agent_feature_count', json('{"computed_type": "distinct_count", "field": "license", "format": "computed", "output_as": "table", "source_section": "agent_feature_licenses"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'commcell_meta', json('{"format": "metadata_pairs", "label_map": [{"canonical": "registration_code", "source": "Registration code", "transforms": ["trim", "mask_registration_code"]}], "null_values": ["N/A", "-", ""], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, '_commcell_observed', json('{"format": "metadata_pairs", "label_map": [{"canonical": "commcell_name", "source": ["CommCell Name"]}, {"canonical": "commcell_version", "source": ["Version", "CommCell Version"]}, {"canonical": "license_expiry", "source": ["License expiration", "License Expiry", "License expiry"]}, {"canonical": "last_collection", "source": ["Usage collection time", "Last collection time", "Last Collection Time", "Usage Collection Time"]}], "null_values": [], "output_as": "table"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'capacity_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Capacity Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'operating_instance_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Operating Instance Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'virtualization_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Virtualization Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'user_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "User Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'data_insights_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Data Insights Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT id, 'air_gap_protect_licenses', json('{"column_map": [{"canonical": "license", "source": "License", "type": "string"}, {"canonical": "entitlement_value", "source": ["Available Total", "Available Total (TB)", "Available Total (instances)", "Available Total (users)", "Available Total (VMs)", "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)", "Permanent Purchased (users)", "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)", "Term Purchased (users)"], "transforms": ["number_with_unit"]}, {"canonical": "used", "source": ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"], "transforms": ["number_with_unit"]}, {"canonical": "status", "source": "Summary", "type": "string"}], "null_values": ["N/A", "-", ""], "output_as": "table", "section_title_match": "Air Gap Protect Licenses", "section_title_selector": ".reportstabletitle, h2"}')
  FROM subject_sources WHERE subject_id = 'license_summary' AND subject_version = 1 AND source_type = 'html';
