"""
cvhealthcheck.db.domain_labels
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Read access to the controlled domain-label vocabulary (the ``domain_label``
table, migration 0029).

The catalog classifies subjects on two axes: ``subjects.category`` is the
single / primary axis (exactly one per subject version), and domain labels are
the additive, many-valued axis (via the ``subject_domain_labels`` association).
The two vocabularies are disjoint by construction.

Phase 1 exposes the vocabulary only — no subject is labeled yet. These accessors
are reused by later phases (the authoring-side unknown-label check and the MCP
read path) and by the schema tests. Connections are expected to come from
``cvhealthcheck.db.database.get_db`` (``row_factory = sqlite3.Row``).
"""
from __future__ import annotations

import sqlite3


def list_domain_labels(db: sqlite3.Connection) -> list[dict]:
    """Return the full domain-label vocabulary.

    Ordered by ``sort_order`` (nulls last) then ``label``. Each row is a dict:
    ``{label, display_label, description, sort_order}``.
    """
    rows = db.execute(
        """
        SELECT label, display_label, description, sort_order
        FROM domain_label
        ORDER BY sort_order IS NULL, sort_order, label
        """
    ).fetchall()
    return [
        {
            "label": r["label"],
            "display_label": r["display_label"],
            "description": r["description"],
            "sort_order": r["sort_order"],
        }
        for r in rows
    ]


def domain_label_vocabulary(db: sqlite3.Connection) -> set[str]:
    """Return the set of valid domain-label slugs."""
    return {r["label"] for r in db.execute("SELECT label FROM domain_label")}


def subject_labels_map(db: sqlite3.Connection) -> dict[int, list[str]]:
    """Map ``subject_row_id`` -> ordered domain-label slugs, in a single query.

    Built from one join over ``subject_domain_labels`` and ``domain_label``,
    ordered by ``sort_order`` (nulls last) then ``label`` so a subject's labels
    have a deterministic order. Subjects with no labels are absent from the map —
    callers default to ``[]``.

    Use this instead of a per-subject lookup: a caller listing every subject
    would otherwise issue one query per subject (N+1).
    """
    rows = db.execute(
        """
        SELECT sdl.subject_row_id AS subject_row_id, sdl.label AS label
        FROM subject_domain_labels AS sdl
        JOIN domain_label AS dl ON dl.label = sdl.label
        ORDER BY sdl.subject_row_id,
                 dl.sort_order IS NULL, dl.sort_order, dl.label
        """
    ).fetchall()
    result: dict[int, list[str]] = {}
    for r in rows:
        result.setdefault(r["subject_row_id"], []).append(r["label"])
    return result
