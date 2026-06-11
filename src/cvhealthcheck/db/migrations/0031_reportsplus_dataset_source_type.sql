-- =============================================================================
-- Migration 0031: admit 'reportsplus_dataset' in subject_sources.source_type
-- (ADR 0014 — directly-addressed Reports Plus dataset source)
-- =============================================================================
-- WIDEN the subject_sources.source_type CHECK to admit 'reportsplus_dataset'.
-- SQLite can't alter a CHECK in place, so subject_sources is rebuilt — the same
-- FK-safe, id-preserving pattern as migrations 0026/0027 (foreign_keys OFF;
-- the copy keeps PK values so subject_section_sources.source_id stays valid).
-- ADDITIVE and IDEMPOTENT: the CHECK only gains a value, every existing row is
-- preserved by id, and no seed rows are inserted — subjects of this type are
-- authored via MCP proposals (ADR 0014 D4), not migrations.
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
    -- ADR 0014: 'reportsplus_dataset' added (directly-addressed RP dataset).
    CHECK  (source_type IN ('html','csv','rest','json','rest_command_center_api','reportsplus_dataset')),
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

COMMIT;

PRAGMA foreign_keys = ON;
