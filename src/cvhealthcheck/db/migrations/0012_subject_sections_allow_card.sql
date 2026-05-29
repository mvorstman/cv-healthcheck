-- =============================================================================
-- Migration 0012: allow 'card' in subject_sections.section_type CHECK
-- =============================================================================
-- ADR 0004 phase 4 adds the `card` section type. SQLite cannot alter a CHECK
-- constraint in place, so subject_sections is rebuilt with the widened CHECK —
-- the same table-rebuild pattern migration 0004 used for staged_artifacts.
--
-- Safe: nothing references subject_sections with an incoming FK (its only FK is
-- OUTGOING to subjects), so the drop/rename can't dangle a reference. The data
-- copy preserves every existing row; the UNIQUE constraint, the
-- default_selected CHECK, the FK to subjects, and the index are all recreated
-- identically — only the section_type CHECK changes (adds 'card').
-- =============================================================================

BEGIN;

CREATE TABLE subject_sections_new (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id       TEXT    NOT NULL,
    subject_version  INTEGER NOT NULL DEFAULT 1,
    section_id       TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    section_type     TEXT    NOT NULL,  -- findings | table | metric | chart | card
    default_selected INTEGER NOT NULL DEFAULT 1,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (subject_id, subject_version, section_id),
    CHECK  (section_type IN ('findings','table','metric','chart','card')),
    CHECK  (default_selected IN (0,1)),
    FOREIGN KEY (subject_id, subject_version)
        REFERENCES subjects(subject_id, version)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO subject_sections_new
SELECT id, subject_id, subject_version, section_id, title, section_type,
       default_selected, sort_order, created_at
FROM subject_sections;

DROP TABLE subject_sections;
ALTER TABLE subject_sections_new RENAME TO subject_sections;

CREATE INDEX IF NOT EXISTS idx_subject_sections_subject
    ON subject_sections (subject_id, subject_version);

COMMIT;
