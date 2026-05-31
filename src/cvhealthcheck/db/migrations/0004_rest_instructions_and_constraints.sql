-- =============================================================================
-- Migration 0004: REST Extraction Instructions + staged_artifacts CHECK
-- =============================================================================
-- Part A: Add subject_section_sources rows for REST sources that have known
--         static dataset GUIDs.
--
-- Status per subject:
--   client_growth    — REST binding added in 0003 (monthly_table) ✓
--   capacity_license — REST binding added in 0003 (table) ✓
--   backup_job_summary — primary dataset GUID is known; added here
--   security_assessment — uses dynamic dataset discovery via report page 336;
--                         GUIDs vary per environment. TODO: add when stable.
--   license_summary — uses dynamic dataset discovery via report page 206;
--                     GUIDs vary per environment. TODO: add when stable.
--   environment — REST source is GET /commandcenter/api/CommServ (not a
--                 Reports Plus dataset). Not expressible as RESTExtractor
--                 instructions. TODO: implement dedicated env collector.
--
-- Part B: Recreate staged_artifacts with a CHECK constraint on status to
--         enforce the 'pending'|'approved'|'rejected' invariant at db level.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Part A: backup_job_summary REST section source binding
-- Dataset GUID: 2638c3d3-adc7-4b61-bb24-2ba509229bf5
-- This is the primary backup job dataset fetched by collect_backup_job_summary().
-- Mapped to recent_jobs (raw job rows). Summary/breakdown sections are computed
-- by the collector, not fetched as separate datasets.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id,
       'backup_job_summary.recent_jobs',
       json('{
           "dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
           "fields": ["JobId", "ClientName", "Status", "StartTime", "SizeKB"],
           "orderby": "StartTime Desc",
           "limit": 100,
           "output_as": "table"
       }')
FROM subject_sources s
WHERE s.subject_id     = 'backup_job_summary'
  AND s.subject_version = 1
  AND s.source_type    = 'rest';


-- -----------------------------------------------------------------------------
-- Part B: Recreate staged_artifacts with CHECK (status IN (...))
-- SQLite does not support adding a CHECK constraint to an existing column.
-- The table is recreated and data migrated in a single transaction.
-- All column definitions are taken from migrations 0002 + 0003.
-- -----------------------------------------------------------------------------

BEGIN;

CREATE TABLE staged_artifacts_new (
    stage_id        TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL,
    source_file     TEXT,
    source_type     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
    artifact_json   TEXT NOT NULL,
    ai_notes        TEXT,
    created_at      TEXT NOT NULL,
    reviewed_at     TEXT,
    reviewed_by     TEXT,
    engagement_id   TEXT,
    customer_id     TEXT,
    artifact_type   TEXT NOT NULL DEFAULT 'artifact',
    subject_version INTEGER,
    verification_status  TEXT,
    verification_sources TEXT,
    verification_notes   TEXT,
    verified_at          TEXT,
    user_edits_json      TEXT,
    filter_state_json    TEXT,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (customer_id)   REFERENCES customers(customer_id)
);

INSERT INTO staged_artifacts_new
SELECT
    stage_id, subject_id, source_file, source_type, status,
    artifact_json, ai_notes, created_at, reviewed_at, reviewed_by,
    engagement_id, customer_id, artifact_type, subject_version,
    verification_status, verification_sources, verification_notes,
    verified_at, user_edits_json, filter_state_json
FROM staged_artifacts;

DROP TABLE staged_artifacts;
ALTER TABLE staged_artifacts_new RENAME TO staged_artifacts;

CREATE INDEX IF NOT EXISTS idx_staged_artifacts_status
    ON staged_artifacts (status);
CREATE INDEX IF NOT EXISTS idx_staged_artifacts_subject
    ON staged_artifacts (subject_id);
CREATE INDEX IF NOT EXISTS idx_staged_artifacts_type
    ON staged_artifacts (artifact_type);

COMMIT;
