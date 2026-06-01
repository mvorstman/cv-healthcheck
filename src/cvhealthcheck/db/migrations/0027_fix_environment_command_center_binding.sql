-- =============================================================================
-- Migration 0027: forward-fix — land migration 0026's intended effect on a live
-- DB where 0026 is stamped-applied-but-ineffective (ADR 0007 Phase 2)
-- =============================================================================
-- WHY THIS EXISTS
-- The first version of migration 0026 ran a plain `INSERT OR IGNORE` for the
-- environment `rest_command_center_api` source while subject_sources still had
-- the old 4-value source_type CHECK. The CHECK silently rejected the row, but
-- 0026 was recorded in schema_migrations anyway. Migrations are run-once by id,
-- so the corrected 0026 can never re-run on data/app.db — it is stuck with the
-- old 4-value CHECK and no command-center source. Collect on environment then
-- falls through to RESTExtractor and errors with "missing report_id".
--
-- 0027 lands 0026's intended effect via a NEW id, so the run-once system applies
-- it. It is fully IDEMPOTENT and FK-safe:
--   - on a LIVE DB (broken 0026): widens the CHECK + adds the source/binding.
--   - on a FRESH DB (0026's corrected effect already present): a no-op — the
--     rebuild reproduces the already-widened table, and the OR IGNORE inserts
--     skip (UNIQUE: subject_sources(subject_id,version,source_type) and
--     subject_section_sources(source_id,section_id)).
-- The rebuild is unconditional (no CHECK-state detection needed): rebuilding to a
-- fixed widened schema yields the same table regardless of the starting CHECK.
--
-- ADDITIVE: every existing row is preserved by id (esp. environment's rest row
-- id 7 and its environment.metadata live-card binding from 0023/0024). The rest
-- row / live-card binding are NOT removed or altered — Phase 3 owns the cutover;
-- coexistence is intended for now.
-- =============================================================================

PRAGMA foreign_keys = OFF;

BEGIN;

-- (1) Rebuild subject_sources to the WIDENED source_type CHECK (idempotent: same
--     widened table whether the live 4-value or the fresh 5-value CHECK was there).
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

-- (2) Add environment's command-center source (no-op if it already exists).
INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('environment', 1, 'rest_command_center_api', 1, NULL, NULL);

-- (3) Add the provisional 3-field collect binding (no-op if it already exists).
--     CommCell Name (nested), Version (flat), Timezone (nested); NO CommCell ID.
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
