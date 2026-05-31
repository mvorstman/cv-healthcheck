"""ADR 0004 phase 2 — threshold-rule evaluator tests (the minimum evaluative
machinery a metric needs to show a template-default verdict)."""
import pytest

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.evaluative.threshold import evaluate_threshold_rule

RULE = {
    "rule_id": "utilisation_threshold",
    "target": "utilisation_pct",
    "kind": "threshold",
    "comparison": ">=",
    "bands": [
        {"at": 90, "severity": "critical"},
        {"at": 70, "severity": "warning"},
    ],
    "default_severity": "good",
    "mute_on_sentinel": True,
}


def test_good_below_all_bands():
    v = evaluate_threshold_rule(RULE, 50.0, label="Utilisation", unit="%")
    assert v.severity == FindingSeverity.good
    assert v.layer == "template_default"
    assert v.rule_id == "utilisation_threshold"
    assert v.reason  # populated


def test_warning_band():
    v = evaluate_threshold_rule(RULE, 70.0, label="Utilisation", unit="%")
    assert v.severity == FindingSeverity.warning
    assert "70" in v.reason and ">=" in v.reason


def test_critical_band_wins_when_both_hold():
    # 95 satisfies both the 70 and 90 bands; the highest severity wins.
    v = evaluate_threshold_rule(RULE, 95.0, label="Utilisation", unit="%")
    assert v.severity == FindingSeverity.critical
    assert "90" in v.reason


def test_sentinel_muted():
    v = evaluate_threshold_rule(RULE, None, label="Utilisation", unit="%")
    assert v.severity == FindingSeverity.muted
    assert "n/a" in v.reason.lower()


def test_sentinel_without_mute_falls_to_default():
    rule = {**RULE, "mute_on_sentinel": False}
    v = evaluate_threshold_rule(rule, None, label="Utilisation", unit="%")
    assert v.severity == FindingSeverity.good


def test_reason_formats_whole_numbers_cleanly():
    v = evaluate_threshold_rule(RULE, 70.0, label="Utilisation", unit="%")
    # No trailing ".0" noise in the auditable reason.
    assert "70.0" not in v.reason
    assert "70%" in v.reason


def test_less_than_comparison():
    rule = {
        "rule_id": "free_space",
        "target": "free_pct",
        "comparison": "<=",
        "bands": [{"at": 5, "severity": "critical"}, {"at": 15, "severity": "warning"}],
        "default_severity": "good",
    }
    assert evaluate_threshold_rule(rule, 3, label="Free", unit="%").severity == FindingSeverity.critical
    assert evaluate_threshold_rule(rule, 10, label="Free", unit="%").severity == FindingSeverity.warning
    assert evaluate_threshold_rule(rule, 40, label="Free", unit="%").severity == FindingSeverity.good


def test_unsupported_comparison_raises():
    rule = {"rule_id": "x", "comparison": "~=", "bands": [{"at": 1, "severity": "warning"}]}
    with pytest.raises(ValueError):
        evaluate_threshold_rule(rule, 5, label="X")
