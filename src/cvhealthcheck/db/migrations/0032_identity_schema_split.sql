-- =============================================================================
-- Migration 0032: identity-schema split (Fix 3, ADR-0015 profile layer)
-- =============================================================================
-- The three identity values were conflated on the customers row — most visibly
-- commcell_hostname carrying a reach URL while commcell_id sometimes held a
-- NAME label (default.commcell_id = 'SMOKE-TEST-CS'). This migration adds the
-- columns that keep them distinct; it does NOT guess at mislabelled data.
--
-- Five additive columns:
--   connection_url    — the WebServer/gateway base URL the app reaches (reach).
--   commserve_name    — human/product CommServe identity label, e.g. CS01.
--   registration_code — license-bound secondary verifier (8C8-CE7-EE39 style).
--   rp_server_url     — optional separate Reports Plus / Metrics server URL.
--   rp_scoping_id     — optional resolved CommServUniqueId / datasource id.
--
-- Data move (URL-SHAPED ONLY): commcell_hostname values that parse as http(s)
-- URLs migrate to connection_url. Non-URL values are deliberately NOT moved —
-- they are flagged for manual fix (db.customers.legacy_hostname_review_flags),
-- never guessed. On the current lab data both non-NULL hostnames are URL-shaped,
-- so zero rows are expected to flag; the flag path ships regardless.
--
-- commcell_hostname becomes READ-ONLY-LEGACY from this point: no code path
-- writes it post-migration (the customers page writes connection_url). It is
-- frozen at its migration-time value and dropped in a later explicit cleanup
-- (which also removes the read-time fallback). NOTHING is backfilled by guess:
-- default.commcell_id = 'SMOKE-TEST-CS' (a name in the id column) and
-- test_customer_1.commcell_id = '33f7' (a suspected transposition of 337f) stay
-- exactly as they are, for manual correction once the columns exist.
-- =============================================================================

ALTER TABLE customers ADD COLUMN connection_url    TEXT;
ALTER TABLE customers ADD COLUMN commserve_name    TEXT;
ALTER TABLE customers ADD COLUMN registration_code TEXT;
ALTER TABLE customers ADD COLUMN rp_server_url     TEXT;
ALTER TABLE customers ADD COLUMN rp_scoping_id     TEXT;

UPDATE customers
   SET connection_url = commcell_hostname
 WHERE commcell_hostname LIKE 'http://%'
    OR commcell_hostname LIKE 'https://%';
