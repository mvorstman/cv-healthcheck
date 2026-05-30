"""Phase-8 follow-on — rule-kind dispatch + the `presence` kind.

engine.evaluate now dispatches on rule `kind`: threshold (or absent) routes to
the unchanged threshold evaluator; presence routes to evaluate_presence_rule;
unknown kind fails loudly. presence judges set-ness; its verdict composes with
layering/override and the recommend seam exactly like a threshold verdict.
"""
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import FindingSeverity as S
from cvhealthcheck.artifacts.models import MetricSection
from cvhealthcheck.evaluative import engine
from cvhealthcheck.evaluative.presence import evaluate_presence_rule
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.metric_section import build_metric_section
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


_PRESENCE = {"rule_id": "p", "kind": "presence", "severity_when_missing": "warning",
             "severity_when_present": "good"}


# ── the presence evaluator ──

def test_presence_set_vs_missing_vs_empty():
    assert evaluate_presence_rule(_PRESENCE, 50.0, label="Purchased").severity == S.good
    assert evaluate_presence_rule(_PRESENCE, 50.0, label="Purchased").reason == "Purchased is set"
    assert evaluate_presence_rule(_PRESENCE, None, label="Prev").severity == S.warning
    assert evaluate_presence_rule(_PRESENCE, None, label="Prev").reason == "Prev is not set"
    assert evaluate_presence_rule(_PRESENCE, "", label="X").severity == S.warning      # empty string -> missing
    assert evaluate_presence_rule(_PRESENCE, 0, label="X").severity == S.good           # 0 is a real value -> present
    assert evaluate_presence_rule(_PRESENCE, False, label="X").severity == S.good       # False is present
    # severity_when_present defaults to good
    assert evaluate_presence_rule({"rule_id": "p", "kind": "presence", "severity_when_missing": "critical"},
                                  1, label="X").severity == S.good


def test_severity_when_missing_critical():
    rule = {"rule_id": "p", "kind": "presence", "severity_when_missing": "critical"}
    assert evaluate_presence_rule(rule, None, label="X").severity == S.critical


# ── dispatch by kind ──

def test_dispatch_routes_by_kind():
    # threshold kind
    sev, chain = engine.evaluate(95.0, [{"rule_id": "t", "kind": "threshold", "comparison": ">=",
                                         "bands": [{"at": 90, "severity": "critical"}], "default_severity": "good"}],
                                 label="U")
    assert sev == S.critical and chain[0].reason.endswith("threshold")
    # presence kind
    sev2, chain2 = engine.evaluate(None, [_PRESENCE], label="Prev")
    assert sev2 == S.warning and chain2[0].reason == "Prev is not set"


def test_absent_kind_defaults_to_threshold():
    # no `kind` declared -> threshold path (the parity guarantee)
    sev, chain = engine.evaluate(95.0, [{"rule_id": "t", "comparison": ">=",
                                         "bands": [{"at": 90, "severity": "critical"}], "default_severity": "good"}],
                                 label="U")
    assert sev == S.critical and "threshold" in chain[0].reason


def test_unknown_kind_fails_loudly():
    with pytest.raises(ValueError, match="Unknown rule kind 'enum'"):
        engine.evaluate(5.0, [{"rule_id": "x", "kind": "enum"}], label="X")


# ── presence composes with the seam + override layering ──

def test_presence_rule_surfaces_recommendation_intent():
    spec = {
        "items": [{"id": "flag", "label": "Flag", "source": "field", "field": "flag"}],
        "evaluative": {"rules": [{
            "rule_id": "flag_presence", "target": "flag", "kind": "presence",
            "severity_when_missing": "critical", "severity_when_present": "good",
            "recommendation": {"intent_kind": "attention", "signal": "config.flag", "inputs": ["flag"]},
        }]},
    }
    sec = build_metric_section("s.m", "S", spec, [{"flag": "on"}])
    item = sec.items[0]
    assert item.severity == S.good
    assert item.recommendation_intent is not None                 # seam composes across kinds
    assert item.recommendation_intent.signal == "config.flag"
    assert item.recommendation_intent.inputs_resolved == {"flag": "on"}


def test_presence_verdict_can_be_overridden_muted():
    spec = {
        "items": [{"id": "flag", "label": "Flag", "source": "field", "field": "flag"}],
        "evaluative": {"rules": [{"rule_id": "flag_presence", "target": "flag", "kind": "presence",
                                  "severity_when_missing": "critical"}]},
    }
    overrides = [{"rule_id": "flag_presence", "severity": "muted", "reason": "waived"}]
    sec = build_metric_section("s.m", "S", spec, [{"flag": None}], overrides=overrides)
    item = sec.items[0]
    assert item.severity == S.muted                               # override mutes a presence verdict like any other
    assert [(v.layer, v.severity) for v in item.verdict_chain] == [
        ("template_default", S.critical), ("override", S.muted)]


# ── end-to-end: _metric_test now shows threshold + presence side by side ──

def test_e2e_threshold_and_presence_side_by_side(migrated_db_path: Path):
    conn = sqlite3.connect(str(migrated_db_path)); conn.row_factory = sqlite3.Row
    try:
        art = result_to_artifact(FixtureExtractor(conn).extract("_metric_test", 1), "_metric_test", "MT")
    finally:
        conn.close()
    items = {i.id: i for i in next(s for s in art.sections if isinstance(s, MetricSection)).items}
    assert items["used"].severity == S.critical                   # threshold
    assert items["utilisation_pct"].severity == S.warning         # threshold
    assert items["purchased"].severity == S.good                  # presence (set -> good)
    assert items["purchased"].verdict_chain[0].rule_id == "purchased_presence"
    assert items["purchased"].verdict_chain[0].reason == "Purchased is set"
