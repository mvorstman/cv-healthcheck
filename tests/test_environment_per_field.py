"""Phase-8 follow-on — per-field evaluation on the bespoke environment track.

CommCell Details / environment is built by the bespoke _build_environment_subject
(one of the six system subjects with custom view shapes, ADR 0001 source-building
fork), NOT the generic build_card_section path that _card_test uses. This slice
routes its identity card through the SAME shared path (build_card_section →
engine.evaluate → _card_section_view → the per-field card renderer), and authors
one presence rule (Version is set → good). The other identity fields stay bare.
"""
from __future__ import annotations

from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.artifacts.enums import ArtifactStatus
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.quickhc.subject_data_service import _build_environment_subject

_CC = {
    "hostName": "cs01",
    "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D",
    "csVersionInfo": "11 SP40.47",
    "timeZone": "0:0:America/Danmarkshavn",
}


def _identity_section(cc: dict) -> dict:
    return _build_environment_subject(cc)["sections"][0]


def test_environment_identity_routed_onto_shared_card_path():
    """The bespoke builder now emits a `card` section (not the old hand-built
    `meta` section), so it flows through the shared per-field card renderer."""
    sec = _identity_section(_CC)
    assert sec["type"] == "card"
    assert sec["columns"] == 4
    assert sec["meta"] == "CommCell profile"          # original sub-label preserved


def test_environment_version_presence_verdict():
    sec = _identity_section(_CC)
    by = {i["label"]: i for i in sec["items"]}
    # The one evaluated field: Version, via a presence rule -> good.
    assert by["Version"]["sev"] == "good"
    assert by["Version"]["reason"] == "Version is set"
    # The other three identity fields stay bare (no rule this slice).
    assert by["CommCell Name"]["sev"] is None
    assert by["CommCell ID"]["sev"] is None
    assert by["Timezone"]["sev"] is None
    # Section header badge rolls up from the one judged field.
    assert sec["sev"] == "good"


def test_environment_identity_values_and_order_preserved():
    """Field mapping is unchanged from the old meta card: same four cells, same
    values, same order (labels are CSS-uppercased at render, so display is
    identical to the prior COMMCELL NAME / ID / VERSION / TIMEZONE)."""
    sec = _identity_section(_CC)
    assert [(i["label"], i["value"]) for i in sec["items"]] == [
        ("CommCell Name", "cs01"),
        ("CommCell ID", "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"),
        ("Version", "11 SP40.47"),
        ("Timezone", "0:0:America/Danmarkshavn"),
    ]


def test_environment_version_missing_renders_dash_and_warns():
    """An absent version renders as '—' (unchanged display) AND the presence
    rule reads it as not-set -> warning."""
    cc = dict(_CC, csVersionInfo="")
    by = {i["label"]: i for i in _identity_section(cc)["items"]}
    assert by["Version"]["value"] == "—"
    assert by["Version"]["sev"] == "warn"


def test_environment_no_data_branch_unchanged():
    """The no-data branch (cc is None) is untouched — no identity card built."""
    subj = _build_environment_subject(None)
    assert subj["id"] == "environment"
    # nodata subject carries no judged identity card section.
    assert all(s.get("type") != "card" for s in subj.get("sections", []))


# ── Model-layer: the shared path's CardSection validates on reload ──

def test_environment_identity_card_validates_on_reload():
    """The identity card the bespoke builder produces (via build_card_section)
    is a real CardSection that round-trips through CanonicalArtifact validation,
    same as the generic path."""
    spec = {
        "columns": 4,
        "items": [
            {"label": "CommCell Name", "field": "name"},
            {"label": "Version", "field": "version"},
        ],
        "evaluative": {"rules": [
            {"rule_id": "environment_version_presence", "target_field": "version",
             "kind": "presence", "severity_when_missing": "warning",
             "severity_when_present": "good"},
        ]},
    }
    sec = build_card_section("environment.metadata", "Environment metadata",
                             spec, [{"name": "cs01", "version": "11 SP40.47"}])
    art = CanonicalArtifact(
        artifact_type="environment", generated_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        source=ArtifactSource(type=SourceType.rest),
        subject=ArtifactSubject(id="environment", title="CommCell Details"),
        summary=ArtifactSummary(status=ArtifactStatus.good), sections=[sec],
    )
    CanonicalArtifact.model_validate(art.model_dump(mode="json"))  # no raise


def test_environment_identity_no_rule_is_bare_and_additive():
    """Parity: the SAME shared path with NO rule authored leaves every field
    bare — no per-field badges, no section verdict, and each CardItem serializes
    to exactly {label,value,unit} (byte-identical to the prior bare identity
    card shape). Adding the capability is additive-absent."""
    spec = {
        "columns": 4,
        "items": [
            {"label": "CommCell Name", "field": "name"},
            {"label": "CommCell ID", "field": "guid"},
            {"label": "Version", "field": "version"},
            {"label": "Timezone", "field": "timezone"},
        ],
        # no evaluative block
    }
    rows = [{"name": "cs01", "guid": "G", "version": "11 SP40.47", "timezone": "UTC"}]
    sec = build_card_section("environment.metadata", "Environment metadata", spec, rows)
    assert sec.severity is None and sec.verdict_chain == []
    for item in sec.items:
        assert item.severity is None and item.verdict_chain == []
    dumped = sec.model_dump(mode="json")["items"]
    for cell in dumped:
        assert set(cell.keys()) == {"label", "value", "unit"}
