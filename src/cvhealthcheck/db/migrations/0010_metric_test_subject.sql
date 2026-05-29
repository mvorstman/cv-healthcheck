-- =============================================================================
-- Migration 0010: internal metric-section test subject (ADR 0004 phase 2)
-- =============================================================================
-- Seeds a contrived, internal subject "_metric_test" whose single metric
-- section exercises the full phase-2 metric pipeline against a static JSON
-- fixture (data/test_fixtures/metric_test.json) — no lab dependency:
--
--   - multi-field metric (used / purchased / prev_active),
--   - a CEL-derived value (utilisation_pct = used / purchased * 100.0),
--   - a sentinel case (prev_active_capacity = -1 -> "n/a"),
--   - a template-default threshold rule (warn >= 70, critical >= 90) that
--     fires (latest used 35 / purchased 50 = 70% -> warning).
--
-- The subject_id prefix "_" marks it as an internal/test subject; it is hidden
-- in the workspace sidebar unless the settings-page "show test subjects"
-- toggle is on. It exercises the SAME shape of work capacity_license needs in
-- phase 5, so the metric implementation is validated against realistic
-- complexity, not a trivial case.
--
-- The metric three-face metadata (semantic / items / evaluative) and the
-- conformance block live in subject_section_sources.extraction_instructions —
-- the same flexible catalog payload phase 1's conformance used. (Note for the
-- eventual catalog-vs-code review: this is the second concept living there.)
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subjects
    (subject_id, version, title, description, category, category_label,
     status, created_by, preferred_source)
VALUES
    ('_metric_test', 1,
     'Metric Section Test',
     'Internal test subject exercising the ADR 0004 metric section type.',
     'operations', 'Operations',
     'active', 'system', 'json');


INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('_metric_test', 1, '_metric_test.capacity',
     'Capacity Utilisation', 'metric', 1, 0);


INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('_metric_test', 1, 'json', 1, NULL, NULL);


INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    '_metric_test.capacity',
    '{'
    || '"fixture_path":"data/test_fixtures/metric_test.json",'
    || '"output_as":"metric",'
    || '"conformance":{'
    ||   '"required_fields":["month","used_capacity","purchased_capacity","prev_active_capacity"],'
    ||   '"field_types":{"used_capacity":"number","purchased_capacity":"number"}'
    || '},'
    || '"metric":{'
    ||   '"semantic":{"sentinel":-1},'
    ||   '"items":['
    ||     '{"id":"used","label":"Used","unit":"TB","source":"field","field":"used_capacity"},'
    ||     '{"id":"purchased","label":"Purchased","unit":"TB","source":"field","field":"purchased_capacity"},'
    ||     '{"id":"prev_active","label":"Prev Active","unit":"TB","source":"field","field":"prev_active_capacity"},'
    ||     '{"id":"utilisation_pct","label":"Utilisation","unit":"%","source":"cel","expr":"used / purchased * 100.0","derived":true}'
    ||   '],'
    ||   '"evaluative":{'
    ||     '"rules":['
    ||       '{"rule_id":"utilisation_threshold","target":"utilisation_pct","kind":"threshold",'
    ||       '"comparison":">=","bands":[{"at":90,"severity":"critical"},{"at":70,"severity":"warning"}],'
    ||       '"default_severity":"good","mute_on_sentinel":true}'
    ||     ']'
    ||   '}'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = '_metric_test' AND ss.source_type = 'json';
