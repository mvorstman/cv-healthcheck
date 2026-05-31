-- =============================================================================
-- Migration 0019: rule_overrides — the override layer's storage (ADR 0004 phase 8 step 3, DP10)
-- =============================================================================
-- An override is a per-assessment waiver/adjustment of a rule's verdict.
--
-- DP10 (RESOLVED against the live entity model): the scope key is
--   (customer_id, project_id?, subject_id, subject_version, section_id, rule_id).
-- project_id is the default scope ("this assessment"); a customer-wide standing
-- waiver is the deliberate exception, written with project_id IS NULL. The
-- design draft's engagement_id keyed a DEAD table (the engagements orphan,
-- backlog #13 — never populated), which would have made every override silently
-- customer-wide; project_id is the entity that actually exists (customer 1→N
-- project 1→N finalization; artifacts attach to a project's working state).
--
-- DP5: an override carries severity AND reason (the reason is the audit value,
-- e.g. "waived for Acme burst window"). DP13: severity may be any value incl.
-- 'muted' (deliberate-mute).
--
-- Resolution into the verdict_chain happens at canonicalization (working state)
-- only; finalized artifacts are read as-stored and never re-resolved against
-- current overrides (ADR 0006). Additive table; no seed (no production overrides
-- — the new-behavior tests seed their own).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rule_overrides (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      TEXT    NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    -- NULL = customer-wide standing waiver (the deliberate broad exception);
    -- non-NULL = scoped to this assessment (the default).
    project_id       TEXT    REFERENCES projects(project_id) ON DELETE CASCADE,
    subject_id       TEXT    NOT NULL,
    subject_version  INTEGER NOT NULL DEFAULT 1,
    section_id       TEXT    NOT NULL,
    rule_id          TEXT    NOT NULL,
    severity         TEXT    NOT NULL,   -- critical | warning | info | good | muted
    reason           TEXT    NOT NULL,   -- audit value (DP5)
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    created_by       TEXT,
    -- One override per scope+rule. (SQLite treats NULL project_ids as distinct,
    -- so a customer-wide row and a project-specific row for the same rule_id
    -- coexist; the loader prefers the project-specific one.)
    UNIQUE (customer_id, project_id, subject_id, subject_version, section_id, rule_id),
    CHECK  (severity IN ('critical','warning','info','good','muted'))
);

CREATE INDEX IF NOT EXISTS idx_rule_overrides_scope
    ON rule_overrides (customer_id, subject_id, subject_version, section_id);
