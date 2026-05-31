"""ADR 0004 phase-8 follow-on — the ``enum`` and ``format`` rule-kind evaluators,
behind the same engine dispatch as threshold/presence.

Covers, per evaluator: hit / miss, the missing-value path, and the "no spec
configured" path; plus that the engine dispatches each kind and that a bad regex
fails loudly. These evaluators carry their config (allowed-set / pattern) on the
rule dict, the same plumbing presence/threshold use.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.evaluative import engine
from cvhealthcheck.evaluative.enum_rule import evaluate_enum_rule
from cvhealthcheck.evaluative.format_rule import evaluate_format_rule


# ── enum ──

def _enum_rule(**over):
    base = {"rule_id": "tz_enum", "kind": "enum",
            "allowed_values": ["UTC", "America/Danmarkshavn"]}
    base.update(over)
    return base


def test_enum_hit_is_good():
    v = evaluate_enum_rule(_enum_rule(), "UTC", label="Timezone")
    assert v.severity == FindingSeverity.good
    assert v.rule_id == "tz_enum"
    assert "in the allowed set" in v.reason


def test_enum_miss_is_warning():
    v = evaluate_enum_rule(_enum_rule(), "Mars/Olympus", label="Timezone")
    assert v.severity == FindingSeverity.warning
    assert "not in the allowed set" in v.reason


def test_enum_miss_severity_is_configurable():
    v = evaluate_enum_rule(_enum_rule(severity_when_disallowed="critical"),
                           "nope", label="Timezone")
    assert v.severity == FindingSeverity.critical


def test_enum_missing_value_uses_missing_severity():
    for empty in (None, ""):
        v = evaluate_enum_rule(_enum_rule(), empty, label="Timezone")
        assert v.severity == FindingSeverity.warning
        assert v.reason == "Timezone is not set"


def test_enum_no_allowed_set_configured_passes():
    # No spec -> nothing to disallow -> pass (good), never raises.
    for spec in ({"rule_id": "e", "kind": "enum"},               # key absent
                 {"rule_id": "e", "kind": "enum", "allowed_values": []}):  # empty
        v = evaluate_enum_rule(spec, "anything", label="Timezone")
        assert v.severity == FindingSeverity.good
        assert "no allowed-set configured" in v.reason


# ── format ──

def _format_rule(**over):
    base = {"rule_id": "name_fmt", "kind": "format",
            "pattern": r"[A-Za-z][A-Za-z0-9_.-]*"}
    base.update(over)
    return base


def test_format_match_is_good():
    v = evaluate_format_rule(_format_rule(), "cs01.lab.local", label="CommCell Name")
    assert v.severity == FindingSeverity.good
    assert v.rule_id == "name_fmt"
    assert "matches the required format" in v.reason


def test_format_no_match_is_warning():
    # leading digit violates "[A-Za-z]..." -> fullmatch fails
    v = evaluate_format_rule(_format_rule(), "9bad name!", label="CommCell Name")
    assert v.severity == FindingSeverity.warning
    assert "does not match the required format" in v.reason


def test_format_is_anchored_fullmatch():
    # a partial match must NOT pass — the WHOLE value must conform.
    v = evaluate_format_rule(_format_rule(pattern=r"[A-Za-z]+"), "abc123", label="CommCell Name")
    assert v.severity == FindingSeverity.warning


def test_format_no_match_severity_is_configurable():
    v = evaluate_format_rule(_format_rule(severity_when_no_match="critical"),
                             "9bad", label="CommCell Name")
    assert v.severity == FindingSeverity.critical


def test_format_missing_value_uses_missing_severity():
    for empty in (None, ""):
        v = evaluate_format_rule(_format_rule(), empty, label="CommCell Name")
        assert v.severity == FindingSeverity.warning
        assert v.reason == "CommCell Name is not set"


def test_format_no_pattern_configured_passes():
    # No spec -> no convention to enforce -> pass (good), never raises.
    for spec in ({"rule_id": "f", "kind": "format"},              # key absent
                 {"rule_id": "f", "kind": "format", "pattern": ""}):  # empty
        v = evaluate_format_rule(spec, "anything", label="CommCell Name")
        assert v.severity == FindingSeverity.good
        assert "no format pattern configured" in v.reason


def test_format_invalid_regex_raises():
    bad = {"rule_id": "f", "kind": "format", "pattern": "([unclosed"}
    with pytest.raises(ValueError, match="Invalid format pattern"):
        evaluate_format_rule(bad, "x", label="CommCell Name")


# ── engine dispatch (both kinds routed behind the single locus) ──

def test_engine_dispatches_enum_kind():
    sev, chain = engine.evaluate("UTC", [_enum_rule()], label="Timezone")
    assert sev == FindingSeverity.good
    assert chain[0].rule_id == "tz_enum" and chain[0].layer == "template_default"


def test_engine_dispatches_format_kind():
    sev, chain = engine.evaluate("cs01.lab.local", [_format_rule()], label="CommCell Name")
    assert sev == FindingSeverity.good
    assert chain[0].rule_id == "name_fmt"


def test_engine_unknown_kind_lists_all_four():
    with pytest.raises(ValueError, match="threshold, presence, enum, format"):
        engine.evaluate("x", [{"rule_id": "z", "kind": "bogus"}], label="X")
