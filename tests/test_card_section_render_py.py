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
    # No-rule card: every field's per-item sev is None -> renderer paints no
    # badge (the field stays bare).
    assert all(i["sev"] is None for i in view["items"])


def test_card_view_per_field_verdicts():
    """Phase-8 follow-on: each judged field carries its own sev + reason (the
    metric-item shape), so the renderer can paint a per-field badge; unjudged
    fields carry sev=None and render bare."""
    sec = CardSection(
        type="card", id="_card_test.identity", title="CommCell", columns=4,
        items=[
            CardItem(label="CommCell Name", value="cs01"),  # no verdict
            CardItem(
                label="Version", value="11 SP40.47",
                severity=FindingSeverity.good,
                verdict_chain=[VerdictEntry(layer="template_default", rule_id="version_presence",
                                            severity=FindingSeverity.good, reason="Version is set")],
            ),
            CardItem(label="Timezone", value="UTC"),  # no verdict
            CardItem(
                label="Free Space", value=8.0, unit="%",
                severity=FindingSeverity.warning,
                verdict_chain=[VerdictEntry(layer="template_default", rule_id="free_space_threshold",
                                            severity=FindingSeverity.warning,
                                            reason="Free Space 8% <= 15% threshold")],
            ),
        ],
        severity=FindingSeverity.warning,  # rolled-up header badge
    )
    items = {i["label"]: i for i in artifact_to_view(_artifact(sec))["sections"][0]["items"]}

    # Judged fields carry the metric-item badge shape (sev code + reason tooltip).
    assert items["Free Space"]["sev"] == "warn"
    assert items["Free Space"]["reason"] == "Free Space 8% <= 15% threshold"
    assert items["Version"]["sev"] == "good"
    assert items["Version"]["reason"] == "Version is set"

    # Unjudged identity fields stay bare (no badge): sev None, empty reason.
    assert items["CommCell Name"]["sev"] is None and items["CommCell Name"]["reason"] == ""
    assert items["Timezone"]["sev"] is None
