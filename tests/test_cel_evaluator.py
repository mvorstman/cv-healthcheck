"""Tests for the ADR 0004 CEL evaluator wrapper.

Covers the four example expressions from ADR 0004 §"Formula language", the
ADR-enumerated aggregation primitives, native-type round-tripping, and the
loud-fail error behavior (malformed / missing field / type mismatch).
"""
import math

import pytest

from cvhealthcheck.cel import (
    CELCompileError,
    CELError,
    CELEvaluationError,
    evaluate,
)


# Shared fixtures: a 13-month-ish records window like the regressed subjects'.
RECORDS = [
    {"month": "2024-06", "total_clients": 100, "used_capacity": 10.0, "purchased_capacity": 50.0},
    {"month": "2024-07", "total_clients": 110, "used_capacity": 20.0, "purchased_capacity": 50.0},
    {"month": "2024-08", "total_clients": 125, "used_capacity": 35.0, "purchased_capacity": 50.0},
]


# ── ADR §"Formula language" example expressions ──

def test_index_last_record_field():
    # records[size(records)-1].total_clients
    assert evaluate("records[size(records)-1].total_clients", {"records": RECORDS}) == 125


def test_filter_map_sum_latest_month():
    # ADR shorthand: sum(records.filter(r, r.month == latest_month).used_capacity)
    # Faithful CEL uses .map to project the field off the filtered list.
    expr = "sum(records.filter(r, r.month == latest_month).map(r, r.used_capacity))"
    assert evaluate(expr, {"records": RECORDS, "latest_month": "2024-08"}) == 35.0


def test_arithmetic_percentage():
    # latest_used / latest_purchased * 100.0
    result = evaluate(
        "latest_used / latest_purchased * 100.0",
        {"latest_used": 35.0, "latest_purchased": 50.0},
    )
    assert result == pytest.approx(70.0)


def test_size_guard_and_yoy_predicate():
    # records.size() >= 13 && records[size(records)-13].total_clients > 0
    # Only 3 records here, so the guard short-circuits to False.
    expr = "records.size() >= 13 && records[size(records)-13].total_clients > 0"
    assert evaluate(expr, {"records": RECORDS}) is False

    # With 13 records the guard passes and the second clause is evaluated.
    thirteen = [{"total_clients": 5} for _ in range(13)]
    assert evaluate(expr, {"records": thirteen}) is True


# ── ADR-enumerated aggregation primitives ──

def test_aggregation_primitives():
    used = "records.map(r, r.used_capacity)"
    assert evaluate(f"sum({used})", {"records": RECORDS}) == pytest.approx(65.0)
    assert evaluate(f"count({used})", {"records": RECORDS}) == 3
    assert evaluate(f"avg({used})", {"records": RECORDS}) == pytest.approx(65.0 / 3)
    assert evaluate(f"min({used})", {"records": RECORDS}) == pytest.approx(10.0)
    assert evaluate(f"max({used})", {"records": RECORDS}) == pytest.approx(35.0)
    assert evaluate(f"latest({used})", {"records": RECORDS}) == pytest.approx(35.0)


def test_latest_returns_last_element():
    assert evaluate("latest(records).month", {"records": RECORDS}) == "2024-08"


# ── Native-type round-tripping (no celtypes leak out) ──

def test_results_are_native_python_types():
    assert type(evaluate("1 + 1", {})) is int
    assert type(evaluate("1.5 + 1.5", {})) is float
    assert type(evaluate("'a' + 'b'", {})) is str
    assert type(evaluate("true && false", {})) is bool
    listed = evaluate("[1, 2, 3]", {})
    assert listed == [1, 2, 3] and type(listed) is list
    mapped = evaluate("{'k': 1}", {})
    assert mapped == {"k": 1} and type(mapped) is dict


def test_empty_context_allowed():
    assert evaluate("2 * 21") == 42


# ── Loud-fail error behavior ──

def test_malformed_expression_raises_compile_error():
    with pytest.raises(CELCompileError):
        evaluate("this is not valid (", {})


def test_missing_field_raises_evaluation_error():
    with pytest.raises(CELEvaluationError):
        evaluate("records[0].nonexistent_field", {"records": RECORDS})


def test_undeclared_reference_raises_evaluation_error():
    with pytest.raises(CELEvaluationError):
        evaluate("totally_undeclared_name + 1", {})


def test_type_mismatch_raises_evaluation_error():
    with pytest.raises(CELEvaluationError):
        evaluate("1 + 'a'", {})


def test_division_by_zero_raises_evaluation_error():
    with pytest.raises(CELEvaluationError):
        evaluate("1 / 0", {})


def test_avg_empty_window_raises_evaluation_error():
    with pytest.raises(CELEvaluationError):
        evaluate("avg(records.map(r, r.x))", {"records": []})


def test_error_subclasses_share_base():
    assert issubclass(CELCompileError, CELError)
    assert issubclass(CELEvaluationError, CELError)
