"""ADR 0004 phase 2 (2b) — build_metric_section + result_to_artifact emission.

Exercises the capacity_license-shaped metric work: multi-field, a CEL-derived
percentage, a sentinel field (-1 -> n/a), and a template-default threshold
rule producing a severity + verdict chain.
"""
import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity
from cvhealthcheck.artifacts.models import CanonicalArtifact, MetricSection
from cvhealthcheck.cel import CELEvaluationError
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.metric_section import build_metric_section
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# Capacity-license-shaped fixture: monthly rows, latest used=35 / purchased=50
# (utilisation 70% -> warn), plus a sentinel field (-1 = "n/a").
ROWS = [
    {"month": "2024-06", "used_capacity": 20.0, "purchased_capacity": 50.0, "prev_active_capacity": 18.0},
    {"month": "2024-07", "used_capacity": 30.0, "purchased_capacity": 50.0, "prev_active_capacity": 25.0},
    {"month": "2024-08", "used_capacity": 35.0, "purchased_capacity": 50.0, "prev_active_capacity": -1},
]

SPEC = {
    "semantic": {"sentinel": -1},
    "items": [
        {"id": "used", "label": "Used", "unit": "TB", "source": "field", "field": "used_capacity"},
        {"id": "purchased", "label": "Purchased", "unit": "TB", "source": "field", "field": "purchased_capacity"},
        {"id": "prev_active", "label": "Previous Active", "unit": "TB", "source": "field", "field": "prev_active_capacity"},
        {"id": "utilisation_pct", "label": "Utilisation", "unit": "%", "source": "cel",
         "expr": "used / purchased * 100.0", "derived": True},
    ],
    "evaluative": {
        "rules": [
            {"rule_id": "utilisation_threshold", "target": "utilisation_pct", "comparison": ">=",
             "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
             "default_severity": "good", "mute_on_sentinel": True},
        ]
    },
}


def _items(section: MetricSection) -> dict:
    return {i.id: i for i in section.items}


def test_multi_field_and_cel_derivation():
    section = build_metric_section("_metric_test.metric", "Capacity", SPEC, ROWS)
    items = _items(section)
    assert items["used"].value == 35.0
    assert items["purchased"].value == 50.0
    assert items["utilisation_pct"].value == pytest.approx(70.0)
    assert items["utilisation_pct"].derived is True
    assert section.render_mode == "metric"


def test_evaluative_metric_default_render_mode_unchanged():
    # ADR 0004 phase 6 rider: the render_mode change must NOT alter the default
    # evaluative path. A spec with no render_mode -> "metric", with the verdict
    # intact (the capacity_license / _metric_test shape, byte-for-byte).
    assert "render_mode" not in SPEC  # the evaluative spec declares none
    section = build_metric_section("_metric_test.metric", "Capacity", SPEC, ROWS)
    assert section.render_mode == "metric"
    util = _items(section)["utilisation_pct"]
    assert util.severity == FindingSeverity.warning
    assert len(util.verdict_chain) == 1 and util.verdict_chain[0].layer == "template_default"


def test_meta_mode_informational_metric_has_no_verdict():
    # client_growth's non-evaluative metric: render_mode "meta", no rules ->
    # plain values, no severity, no verdict_chain.
    spec = {
        "render_mode": "meta",
        "items": [
            {"id": "total", "label": "Total Clients", "source": "field", "field": "total_clients", "agg": "latest"},
        ],
    }
    rows = [{"total_clients": 5}]
    section = build_metric_section("client_growth.summary", "Summary", spec, rows)
    assert section.render_mode == "meta"
    item = section.items[0]
    assert item.value == 5
    assert item.severity is None
    assert item.verdict_chain == []


def test_sentinel_field_becomes_none():
    section = build_metric_section("_metric_test.metric", "Capacity", SPEC, ROWS)
    # Latest prev_active_capacity is -1 (sentinel) -> n/a, NOT a real 0.
    assert _items(section)["prev_active"].value is None


def test_threshold_rule_sets_severity_and_verdict():
    section = build_metric_section("_metric_test.metric", "Capacity", SPEC, ROWS)
    util = _items(section)["utilisation_pct"]
    assert util.severity == FindingSeverity.warning
    assert len(util.verdict_chain) == 1
    entry = util.verdict_chain[0]
    assert entry.layer == "template_default"
    assert entry.rule_id == "utilisation_threshold"
    assert "70" in entry.reason
    # Non-target items carry no verdict.
    assert _items(section)["used"].severity is None


def test_critical_band():
    rows = [dict(ROWS[-1], used_capacity=48.0)]  # 48/50 = 96% -> critical
    section = build_metric_section("_metric_test.metric", "Capacity", SPEC, rows)
    assert _items(section)["utilisation_pct"].severity == FindingSeverity.critical


def test_sentinel_derived_value_muted():
    # used is sentinel -> None; sentinel_when guards the derivation; rule mutes.
    spec = {
        "semantic": {"sentinel": -1},
        "items": [
            {"id": "used", "label": "Used", "source": "field", "field": "used_capacity"},
            {"id": "purchased", "label": "Purchased", "source": "field", "field": "purchased_capacity"},
            {"id": "utilisation_pct", "label": "Utilisation", "unit": "%", "source": "cel",
             "expr": "used / purchased * 100.0", "sentinel_when": "used == null"},
        ],
        "evaluative": {"rules": [
            {"rule_id": "u", "target": "utilisation_pct", "comparison": ">=",
             "bands": [{"at": 70, "severity": "warning"}], "default_severity": "good",
             "mute_on_sentinel": True},
        ]},
    }
    rows = [{"used_capacity": -1, "purchased_capacity": 50.0}]
    section = build_metric_section("_metric_test.metric", "Capacity", spec, rows)
    util = _items(section)["utilisation_pct"]
    assert util.value is None
    assert util.severity == FindingSeverity.muted


def test_bad_cel_expression_raises_loud():
    spec = {
        "items": [
            {"id": "x", "label": "X", "source": "cel", "expr": "this is not valid ("},
        ],
    }
    with pytest.raises(Exception):  # CELCompileError (subclass) — loud-fail
        build_metric_section("s", "S", spec, ROWS)


def test_cel_over_missing_field_raises_loud():
    spec = {"items": [{"id": "x", "label": "X", "source": "cel", "expr": "records[0].nope + 1"}]}
    with pytest.raises(CELEvaluationError):
        build_metric_section("s", "S", spec, ROWS)


# ── result_to_artifact emission ──

def _metric_result() -> ExtractionResult:
    result = ExtractionResult(subject_id="_metric_test", source_type="json")
    sid = "_metric_test.metric"
    result.sections[sid] = ROWS
    result.section_output_types[sid] = "metric"
    result.section_titles[sid] = "Capacity"
    result.section_metric_specs[sid] = SPEC
    return result


def test_result_to_artifact_emits_metric_section():
    artifact = result_to_artifact(_metric_result(), "_metric_test", "Metric Test")
    CanonicalArtifact.model_validate(artifact.model_dump())
    metric_secs = [s for s in artifact.sections if isinstance(s, MetricSection)]
    assert len(metric_secs) == 1
    assert metric_secs[0].render_mode == "metric"
    # Worst metric verdict (warning) drives overall status.
    assert artifact.summary.status == ArtifactStatus.warning


def test_result_to_artifact_metric_roundtrips_through_json():
    artifact = result_to_artifact(_metric_result(), "_metric_test", "Metric Test")
    reloaded = CanonicalArtifact.model_validate(artifact.model_dump(mode="json"))
    sec = next(s for s in reloaded.sections if isinstance(s, MetricSection))
    util = next(i for i in sec.items if i.id == "utilisation_pct")
    assert util.value == pytest.approx(70.0)
    assert util.verdict_chain[0].reason
