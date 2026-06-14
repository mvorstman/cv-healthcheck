-- =============================================================================
-- Migration 0036: rule ownership / classification axis (ADR-0015 D4a) — INERT
-- =============================================================================
-- D4 ("the rules registry gains a template-vs-profile axis so policy rules and
-- customer assertions stop sharing one undifferentiated namespace"), first slice.
--
-- INERT: this adds a classification dimension ONLY. It does NOT change verdict
-- composition, binding, override resolution, or firing — exactly like the
-- project_id stamp was inert when it landed. The axis becomes load-bearing in a
-- later slice (D4b, when scoping consumes it).
--
-- rule_class default is 'policy'. NOTE for D4b: default-policy is safe ONLY while
-- the axis is inert. Once the axis scopes firing, D4b must decide whether scoping
-- should REQUIRE explicit classification rather than defaulting universal — a
-- customer_assertion mis-defaulted to 'policy' would otherwise fire against every
-- customer. Not this slice's concern; flagged so D4b owns it.

ALTER TABLE rules ADD COLUMN rule_class TEXT NOT NULL DEFAULT 'policy'
    CHECK (rule_class IN ('policy', 'customer_assertion'));

-- Backfill — Step-0 classification (read-only audit, 2026-06-14). The
-- customer/person-specific assertion rules are reclassified; the policy rules
-- correctly take the 'policy' column default (so no customer_assertion silently
-- rides the default). These rules are runtime-authored (not migration-seeded), so
-- the UPDATE is a no-op on a fresh deployment and classifies the existing
-- lab/dev registry where they are present.
--   policy (default): audit_critical_retention_warning, capacity_utilisation,
--     metrics_healthcheck_service_disabled, sg_empty_group, spcj_aux_copy_pending,
--     spcj_data_not_available, spcj_job_failed, spcj_job_killed,
--     spcj_unencrypted_job, users_never_logged_in.
--   customer_assertion (below): company-/person-/naming-standard-specific.
UPDATE rules SET rule_class = 'customer_assertion' WHERE rule_id IN (
    'clients_company1_warning',     -- company eq Company_1
    'clients_company2_critical',    -- company eq Company_2
    'michiel_account_enabled',      -- person 'michiel'
    'sg_naming_convention',         -- org naming standard 'GRP_' (customer-specific)
    'sg_rommelgroep_company_1',     -- group 'rommelgroep' under Company_1
    'users_michiel_enabled_critical' -- person 'michiel'
);
