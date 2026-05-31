"""
cvhealthcheck.db.rule_overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 8 step 3 — the override layer's storage (DP10).

An override is a per-assessment waiver/adjustment of a rule's verdict, keyed to
the live entity model:

    (customer_id, project_id?, subject_id, subject_version, section_id, rule_id)

``project_id`` is the default scope ("this assessment") and is NOT NULL by
default; a customer-wide *standing* waiver is the deliberate exception, written
with ``project_id IS NULL``. (The design draft's ``engagement_id`` keyed a DEAD
table — the ``engagements`` orphan, backlog #13 — which would have made every
override silently customer-wide; ``project_id`` is the entity that actually
exists.)

This module only *loads* overrides (catalog/policy read). Resolution into the
verdict_chain happens in ``evaluative/engine.py`` at canonicalization — and only
for the WORKING artifact being built. Finalized artifacts are read as-stored and
never re-resolved against current overrides (ADR 0006: verdicts computed at
canonicalization, read at render; finalization is a second frozen canonicalization
point).
"""
from __future__ import annotations

import sqlite3
from typing import Any


def load_section_overrides(
    db: sqlite3.Connection,
    customer_id: str,
    project_id: str,
    subject_id: str,
    version: int,
) -> dict[str, list[dict[str, Any]]]:
    """Return ``{section_id: [{rule_id, severity, reason}, …]}`` for the active
    (customer, project) + subject version.

    Matches project-specific overrides (``project_id = ?``) AND customer-wide
    standing ones (``project_id IS NULL``). When both exist for the same
    ``(section_id, rule_id)``, the **project-specific** one wins (more specific
    scope) — so a customer-wide standing waiver is the fallback, not a
    double-fire.

    Defensive against a DB migrated below 0019 (no ``rule_overrides`` table) —
    returns ``{}`` rather than raising.
    """
    try:
        rows = db.execute(
            "SELECT section_id, rule_id, severity, reason, project_id "
            "FROM rule_overrides "
            "WHERE customer_id = ? AND subject_id = ? AND subject_version = ? "
            "AND (project_id = ? OR project_id IS NULL)",
            (customer_id, subject_id, version, project_id),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    # (section_id, rule_id) -> row, preferring a project-specific row over a
    # customer-wide (NULL) one.
    chosen: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        key = (row["section_id"], row["rule_id"])
        incumbent = chosen.get(key)
        if incumbent is None or (incumbent["project_id"] is None and row["project_id"] is not None):
            chosen[key] = row

    out: dict[str, list[dict[str, Any]]] = {}
    for (section_id, _rule_id), row in chosen.items():
        out.setdefault(section_id, []).append(
            {"rule_id": row["rule_id"], "severity": row["severity"], "reason": row["reason"]}
        )
    return out
