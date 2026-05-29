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


def test_card_test_subject_collects_identity_with_status(migrated_db_path: Path):
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

    # free_space_pct 8 <= 15 -> warning; the card carries the verdict and it
    # drives overall artifact status.
    assert card.severity == FindingSeverity.warning
    assert card.verdict_chain[0].layer == "template_default"
    assert card.verdict_chain[0].reason
    assert artifact.summary.status == ArtifactStatus.warning


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
