"""
cvhealthcheck.db.rules
~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 phase 8 step 2 — the rules registry (DP1).

A named rule definition lives once in the ``rules`` table, addressed by
``rule_id`` (flat global namespace, DP3 — the PRIMARY KEY enforces uniqueness,
so a collision is an authoring error caught at insert/migration time). Catalog
sections reference a rule by ``{"ref": rule_id, …binding…}`` instead of inlining
the body; the evaluative engine resolves the ref against this registry at
canonicalization time.

This module *loads* the registry and (ADR 0010) resolves a subject's row-rule
*bindings* into concrete definitions — both catalog reads. Evaluation itself
happens elsewhere (``evaluative/engine.py`` for metric/card inside
``result_to_artifact``; ``evaluative/row_match.py`` for row-scope rules). Loading
registry rows / bindings here is the same kind of catalog read the extractors
already do for ``extraction_instructions``; it is not evaluation.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def load_rules_registry(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return ``{rule_id: definition_dict}`` for every registered rule.

    Defensive against a DB migrated below 0018 (no ``rules`` table yet) — returns
    an empty registry rather than raising, so extraction still runs (inline rules
    are unaffected; only refs would then fail to resolve, loudly, at build time).
    """
    try:
        rows = db.execute("SELECT rule_id, definition_json FROM rules").fetchall()
    except sqlite3.OperationalError:
        return {}
    registry: dict[str, dict[str, Any]] = {}
    for row in rows:
        registry[row["rule_id"]] = json.loads(row["definition_json"])
    return registry


def load_subject_row_rules(
    db: sqlite3.Connection, subject_id: str, version: int = 1
) -> dict[str, list[dict[str, Any]]]:
    """ADR 0010 D2 — resolve a subject's row-scope rule *bindings* into
    ``{section_id: [resolved row_match rule defs]}``.

    A table section binds row rules in its ``extraction_instructions`` under
    ``evaluative.row_rules`` as ``[{"ref": rule_id}]`` (the same ref-from-binding
    model the metric/card rules use). Each ref is resolved against the rules
    registry (``engine.resolve_rule`` — an unknown ref fails loudly). Only
    ``kind == "row_match"`` defs are returned; refs are deduped per section by
    ``rule_id``. Defensive against a DB with no registry / no bindings (returns an
    empty map) so collection still runs.

    Feeds both the dry-run (``evaluate_subject`` over the latest artifact) and the
    extractors (``result.section_row_rules`` at collection time)."""
    from cvhealthcheck.evaluative.engine import resolve_rule

    registry = load_rules_registry(db)
    try:
        rows = db.execute(
            "SELECT sss.section_id AS section_id,"
            "       sss.extraction_instructions AS instr "
            "FROM subject_section_sources sss "
            "JOIN subject_sources src ON src.id = sss.source_id "
            "WHERE src.subject_id = ? AND src.subject_version = ?",
            (subject_id, version),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        try:
            instructions = json.loads(row["instr"]) if row["instr"] else {}
        except (json.JSONDecodeError, TypeError):
            continue
        entries = ((instructions.get("evaluative") or {}).get("row_rules")) or []
        section_id = row["section_id"]
        for entry in entries:
            resolved = resolve_rule(entry, registry)
            if resolved.get("kind") != "row_match":
                continue
            bucket = out.setdefault(section_id, [])
            if not any(r.get("rule_id") == resolved.get("rule_id") for r in bucket):
                bucket.append(resolved)
    return out
