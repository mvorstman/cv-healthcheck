"""
cvhealthcheck.evaluative.subject_eval
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0010 Phase 2 — the row-scope dry-run. The rules-side parallel to ``probe``:
re-run a subject's bound ``row_match`` rules over its **latest stored artifact**
and return a findings preview **without persisting** anything.

It does NOT re-collect and does NOT touch the artifact (D4/D5: findings are
re-derivable; the stored artifact is read-only here). It reuses the exact
evaluator the canonicalization pass uses (``row_match.evaluate_row_rule``) and
the exact binding loader the extractors use (``load_subject_row_rules``), so the
preview matches what the next collection would bake in.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from cvhealthcheck.artifacts.models import TableSection
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.db.rules import load_subject_row_rules
from cvhealthcheck.evaluative.row_match import evaluate_row_rule


def evaluate_subject(
    db: sqlite3.Connection,
    subject_id: str,
    *,
    version: int | None = None,
    store: ArtifactStore | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Dry-run: the subject's bound ``row_match`` rules evaluated over its latest
    artifact's table sections. Returns a preview dict::

        {"subject_id", "has_artifact": bool, "rules_evaluated": int,
         "count": int, "findings": [ {rule_id, severity, row_ref, title,
         message, recommendation, section_id}, ... ]}

    Persists nothing. ``has_artifact=False`` when the subject has no collected
    artifact yet (preview is empty, not an error)."""
    if version is None:
        from cvhealthcheck.db.subjects import get_subject
        subject = get_subject(db, subject_id)
        version = subject["version"] if subject else 1

    row_rules = load_subject_row_rules(db, subject_id, version)
    store = store or ArtifactStore("default", "default")
    try:
        artifact = store.load_latest_artifact(subject_id)
    except FileNotFoundError:
        return {
            "subject_id": subject_id, "has_artifact": False,
            "rules_evaluated": 0, "count": 0, "findings": [],
            "note": "no collected artifact to evaluate",
        }

    table_rows = {
        sec.id: [dict(item) for item in sec.items]
        for sec in artifact.sections
        if isinstance(sec, TableSection)
    }

    findings: list[dict[str, Any]] = []
    rules_evaluated = 0
    for section_id, rules in row_rules.items():
        rows = table_rows.get(section_id) or []
        for rule in rules:
            rules_evaluated += 1
            for derived in evaluate_row_rule(rule, rows, now=now):
                derived = dict(derived)
                derived["section_id"] = section_id
                findings.append(derived)

    return {
        "subject_id": subject_id, "has_artifact": True,
        "rules_evaluated": rules_evaluated, "count": len(findings),
        "findings": findings,
    }
