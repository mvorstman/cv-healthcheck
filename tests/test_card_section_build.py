"""ADR 0004 phase 4 (4c) — build_card_section (field mapping + reused verdict)
and result_to_artifact emission of CardSection on output_as == "card"."""
from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity
from cvhealthcheck.artifacts.models import CanonicalArtifact, CardSection
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


ROWS = [{"host": "cs01", "version": "11 SP40", "timezone": "UTC", "free_pct": 8.0}]
SPEC = {
    "columns": 4,
    "items": [
        {"label": "CommCell Name", "field": "host"},
        {"label": "Version", "field": "version"},
        {"label": "Timezone", "field": "timezone"},
        {"label": "Free Space", "field": "free_pct", "unit": "%"},
    ],
    "evaluative": {
        "rule": {
            "rule_id": "free_space", "target_field": "free_pct", "comparison": "<=",
            "bands": [{"at": 5, "severity": "critical"}, {"at": 15, "severity": "warning"}],
            "default_severity": "good", "unit": "%",
        }
    },
}


def test_field_mapping_reads_one_row():
    sec = build_card_section("_card_test.identity", "CommCell", SPEC, ROWS)
    items = {i.label: i for i in sec.items}
    assert items["CommCell Name"].value == "cs01"
    assert items["Free Space"].value == 8.0 and items["Free Space"].unit == "%"
    assert sec.columns == 4


def test_card_carries_verdict_from_reused_evaluator():
    sec = build_card_section("_card_test.identity", "CommCell", SPEC, ROWS)
    # free_pct 8 <= 15 -> warning (and 8 > 5 so not critical)
    assert sec.severity == FindingSeverity.warning
    assert len(sec.verdict_chain) == 1
    assert sec.verdict_chain[0].layer == "template_default"
    assert sec.verdict_chain[0].reason


def test_card_no_rule_no_verdict():
    sec = build_card_section("c", "C", {"items": [{"label": "Host", "field": "host"}]}, ROWS)
    assert sec.severity is None
    assert sec.verdict_chain == []


def test_card_missing_field_is_none():
    sec = build_card_section("c", "C", {"items": [{"label": "Missing", "field": "nope"}]}, ROWS)
    assert sec.items[0].value is None


def test_card_non_numeric_target_does_not_crash():
    spec = {
        "items": [{"label": "Host", "field": "host"}],
        "evaluative": {"rule": {"rule_id": "r", "target_field": "host", "comparison": ">=",
                                "bands": [{"at": 1, "severity": "warning"}],
                                "default_severity": "good", "mute_on_sentinel": True}},
    }
    sec = build_card_section("c", "C", spec, ROWS)  # host is "cs01" -> None -> muted
    assert sec.severity == FindingSeverity.muted


def test_empty_rows_yields_none_values():
    sec = build_card_section("c", "C", SPEC, [])
    assert all(i.value is None for i in sec.items)


# ── result_to_artifact emission ──

def _card_result() -> ExtractionResult:
    r = ExtractionResult(subject_id="_card_test", source_type="json")
    sid = "_card_test.identity"
    r.sections[sid] = ROWS
    r.section_output_types[sid] = "card"
    r.section_titles[sid] = "CommCell"
    r.section_card_specs[sid] = SPEC
    return r


def test_result_to_artifact_emits_card_and_status():
    art = result_to_artifact(_card_result(), "_card_test", "Card Test")
    CanonicalArtifact.model_validate(art.model_dump())
    cards = [s for s in art.sections if isinstance(s, CardSection)]
    assert len(cards) == 1 and cards[0].severity == FindingSeverity.warning
    # The card verdict drives overall artifact status.
    assert art.summary.status == ArtifactStatus.warning


def test_card_roundtrips_through_json():
    art = result_to_artifact(_card_result(), "_card_test", "Card Test")
    reloaded = CanonicalArtifact.model_validate(art.model_dump(mode="json"))
    sec = next(s for s in reloaded.sections if isinstance(s, CardSection))
    assert {i.label for i in sec.items} == {"CommCell Name", "Version", "Timezone", "Free Space"}
    assert sec.verdict_chain[0].reason
