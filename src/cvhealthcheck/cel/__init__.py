"""CEL (Common Expression Language) plumbing for ADR 0004.

The three-face metadata vocabulary uses CEL for derived values, rule
predicates, and field-source expressions. This package provides the thin
evaluator wrapper over the `cel-python` library (imported as ``celpy``)
that ADR 0004 §"Formula language" calls for.

Public surface:

    from cvhealthcheck.cel import evaluate, CELError, CELCompileError,
        CELEvaluationError
"""
from __future__ import annotations

from cvhealthcheck.cel.evaluator import (
    CELCompileError,
    CELError,
    CELEvaluationError,
    evaluate,
)

__all__ = [
    "evaluate",
    "CELError",
    "CELCompileError",
    "CELEvaluationError",
]
