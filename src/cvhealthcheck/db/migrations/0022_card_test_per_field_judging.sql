-- =============================================================================
-- Migration 0022: _card_test — per-field card judging (phase-8 follow-on)
-- =============================================================================
-- Mirrors the metric per-field slice (0020/0021) for CARD sections: each field
-- of the card is judged independently instead of one section-level verdict.
--
-- Replaces the single section-level `evaluative.rule` (free_space_pct → warning)
-- with two per-field rules on two DISTINCT fields, using two rule KINDS:
--
--   - free_space_threshold (THRESHOLD) on free_space_pct: 8% <= 15% → warning
--     (8 > 5 so not critical). Carries a `recommendation` payload (§3a) to prove
--     the judge→recommend seam composes for card fields too — recommendation_intent
--     surfaces on this field (it fires non-muted) and is ABSENT on the other.
--   - version_presence (PRESENCE) on version: "11 SP40.47" is set → good.
--
-- Result: the card shows two independent per-field verdicts (one warning, one
-- good), and the section severity rolls up most-severe-surviving = warning
-- (DP4) — so overall artifact status is unchanged at `warning`, but the
-- provenance now lives per-field rather than section-level.
--
-- Scoped to the generic _card_test only — does NOT touch the bespoke
-- _build_environment_subject / CommCell Details (a separate later slice).
-- Resolution stays in the single engine locus inside result_to_artifact.
--
-- json_replace swaps only the card's evaluative object; items / columns /
-- conformance / fixture_path are untouched.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_replace(
        extraction_instructions,
        '$.card.evaluative',
        json('{
            "rules": [
                {"rule_id": "free_space_threshold", "target_field": "free_space_pct",
                 "kind": "threshold", "comparison": "<=",
                 "bands": [{"at": 5, "severity": "critical"}, {"at": 15, "severity": "warning"}],
                 "default_severity": "good", "unit": "%",
                 "recommendation": {"intent_kind": "remediation", "signal": "capacity.free_space",
                                    "inputs": ["free_space_pct"], "note": null}},
                {"rule_id": "version_presence", "target_field": "version", "kind": "presence",
                 "severity_when_missing": "warning", "severity_when_present": "good"}
            ]
        }'))
WHERE section_id = '_card_test.identity'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = '_card_test' AND subject_version = 1 AND source_type = 'json'
  );
