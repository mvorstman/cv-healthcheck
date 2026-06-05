-- =============================================================================
-- Migration 0030: sparse domain-label backfill for active subjects (Domain Labels Phase 4)
-- =============================================================================
-- Applies the approved sparse label set (ADR-0012) to existing subjects. This is
-- a DATA migration only — no schema change, `subjects.category` is untouched.
--
-- Each assignment resolves the target by `subject_id` + `status = 'active'` at
-- apply time (NOT a hardcoded id), so it labels whatever active version row
-- exists in the catalog it runs against — `id`s differ between a fresh seed and
-- the real catalog. `INSERT OR IGNORE` makes re-application a no-op (the
-- `UNIQUE(subject_row_id, label)` from migration 0029), and a target that does
-- not exist in a given catalog resolves to zero rows (a silent no-op, not an
-- error): three targets (`audit_trail`, `metrics_reporting`, `users`) are
-- AI-authored runtime subjects present only in the real catalog, so on a fresh
-- migration-seeded catalog only the three seeded targets are labeled.
--
-- Labels attach to each target's ACTIVE version row. Per ADR-0012 they do not
-- follow a future supersede — a re-proposed version re-authors its own labels.
--
-- Approved set (8 assignments):
--   security_assessment  -> compliance, governance
--   audit_trail          -> compliance, governance
--   users                -> governance
--   metrics_reporting    -> governance
--   backup_job_summary   -> backup
--   client_growth        -> reporting
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'compliance' FROM subjects WHERE subject_id = 'security_assessment' AND status = 'active';
INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'governance' FROM subjects WHERE subject_id = 'security_assessment' AND status = 'active';

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'compliance' FROM subjects WHERE subject_id = 'audit_trail' AND status = 'active';
INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'governance' FROM subjects WHERE subject_id = 'audit_trail' AND status = 'active';

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'governance' FROM subjects WHERE subject_id = 'users' AND status = 'active';

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'governance' FROM subjects WHERE subject_id = 'metrics_reporting' AND status = 'active';

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'backup' FROM subjects WHERE subject_id = 'backup_job_summary' AND status = 'active';

INSERT OR IGNORE INTO subject_domain_labels (subject_row_id, label)
SELECT id, 'reporting' FROM subjects WHERE subject_id = 'client_growth' AND status = 'active';
