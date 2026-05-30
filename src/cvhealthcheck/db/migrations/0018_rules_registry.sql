-- =============================================================================
-- Migration 0018: rules registry + reference-by-id (ADR 0004 phase 8 step 2)
-- =============================================================================
-- DP1: a named rule definition lives once in the `rules` table, addressed by
-- `rule_id` (DP3 flat global namespace — PRIMARY KEY enforces uniqueness, so a
-- collision is an authoring error caught at insert/migration time). Catalog
-- sections reference a rule by {"ref": rule_id, …binding…} instead of inlining
-- the body; the evaluative engine resolves the ref at canonicalization.
--
-- DP2 (registry-or-inline, NO forced migration): the resolver accepts both.
-- This migration migrates ONLY capacity_license's utilisation rule to a ref —
-- the parity-gate proof that a ref-resolved rule produces byte-identical output
-- to the inline rule. client_growth, backup_job_summary, and the
-- _metric_test/_card_test subjects keep their inline rules untouched.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rules (
    rule_id          TEXT PRIMARY KEY,           -- flat global id (DP3); PK = collision check
    definition_json  TEXT NOT NULL,              -- the rule body (kind/comparison/bands/…)
    created_by       TEXT NOT NULL DEFAULT 'system',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- The capacity_license utilisation rule, lifted verbatim from its inline body
-- (migration 0014) into the registry. The definition carries `rule_id` so a
-- ref-resolved dict is byte-identical to the inline dict the evaluator saw.
INSERT OR IGNORE INTO rules (rule_id, definition_json) VALUES
    ('capacity_utilisation', json('{
        "rule_id": "capacity_utilisation",
        "kind": "threshold",
        "comparison": ">=",
        "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
        "default_severity": "good",
        "mute_on_sentinel": true
    }'));

-- Re-point capacity_license.summary's metric.evaluative.rules from the inline
-- body to a ref. json_replace swaps only the existing rules array; the rest of
-- the binding (column_map, conformance, items, …) is untouched. The binding
-- (target) stays on the section; the rule body now comes from the registry.
UPDATE subject_section_sources
SET extraction_instructions = json_replace(
        extraction_instructions,
        '$.metric.evaluative.rules',
        json('[{"ref": "capacity_utilisation", "target": "utilisation_pct"}]'))
WHERE section_id = 'capacity_license.summary'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'capacity_license' AND subject_version = 1 AND source_type = 'rest'
  );
