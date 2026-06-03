"""ADR 0010 Phase 1 — row-scope evaluation rules: coercion + row_match + the
result_to_artifact compliance pass. Pure-core tests (no MCP, no catalog wiring).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import FindingsSection
from cvhealthcheck.evaluative import coerce
from cvhealthcheck.evaluative.row_match import evaluate_row_rule
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

NOW = datetime(2026, 6, 3, tzinfo=timezone.utc)

# Real-shaped fixtures (ADR 0010): server_groups has an empty group AND a
# duplicate name (rommelgroep, ids 19 & 41 — row_ref MUST be id, not name).
SERVER_GROUPS = [
    {"id": 19, "name": "rommelgroep", "server_count": 0, "association": "manual"},
    {"id": 41, "name": "rommelgroep", "server_count": 5, "association": "auto"},
    {"id": 7,  "name": "prod",        "server_count": 12, "association": "auto"},
]
USERS = [
    {"id": 1, "name": "admin", "lastLoggedIn": 1777593600, "enabled": "true",  "locked": "false"},  # 2026-05-01, recent
    {"id": 2, "name": "ghost", "lastLoggedIn": 0,          "enabled": "true",  "locked": "false"},  # epoch 0 = never
    {"id": 3, "name": "stale", "lastLoggedIn": 1577836800, "enabled": "true",  "locked": "true"},   # 2020, stale + locked
]
LICENSES = [
    {"id": 1, "license": "capacity", "used": "12 TB", "available_total": "10 TB"},
    {"id": 2, "license": "object",   "used": "3 TB",  "available_total": "Unlimited"},
]


# ── coerce ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("0 TB", 0.0), ("4 clients", 4.0), ("10 millions", 10.0), ("12 TB", 12.0),
    ("1,024 GB", 1024.0), (5, 5.0), (3.5, 3.5), ("Unlimited", float("inf")),
    ("N/A", None), ("-", None), ("", None), (None, None), ("nonsense", None),
    (True, None),  # bool is not a measurement
])
def test_to_number(value, expected):
    assert coerce.to_number(value) == expected

@pytest.mark.parametrize("value,absent", [
    (None, True), ("N/A", True), ("-", True), ("", True), ("null", True),
    ("0", False), (0, False), ("rommelgroep", False), ("Unlimited", False),
])
def test_is_absent(value, absent):
    assert coerce.is_absent(value) is absent

def test_age_days_iso_and_epoch():
    assert coerce.age_days("2026-05-04", now=NOW) == pytest.approx(30, abs=1)
    assert coerce.age_days("2026-05-04T00:00:00Z", now=NOW) == pytest.approx(30, abs=1)
    # epoch 0 ("never") reads as ~20k days old → very stale
    assert coerce.age_days(0, now=NOW) > 20000
    assert coerce.age_days("N/A", now=NOW) is None


# ── predicates / evaluate_row_rule ────────────────────────────────────────────

def _rule(conditions, *, emit="per_row", severity="warning", title="t", message="m",
          count_operator=None, count_value=None, rule_id="r1"):
    return {"rule_id": rule_id, "kind": "row_match", "conditions": conditions,
            "emit": emit, "severity": severity, "title": title, "message": message,
            "count_operator": count_operator, "count_value": count_value}

def test_eq_string_and_per_row_row_ref_is_id_not_name():
    # Both rommelgroep rows match by NAME; the findings MUST stay distinct via id.
    rule = _rule([{"target": "name", "operator": "eq", "value": "rommelgroep"}])
    findings = evaluate_row_rule(rule, SERVER_GROUPS, now=NOW)
    assert len(findings) == 2
    assert {f["row_ref"] for f in findings} == {"19", "41"}   # ids, not "rommelgroep"

def test_numeric_compare_empty_group():
    rule = _rule([{"target": "server_count", "operator": "lt", "value": 1}])
    findings = evaluate_row_rule(rule, SERVER_GROUPS, now=NOW)
    assert [f["row_ref"] for f in findings] == ["19"]

def test_field_to_field_ref_and_unlimited():
    # used > available_total: capacity over-allocated; object's "Unlimited" never is.
    rule = _rule([{"target": "used", "operator": "gt", "value": {"ref": "available_total"}}])
    findings = evaluate_row_rule(rule, LICENSES, now=NOW)
    assert [f["row_ref"] for f in findings] == ["1"]

def test_between_and_contains_and_ne():
    assert [f["row_ref"] for f in evaluate_row_rule(
        _rule([{"target": "server_count", "operator": "between", "value": 1, "value2": 10}]),
        SERVER_GROUPS, now=NOW)] == ["41"]
    assert [f["row_ref"] for f in evaluate_row_rule(
        _rule([{"target": "name", "operator": "contains", "value": "rommel"}]),
        SERVER_GROUPS, now=NOW)] == ["19", "41"]
    assert [f["row_ref"] for f in evaluate_row_rule(
        _rule([{"target": "association", "operator": "ne", "value": "auto"}]),
        SERVER_GROUPS, now=NOW)] == ["19"]

def test_exists_not_exists_treats_absent_as_absent():
    rows = [{"id": 1, "email": "a@x"}, {"id": 2, "email": "N/A"}, {"id": 3}]
    assert [f["row_ref"] for f in evaluate_row_rule(
        _rule([{"target": "email", "operator": "exists"}]), rows, now=NOW)] == ["1"]
    assert [f["row_ref"] for f in evaluate_row_rule(
        _rule([{"target": "email", "operator": "not_exists"}]), rows, now=NOW)] == ["2", "3"]
    # a comparison against an absent cell is FALSE, not an error
    assert evaluate_row_rule(
        _rule([{"target": "email", "operator": "eq", "value": "a@x"}]),
        [{"id": 9, "email": "N/A"}], now=NOW) == []

def test_stale_days_epoch_never_and_iso():
    rule = _rule([{"target": "lastLoggedIn", "operator": "stale_days", "value": 365}])
    findings = evaluate_row_rule(rule, USERS, now=NOW)
    assert {f["row_ref"] for f in findings} == {"2", "3"}   # ghost (epoch 0) + stale (2020)

def test_never_logged_in_eq_zero():
    rule = _rule([{"target": "lastLoggedIn", "operator": "eq", "value": 0}])
    assert [f["row_ref"] for f in evaluate_row_rule(rule, USERS, now=NOW)] == ["2"]

def test_multi_condition_and():
    rule = _rule([
        {"target": "enabled", "operator": "eq", "value": "true"},
        {"target": "locked",  "operator": "eq", "value": "true"},
    ])
    # only 'stale' is both enabled AND locked
    assert [f["row_ref"] for f in evaluate_row_rule(rule, USERS, now=NOW)] == ["3"]
    # flip one condition false → no matches
    rule2 = _rule([
        {"target": "enabled", "operator": "eq", "value": "true"},
        {"target": "locked",  "operator": "eq", "value": "nope"},
    ])
    assert evaluate_row_rule(rule2, USERS, now=NOW) == []

def test_emit_count_threshold():
    rule = _rule([{"target": "server_count", "operator": "lt", "value": 1}],
                 emit="count", count_operator="gte", count_value=1,
                 title="{count} empty groups")
    findings = evaluate_row_rule(rule, SERVER_GROUPS, now=NOW)
    assert len(findings) == 1 and findings[0]["title"] == "1 empty groups"
    # below threshold → nothing
    rule_hi = _rule([{"target": "server_count", "operator": "lt", "value": 1}],
                    emit="count", count_operator="gte", count_value=5)
    assert evaluate_row_rule(rule_hi, SERVER_GROUPS, now=NOW) == []

def test_templating_tokens():
    rule = _rule(
        [{"target": "used", "operator": "gt", "value": {"ref": "available_total"}}],
        title="Over-allocated: {row.license}",
        message="{row.license} uses {row.used} of {row.available_total} (value={value}, target={target})")
    f = evaluate_row_rule(rule, LICENSES, now=NOW)[0]
    assert f["title"] == "Over-allocated: capacity"
    assert f["message"] == "capacity uses 12 TB of 10 TB (value=12 TB, target=used)"

def test_unknown_operator_and_bad_emit_raise():
    with pytest.raises(ValueError, match="unknown predicate operator"):
        evaluate_row_rule(_rule([{"target": "x", "operator": "wat", "value": 1}]),
                          [{"id": 1, "x": 1}], now=NOW)
    with pytest.raises(ValueError, match="emit must be"):
        evaluate_row_rule(_rule([{"target": "x", "operator": "eq", "value": 1}], emit="weird"),
                          [{"id": 1, "x": 1}], now=NOW)


# ── result_to_artifact compliance pass ────────────────────────────────────────

def _table_result(subject_id, rows, row_rules):
    r = ExtractionResult(subject_id=subject_id, source_type="rest")
    sid = f"{subject_id}.rows"
    r.sections[sid] = rows
    r.section_output_types[sid] = "table"
    r.section_titles[sid] = "Rows"
    r.section_row_rules[sid] = row_rules
    return r

def test_result_to_artifact_emits_compliance_findings_section():
    rule = _rule([{"target": "server_count", "operator": "lt", "value": 1}],
                 severity="critical", title="Empty group: {row.name}",
                 message="Group {row.name} (id {row.id}) has no servers.")
    result = _table_result("server_groups", SERVER_GROUPS, [rule])
    artifact = result_to_artifact(result, "server_groups", "Server Groups")

    comp = next(s for s in artifact.sections if isinstance(s, FindingsSection)
                and s.id == "server_groups.compliance")
    assert comp.title == "Compliance"
    assert [f.title for f in comp.items] == ["Empty group: rommelgroep"]
    assert comp.items[0].severity.value == "critical"
    assert comp.items[0].category == "server_groups.rows"
    # a critical compliance finding drives overall status
    assert artifact.summary.status == ArtifactStatus.critical
    # the table section is still present and unmodified (rules are read-only)
    table = next(s for s in artifact.sections if s.type == "table")
    assert len(table.items) == 3

def test_result_to_artifact_no_rules_no_compliance_section():
    result = _table_result("server_groups", SERVER_GROUPS, [])
    artifact = result_to_artifact(result, "server_groups", "Server Groups")
    assert not any(getattr(s, "id", "").endswith(".compliance") for s in artifact.sections)
