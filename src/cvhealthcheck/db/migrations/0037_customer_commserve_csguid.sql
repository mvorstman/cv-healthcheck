-- =============================================================================
-- Migration 0037: customer declared CommServe csGUID (Fix-4 namespace-precision)
-- =============================================================================
-- The Fix-4 identity verdict moves from the cross-namespace CommCell ID
-- (declared LICENSED `337f` vs wire INTERNAL `2`, which false-mismatched the
-- legitimate customer) to the CommServe **csGUID** — a single stable namespace
-- already in the /CommServ payload. This adds the DECLARED side of that compare.
--
-- Nullable + additive: a row with no declared GUID verifies as `attested` (no
-- proof possible), never mismatch. Populated either by TOFU (the live collect
-- records the wire csGUID on the first verified connect, set-once) or manually on
-- the customer form. A CHANGED GUID is a signal (surfaces as mismatch), not an
-- auto-update — TOFU never overwrites an existing value.

ALTER TABLE customers ADD COLUMN commserve_csguid TEXT;
