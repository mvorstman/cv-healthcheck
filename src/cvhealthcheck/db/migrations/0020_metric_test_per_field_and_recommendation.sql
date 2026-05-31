-- =============================================================================
-- Migration 0020: _metric_test — per-field rules + first recommend-seam exercise
-- =============================================================================
-- Phase-8 follow-on (smallest slice): two fields of the _metric_test metric
-- section judged independently, and the first exercise of the judge→recommend
-- seam (recommend-seam-contract.md §3a/§3b).
--
-- Adds a per-field threshold rule on `used` (fires CRITICAL on the fixture's
-- used=35) carrying a `recommendation` payload (§3a). The pre-existing
-- `utilisation_threshold` rule on `utilisation_pct` is kept UNCHANGED and has NO
-- recommendation — so the section shows two independent per-field verdicts, and
-- recommendation_intent surfaces on `used` only (absent on the un-declared
-- utilisation_pct field).
--
-- Threshold kind only (no presence/format/enum this slice). No card changes.
-- Resolution stays in the single engine locus inside result_to_artifact.
--
-- Demo-override note: the render-demo override seeded in data/app.db targets
-- `utilisation_threshold` (mutes utilisation_pct in the running workspace). It
-- does NOT touch `used`, so the recommendation-bearing field is unaffected by
-- it. In tests (no override) utilisation_pct is `warning`; in the running app it
-- is `muted` — either way `used` is `critical` + carries recommendation_intent.
--
-- json_replace swaps only the rules array; the rest of the binding (items,
-- column_map, conformance) is untouched.
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
                                "inputs": ["utilisation_pct"], "note": null}}
        ]'))
WHERE section_id = '_metric_test.capacity'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = '_metric_test' AND subject_version = 1 AND source_type = 'json'
  );
