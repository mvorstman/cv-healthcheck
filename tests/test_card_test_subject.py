"""ADR 0004 phase 4 (4h + 4d) — the seeded _card_test subject collects an
identity card carrying a status verdict via FixtureExtractor, and card sections
run the phase-1 conformance check."""
import json
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity
from cvhealthcheck.artifacts.models import CanonicalArtifact, CardSection
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_card_test_subject_per_field_judging(migrated_db_path: Path):
    """Phase-8 follow-on: _card_test now judges each field independently
    (migration 0022) — a threshold verdict on free_space_pct AND a presence
    verdict on version, each on its own CardItem, with the section severity
    rolled up from them."""
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_card_test", 1)
    finally:
        conn.close()
    assert not result.errors
    assert result.section_output_types["_card_test.identity"] == "card"

    artifact = result_to_artifact(result, "_card_test", "Card Section Test")
    CanonicalArtifact.model_validate(artifact.model_dump())
    card = next(s for s in artifact.sections if isinstance(s, CardSection))

    labels = {i.label: i for i in card.items}
    assert labels["CommCell Name"].value == "cs01.lab.local"
    assert labels["Version"].value == "11 SP40.47"
    assert labels["Free Space"].value == 8.0 and labels["Free Space"].unit == "%"
    assert card.columns == 4

    # Two independent per-field verdicts, two different rule kinds.
    free = labels["Free Space"]
    assert free.severity == FindingSeverity.warning          # 8% <= 15% (threshold)
    assert free.verdict_chain[0].layer == "template_default"
    assert free.verdict_chain[0].rule_id == "free_space_threshold"

    version = labels["Version"]
    assert version.severity == FindingSeverity.good          # "11 SP40.47" is set (presence)
    assert version.verdict_chain[0].rule_id == "version_presence"
    assert version.verdict_chain[0].reason == "Version is set"

    # Unjudged identity fields carry no verdict.
    assert labels["CommCell Name"].severity is None
    assert labels["Timezone"].severity is None

    # Section severity rolls up most-severe-surviving = warning; the per-field
    # chains hold the provenance, so the section chain stays empty.
    assert card.severity == FindingSeverity.warning
    assert card.verdict_chain == []
    assert artifact.summary.status == ArtifactStatus.warning


def test_card_test_subject_recommendation_seam_per_field(migrated_db_path: Path):
    """Recommend seam composes for card fields: the free_space rule declares a
    recommendation payload, so recommendation_intent surfaces on that field
    only — absent on the presence-judged field and on unjudged fields (SC4)."""
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_card_test", 1)
    finally:
        conn.close()
    artifact = result_to_artifact(result, "_card_test", "Card Section Test")
    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    labels = {i.label: i for i in card.items}

    intent = labels["Free Space"].recommendation_intent
    assert intent is not None
    assert intent.intent_kind == "remediation"
    assert intent.signal == "capacity.free_space"
    assert intent.inputs_resolved == {"free_space_pct": 8.0}

    # Declaring-field only — absent elsewhere.
    assert labels["Version"].recommendation_intent is None
    assert labels["CommCell Name"].recommendation_intent is None

    # Reload validation passes, and the serializer OMITS the evaluative keys on
    # unjudged fields (byte-identical to the pre-slice {label,value,unit} shape).
    reloaded = CanonicalArtifact.model_validate(artifact.model_dump(mode="json"))
    rcard = next(s for s in reloaded.sections if isinstance(s, CardSection))
    assert {i.label for i in rcard.items} == {"CommCell Name", "Version", "Timezone", "Free Space"}
    dumped = {i["label"]: i for i in card.model_dump(mode="json")["items"]}
    assert "recommendation_intent" in dumped["Free Space"]
    assert "recommendation_intent" not in dumped["Version"]
    assert set(dumped["Timezone"].keys()) == {"label", "value", "unit"}


def test_card_conformance_failure_records_section(migrated_db_path: Path):
    from cvhealthcheck.extractors import fixture as fx

    bad = fx.FIXTURE_ROOT / "_tmp_bad_card.json"
    bad.write_text(json.dumps([{"host": "cs01"}]), encoding="utf-8")  # missing required fields
    try:
        conn = _conn(migrated_db_path)
        try:
            conn.execute(
                "UPDATE subject_section_sources SET extraction_instructions = "
                "replace(extraction_instructions, 'data/test_fixtures/card_test.json', "
                "'data/test_fixtures/_tmp_bad_card.json') "
                "WHERE section_id = '_card_test.identity'"
            )
            conn.commit()
            result = FixtureExtractor(conn).extract("_card_test", 1)
        finally:
            conn.close()
    finally:
        bad.unlink(missing_ok=True)

    assert "_card_test.identity" in result.section_failures
    assert "_card_test.identity" not in result.sections
    failure = result.section_failures["_card_test.identity"]
    assert failure["reason"] == "missing_required_field"
    assert "version" in failure["delta"]["missing"]
