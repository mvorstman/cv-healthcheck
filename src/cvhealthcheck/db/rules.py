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

This module only *loads* the registry (catalog data) — resolution + evaluation
happen in ``evaluative/engine.py`` inside ``result_to_artifact`` (the one
canonicalization path). Loading registry rows here is the same kind of catalog
read the extractors already do for ``extraction_instructions``; it is not
evaluation.
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
