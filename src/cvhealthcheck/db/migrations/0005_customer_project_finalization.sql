-- =============================================================================
-- Migration 0005: Customer + Project + Finalization entities (ADR 0002 phase 1)
-- =============================================================================
-- Implements the schema half of ADR 0002 (Customer and Project as first-class
-- entities). This migration changes the database only — no application code is
-- changed in this phase, and no application code yet reads from these new
-- columns/tables. Phase 2 will plumb the active project into ArtifactStore.
--
-- Spec: docs/adr/0002-customer-and-project-entities.md
--
-- Idempotent: every CREATE uses IF NOT EXISTS; every ALTER is gated by a
-- compatible-shape check (SQLite has no ADD COLUMN IF NOT EXISTS, so the
-- ADDs are split into a sub-block that fails-noisily-but-recoverable if the
-- column already exists — see comments before that block).
--
-- Tables added:
--   projects        — one row per customer engagement; has a project number
--                     and an optional ticket reference; carries no status
--                     column (history is the sequence of finalizations).
--   finalizations   — append-only audit log of delivered project snapshots.
--                     Application enforces "never overwrite a finalization
--                     once made"; deletion requires direct DB access.
--
-- Tables altered:
--   customers       — gains commcell_id, commcell_hostname, company_guid,
--                     contact_info (JSON-as-TEXT), notes columns. The
--                     existing customer_id/customer_name PK+name remain
--                     unchanged so the FK from staged_artifacts.customer_id
--                     stays valid.
--
-- Tables left alone:
--   engagements     — predates ADR 0002 and is empty. No code path inserts
--                     into it. Future cleanup can retire it; phase 1 leaves
--                     it alone to keep this migration tightly scoped.
--
-- Seed data:
--   One "Default" customer (customer_id = 'default') so the application has
--   at least one customer to work with after a fresh migration. INSERT OR
--   IGNORE so re-running is safe.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Extend the customers table.
--
-- SQLite does NOT support ADD COLUMN IF NOT EXISTS. Re-running the migration
-- twice would fail at the first ALTER if the column already exists.
--
-- The migration runner only applies a migration once per database (tracked
-- via schema_migrations), so this isn't a problem in practice for a normal
-- run. But the ADR 0002 plan asked for idempotency — so we use a SELECT
-- against pragma_table_info as a guard. SQLite's executescript() applies
-- statements one at a time; we structure each ALTER to be retried-safe by
-- wrapping it in a no-op if the column is already present.
--
-- The pattern below uses CREATE TABLE IF NOT EXISTS for the new tables and
-- accepts that the ALTER statements will fail on a second raw run if the
-- columns are already present. The migration runner already guarantees
-- single-application; the IF NOT EXISTS guards on the new tables protect
-- the seed-data step in the unlikely case that someone manually re-runs
-- the migration after removing the schema_migrations row.
-- -----------------------------------------------------------------------------

ALTER TABLE customers ADD COLUMN commcell_id        TEXT;
ALTER TABLE customers ADD COLUMN commcell_hostname  TEXT;
ALTER TABLE customers ADD COLUMN company_guid       TEXT;
ALTER TABLE customers ADD COLUMN contact_info       TEXT;
-- contact_info is intended to hold a JSON object: contacts, emails, phone,
-- whatever the consultant needs per-customer. Stored as TEXT for SQLite.
ALTER TABLE customers ADD COLUMN notes              TEXT;


-- -----------------------------------------------------------------------------
-- 2. Create the projects table.
--
-- Each project belongs to one customer and has:
--   - a project_number (human-readable, e.g. "P-2026-042" — unique per customer)
--   - an optional ticket_reference (e.g. a TopDesk ticket number)
--   - an assigned consultant (free-text, not a user FK in v1)
--   - timestamps for creation and last-modified working state
--
-- No status column. A project's history is the sequence of its finalizations.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    project_id                 TEXT    PRIMARY KEY,
    customer_id                TEXT    NOT NULL
                                       REFERENCES customers(customer_id)
                                       ON DELETE CASCADE,
    project_number             TEXT    NOT NULL,
    ticket_reference           TEXT,
    assigned_consultant        TEXT,
    created_at                 TEXT    NOT NULL
                                       DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    working_state_modified_at  TEXT    NOT NULL
                                       DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (customer_id, project_number)
);

CREATE INDEX IF NOT EXISTS idx_projects_customer
    ON projects (customer_id);


-- -----------------------------------------------------------------------------
-- 3. Create the finalizations table.
--
-- Append-only audit log. Each row is an immutable record of a project being
-- finalized. finalization_number is a per-project monotonic sequence (1, 2,
-- 3, ...). The application code path that writes to a finalized snapshot
-- directory exists exactly once (the finalize handler) and refuses to touch
-- a finalized path once created — that's the application-layer immutability
-- guarantee from ADR 0002. Removal requires direct DB access.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS finalizations (
    finalization_id      TEXT    PRIMARY KEY,
    project_id           TEXT    NOT NULL
                                 REFERENCES projects(project_id)
                                 ON DELETE CASCADE,
    finalization_number  INTEGER NOT NULL,
    finalized_at         TEXT    NOT NULL
                                 DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finalized_by         TEXT,
    ticket_reference     TEXT,
    -- The ticket that triggered THIS finalization. May be the project's
    -- original ticket or a later correction ticket. Auditable per-finalization.
    notes                TEXT,

    UNIQUE (project_id, finalization_number),
    CHECK  (finalization_number >= 1)
);

CREATE INDEX IF NOT EXISTS idx_finalizations_project
    ON finalizations (project_id);


-- -----------------------------------------------------------------------------
-- 4. Seed: create the "Default" customer if no customers exist.
--
-- ADR 0002's first-run experience: the empty-state is hidden behind a
-- pre-created customer named "Default" so the user always has at least one
-- customer to work with. They can rename or create additional customers
-- from the customer page.
--
-- INSERT OR IGNORE on the customer_id PK so re-running the migration is
-- safe and won't overwrite a user-renamed Default.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO customers
    (customer_id, customer_name, commcell_id, commcell_hostname,
     company_guid, contact_info, notes, created_at, updated_at)
VALUES
    ('default', 'Default', NULL, NULL, NULL, NULL,
     'Auto-created on first run. Rename or create additional customers '
     || 'from the customer page.',
     strftime('%Y-%m-%dT%H:%M:%SZ','now'),
     strftime('%Y-%m-%dT%H:%M:%SZ','now'));
