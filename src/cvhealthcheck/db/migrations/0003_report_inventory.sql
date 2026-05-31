-- =============================================================================
-- Migration 0003: Report Inventory
-- =============================================================================
-- Adds the catalog/acquisition/staging layers for the Report Inventory feature.
-- All additions are additive — no existing tables are altered destructively.
-- Idempotent: every CREATE uses IF NOT EXISTS.
--
-- New tables:
--   subjects                  — catalog layer: what a report type is
--   subject_sections          — catalog layer: what sections a subject has
--   subject_sources           — acquisition layer: how to recognise + extract
--   subject_section_sources   — acquisition layer: per-section extraction binding
--   collector_schemas         — stub for future JSON collector source type
--
-- Altered tables:
--   staged_artifacts          — adds artifact_type discriminator + verification cols
--
-- Seed data:
--   Six existing subjects migrated from QUICK_HC_TILES (created_by = 'system')
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. ALTER staged_artifacts
--    Add columns needed to distinguish subject proposals from artifact proposals,
--    and to track cross-source verification state.
--    SQLite only supports ADD COLUMN — one statement per column.
-- -----------------------------------------------------------------------------

ALTER TABLE staged_artifacts
    ADD COLUMN artifact_type TEXT NOT NULL DEFAULT 'artifact';
-- values: 'artifact' (existing flow) | 'subject_proposal' (new flow)

ALTER TABLE staged_artifacts
    ADD COLUMN subject_version INTEGER;
-- populated for subject_proposal rows; NULL for artifact rows

ALTER TABLE staged_artifacts
    ADD COLUMN verification_status TEXT;
-- NULL | 'pending' | 'passed' | 'failed' | 'skipped'

ALTER TABLE staged_artifacts
    ADD COLUMN verification_sources TEXT;
-- JSON array: ["html","csv"] — which source types were compared

ALTER TABLE staged_artifacts
    ADD COLUMN verification_notes TEXT;
-- human-readable discrepancies found during cross-source reconciliation

ALTER TABLE staged_artifacts
    ADD COLUMN verified_at TEXT;
-- ISO-8601 timestamp, set when verification_status changes from NULL/pending

ALTER TABLE staged_artifacts
    ADD COLUMN user_edits_json TEXT;
-- NULL until first manual edit in staging UI;
-- on approval, canonical artifact = merge(artifact_json, user_edits_json)

ALTER TABLE staged_artifacts
    ADD COLUMN filter_state_json TEXT;
-- JSON object: captured filter state from import (e.g. {"type":"Full","timeframe":"Weekly"})

CREATE INDEX IF NOT EXISTS idx_staged_artifacts_type
    ON staged_artifacts (artifact_type);


-- -----------------------------------------------------------------------------
-- 2. subjects
--    Catalog layer — defines what a report type *is*.
--    One row per (subject_id, version) pair.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subjects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      TEXT    NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    superseded_by   INTEGER REFERENCES subjects(id),
    title           TEXT    NOT NULL,
    description     TEXT,
    category        TEXT    NOT NULL,    -- slug: identity | security | licensing | performance | operations | storage
    category_label  TEXT    NOT NULL,    -- display: 'Identity', 'Security', etc.
    status          TEXT    NOT NULL DEFAULT 'active',
    -- active | superseded | proposed | disabled
    created_by      TEXT    NOT NULL DEFAULT 'system',
    -- system | ai | user
    preferred_source TEXT,
    -- html | csv | rest | json — hint only, extractor uses what is available
    related_subjects TEXT,
    -- JSON array of subject_id strings, e.g. ["growth_and_trends"]
    change_notes    TEXT,
    -- what changed from the previous version; NULL for v1
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (subject_id, version),
    CHECK  (status IN ('active','superseded','proposed','disabled')),
    CHECK  (version >= 1)
);

CREATE INDEX IF NOT EXISTS idx_subjects_subject_id ON subjects (subject_id);
CREATE INDEX IF NOT EXISTS idx_subjects_status     ON subjects (status);
CREATE INDEX IF NOT EXISTS idx_subjects_category   ON subjects (category);


-- -----------------------------------------------------------------------------
-- 3. subject_sections
--    Catalog layer — defines the sections within a subject.
--    Mirrors the SectionDefinition tuples in QUICK_HC_TILES.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subject_sections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id       TEXT    NOT NULL,
    subject_version  INTEGER NOT NULL DEFAULT 1,
    section_id       TEXT    NOT NULL,  -- stable identifier, e.g. "security_assessment.access_security"
    title            TEXT    NOT NULL,
    section_type     TEXT    NOT NULL,  -- findings | table | metric | chart
    default_selected INTEGER NOT NULL DEFAULT 1,  -- 1 = include in report by default
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (subject_id, subject_version, section_id),
    CHECK  (section_type IN ('findings','table','metric','chart')),
    CHECK  (default_selected IN (0,1)),
    FOREIGN KEY (subject_id, subject_version)
        REFERENCES subjects(subject_id, version)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_subject_sections_subject
    ON subject_sections (subject_id, subject_version);


-- -----------------------------------------------------------------------------
-- 4. subject_sources
--    Acquisition layer — one row per (subject, version, source_type).
--    Holds recognition hints and top-level source metadata.
--    Per-section extraction instructions live in subject_section_sources.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subject_sources (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id              TEXT    NOT NULL,
    subject_version         INTEGER NOT NULL DEFAULT 1,
    source_type             TEXT    NOT NULL,
    -- html | csv | rest | json
    extractable             INTEGER NOT NULL DEFAULT 1,
    -- 0 = source type is recognisable but not extractable (charts-only, client-side rendered)
    non_extractable_reason  TEXT,
    -- 'charts_only' | 'client_side_rendered' | NULL
    recognition_hints       TEXT,
    -- JSON object: clues used to identify this file as this subject+version
    -- e.g. {"html":{"title_contains":"License summary","table_count":2,
    --               "first_table_headers":["License","Available Total","Used"]}}
    added_at                TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (subject_id, subject_version, source_type),
    CHECK  (extractable IN (0,1)),
    CHECK  (source_type IN ('html','csv','rest','json')),
    FOREIGN KEY (subject_id, subject_version)
        REFERENCES subjects(subject_id, version)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_subject_sources_subject
    ON subject_sources (subject_id, subject_version);
CREATE INDEX IF NOT EXISTS idx_subject_sources_type
    ON subject_sources (source_type);


-- -----------------------------------------------------------------------------
-- 5. subject_section_sources
--    Acquisition layer — per-section extraction instructions.
--    A subject_source row may have zero or many section bindings.
--    Zero = source is registered but no extraction instructions defined yet.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subject_section_sources (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                INTEGER NOT NULL REFERENCES subject_sources(id) ON DELETE CASCADE,
    section_id               TEXT    NOT NULL,
    extraction_instructions  TEXT,
    -- JSON object describing how to extract this section from this source type.
    -- Structure varies by source_type:
    --
    -- html: {
    --   "table_selector": "#table_Table1 table",
    --   "section_title_selector": ".panel-table-title",
    --   "column_map": [{"source":"License","canonical":"license_name","type":"string"},...],
    --   "null_values": ["N/A","-",""],
    --   "header_row": 0
    -- }
    --
    -- csv: {
    --   "format": "single_table" | "multi_section",
    --   "section_label": "Clients Count",     -- for multi_section: label to match
    --   "section_index": 5,                   -- fallback when no label
    --   "section_separator": "blank_lines",
    --   "column_map": [...],
    --   "column_structure": "fixed" | "dynamic_pivot",
    --   "dynamic_columns": {                  -- only for dynamic_pivot
    --     "start_index": 1,
    --     "header_pattern": "\\d+/\\d+ - \\d+/\\d+",
    --     "canonical_prefix": "week",
    --     "store_as": "key_value_pairs"
    --   },
    --   "skip_rows": 0,
    --   "null_values": ["-1","N/A",""],
    --   "stop_at_pattern": null
    -- }
    --
    -- rest: {
    --   "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    --   "fields": ["MonthStart","Total","Removed","Added"],
    --   "orderby": "MonthStart Asc",
    --   "parameters": {"type": 2},
    --   "timestamp_fields": ["MonthStart"],
    --   "timestamp_format": "unix_seconds",
    --   "size_unit": null,
    --   "null_values": [null]
    -- }
    --
    -- json: {
    --   "schema_id": "system_inventory_v1",
    --   "json_path": "$.hosts[*]",
    --   "field_map": [{"source":"hostname","canonical":"hostname","type":"string"}]
    -- }
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (source_id, section_id)
);

CREATE INDEX IF NOT EXISTS idx_section_sources_source
    ON subject_section_sources (source_id);
CREATE INDEX IF NOT EXISTS idx_section_sources_section
    ON subject_section_sources (section_id);


-- -----------------------------------------------------------------------------
-- 6. collector_schemas
--    Stub table for the future JSON collector tool.
--    cv-healthcheck owns the contract — collector tools are built to match.
--    Empty for now; populated when the collector project starts.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS collector_schemas (
    schema_id    TEXT    PRIMARY KEY,   -- e.g. "system_inventory"
    version      INTEGER NOT NULL DEFAULT 1,
    description  TEXT,
    json_schema  TEXT,                  -- the JSON Schema document (draft-07)
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (schema_id, version)
);


-- =============================================================================
-- SEED DATA
-- Six existing subjects migrated from QUICK_HC_TILES.
-- created_by = 'system', version = 1, status = 'active'.
-- All INSERT OR IGNORE so re-running the migration is safe.
-- Subject IDs match artifact_type values used by the existing adapters
-- and ArtifactStore paths.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Subjects
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subjects
    (subject_id, version, title, description, category, category_label,
     status, created_by, preferred_source)
VALUES
    ('environment', 1,
     'CommCell Details',
     'CommCell identity, version, and collection status.',
     'identity', 'Identity',
     'active', 'system', 'rest'),

    ('security_assessment', 1,
     'Security Assessment',
     'Security posture across access, auditing, platform hardening, and capabilities.',
     'security', 'Security',
     'active', 'system', 'html'),

    ('license_summary', 1,
     'License Summary',
     'Current license usage — other licenses and agent/feature licenses.',
     'licensing', 'Licensing',
     'active', 'system', 'html'),

    ('client_growth', 1,
     'Client Growth',
     'Monthly client count trend — added, removed, total.',
     'performance', 'Performance',
     'active', 'system', 'rest'),

    ('capacity_license', 1,
     'Capacity Licenses',
     'Capacity license consumption over time.',
     'performance', 'Performance',
     'active', 'system', 'rest'),

    ('backup_job_summary', 1,
     'Backup Job Summary',
     'Recent backup job outcomes, status breakdown, and failure list.',
     'operations', 'Operations',
     'active', 'system', 'rest');


-- -----------------------------------------------------------------------------
-- Sections — environment
-- Mirrors the section IDs from registry.py constants.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('environment', 1, 'environment.metadata',
     'CommCell identity', 'metric', 1, 1);


-- -----------------------------------------------------------------------------
-- Sections — security_assessment
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('security_assessment', 1, 'security_assessment.metadata',
     'Report metadata', 'metric', 0, 0),

    ('security_assessment', 1, 'security_assessment.summary',
     'Summary', 'metric', 1, 1),

    ('security_assessment', 1, 'security_assessment.highlights',
     'Highlights', 'findings', 1, 2),

    ('security_assessment', 1, 'security_assessment.all_findings',
     'All findings', 'findings', 0, 3),

    ('security_assessment', 1, 'security_assessment.access_security',
     'Access Security', 'findings', 1, 4),

    ('security_assessment', 1, 'security_assessment.auditing',
     'Auditing', 'findings', 1, 5),

    ('security_assessment', 1, 'security_assessment.platform_security',
     'Platform Security', 'findings', 1, 6),

    ('security_assessment', 1, 'security_assessment.company_and_owners_security',
     'Company and Owners Security', 'findings', 1, 7),

    ('security_assessment', 1, 'security_assessment.capabilities',
     'Capabilities', 'findings', 1, 8),

    ('security_assessment', 1, 'security_assessment.hardening',
     'Hardening', 'findings', 1, 9);


-- -----------------------------------------------------------------------------
-- Sections — license_summary
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('license_summary', 1, 'license_summary.metadata',
     'CommCell info', 'metric', 1, 1),

    ('license_summary', 1, 'license_summary.other_licenses',
     'Other Licenses — current usage', 'table', 1, 2),

    ('license_summary', 1, 'license_summary.agent_feature_licenses',
     'Agent and Feature Licenses — current usage', 'table', 1, 3),

    ('license_summary', 1, 'license_summary.workload_sections',
     'Workload sections', 'table', 0, 4);


-- -----------------------------------------------------------------------------
-- Sections — client_growth
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('client_growth', 1, 'client_growth.summary',
     'Summary', 'metric', 1, 1),

    ('client_growth', 1, 'client_growth.chart',
     'Growth chart', 'chart', 1, 2),

    ('client_growth', 1, 'client_growth.monthly_table',
     'Monthly detail', 'table', 1, 3);


-- -----------------------------------------------------------------------------
-- Sections — capacity_license
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('capacity_license', 1, 'capacity_license.summary',
     'Summary', 'metric', 1, 1),

    ('capacity_license', 1, 'capacity_license.table',
     'Usage detail', 'table', 1, 2);


-- -----------------------------------------------------------------------------
-- Sections — backup_job_summary
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('backup_job_summary', 1, 'backup_job_summary.summary',
     'Summary', 'metric', 1, 1),

    ('backup_job_summary', 1, 'backup_job_summary.status_breakdown',
     'Status breakdown', 'table', 1, 2),

    ('backup_job_summary', 1, 'backup_job_summary.recent_failures',
     'Recent failures', 'findings', 1, 3),

    ('backup_job_summary', 1, 'backup_job_summary.recent_jobs',
     'Recent jobs', 'table', 0, 4);


-- -----------------------------------------------------------------------------
-- Sources — security_assessment
-- HTML is the primary extractable source. CSV exists but no instructions yet.
-- REST is available via Reports Plus (report_id 336).
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('security_assessment', 1, 'html', 1, NULL,
     '{"title_contains":"Security Assessment","has_selector":".panel-table-title","grid_present":true}'),

    ('security_assessment', 1, 'csv', 1, NULL,
     '{"first_line_contains":"Security Assessment"}'),

    ('security_assessment', 1, 'rest', 1, NULL,
     '{"report_id":336,"report_name":"Security Assessment"}');


-- -----------------------------------------------------------------------------
-- Sources — license_summary
-- HTML has two well-structured tables. CSV exists.
-- REST available via Reports Plus.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('license_summary', 1, 'html', 1, NULL,
     '{"title_contains":"License summary","has_selector":".reportstabletitle","table_count":2,"first_table_headers":["License","Available Total","Used"]}'),

    ('license_summary', 1, 'csv', 1, NULL,
     '{"first_line_contains":"License summary"}'),

    ('license_summary', 1, 'rest', 1, NULL,
     '{"report_name":"License summary"}');


-- -----------------------------------------------------------------------------
-- Sources — environment
-- REST only — CommServ identity comes from the REST API.
-- HTML/CSV exports of CommCell details do not exist as a standalone report.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('environment', 1, 'rest', 1, NULL,
     '{"endpoint_contains":"commserv"}');


-- -----------------------------------------------------------------------------
-- Sources — client_growth
-- REST preferred. CSV available from Growth and Trends multi-section export.
-- HTML is charts-only — not extractable.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('client_growth', 1, 'rest', 1, NULL,
     '{"dataset_guid":"f2bfe9ce-0101-4377-be9e-285981ac7fd8"}'),

    ('client_growth', 1, 'csv', 1, NULL,
     '{"first_line_contains":"Growth and Trends","section_label":"Clients Count"}'),

    ('client_growth', 1, 'html', 0, 'charts_only',
     '{"title_contains":"Growth and Trends"}');


-- -----------------------------------------------------------------------------
-- Sources — capacity_license
-- REST preferred. CSV available from Growth and Trends multi-section export.
-- HTML charts-only.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('capacity_license', 1, 'rest', 1, NULL,
     '{"dataset_guid":"43c5c8f8-5864-48de-8153-f85a91abd93a"}'),

    ('capacity_license', 1, 'csv', 1, NULL,
     '{"first_line_contains":"Growth and Trends","section_index":6}'),

    ('capacity_license', 1, 'html', 0, 'charts_only',
     '{"title_contains":"Growth and Trends"}');


-- -----------------------------------------------------------------------------
-- Sources — backup_job_summary
-- REST preferred. No known HTML/CSV export format identified yet.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('backup_job_summary', 1, 'rest', 1, NULL,
     '{"report_name":"Backup Job Summary"}');


-- =============================================================================
-- Extraction instructions for the two subjects with full adapter code:
-- security_assessment and license_summary.
--
-- These are the only two subjects where the existing Python adapters were
-- reviewed and can be accurately expressed as JSON instructions.
-- The other four subjects get source bindings with no section-level
-- instructions yet (extractable = 1 but no subject_section_sources rows).
-- Instructions for those subjects are added when their adapters are written.
-- =============================================================================

-- security_assessment HTML — six table sections, each identified by .panel-table-title

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.access_security', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Access Security",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.auditing', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Auditing",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.platform_security', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Platform Security",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.company_and_owners_security', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Company and Owners Security",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.capabilities', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Capabilities",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'security_assessment.hardening', json('{
    "table_selector": "table",
    "section_title_selector": ".panel-table-title",
    "section_title_match": "Hardening",
    "column_map": [
        {"source": "Parameter",  "canonical": "parameter",  "type": "string"},
        {"source": "Status",     "canonical": "status",     "type": "string"},
        {"source": "Remarks",    "canonical": "remarks",    "type": "string"},
        {"source": "Action",     "canonical": "action",     "type": "string"}
    ],
    "status_to_severity": {
        "Critical": "critical",
        "Warning":  "warning",
        "Good":     "good",
        "Info":     "info"
    },
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'security_assessment'
  AND s.subject_version = 1
  AND s.source_type = 'html';


-- license_summary HTML — two tables identified by .reportstabletitle selector

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'license_summary.other_licenses', json('{
    "table_selector": "table",
    "section_title_selector": ".reportstabletitle",
    "section_title_match": "Other Licenses",
    "column_map": [
        {"source": "License",         "canonical": "license_name",       "type": "string"},
        {"source": "Available Total", "canonical": "available_total_raw", "type": "string",
         "note": "value includes unit e.g. 0 TB — parse in normaliser"},
        {"source": "Used",            "canonical": "used_raw",            "type": "string",
         "note": "value includes unit e.g. 4 clients — parse in normaliser"}
    ],
    "null_values": ["N/A", "-", ""],
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'license_summary'
  AND s.subject_version = 1
  AND s.source_type = 'html';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'license_summary.agent_feature_licenses', json('{
    "table_selector": "table",
    "section_title_selector": ".reportstabletitle",
    "section_title_match": "Agent and Feature Licenses",
    "column_map": [
        {"source": "License",           "canonical": "license_name",      "type": "string"},
        {"source": "Permanent Total",   "canonical": "permanent_total",   "type": "string"},
        {"source": "Permanent Used",    "canonical": "permanent_used",    "type": "string"},
        {"source": "Term Total",        "canonical": "term_total",        "type": "string"},
        {"source": "Term Used",         "canonical": "term_used",         "type": "string"},
        {"source": "Client",            "canonical": "client",            "type": "string"},
        {"source": "Agent",             "canonical": "agent",             "type": "string"},
        {"source": "Install Date",      "canonical": "install_date",      "type": "string"}
    ],
    "null_values": ["N/A", "-", ""],
    "output_as": "table",
    "note": "license_name repeats for multi-client licenses (e.g. Server File System) — this is expected, not a data error"
}')
FROM subject_sources s
WHERE s.subject_id = 'license_summary'
  AND s.subject_version = 1
  AND s.source_type = 'html';


-- license_summary CSV extraction instructions

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'license_summary.other_licenses', json('{
    "format": "single_table",
    "column_map": [
        {"source": "License",         "canonical": "license_name",       "type": "string"},
        {"source": "Available Total", "canonical": "available_total_raw", "type": "string"},
        {"source": "Used",            "canonical": "used_raw",            "type": "string"}
    ],
    "null_values": ["N/A", "-", ""],
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'license_summary'
  AND s.subject_version = 1
  AND s.source_type = 'csv';

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'license_summary.agent_feature_licenses', json('{
    "format": "single_table",
    "column_map": [
        {"source": "License",         "canonical": "license_name",     "type": "string"},
        {"source": "Permanent Total", "canonical": "permanent_total",  "type": "string"},
        {"source": "Permanent Used",  "canonical": "permanent_used",   "type": "string"},
        {"source": "Term Total",      "canonical": "term_total",       "type": "string"},
        {"source": "Term Used",       "canonical": "term_used",        "type": "string"},
        {"source": "Client",          "canonical": "client",           "type": "string"},
        {"source": "Agent",           "canonical": "agent",            "type": "string"},
        {"source": "Install Date",    "canonical": "install_date",     "type": "string"}
    ],
    "null_values": ["N/A", "-", ""],
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'license_summary'
  AND s.subject_version = 1
  AND s.source_type = 'csv';


-- client_growth CSV (from Growth and Trends multi-section export)
-- Column names in the CSV are "None_Total", "None_Removed", "None_Added" — mangled series names.
-- Mapped to canonical names here; normaliser treats None_ prefix as artefact.

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'client_growth.monthly_table', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_label": "Clients Count",
    "column_map": [
        {"source": "MonthStart",    "canonical": "month_start",  "type": "string"},
        {"source": "None_Total",    "canonical": "total",        "type": "integer",
         "fuzzy_match": true, "note": "CSV serialises series name as None_Total"},
        {"source": "None_Removed",  "canonical": "removed",      "type": "integer",
         "fuzzy_match": true},
        {"source": "None_Added",    "canonical": "added",        "type": "integer",
         "fuzzy_match": true}
    ],
    "null_values": ["-1", "N/A", ""],
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'client_growth'
  AND s.subject_version = 1
  AND s.source_type = 'csv';


-- client_growth REST

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'client_growth.monthly_table', json('{
    "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    "fields": ["MonthStart", "Total", "Removed", "Added"],
    "orderby": "MonthStart Asc",
    "limit": 15,
    "timestamp_fields": ["MonthStart"],
    "timestamp_format": "unix_seconds",
    "null_values": [null],
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'client_growth'
  AND s.subject_version = 1
  AND s.source_type = 'rest';


-- capacity_license REST
-- null values for months before license was active (-1 in CSV, null in REST)

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'capacity_license.table', json('{
    "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
    "fields": ["Month", "Entity Name", "Used Capacity"],
    "orderby": "Month Asc",
    "parameters": {"type": 2},
    "size_unit": "MB",
    "null_values": [null],
    "note": "null = license not yet active for that month, not a data error",
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'capacity_license'
  AND s.subject_version = 1
  AND s.source_type = 'rest';


-- capacity_license CSV (from Growth and Trends, section_index 6, no label)
-- -1 sentinel = null in CSV serialisation

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'capacity_license.table', json('{
    "format": "multi_section",
    "section_separator": "blank_lines",
    "section_index": 6,
    "column_map": [
        {"source": "Month",       "canonical": "month",          "type": "string"},
        {"source": "Entity Name", "canonical": "entity_name",    "type": "string"},
        {"source": "Used Capacity","canonical": "used_capacity", "type": "integer"}
    ],
    "null_values": ["-1", "N/A", ""],
    "note": "-1 sentinel means not-licensed, normalised to null",
    "output_as": "table"
}')
FROM subject_sources s
WHERE s.subject_id = 'capacity_license'
  AND s.subject_version = 1
  AND s.source_type = 'csv';


-- =============================================================================
-- Verification query — run after applying the migration to confirm seeding.
-- Not executed as part of the migration itself.
--
-- SELECT s.subject_id, s.version, s.status,
--        COUNT(DISTINCT ss.id)  AS sections,
--        COUNT(DISTINCT src.id) AS sources,
--        COUNT(DISTINCT sss.id) AS section_source_bindings
-- FROM subjects s
-- LEFT JOIN subject_sections ss
--        ON ss.subject_id = s.subject_id AND ss.subject_version = s.version
-- LEFT JOIN subject_sources src
--        ON src.subject_id = s.subject_id AND src.subject_version = s.version
-- LEFT JOIN subject_section_sources sss ON sss.source_id = src.id
-- GROUP BY s.subject_id, s.version
-- ORDER BY s.id;
--
-- Expected output:
-- environment          1 active   1 section   1 source    0 bindings  (no HTML/CSV export)
-- security_assessment  1 active  10 sections  3 sources   6 bindings  (HTML only; 6 SA sections)
-- license_summary      1 active   4 sections  3 sources   4 bindings  (HTML: 2, CSV: 2)
-- client_growth        1 active   3 sections  3 sources   2 bindings  (REST: 1, CSV: 1)
-- capacity_license     1 active   2 sections  3 sources   2 bindings  (REST: 1, CSV: 1)
-- backup_job_summary   1 active   4 sections  1 source    0 bindings  (REST only; no instructions yet)
-- =============================================================================
