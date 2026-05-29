"""
cvhealthcheck.cel.evaluator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thin wrapper over `cel-python` (``celpy``) — the formula language ADR 0004
adopts for derived values, rule predicates, and field-source expressions.

The wrapper exists for three reasons:

1. **One small API surface.** ``evaluate(expression, context)`` takes a CEL
   expression string and a plain Python dict of named values, and returns a
   plain Python value. Callers never touch ``celpy.celtypes`` — the wrapper
   converts the context in (via ``celpy.json_to_cel``) and the result out
   (via ``_to_native``).

2. **Loud failure.** Bad expressions raise; they never silently return None.
   A malformed expression raises ``CELCompileError``; a runtime failure
   (missing field, type mismatch, division by zero, undeclared reference)
   raises ``CELEvaluationError``. Both subclass ``CELError``. This is the
   error behavior ADR 0004 §2a specifies.

3. **The ADR's aggregation primitives.** Plain CEL has ``size()`` but not
   ``sum`` / ``count`` / ``avg`` / ``min`` / ``max`` / ``latest`` — yet
   ADR 0004 §"Catalog-vs-code boundary" enumerates exactly those as
   supported aggregations over a section's ``records``. They are registered
   here as custom CEL functions. This is *implementing* the documented
   primitive set, not extending it: per the ADR's stop-and-steer rule, the
   primitive set is fixed in the ADR and is not widened during
   implementation. Field-level transforms (``parse_number``,
   ``parse_percent``, ``strip_html``, ``lookup``) are also ADR primitives but
   are deferred until a section type exercises them (phase 2+), to avoid
   speculative plumbing.

Note on ADR examples: ADR 0004 §"Formula language" shows
``sum(records.filter(r, r.month == latest_month).used_capacity)``. Field
projection on a filtered *list* (``.used_capacity``) is shorthand — it is not
valid CEL. The faithful, working form projects with ``.map``:
``sum(records.filter(r, r.month == latest_month).map(r, r.used_capacity))``.
"""
from __future__ import annotations

from typing import Any

import celpy
from celpy import celtypes


class CELError(Exception):
    """Base class for all CEL evaluation failures raised by this wrapper."""


class CELCompileError(CELError):
    """The expression could not be parsed/compiled (syntax error)."""


class CELEvaluationError(CELError):
    """The expression compiled but failed at evaluation time.

    Covers missing fields, type mismatches, division by zero, and
    undeclared references — anything CEL surfaces once the program runs
    against a context.
    """


# ── ADR-enumerated aggregation primitives ──
#
# These mirror ADR 0004 §"Catalog-vs-code boundary": "Aggregations over named
# windows: sum, count, avg, min, max, latest over the section's records."
# Each receives celtypes values and returns a celtypes value.

def _numbers(items: Any) -> list[float]:
    return [float(x) for x in items]


def _agg_sum(items: Any) -> celtypes.DoubleType:
    return celtypes.DoubleType(sum(_numbers(items)))


def _agg_count(items: Any) -> celtypes.IntType:
    return celtypes.IntType(len(items))


def _agg_avg(items: Any) -> celtypes.DoubleType:
    nums = _numbers(items)
    if not nums:
        # Loud-fail: averaging an empty window is a real error, not 0.
        raise ZeroDivisionError("avg() of an empty list")
    return celtypes.DoubleType(sum(nums) / len(nums))


def _agg_min(items: Any) -> Any:
    return min(items)


def _agg_max(items: Any) -> Any:
    return max(items)


def _agg_latest(items: Any) -> Any:
    """The last element of the window (most recently collected record).

    Records arrive ordered oldest→newest from the extractor, so the latest
    value is the final element. Raises on an empty window.
    """
    seq = list(items)
    if not seq:
        raise IndexError("latest() of an empty list")
    return seq[-1]


_AGGREGATION_FUNCTIONS: dict[str, Any] = {
    "sum": _agg_sum,
    "count": _agg_count,
    "avg": _agg_avg,
    "min": _agg_min,
    "max": _agg_max,
    "latest": _agg_latest,
}


# A single shared environment is safe to reuse — celpy environments are
# stateless across compiles.
_ENV = celpy.Environment()


def evaluate(expression: str, context: dict[str, Any] | None = None) -> Any:
    """Evaluate a CEL ``expression`` against ``context``; return a native value.

    ``context`` maps variable names to plain Python values (dicts, lists,
    str/int/float/bool/None). Values are converted to CEL types internally.
    The result is converted back to native Python types.

    Raises ``CELCompileError`` if the expression is malformed and
    ``CELEvaluationError`` if it fails at runtime. Never returns None to
    signal failure — failures raise.
    """
    context = context or {}

    try:
        ast = _ENV.compile(expression)
    except celpy.CELParseError as exc:
        raise CELCompileError(f"Could not compile CEL expression {expression!r}: {exc}") from exc

    program = _ENV.program(ast, functions=_AGGREGATION_FUNCTIONS)

    try:
        activation = {name: celpy.json_to_cel(value) for name, value in context.items()}
    except (ValueError, TypeError) as exc:
        raise CELEvaluationError(
            f"Could not convert context for CEL expression {expression!r}: {exc}"
        ) from exc

    try:
        result = program.evaluate(activation)
    except celpy.CELEvalError as exc:
        raise CELEvaluationError(
            f"CEL expression {expression!r} failed at evaluation: {exc}"
        ) from exc
    except (ZeroDivisionError, IndexError, ValueError, TypeError, KeyError) as exc:
        # Errors raised from registered aggregation functions surface here.
        raise CELEvaluationError(
            f"CEL expression {expression!r} failed at evaluation: {exc}"
        ) from exc

    # celpy can also *return* (rather than raise) a CELEvalError value.
    if isinstance(result, celpy.CELEvalError):
        raise CELEvaluationError(f"CEL expression {expression!r} failed at evaluation: {result}")

    return _to_native(result)


def _to_native(value: Any) -> Any:
    """Convert celpy celtypes back to plain Python recursively.

    celtypes subclass their Python counterparts, so most values would behave
    natively even unconverted — but artifacts are stored as JSON and tests
    compare against plain values, so we normalise explicitly.
    """
    # bool before int: BoolType subclasses int.
    if isinstance(value, celtypes.BoolType) or isinstance(value, bool):
        return bool(value)
    if isinstance(value, (celtypes.IntType, celtypes.UintType)):
        return int(value)
    if isinstance(value, celtypes.DoubleType):
        return float(value)
    if isinstance(value, celtypes.StringType):
        return str(value)
    if isinstance(value, celtypes.BytesType):
        return bytes(value)
    if isinstance(value, (celtypes.ListType, list, tuple)):
        return [_to_native(v) for v in value]
    if isinstance(value, (celtypes.MapType, dict)):
        return {_to_native(k): _to_native(v) for k, v in value.items()}
    return value
