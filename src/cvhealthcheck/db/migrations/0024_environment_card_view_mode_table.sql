-- =============================================================================
-- Migration 0024: environment card view_mode = "table" (presentational, DATA)
-- =============================================================================
-- Render the CommCell Details card as a Field/Value TABLE instead of tiles. The
-- tiles-vs-table choice is DATA on the section (card.view_mode), read by the
-- generic renderer — not a hardcoded per-subject branch. It rides on the SAME
-- extraction_instructions binding that already carries card.evaluative.rules
-- (migration 0023), mirroring how rules attach as data.
--
-- "tiles" stays the default everywhere (the view builder defaults to it), so no
-- other subject changes. Only environment opts into "table" here.
--
-- Presentation only: the field set, values, hex ID, clean timezone, and the
-- per-field verdict plumbing are untouched — this just adds a layout hint.
-- json_set adds $.card.view_mode without disturbing $.card.evaluative.rules.
-- -----------------------------------------------------------------------------

UPDATE subject_section_sources
SET extraction_instructions = json_set(extraction_instructions, '$.card.view_mode', 'table')
WHERE section_id = 'environment.metadata'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'environment' AND subject_version = 1 AND source_type = 'rest'
  );
