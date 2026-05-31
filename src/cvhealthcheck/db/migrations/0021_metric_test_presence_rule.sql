-- =============================================================================
-- Migration 0021: _metric_test — first `presence` rule (rule-kind dispatch)
-- =============================================================================
-- Phase-8 follow-on (smallest slice): the engine now dispatches on rule `kind`,
-- and `presence` is the first non-threshold kind. This adds a presence rule on
-- the `purchased` field of _metric_test — independent of the existing
-- threshold rules (utilisation_threshold on utilisation_pct, used_capacity_threshold
-- on used) — so the section shows threshold + presence verdicts side by side.
--
-- purchased = 50 in the fixture → present → severity_when_present (good).
-- (severity_when_missing is declared per the presence semantics; demonstrated
-- against a missing field in tests.)
--
-- Parity: every pre-existing rule has kind "threshold" (or none → defaults to
-- threshold), so they route to the unchanged threshold evaluator — byte-identical.
-- json_replace swaps only the rules array; items/column_map/conformance untouched.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_replace(
        extraction_instructions,
        '$.metric.evaluative.rules',
        json('[
            {"rule_id": "utilisation_threshold", "target": "utilisation_pct", "kind": "threshold",
             "comparison": ">=", "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
             "default_severity": "good", "mute_on_sentinel": true},
            {"rule_id": "used_capacity_threshold", "target": "used", "kind": "threshold",
             "comparison": ">=", "bands": [{"at": 30, "severity": "critical"}], "default_severity": "good",
             "recommendation": {"intent_kind": "trend_projection", "signal": "capacity.trend",
                                "inputs": ["utilisation_pct"], "note": null}},
            {"rule_id": "purchased_presence", "target": "purchased", "kind": "presence",
             "severity_when_missing": "warning", "severity_when_present": "good"}
        ]'))
WHERE section_id = '_metric_test.capacity'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = '_metric_test' AND subject_version = 1 AND source_type = 'json'
  );
