"""ADR 0004 evaluative face.

Phase 2 ships the minimum a metric section needs to show a verdict: a
template-default threshold-rule evaluator (``threshold``). Phase 8 builds the
full face here — Shapes 2/3, the rules registry, vendor → template → override
layering, and the full verdict chain — on top of the same VerdictEntry shape.
"""
from __future__ import annotations

from cvhealthcheck.evaluative.threshold import evaluate_threshold_rule

__all__ = ["evaluate_threshold_rule"]
