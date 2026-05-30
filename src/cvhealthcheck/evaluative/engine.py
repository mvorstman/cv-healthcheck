"""
cvhealthcheck.evaluative.engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 8 — the single evaluation locus for metric/card sections.

``evaluate(value, rule, *, label, unit)`` is the one place a metric item or a
card section turns a value + a ``template_default`` threshold rule into a
resolved ``(severity, verdict_chain)``.

Phase 8 step 1 is a **pure refactor**: it unifies the two previously-duplicated
call sites (``metric_section`` per item, ``card_section`` per section) onto this
single function, with **no behavior change** — it delegates to the existing
``evaluate_threshold_rule`` primitive and produces the identical single-entry
``template_default`` chain phase 2 produced.

Later phase-8 steps EXTEND this locus (vendor → template → override layering,
the rules registry, Shapes 2/3); they do not add a second evaluator. Per ADR
0004 phase-8 design DP7 option (i): **findings are transcribed at extraction**
(``status_to_severity``), not evaluated here — only metric/card route through
this engine.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import VerdictEntry
from cvhealthcheck.evaluative.threshold import evaluate_threshold_rule


def evaluate(
    value: float | int | None,
    rule: dict[str, Any] | None,
    *,
    label: str,
    unit: str | None = None,
) -> tuple[FindingSeverity | None, list[VerdictEntry]]:
    """Resolve ``(severity, verdict_chain)`` for one evaluated value.

    No rule → the value is unjudged → ``(None, [])`` (a metric item / card with
    no evaluative rule). With a ``template_default`` threshold rule, return a
    single-entry verdict chain — byte-identical to the prior per-call-site
    ``evaluate_threshold_rule`` usage, now funnelled through one locus.
    """
    if rule is None:
        return None, []
    verdict = evaluate_threshold_rule(rule, value, label=label, unit=unit)
    return verdict.severity, [verdict]
