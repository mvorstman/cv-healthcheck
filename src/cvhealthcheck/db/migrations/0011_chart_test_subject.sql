-- =============================================================================
-- Migration 0011: internal chart-section test subject (ADR 0004 phase 3)
-- =============================================================================
-- Seeds a contrived, internal subject "_chart_test" with TWO chart sections
-- that exercise the single chart_type-discriminated renderer across BOTH data
-- shapes, from static JSON fixtures (no lab):
--
--   - LINE: multi-series over a shared X (months) — Added + Total client trend
--     (data/test_fixtures/chart_test_trend.json).
--   - PIE: single proportional series — job status breakdown
--     (data/test_fixtures/chart_test_status.json).
--
-- One renderer handles both; chart_type discriminates. Same is_test toggle as
-- the phase-2 metric test subject (subject_id prefix "_" => hidden by default).
-- One test subject per section type (metric: _metric_test; chart: _chart_test).
--
-- The chart three-face metadata (presentational chart_type + axes; semantic
-- column→labels/series mapping; evaluative empty for charts) plus a conformance
-- block live in subject_section_sources.extraction_instructions.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subjects
    (subject_id, version, title, description, category, category_label,
     status, created_by, preferred_source)
VALUES
    ('_chart_test', 1,
     'Chart Section Test',
     'Internal test subject exercising the ADR 0004 chart section type (line + pie).',
     'operations', 'Operations',
     'active', 'system', 'json');


INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('_chart_test', 1, '_chart_test.trend',
     'Client Trend (line)', 'chart', 1, 0),
    ('_chart_test', 1, '_chart_test.status',
     'Job Status (pie)', 'chart', 1, 1);


INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('_chart_test', 1, 'json', 1, NULL, NULL);


-- Line chart section
INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    '_chart_test.trend',
    '{'
    || '"fixture_path":"data/test_fixtures/chart_test_trend.json",'
    || '"output_as":"chart",'
    || '"conformance":{"required_fields":["month","added","total"]},'
    || '"chart":{'
    ||   '"chart_type":"line",'
    ||   '"x_axis":{"label":"Month"},'
    ||   '"y_axis":{"label":"Clients"},'
    ||   '"labels":{"source":"column","column":"month"},'
    ||   '"series":['
    ||     '{"id":"added","label":"Added","source":"column","column":"added"},'
    ||     '{"id":"total","label":"Total","source":"column","column":"total"}'
    ||   ']'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = '_chart_test' AND ss.source_type = 'json';


-- Pie chart section
INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    '_chart_test.status',
    '{'
    || '"fixture_path":"data/test_fixtures/chart_test_status.json",'
    || '"output_as":"chart",'
    || '"conformance":{"required_fields":["status","count"]},'
    || '"chart":{'
    ||   '"chart_type":"pie",'
    ||   '"labels":{"source":"column","column":"status"},'
    ||   '"series":[{"id":"breakdown","label":"Jobs","source":"column","column":"count"}]'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = '_chart_test' AND ss.source_type = 'json';
