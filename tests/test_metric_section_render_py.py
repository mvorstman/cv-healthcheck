"""ADR 0004 phase 2 (2e) — Python renderer for metric sections, and the
guarantee that render_mode="meta" MetricSections (License Summary's
commcell_info) are byte-for-byte unchanged."""
from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    MetricItem,
    MetricSection,
    VerdictEntry,
)
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

_NOW = datetime(2026, 5, 29, tzinfo=timezone.utc)


def _artifact(section: MetricSection, status=ArtifactStatus.warning) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="_metric_test",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.json_import),
        subject=ArtifactSubject(id="_metric_test", title="Metric Test"),
        summary=ArtifactSummary(status=status),
        sections=[section],
    )


def _rich_section() -> MetricSection:
    return MetricSection(
        type="metric", id="_metric_test.metric", title="Capacity", render_mode="metric",
        items=[
            MetricItem(id="used", label="Used", value=35.0, unit="TB"),
            MetricItem(id="prev", label="Previous", value=None, unit="TB"),
            MetricItem(
                id="utilisation_pct", label="Utilisation", value=70.0, unit="%", derived=True,
                severity=FindingSeverity.warning,
                verdict_chain=[VerdictEntry(layer="template_default", rule_id="r",
                                            severity=FindingSeverity.warning,
                                            reason="Utilisation 70% >= 70% threshold")],
            ),
        ],
    )


def test_rich_metric_section_renders_as_metric_type():
    view = artifact_to_view(_artifact(_rich_section()))
    sec = view["sections"][0]
    assert sec["type"] == "metric"
    items = {i["id"]: i for i in sec["items"]}
    assert items["used"]["value"] == "35"
    assert items["used"]["unit"] == "TB"
    assert items["prev"]["value"] == "n/a"          # sentinel, not "0", not "-1"
    assert items["utilisation_pct"]["value"] == "70"
    assert items["utilisation_pct"]["derived"] is True
    assert items["utilisation_pct"]["sev"] == "warn"
    assert "70%" in items["utilisation_pct"]["reason"]
    assert items["used"]["sev"] is None             # non-judged item has no badge
    # ADR 0004 phase 4 (FIX 1): the metric section also exposes a section-level
    # summary verdict for the header badge — the worst item severity.
    assert sec["sev"] == "warn"
    assert "70%" in sec["reason"]


def test_meta_mode_metricsection_unchanged():
    # render_mode defaults to "meta" — the License Summary commcell_info case.
    legacy = MetricSection(
        type="metric", id="commcell_info", title="CommCell",
        items=[MetricItem(id="name", label="CommCell Name", value="cs01")],
    )
    sec = artifact_to_view(_artifact(legacy, status=ArtifactStatus.good))["sections"][0]
    # Same shape as before phase 2: a "meta" key/value block, NOT "metric".
    assert sec["type"] == "meta"
    assert sec["rows"] == [{"k": "COMMCELL NAME", "v": "cs01"}]
