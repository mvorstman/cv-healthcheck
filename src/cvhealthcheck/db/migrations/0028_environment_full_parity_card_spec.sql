-- =============================================================================
-- Migration 0028: environment command-center card — FULL 9-field parity spec
-- + retargeted per-field rules (ADR 0007 Phase 3)
-- =============================================================================
-- Replace the PROVISIONAL 3-field spec migration 0026/0027 put on environment's
-- rest_command_center_api binding (environment.metadata) with the FULL 9-field
-- parity spec that mirrors the live-served identity card built by
-- _build_environment_subject / _build_environment_identity_section. Goal: the
-- STORED command-center artifact becomes a parity replacement for the live card.
--
-- FIELD MAPPING (live builder flat key -> declarative dot-path on the real GET
-- /commandcenter/api/CommServ `.raw` nested dict — verified all 9 resolve):
--   CommCell Name        -> commcell.commCellName
--   CommCell ID          -> commcell.commCellId   (type:hex, ADR 0007 D3; 2 -> "2")
--   CommCell GUID        -> commcell.csGUID
--   Version              -> csVersionInfo
--   OS Type              -> osType
--   Current SP Version   -> currentSPVersion
--   Installed SP Version -> installedSPVersion
--   Timezone             -> csTimeZone.TimeZoneName   (real response is already
--                           the clean IANA name; the live builder's
--                           _normalize_timezone "0:0:" strip is a defensive no-op
--                           on real data — declarative parity holds on real data)
--   Hostname             -> hostName
--
-- RULES (retargeted from the row-7 live-card binding's flat keys to row-22's
-- dot-path field ids; rules bind by target_field == an item's `field`):
--   environment_version_presence : version  -> csVersionInfo            (presence)
--   environment_timezone_enum    : timezone -> csTimeZone.TimeZoneName   (enum)
--   environment_name_format      : name     -> commcell.commCellName     (format)
-- All three are inline (no registry ref) and non-threshold; on the real data they
-- fire good / good / good (version set; enum has no allowed-set -> safe-good;
-- format has no pattern -> safe-good) — matching the live card's roll-up.
--
-- IDEMPOTENT + FK-SAFE: a pure UPDATE of one binding row's extraction_instructions
-- to a fixed value (no table rebuild, no FK touch). Re-running is a no-op; on a
-- fresh DB it upgrades 0027's provisional 3-field spec to the 9-field spec.
--
-- NOTE (view_mode): the spec carries "view_mode":"table" as the declared parity
-- intent, but the STORED-artifact render path (canonical_view.artifact_to_view ->
-- _card_section_view) currently hardcodes "tiles" and does NOT thread a section
-- view_mode, so the stored card renders as tiles today. Threading view_mode into
-- the artifact render path is a separate follow-on; it is outside this slice's
-- hard parity gate (9 fields + 3 firing rules with correct severities).
--
-- NOTE (retire): this migration does NOT retire _build_environment_subject. The
-- live builder also authors environment's rest_command_center_api SOURCE tile +
-- Collect button + Endpoint/Host meta, which get_tiles()/_build_generic_sources
-- do not yet surface for the command-center source. Retiring the builder ripples
-- into that source-tile wiring and is steered separately.
-- =============================================================================

UPDATE subject_section_sources
SET extraction_instructions =
    '{'
    || '"output_as":"card",'
    || '"card":{'
    ||   '"columns":4,'
    ||   '"view_mode":"table",'
    ||   '"items":['
    ||     '{"label":"CommCell Name","field":"commcell.commCellName"},'
    ||     '{"label":"CommCell ID","field":"commcell.commCellId","type":"hex"},'
    ||     '{"label":"CommCell GUID","field":"commcell.csGUID"},'
    ||     '{"label":"Version","field":"csVersionInfo"},'
    ||     '{"label":"OS Type","field":"osType"},'
    ||     '{"label":"Current SP Version","field":"currentSPVersion"},'
    ||     '{"label":"Installed SP Version","field":"installedSPVersion"},'
    ||     '{"label":"Timezone","field":"csTimeZone.TimeZoneName"},'
    ||     '{"label":"Hostname","field":"hostName"}'
    ||   '],'
    ||   '"evaluative":{"rules":['
    ||     '{"rule_id":"environment_version_presence","target_field":"csVersionInfo",'
    ||       '"kind":"presence","severity_when_missing":"warning","severity_when_present":"good"},'
    ||     '{"rule_id":"environment_timezone_enum","target_field":"csTimeZone.TimeZoneName","kind":"enum"},'
    ||     '{"rule_id":"environment_name_format","target_field":"commcell.commCellName","kind":"format"}'
    ||   ']}'
    || '}'
    || '}'
WHERE section_id = 'environment.metadata'
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'environment'
        AND subject_version = 1
        AND source_type = 'rest_command_center_api'
  );
