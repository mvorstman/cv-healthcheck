"""ADR 0004 phase 4 (4e) — Python renderer for card sections."""
from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    CardItem,
    CardSection,
    VerdictEntry,
)
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

_NOW = datetime(2026, 5, 29, tzinfo=timezone.utc)


def _artifact(section: CardSection) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="_card_test", generated_at=_NOW,
        source=ArtifactSource(type=SourceType.json_import),
        subject=ArtifactSubject(id="_card_test", title="Card Test"),
        summary=ArtifactSummary(status=ArtifactStatus.warning),
        sections=[section],
    )


def test_card_view_with_status():
    sec = CardSection(
        type="card", id="_card_test.identity", title="CommCell", columns=4,
        items=[
            CardItem(label="CommCell Name", value="cs01"),
            CardItem(label="Free Space", value=8.0, unit="%"),
            CardItem(label="Missing", value=None),
        ],
        severity=FindingSeverity.warning,
        verdict_chain=[VerdictEntry(layer="template_default", rule_id="r",
                                    severity=FindingSeverity.warning,
                                    reason="Free space 8% <= 15% threshold")],
    )
    view = artifact_to_view(_artifact(sec))["sections"][0]
    assert view["type"] == "card"
    assert view["columns"] == 4
    items = {i["label"]: i for i in view["items"]}
    assert items["CommCell Name"]["value"] == "cs01"
    assert items["Free Space"]["value"] == "8" and items["Free Space"]["unit"] == "%"
    assert items["Missing"]["value"] == "—"        # None renders as em dash
    assert view["sev"] == "warn"
    assert "threshold" in view["reason"]


def test_card_view_without_status():
    sec = CardSection(type="card", id="c.id", title="Card",
                      items=[CardItem(label="Host", value="cs01")])
    view = artifact_to_view(_artifact(sec))["sections"][0]
    assert view["type"] == "card"
    assert view["sev"] is None
    assert view["columns"] is None
