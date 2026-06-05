"""ADR 0007 Phase 1 — the seeded _nested_test subject proves the two new
extract-stage capabilities in isolation (mirrors how _card_test de-risked the
card type):

  D2 — nested-path field selector: card item `field` may be a dot-path resolved
       through nested dicts (commcell.commCellName, csTimeZone.TimeZoneName).
  D3 — hex coercion: `type: "hex"` formats an integer as lowercase hex with no
       "0x" prefix (13183 -> "337f"); the raw integer is kept on the item.

_card_test stays the flat-path oracle and must behave identically.
"""
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.models import CanonicalArtifact, CardSection
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _nested_card(migrated_db_path: Path) -> CardSection:
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_nested_test", 1)
    finally:
        conn.close()
    assert not result.errors
    assert result.section_output_types["_nested_test.identity"] == "card"
    artifact = result_to_artifact(result, "_nested_test", "Nested Path Test")
    CanonicalArtifact.model_validate(artifact.model_dump())  # reload validates
    return next(s for s in artifact.sections if isinstance(s, CardSection))


# ── D2: nested-path reads ──

def test_nested_dot_path_reads_nested_values(migrated_db_path: Path):
    by = {i.label: i for i in _nested_card(migrated_db_path).items}
    assert by["CommCell Name"].value == "cs01"                 # commcell.commCellName
    assert by["Timezone"].value == "America/Danmarkshavn"      # csTimeZone.TimeZoneName


def test_nested_missing_segment_resolves_to_null_without_error():
    """A missing nested segment resolves to None, consistent with .get() — never
    raises (tested directly on the shared resolver via build_card_section)."""
    spec = {"columns": 2, "items": [
        {"label": "Present", "field": "commcell.commCellName"},
        {"label": "Missing deep", "field": "commcell.nope.deeper"},
        {"label": "Missing top", "field": "absent.x"},
    ]}
    rows = [{"commcell": {"commCellName": "cs01"}}]
    sec = build_card_section("x.id", "X", spec, rows)
    by = {i.label: i for i in sec.items}
    assert by["Present"].value == "cs01"
    assert by["Missing deep"].value is None
    assert by["Missing top"].value is None


# ── D3: hex coercion ──

def test_hex_coercion_formats_lowercase_no_prefix(migrated_db_path: Path):
    cid = next(i for i in _nested_card(migrated_db_path).items if i.label == "CommCell ID")
    assert cid.value == "337f"          # hex(13183), lowercase, no "0x"
    assert cid.raw_value == 13183       # raw integer retained in metadata


def test_hex_raw_value_serialized_only_when_present(migrated_db_path: Path):
    sec = _nested_card(migrated_db_path)
    dumped = {i["label"]: i for i in sec.model_dump(mode="json")["items"]}
    # coerced item carries raw_value; uncoerced items omit it (additive-absent)
    assert dumped["CommCell ID"]["raw_value"] == 13183
    assert dumped["CommCell ID"]["value"] == "337f"
    assert "raw_value" not in dumped["CommCell Name"]
    assert "raw_value" not in dumped["Timezone"]


def test_hex_coercion_unit_test_directly():
    spec = {"items": [{"label": "ID", "field": "id", "type": "hex"}]}
    sec = build_card_section("x.id", "X", spec, [{"id": 13183}])
    assert sec.items[0].value == "337f" and sec.items[0].raw_value == 13183
    # non-integer passes through unchanged, no crash, no raw_value
    sec2 = build_card_section("x.id", "X", spec, [{"id": "not-an-int"}])
    assert sec2.items[0].value == "not-an-int" and sec2.items[0].raw_value is None


def test_epoch_to_iso_coercion(): # ADR 0007 D3 closed-enum sibling of hex
    spec = {"items": [{"label": "T", "field": "t", "type": "epoch_to_iso"}]}
    # a known epoch-SECONDS value → ISO 8601 UTC; raw epoch kept
    sec = build_card_section("x.t", "X", spec, [{"t": 1700000000}])
    assert sec.items[0].value == "2023-11-14T22:13:20Z" and sec.items[0].raw_value == 1700000000
    # the live metrics_reporting lastCollectionTime value
    sec2 = build_card_section("x.t", "X", spec, [{"t": 1780040786}])
    assert sec2.items[0].value == "2026-05-29T07:46:26Z" and sec2.items[0].raw_value == 1780040786
    # a field WITHOUT the coercion declared is left untouched (still an int)
    plain = build_card_section("x.t", "X", {"items": [{"label": "T", "field": "t"}]}, [{"t": 1700000000}])
    assert plain.items[0].value == 1700000000 and plain.items[0].raw_value is None


# ── Regression: flat path (_card_test) unchanged ──

def test_card_test_flat_path_unchanged(migrated_db_path: Path):
    """The flat-path oracle still resolves top-level keys identically and carries
    no raw_value (no coercion)."""
    conn = _conn(migrated_db_path)
    try:
        result = FixtureExtractor(conn).extract("_card_test", 1)
    finally:
        conn.close()
    artifact = result_to_artifact(result, "_card_test", "Card Section Test")
    card = next(s for s in artifact.sections if isinstance(s, CardSection))
    by = {i.label: i for i in card.items}
    assert by["CommCell Name"].value == "cs01.lab.local"   # flat top-level read
    assert by["Free Space"].value == 8.0
    assert all(i.raw_value is None for i in card.items)    # no coercion anywhere
