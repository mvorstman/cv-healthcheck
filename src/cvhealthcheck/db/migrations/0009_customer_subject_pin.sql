-- =============================================================================
-- Migration 0009: customer_subject_pin — per-customer template version pinning
-- =============================================================================
-- ADR 0004 phase 1 (Foundation). Subject versioning lands v2+ as new subject
-- rows with a "_vN" suffix on the subject_id (capacity_license_v2). The
-- "family" is the subject_id with the suffix stripped. The source-tile
-- version dropdown lets a consultant choose which version the NEXT collection
-- of a subject family uses.
--
-- Per the phase-1 steering decision, that choice is pinned PER CUSTOMER:
-- one pinned version per (customer, subject family). Collection reads the pin
-- for the active customer; if none is pinned, it falls back to the latest
-- version in the family. The dropdown writes a row here when the selection
-- changes.
--
-- Today every subject family has exactly one version, so this table is empty
-- in practice and every resolution falls through to "the only version". The
-- infrastructure lands now; v2 of any subject arrives in a later phase.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS customer_subject_pin (
    customer_id        TEXT NOT NULL
                            REFERENCES customers(customer_id),
    subject_family     TEXT NOT NULL,    -- subject_family(subject_id), e.g. "capacity_license"
    pinned_subject_id  TEXT NOT NULL,    -- the chosen version, e.g. "capacity_license_v2"
    updated_at         TEXT NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    PRIMARY KEY (customer_id, subject_family)
);

CREATE INDEX IF NOT EXISTS idx_customer_subject_pin_customer
    ON customer_subject_pin (customer_id);
