-- =============================================================================
-- Migration 0026: environment command_center_api collect source + provisional
-- card binding (ADR 0007 Phase 2)
-- =============================================================================
-- Make `environment` collectable through the single-object Command Center API
-- extractor, storing a canonical artifact in working/environment/ — proving the
-- seam (Collect button -> /collect -> CommandCenterExtractor -> result_to_artifact
-- -> save_artifact) end to end.
--
-- Two parts:
--   (1) WIDEN the subject_sources.source_type CHECK to admit 'rest_command_center_api'.
--       SQLite can't alter a CHECK in place, so subject_sources is rebuilt (same
--       pattern migration 0012 used for subject_sections). subject_sources HAS an
--       incoming FK (subject_section_sources.source_id -> subject_sources.id), so
--       the rebuild runs with foreign_keys OFF and preserves every `id` (the copy
--       keeps the PK values), so existing bindings stay valid. Additive: the CHECK
--       only gains a value; nothing is removed.
--   (2) ADD a second subject_sources row for environment (the new source type) and
--       a binding on the existing environment.metadata section. ADDITIVE: it does
--       NOT touch _build_environment_subject, the live-served identity card, or the
--       existing 'rest' source binding (migrations 0023/0024 rules + view_mode).
--
-- PROVISIONAL SPEC — THREE fields only, to prove storage on real data:
--   CommCell Name  -> commcell.commCellName   (nested read, ADR 0007 D2)
--   Version        -> csVersionInfo           (flat read)
--   Timezone       -> csTimeZone.TimeZoneName  (nested read, D2)
-- DELIBERATELY no CommCell ID this slice: the 2-vs-337f value is gated on a live
-- GET CommServ capture (ADR 0007 Phase 3), which also replaces this provisional
-- spec with the full schema-order parity spec (incl. CommCell ID with `type:hex`).
-- =============================================================================

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE subject_sources_new (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id              TEXT    NOT NULL,
    subject_version         INTEGER NOT NULL DEFAULT 1,
    source_type             TEXT    NOT NULL,
    extractable             INTEGER NOT NULL DEFAULT 1,
    non_extractable_reason  TEXT,
    recognition_hints       TEXT,
    added_at                TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (subject_id, subject_version, source_type),
    CHECK  (extractable IN (0,1)),
    -- ADR 0007: 'rest_command_center_api' added (single-object Command Center API).
    CHECK  (source_type IN ('html','csv','rest','json','rest_command_center_api')),
    FOREIGN KEY (subject_id, subject_version)
        REFERENCES subjects(subject_id, version)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO subject_sources_new
SELECT id, subject_id, subject_version, source_type, extractable,
       non_extractable_reason, recognition_hints, added_at
FROM subject_sources;

DROP TABLE subject_sources;
ALTER TABLE subject_sources_new RENAME TO subject_sources;

CREATE INDEX IF NOT EXISTS idx_subject_sources_subject
    ON subject_sources (subject_id, subject_version);
CREATE INDEX IF NOT EXISTS idx_subject_sources_type
    ON subject_sources (source_type);

-- (2) the environment Command Center collect source + provisional 3-field binding.
INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('environment', 1, 'rest_command_center_api', 1, NULL, NULL);

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'environment.metadata',
    '{'
    || '"output_as":"card",'
    || '"card":{'
    ||   '"columns":3,'
    ||   '"items":['
    ||     '{"label":"CommCell Name","field":"commcell.commCellName"},'
    ||     '{"label":"Version","field":"csVersionInfo"},'
    ||     '{"label":"Timezone","field":"csTimeZone.TimeZoneName"}'
    ||   ']'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = 'environment'
  AND ss.subject_version = 1
  AND ss.source_type = 'rest_command_center_api';

COMMIT;

PRAGMA foreign_keys = ON;
