-- =============================================================================
-- Migration 0033: project_id on staged_artifacts (evidence-context foundation)
-- =============================================================================
-- staged_artifacts already records customer_id (D5); it does not record the
-- PROJECT the evidence was staged under. Adding project_id completes the
-- creation-context stamp so approval can read the row's own (customer, project)
-- as authority for an artifact, instead of relying solely on the approver's
-- ambient context.
--
-- Additive and nullable: legacy rows (and all subject_proposal rows, which are
-- catalog-global by design) stay NULL. No backfill — a NULL project_id keeps
-- the existing D5 approval behaviour (approval-supplied context is authority).
-- =============================================================================

ALTER TABLE staged_artifacts ADD COLUMN project_id TEXT;
