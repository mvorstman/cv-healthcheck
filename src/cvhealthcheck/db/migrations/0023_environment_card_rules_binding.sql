-- =============================================================================
-- Migration 0023: environment card rules as DATA (move out of the Python literal)
-- =============================================================================
-- Option A — the environment / CommCell Details identity card now reads its
-- per-field evaluative rules from a catalog binding, not from a Python literal
-- in _build_environment_identity_section. This closes the ONE place in the
-- codebase where an evaluative rule was hardcoded (the survey's finding).
--
-- environment is bespoke (ADR 0001 source-building fork): it sources its card
-- VALUES live from commserv.json and renders a custom view shape, so it has had
-- NO subject_section_sources binding (0 bindings — see migration 0003). This adds
-- exactly one binding row, carrying ONLY the evaluative.rules (the card's items
-- and values stay in the builder / live-sourced from commserv.json). The builder
-- reads card.evaluative.rules off this row and feeds the SAME generic
-- build_card_section path every other subject uses.
--
-- Rules authored AS DATA (mirrors the _card_test precedent, migration 0022):
--   - environment_version_presence (presence)  — MOVED from the Python literal.
--   - environment_timezone_enum    (enum)      — allowed_values ABSENT for now.
--   - environment_name_format      (format)    — pattern ABSENT for now.
--
-- Empty allowed_values/pattern is intentional: per migration cd4a777's evaluators,
-- enum/format with no spec return `good` and never raise, so these render SAFE
-- (good, no badge-of-concern) until the expected values are supplied later via a
-- (future) edit surface / per-customer override.
--
-- The binding rides environment's existing `rest` source (subject_sources row
-- seeded in 0003) and its existing section_id 'environment.metadata'.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    'environment.metadata',
    json('{
        "card": {
            "evaluative": {
                "rules": [
                    {"rule_id": "environment_version_presence", "target_field": "version",
                     "kind": "presence", "severity_when_missing": "warning",
                     "severity_when_present": "good"},
                    {"rule_id": "environment_timezone_enum", "target_field": "timezone",
                     "kind": "enum"},
                    {"rule_id": "environment_name_format", "target_field": "name",
                     "kind": "format"}
                ]
            }
        }
    }')
FROM subject_sources ss
WHERE ss.subject_id = 'environment'
  AND ss.subject_version = 1
  AND ss.source_type = 'rest';
