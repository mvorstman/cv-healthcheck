-- =============================================================================
-- Migration 0029: domain-label vocabulary + subject association (Domain Labels Phase 1)
-- =============================================================================
-- Adds a second, additive classification axis for subjects. `subjects.category`
-- stays the single / primary classification (exactly one per subject version);
-- `domain_label` is a controlled vocabulary of many / additive labels, attached
-- to subject rows through the `subject_domain_labels` association.
--
-- Phase 1 is schema + seed ONLY:
--   * `domain_label` is seeded with four terms (compliance / governance /
--     backup / reporting).
--   * NO subject is labeled — `subject_domain_labels` is created empty;
--     backfilling subject -> label assignments is a later phase.
--   * The FK on `subject_domain_labels.label` is the structural guard that an
--     unknown label can never be associated; the authoring-side "reject unknown
--     label" check lands in a later phase.
--
-- The domain-label vocabulary is disjoint from the `category` vocabulary
-- (identity / security / licensing / performance / operations / storage), so the
-- two axes never collide — additive-only by construction (asserted in tests).
-- -----------------------------------------------------------------------------

-- The controlled vocabulary of domain labels.
CREATE TABLE IF NOT EXISTS domain_label (
    label          TEXT    PRIMARY KEY,   -- slug, e.g. 'compliance'
    display_label  TEXT    NOT NULL,      -- display form, e.g. 'Compliance'
    description    TEXT,                  -- optional human description
    sort_order     INTEGER                -- optional ordering hint
);

-- Many-to-many association between a subject version row and a domain label.
-- subject_row_id -> subjects.id (the per-(subject_id, version) row). Deleting a
-- subject version removes its label associations (ON DELETE CASCADE), matching
-- the codebase's child-cleanup convention. The label FK has no cascade: a
-- vocabulary term that is in use cannot be silently removed.
CREATE TABLE IF NOT EXISTS subject_domain_labels (
    subject_row_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    label           TEXT    NOT NULL REFERENCES domain_label(label),
    UNIQUE (subject_row_id, label)
);

CREATE INDEX IF NOT EXISTS idx_subject_domain_labels_label
    ON subject_domain_labels (label);

-- Seed the vocabulary — exactly four terms. No subject_domain_labels rows are
-- inserted (backfill is a later phase).
INSERT OR IGNORE INTO domain_label (label, display_label, sort_order) VALUES
    ('compliance', 'Compliance', 1),
    ('governance', 'Governance', 2),
    ('backup',     'Backup',     3),
    ('reporting',  'Reporting',  4);
