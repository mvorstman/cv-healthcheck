-- =============================================================================
-- Migration 0025: internal nested-path / hex-coercion test subject (ADR 0007 ph1)
-- =============================================================================
-- Seeds a contrived, internal subject "_nested_test" that proves ADR 0007's two
-- new extract-stage capabilities in isolation, on a dedicated test subject —
-- mirroring how _metric_test / _chart_test / _card_test de-risked ADR 0004:
--
--   D2 — nested-path field selector: card item `field` may be a dot-path
--        (commcell.commCellName, csTimeZone.TimeZoneName) resolved through nested
--        dicts by the shared field resolver.
--   D3 — hex coercion: `type: "hex"` formats an integer as lowercase hex with no
--        "0x" prefix (13183 -> "337f"); the raw integer is kept on the item.
--
-- One card section from a single nested JSON record
-- (data/test_fixtures/nested_test.json). This deliberately mirrors environment's
-- two hard fields (nested Timezone + hex CommCell ID) so Phase 1 de-risks exactly
-- them. _card_test stays the flat-path oracle and is untouched.
--
-- Same is_test toggle as the other test subjects (subject_id prefix "_" => hidden
-- by default). No conformance block — Phase 1 is purely the D2/D3 capability.
-- -----------------------------------------------------------------------------

INSERT OR IGNORE INTO subjects
    (subject_id, version, title, description, category, category_label,
     status, created_by, preferred_source)
VALUES
    ('_nested_test', 1,
     'Nested Path Test',
     'Internal test subject exercising ADR 0007 nested-path field reads + hex coercion.',
     'operations', 'Operations',
     'active', 'system', 'json');


INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('_nested_test', 1, '_nested_test.identity',
     'Nested Identity', 'card', 1, 0);


INSERT OR IGNORE INTO subject_sources
    (subject_id, subject_version, source_type, extractable,
     non_extractable_reason, recognition_hints)
VALUES
    ('_nested_test', 1, 'json', 1, NULL, NULL);


INSERT OR IGNORE INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT
    ss.id,
    '_nested_test.identity',
    '{'
    || '"fixture_path":"data/test_fixtures/nested_test.json",'
    || '"output_as":"card",'
    || '"card":{'
    ||   '"columns":3,'
    ||   '"items":['
    ||     '{"label":"CommCell Name","field":"commcell.commCellName"},'
    ||     '{"label":"CommCell ID","field":"commcell.commCellId","type":"hex"},'
    ||     '{"label":"Timezone","field":"csTimeZone.TimeZoneName"}'
    ||   ']'
    || '}'
    || '}'
FROM subject_sources ss
WHERE ss.subject_id = '_nested_test' AND ss.source_type = 'json';
