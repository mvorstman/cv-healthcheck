-- =============================================================================
-- Migration 0013: internal card-section test subject (ADR 0004 phase 4)
-- =============================================================================
-- Seeds a contrived, internal subject "_card_test" with one card section that
-- exercises the field-mapped identity card AND demonstrates a card carrying a
-- status verdict, from a static JSON fixture (no lab):
--
--   - identity fields: CommCell Name / Version / Timezone / Free Space (a 4-cell
--     labeled grid) from data/test_fixtures/card_test.json (one row),
--   - a section-level verdict via the reused phase-2 threshold evaluator:
--     free_space_pct 8% <= 15% -> warning (8 > 5 so not critical).
--
-- Requires migration 0012 (widened CHECK allowing 'card'), which runs first
-- (lexicographic order). Same is_test toggle as the metric/chart test subjects
-- (subject_id prefix "_" => hidden by default). One test subject per type:
-- _metric_test / _chart_test / _card_test.
--
-- The card three-face metadata (semantic field→value mapping; presentational
-- columns grid; evaluative rule — cards ARE judged per the phase-4 steering
-- decision) plus a conformance block live in
-- subject_section_sources.extraction_instructions.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subjects
    (subject_id, version, title, description, category, category_label,
     status, created_by, preferred_source)
VALUES
    ('_card_test', 1,
     'Card Section Test',
     'Internal test subject exercising the ADR 0004 card section type (identity + status).',
     'operations', 'Operations',
     'active', 'system', 'json');


INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('_card_test', 1, '_card_test.identity',
     'Environment Identity', 'card', 1, 0);


INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('_card_test', 1, 'json', 1, NULL, NULL);


INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    '_card_test.identity',
    '{'
    || '"fixture_path":"data/test_fixtures/card_test.json",'
    || '"output_as":"card",'
    || '"conformance":{"required_fields":["host","version","timezone","free_space_pct"]},'
    || '"card":{'
    ||   '"columns":4,'
    ||   '"items":['
    ||     '{"label":"CommCell Name","field":"host"},'
    ||     '{"label":"Version","field":"version"},'
    ||     '{"label":"Timezone","field":"timezone"},'
    ||     '{"label":"Free Space","field":"free_space_pct","unit":"%"}'
    ||   '],'
    ||   '"evaluative":{'
    ||     '"rule":{"rule_id":"free_space_threshold","target_field":"free_space_pct",'
    ||     '"comparison":"<=","bands":[{"at":5,"severity":"critical"},{"at":15,"severity":"warning"}],'
    ||     '"default_severity":"good","unit":"%"}'
    ||   '}'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = '_card_test' AND ss.source_type = 'json';
