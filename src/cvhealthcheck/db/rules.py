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

import copy
import json
import sqlite3
from typing import Any


# ── ADR-0015 D2a: recipe immutability guard ───────────────────────────────────
#
# Approval locks the extraction RECIPE. The only post-approval write to a
# section's extraction_instructions is rule (un)binding, which may touch ONLY
# evaluative.row_rules. Bindings are an intentionally-mutable layer co-located in
# the section blob today (physical separation is D4). This guard makes approval
# truthful: it rejects any write whose non-row_rules content differs from the
# stored row — an ALLOWLIST (only row_rules may change), so a recipe key nobody
# enumerated, and every other evaluative subkey, is protected by default.

class RecipeImmutabilityError(ValueError):
    """A guarded write tried to change something other than evaluative.row_rules
    in an approved section's extraction_instructions (ADR-0015 D2a)."""


def _as_instr_dict(instr: Any) -> dict[str, Any]:
    if isinstance(instr, dict):
        return instr
    if not instr:
        return {}
    try:
        parsed = json.loads(instr)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _instr_minus_row_rules(instr: Any) -> dict[str, Any]:
    """A deep copy of extraction_instructions with evaluative.row_rules removed;
    an 'evaluative' dict left empty by that removal is dropped, so 'no evaluative'
    and 'evaluative holding only row_rules' compare equal (the first-bind case)."""
    clone = copy.deepcopy(_as_instr_dict(instr))
    evaluative = clone.get("evaluative")
    if isinstance(evaluative, dict):
        evaluative.pop("row_rules", None)
        if not evaluative:
            clone.pop("evaluative", None)
    return clone


def assert_recipe_unchanged(old_instr: Any, new_instr: Any) -> None:
    """Raise RecipeImmutabilityError unless OLD and NEW extraction_instructions are
    structurally identical except for evaluative.row_rules. Compares PARSED
    structures (each arg may be a raw JSON string or a dict), so JSON key
    reordering never trips the guard."""
    if _instr_minus_row_rules(old_instr) != _instr_minus_row_rules(new_instr):
        raise RecipeImmutabilityError(
            "post-approval write may change only evaluative.row_rules; the recipe "
            "(or another evaluative subkey) differs — locked at approval (ADR-0015 D2a)"
        )


def _write_section_instructions(
    db: sqlite3.Connection, row_id: int, old_instr: Any, new_instr: dict[str, Any]
) -> None:
    """Guarded UPDATE of a section's extraction_instructions: rejects any
    non-row_rules delta (ADR-0015 D2a), then persists. Version-agnostic — it
    validates WHAT changed, never WHICH rows are written (multi-version write
    scoping is unchanged; see bind_rule)."""
    assert_recipe_unchanged(old_instr, new_instr)
    db.execute(
        "UPDATE subject_section_sources SET extraction_instructions = ? WHERE id = ?",
        (json.dumps(new_instr), row_id),
    )


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
            # A ref in `evaluative.row_rules` IS a row rule by construction; a def
            # with no explicit `kind` is treated as row_match — the same default
            # the authoring validator applies (validate_row_match_rule). Only a def
            # explicitly some OTHER kind is skipped. (Without this default, a rule
            # authored via save_rule without an explicit kind binds + lists but is
            # silently never evaluated — the read/author divergence this fixes.)
            if resolved.get("kind", "row_match") != "row_match":
                continue
            if not resolved.get("enabled", True):
                continue  # disabled rules don't fire (collection or dry-run)
            bucket = out.setdefault(section_id, [])
            if not any(r.get("rule_id") == resolved.get("rule_id") for r in bucket):
                bucket.append(resolved)
    return out


def load_subject_section_scope(
    db: sqlite3.Connection, subject_id: str, version: int = 1
) -> dict[str, list[dict[str, Any]]]:
    """ADR 0010 — the section-level evaluation SCOPE per section, from
    ``extraction_instructions.evaluative.scope``: a list of AND-ed conditions
    (same shape/operators as row_match conditions). Absent ⇒ no entry (all rows in
    scope). First non-empty scope per section wins (scope is section-level — every
    bound rule inherits it). Feeds both the dry-run and the extractors."""
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
        scope = (instructions.get("evaluative") or {}).get("scope")
        section_id = row["section_id"]
        if isinstance(scope, list) and scope and section_id not in out:
            out[section_id] = scope
    return out


# ── ADR 0010 Phase 2b: authoring (list / save / bind / delete / validate) ─────

def list_rules(
    db: sqlite3.Connection,
    *,
    subject_id: str | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Registered rule definitions. ``subject_id`` filters to rules **bound** to
    that subject (via section ``evaluative.row_rules`` refs, incl. disabled).
    ``enabled`` filters on the def's ``enabled`` flag (default True)."""
    registry = load_rules_registry(db)
    if subject_id is not None:
        bound = _subject_bound_rule_ids(db, subject_id)
        items = [d for rid, d in registry.items() if rid in bound]
    else:
        items = list(registry.values())
    if enabled is not None:
        items = [d for d in items if bool(d.get("enabled", True)) is bool(enabled)]
    return sorted(items, key=lambda d: str(d.get("rule_id")))


def save_rule(db: sqlite3.Connection, definition: dict[str, Any]) -> dict[str, Any]:
    """Upsert a rule definition by ``rule_id`` (the body is the JSON blob). Bumps
    ``version`` when the body changed; preserves the original ``created_by`` on
    update; defaults ``enabled`` to True. Returns the stored definition.

    Kind-specific validation (``validate_row_match_rule``) is the caller's
    responsibility — this is the low-level persist."""
    rule_id = definition.get("rule_id")
    if not rule_id:
        raise ValueError("rule_id is required")
    existing = load_rules_registry(db).get(rule_id)
    new_def = dict(definition)
    new_def.setdefault("enabled", True)
    if existing is None:
        new_def["created_by"] = new_def.get("created_by", "ai")
        new_def["version"] = int(new_def.get("version") or 1)
    else:
        new_def["created_by"] = existing.get("created_by", new_def.get("created_by", "ai"))
        prev = {k: v for k, v in existing.items() if k != "version"}
        cur = {k: v for k, v in new_def.items() if k != "version"}
        new_def["version"] = existing.get("version", 1) + (1 if cur != prev else 0)
    db.execute(
        "INSERT INTO rules (rule_id, definition_json, created_by) VALUES (?, ?, ?) "
        "ON CONFLICT(rule_id) DO UPDATE SET definition_json = excluded.definition_json",
        (rule_id, json.dumps(new_def), new_def["created_by"]),
    )
    db.commit()
    return new_def


def bind_rule(
    db: sqlite3.Connection, rule_id: str, subject_id: str, section_id: str
) -> int:
    """Add ``{"ref": rule_id}`` to every source binding of (subject, section)'s
    ``extraction_instructions.evaluative.row_rules`` — idempotent (never a
    duplicate ref). Returns the number of bindings newly written."""
    rows = db.execute(
        "SELECT sss.id AS id, sss.extraction_instructions AS instr "
        "FROM subject_section_sources sss "
        "JOIN subject_sources src ON src.id = sss.source_id "
        "WHERE src.subject_id = ? AND sss.section_id = ?",
        (subject_id, section_id),
    ).fetchall()
    bound = 0
    for row in rows:
        try:
            instr = json.loads(row["instr"]) if row["instr"] else {}
        except (json.JSONDecodeError, TypeError):
            instr = {}
        row_rules = instr.setdefault("evaluative", {}).setdefault("row_rules", [])
        if not any(e.get("ref") == rule_id for e in row_rules):
            row_rules.append({"ref": rule_id})
            # ADR-0015 D2a: guarded write — only evaluative.row_rules may change.
            _write_section_instructions(db, row["id"], row["instr"], instr)
            bound += 1
    db.commit()
    return bound


def delete_rule(db: sqlite3.Connection, rule_id: str) -> dict[str, Any]:
    """Delete a registry rule AND strip its ``{ref}`` from every section binding,
    so a later collection can't hit the loud "unknown ref" on a dangling
    reference. (There is no findings table — D5; findings live in artifacts — so
    no FK cascade is involved.)"""
    stripped = 0
    rows = db.execute(
        "SELECT id, extraction_instructions FROM subject_section_sources"
    ).fetchall()
    for row in rows:
        instr_raw = row["extraction_instructions"]
        if not instr_raw or rule_id not in instr_raw:
            continue
        try:
            instr = json.loads(instr_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        row_rules = (instr.get("evaluative") or {}).get("row_rules") or []
        kept = [e for e in row_rules if e.get("ref") != rule_id]
        if len(kept) != len(row_rules):
            instr["evaluative"]["row_rules"] = kept
            # ADR-0015 D2a: guarded write — only evaluative.row_rules may change.
            _write_section_instructions(db, row["id"], instr_raw, instr)
            stripped += 1
    cur = db.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,))
    db.commit()
    return {"deleted": rule_id, "existed": cur.rowcount > 0, "bindings_stripped": stripped}


def validate_row_match_rule(
    db: sqlite3.Connection,
    definition: dict[str, Any],
    *,
    bind: dict[str, str] | None = None,
) -> None:
    """Reject a malformed/un-bindable row_match rule at AUTHORING time (raises
    ValueError) rather than failing silently at collection. ADR 0010 §8."""
    from cvhealthcheck.evaluative import coerce
    from cvhealthcheck.evaluative.row_match import COUNT_OPERATORS, KNOWN_OPERATORS

    if not definition.get("rule_id"):
        raise ValueError("rule_id is required")
    if definition.get("kind", "row_match") != "row_match":
        raise ValueError(f"this authors row_match rules; got kind={definition.get('kind')!r}")
    scope = definition.get("scope", "row")
    if scope != "row":
        # TODO: when summary scope lands, scope=summary must reject emit != once (ADR §8).
        raise ValueError(f"scope {scope!r} is not yet supported (only 'row')")
    if definition.get("severity") not in ("critical", "warning", "info", "good"):
        raise ValueError(f"severity must be critical/warning/info/good, got {definition.get('severity')!r}")

    conditions = definition.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("conditions must be a non-empty list")
    for cond in conditions:
        op = cond.get("operator")
        if op not in KNOWN_OPERATORS:
            raise ValueError(f"unknown operator {op!r} (supported: {sorted(KNOWN_OPERATORS)})")
        if op == "between" and cond.get("value2") is None:
            raise ValueError(f"operator 'between' requires value2 (target {cond.get('target')!r})")
        # ADR 0011 D4: a version operator's LITERAL threshold must parse (fail loud
        # at authoring, same class as an unknown operator). A {ref} value is a
        # column compared at eval time, not a typed literal — skip the check.
        if op in ("version_lt", "version_gte"):
            val = cond.get("value")
            if not (isinstance(val, dict) and "ref" in val) and coerce.parse_version(val) is None:
                raise ValueError(
                    f"operator {op!r} requires a parseable version literal; got value={val!r}"
                )

    emit = definition.get("emit", "per_row")
    if emit not in ("per_row", "count"):
        raise ValueError(f"emit must be 'per_row' or 'count', got {emit!r}")
    if emit == "count":
        if definition.get("count_operator") not in COUNT_OPERATORS:
            raise ValueError("emit=count requires count_operator in lt/lte/gt/gte/eq/ne")
        if definition.get("count_value") is None:
            raise ValueError("emit=count requires count_value")

    if bind is not None:
        from cvhealthcheck.db.subjects import get_subject
        subject_id, section_id = bind.get("subject_id"), bind.get("section_id")
        # Scope all section lookups to the ACTIVE subject version (the same version
        # the collection path resolves via get_subject). subject_sections holds one
        # row per version, and a section's type/columns can differ across versions
        # (e.g. cache_configuration: card v1-3 → table v4); an unscoped lookup picks
        # the lowest-rowid (oldest) version and would reject a valid bind.
        active = get_subject(db, subject_id)
        if active is None:
            raise ValueError(f"subject {subject_id!r} has no active version to bind to")
        version = active["version"]
        section = db.execute(
            "SELECT section_type FROM subject_sections"
            " WHERE subject_id = ? AND section_id = ? AND subject_version = ?",
            (subject_id, section_id, version),
        ).fetchone()
        if section is None:
            raise ValueError(f"section {section_id!r} is not present on subject {subject_id!r}")
        if section["section_type"] != "table":
            raise ValueError(
                f"a row-scope rule must bind to a table section; "
                f"{section_id!r} is {section['section_type']!r}"
            )
        columns = _section_column_ids(db, subject_id, section_id, version)
        if columns:  # only enforce when the section declares its columns
            referenced: set[str] = set()
            for cond in conditions:
                if cond.get("target"):
                    referenced.add(cond["target"])
                value = cond.get("value")
                if isinstance(value, dict) and value.get("ref"):
                    referenced.add(value["ref"])
            missing = sorted(c for c in referenced if c not in columns)
            if missing:
                raise ValueError(
                    f"conditions reference columns not in section {section_id!r}: "
                    f"{missing} (available: {sorted(columns)})"
                )


def _subject_bound_rule_ids(db: sqlite3.Connection, subject_id: str) -> set[str]:
    """rule_ids referenced by any of the subject's section bindings (incl. disabled)."""
    rows = db.execute(
        "SELECT sss.extraction_instructions AS instr FROM subject_section_sources sss "
        "JOIN subject_sources src ON src.id = sss.source_id WHERE src.subject_id = ?",
        (subject_id,),
    ).fetchall()
    ids: set[str] = set()
    for row in rows:
        try:
            instr = json.loads(row["instr"]) if row["instr"] else {}
        except (json.JSONDecodeError, TypeError):
            continue
        for entry in ((instr.get("evaluative") or {}).get("row_rules")) or []:
            if entry.get("ref"):
                ids.add(entry["ref"])
    return ids


def _section_column_ids(
    db: sqlite3.Connection, subject_id: str, section_id: str, version: int
) -> set[str]:
    """The column ids a section's bindings declare (table.columns / columns /
    column_map) for the ACTIVE ``version``, unioned across its sources — the
    universe a condition target/ref must come from.

    A transpose property section ALSO admits the implicit per-row keys
    (``id``/``key``/``label``/``value`` — see ``_project_table_rows``) as valid
    rule TARGETS, even though only ``table.columns`` drives DISPLAY (Setting/Value).
    Targetability and display are decoupled here: a rule keyed on the stable
    ``key``/``id`` (target the key, never the label) validates without those keys
    leaking into the rendered columns."""
    rows = db.execute(
        "SELECT sss.extraction_instructions AS instr FROM subject_section_sources sss "
        "JOIN subject_sources src ON src.id = sss.source_id "
        "WHERE src.subject_id = ? AND src.subject_version = ? AND sss.section_id = ?",
        (subject_id, version, section_id),
    ).fetchall()
    cols: set[str] = set()
    for row in rows:
        try:
            instr = json.loads(row["instr"]) if row["instr"] else {}
        except (json.JSONDecodeError, TypeError):
            continue
        table = instr.get("table") if isinstance(instr.get("table"), dict) else {}
        for col in (table.get("columns") or []):
            if isinstance(col, dict) and col.get("id"):
                cols.add(col["id"])
        for col in (instr.get("columns") or []):
            if isinstance(col, dict) and col.get("id"):
                cols.add(col["id"])
        for col in (instr.get("column_map") or []):
            if isinstance(col, dict) and (col.get("canonical") or col.get("id")):
                cols.add(col.get("canonical") or col.get("id"))
        if table.get("transpose"):           # implicit per-row target columns
            cols.update({"id", "key", "label", "value"})
    return cols
