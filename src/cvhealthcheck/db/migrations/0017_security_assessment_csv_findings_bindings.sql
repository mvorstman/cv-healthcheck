-- =============================================================================
-- Migration 0017: security_assessment — generic CSV findings bindings
-- =============================================================================
-- SA had html=6 + rest=6 findings bindings but csv=0, so the bespoke
-- security_assessment/import_csv.py was SA's ONLY CSV path (the Phase-0 gap).
-- This adds the six CSV findings bindings so SA CSV uploads route through the
-- generic CSVExtractor -> result_to_artifact, matching the html/rest set.
--
-- The SA CSV export blank-line-separates its sections into [label, header,
-- data...] blocks (verified against the real export), which is exactly the
-- existing `multi_section` format the generic CSVExtractor already implements
-- (client_growth / capacity_license use it). So these are catalog rows over the
-- existing extractor — NO new transform operator. Each section binds by its
-- first-cell `section_label`; the column_map + status_to_severity mirror the
-- HTML findings bindings (migration 0003) so the canonical findings match.
--
-- Section labels are the CSV's first-cell section headings; section_ids are the
-- catalog's namespaced ids (shared with the html/rest bindings).
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.access_security', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Access Security",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.auditing', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Auditing",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.platform_security', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Platform Security",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.company_and_owners_security', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Company and Owners Security",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.capabilities', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Capabilities",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.hardening', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Hardening",
    "column_map": [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},
        {"source": "Action",    "canonical": "action",    "type": "string"}
    ],
    "status_to_severity": {"Critical": "critical", "Warning": "warning", "Good": "good", "Info": "info"},
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment' AND s.subject_version = 1 AND s.source_type = 'csv';
