"""ADR 0004 phase 4 (4a) — the new CardSection model.

A card is a flat labeled key-value identity block that ALSO carries a
section-level verdict, reusing the exact severity + verdict_chain shape
MetricItem carries (the phase-4 steering decision; phase 8 unifies the
evaluative face). Distinct model from MetricSection (its own `type` literal),
in the Section discriminated union.
"""
import pytest
from pydantic import ValidationError

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    CardItem,
    CardSection,
    VerdictEntry,
)


def test_card_minimal():
    sec = CardSection(type="card", id="env.identity", title="CommCell",
                      items=[CardItem(label="CommCell Name", value="cs01")])
    assert sec.items[0].value == "cs01"
    assert sec.columns is None
    assert sec.severity is None
    assert sec.verdict_chain == []


def test_card_item_value_optional_and_unit():
    item = CardItem(label="Free space", value=None, unit="TB")
    assert item.value is None and item.unit == "TB"


def test_card_carries_verdict_same_shape_as_metric():
    sec = CardSection(
        type="card", id="env.identity", title="CommCell",
        items=[CardItem(label="Version", value="11 SP40")],
        columns=4,
        severity=FindingSeverity.good,
        verdict_chain=[VerdictEntry(layer="template_default", rule_id="r",
                                    severity=FindingSeverity.good,
                                    reason="CommCell healthy")],
    )
    assert sec.columns == 4
    assert sec.severity == FindingSeverity.good
    assert sec.verdict_chain[0].layer == "template_default"
    # Same VerdictEntry type a metric uses.
    assert isinstance(sec.verdict_chain[0], VerdictEntry)


def test_card_discriminated_in_section_union():
    artifact = CanonicalArtifact.model_validate({
        "artifact_type": "_card_test",
        "generated_at": "2026-05-29T00:00:00Z",
        "source": {"type": "json_import"},
        "subject": {"id": "_card_test", "title": "Card Test"},
        "summary": {"status": "good"},
        "sections": [{
            "type": "card", "id": "c.identity", "title": "Identity",
            "items": [{"label": "Host", "value": "cs01"}],
            "severity": "good",
            "verdict_chain": [{"layer": "template_default", "severity": "good",
                               "reason": "ok"}],
        }],
    })
    assert isinstance(artifact.sections[0], CardSection)
    assert artifact.sections[0].items[0].label == "Host"


def test_card_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        CardSection(type="card", id="x", title="X", severity="bogus")
