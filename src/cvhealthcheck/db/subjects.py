from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from cvhealthcheck.extractors.cc_endpoint import (
    COMMAND_CENTER_SOURCE_TYPE,
    validate_cc_endpoint,
)
from cvhealthcheck.extractors.rp_dataset_address import (
    REPORTSPLUS_DATASET_SOURCE_TYPE,
    validate_rp_dataset_address,
)

from .categories import CATEGORY_LABELS
from .section_types import validate_section_type


# ADR 0004 subject versioning: v2+ land as new subject rows with a "_vN"
# suffix on the subject_id (capacity_license_v2). v1 is implicit (no suffix).
# The "family" is the subject_id with the suffix stripped; both
# capacity_license and capacity_license_v2 belong to family capacity_license.
# The suffix must be terminal and must not be the whole id ("v2" has no
# family-bearing prefix, so it stays "v2").
_VERSION_SUFFIX_RE = re.compile(r"^(?P<family>.+)_v\d+$")


def subject_family(subject_id: str) -> str:
    """Return the subject family for a subject_id by stripping a trailing _vN.

    capacity_license      -> capacity_license   (no suffix; v1 is implicit)
    capacity_license_v2   -> capacity_license
    capacity_license_v10  -> capacity_license
    something_v2_else     -> something_v2_else   (suffix must be terminal)
    v2                    -> v2                  (suffix can't be the whole id)
    """
    match = _VERSION_SUFFIX_RE.match(subject_id)
    return match.group("family") if match else subject_id


def version_number(subject_id: str) -> int:
    """Return the numeric version a subject_id encodes. v1 (no suffix) -> 1."""
    match = _VERSION_SUFFIX_RE.match(subject_id)
    if not match:
        return 1
    # The suffix is _v<digits> at the very end.
    return int(subject_id.rsplit("_v", 1)[1])


def list_family_versions(db: sqlite3.Connection, family: str) -> list[str]:
    """Return the catalog subject_ids belonging to ``family``, naturally sorted.

    Natural order = by version number ascending, so v1 (unsuffixed) first:
    [capacity_license, capacity_license_v2, capacity_license_v10]. Only rows
    whose subject_family() actually equals ``family`` are returned — a SQL
    ``LIKE family || '_v%'`` would also match e.g. ``family_v2_else``.
    """
    rows = db.execute(
        "SELECT DISTINCT subject_id FROM subjects "
        "WHERE subject_id = ? OR subject_id LIKE ? ESCAPE '\\'",
        (family, _like_escape(family) + "\\_v%"),
    ).fetchall()
    versions = [r["subject_id"] for r in rows if subject_family(r["subject_id"]) == family]
    return sorted(versions, key=version_number)


def get_pinned_subject_id(
    db: sqlite3.Connection, customer_id: str, family: str
) -> str | None:
    """Return the pinned subject_id for (customer, family), or None if unpinned."""
    row = db.execute(
        "SELECT pinned_subject_id FROM customer_subject_pin "
        "WHERE customer_id = ? AND subject_family = ?",
        (customer_id, family),
    ).fetchone()
    return row["pinned_subject_id"] if row else None


def set_pinned_subject_id(
    db: sqlite3.Connection, customer_id: str, family: str, pinned_subject_id: str
) -> None:
    """Pin ``pinned_subject_id`` as the version (customer, family) collects next."""
    db.execute(
        "INSERT INTO customer_subject_pin "
        "(customer_id, subject_family, pinned_subject_id, updated_at) "
        "VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
        "ON CONFLICT(customer_id, subject_family) DO UPDATE SET "
        "pinned_subject_id = excluded.pinned_subject_id, "
        "updated_at = excluded.updated_at",
        (customer_id, family, pinned_subject_id),
    )
    db.commit()


def resolve_active_version(
    db: sqlite3.Connection, customer_id: str | None, subject_id: str
) -> str:
    """Return which subject_id the next collection of ``subject_id``'s family uses.

    Resolution: the customer's pin for the family if set and still a real
    version in the catalog; otherwise the latest version in the family
    (highest _vN, or the unsuffixed id if it's the only one). If the family
    has no catalog rows at all, fall back to the requested subject_id.

    Today every family has one version, so this returns that one version.
    """
    family = subject_family(subject_id)
    versions = list_family_versions(db, family)

    if customer_id is not None:
        pinned = get_pinned_subject_id(db, customer_id, family)
        if pinned is not None and pinned in versions:
            return pinned

    return versions[-1] if versions else subject_id


def _like_escape(value: str) -> str:
    """Escape SQL LIKE wildcards in ``value`` for use with ESCAPE '\\'."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def create_subject_from_proposal(db: sqlite3.Connection, proposal: dict) -> dict[str, Any]:
    """
    Write a subject proposal dict into the catalog tables.
    Runs in a single transaction — either all writes succeed or none do.
    """
    subject_id = proposal["subject_id"]
    version = proposal["version"]
    title = proposal["title"]
    description = proposal.get("description", "")
    category = proposal["category"]
    sections = proposal.get("sections", [])
    extraction_instructions = proposal.get("extraction_instructions", {})
    supersedes = proposal.get("supersedes")
    change_notes = proposal.get("change_notes")
    related_subjects = proposal.get("related_subjects") or []

    category_label = CATEGORY_LABELS.get(category, category.title())

    try:
        db.execute(
            """
            INSERT OR REPLACE INTO subjects
                (subject_id, version, title, description, category, category_label,
                 status, created_by, change_notes, related_subjects)
            VALUES (?, ?, ?, ?, ?, ?, 'active', 'ai', ?, ?)
            """,
            (
                subject_id,
                version,
                title,
                description,
                category,
                category_label,
                change_notes,
                json.dumps(related_subjects) if related_subjects else None,
            ),
        )

        # Domain labels (ADR-0012): attach the proposal's labels to THIS version's
        # row. They were loud-validated at authoring (propose_new_subject); here the
        # Phase-1 FK is the structural guard. INSERT OR REPLACE above gives a new
        # subjects.id and cascades any prior labels away, so re-proposing a version
        # replaces its label set rather than accumulating.
        labels = proposal.get("labels") or []
        if labels:
            new_row_id = db.execute(
                "SELECT id FROM subjects WHERE subject_id = ? AND version = ?",
                (subject_id, version),
            ).fetchone()["id"]
            try:
                for lbl in labels:
                    db.execute(
                        "INSERT INTO subject_domain_labels"
                        " (subject_row_id, label) VALUES (?, ?)",
                        (new_row_id, lbl),
                    )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "proposal references a label not in the vocabulary"
                ) from exc

        for section in sections:
            validate_section_type(
                section["section_type"],
                subject_id=subject_id,
                section_id=section["section_id"],
            )
            db.execute(
                """
                INSERT OR IGNORE INTO subject_sections
                    (subject_id, subject_version, section_id, title, section_type,
                     default_selected, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subject_id,
                    version,
                    section["section_id"],
                    section["title"],
                    section["section_type"],
                    1 if section.get("default_selected", True) else 0,
                    section.get("sort_order", 0),
                ),
            )

        for source_type, source_info in extraction_instructions.items():
            extractable = 1 if source_info.get("extractable", True) else 0
            non_extractable_reason = source_info.get("non_extractable_reason")
            recognition_hints = dict(source_info.get("recognition_hints") or {})
            # ADR 0009 D2: a Command Center API source carries an explicit relative
            # endpoint. Accept it as a top-level `endpoint` field (or already inside
            # recognition_hints) and validate it relative + read-only before
            # persisting — the AI-asserted endpoint is untrusted input (ADR 0008).
            # The validated path is stored in recognition_hints (resolved
            # open-question (ii): no schema migration). An invalid endpoint raises,
            # rolling back the whole proposal write below.
            if source_type == COMMAND_CENTER_SOURCE_TYPE:
                declared = source_info.get("endpoint", recognition_hints.get("endpoint"))
                if declared is not None:
                    recognition_hints["endpoint"] = validate_cc_endpoint(declared)
            # ADR 0014: a Reports Plus dataset source carries an explicit
            # dataset_address (bare GUID or {reportGuid}:{entryGuid}). Same
            # pattern as the CC endpoint above, but the address is REQUIRED —
            # there is no default dataset; a missing/invalid address raises,
            # rolling back the whole proposal write below.
            if source_type == REPORTSPLUS_DATASET_SOURCE_TYPE:
                declared = source_info.get(
                    "dataset_address", recognition_hints.get("dataset_address")
                )
                recognition_hints["dataset_address"] = validate_rp_dataset_address(
                    declared
                )
            db.execute(
                """
                INSERT OR REPLACE INTO subject_sources
                    (subject_id, subject_version, source_type, extractable,
                     non_extractable_reason, recognition_hints)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    subject_id,
                    version,
                    source_type,
                    extractable,
                    non_extractable_reason,
                    json.dumps(recognition_hints) if recognition_hints else None,
                ),
            )

            source_row = db.execute(
                "SELECT id FROM subject_sources"
                " WHERE subject_id = ? AND subject_version = ? AND source_type = ?",
                (subject_id, version, source_type),
            ).fetchone()
            if source_row is None:
                raise RuntimeError(
                    f"Failed to retrieve source for {subject_id}/{version}/{source_type}"
                )
            source_id = source_row["id"]

            for section_id, instructions in source_info.get("sections", {}).items():
                db.execute(
                    """
                    INSERT OR IGNORE INTO subject_section_sources
                        (source_id, section_id, extraction_instructions)
                    VALUES (?, ?, ?)
                    """,
                    (
                        source_id,
                        section_id,
                        json.dumps(instructions) if instructions else None,
                    ),
                )

        if supersedes is not None:
            db.execute(
                "UPDATE subjects SET status = 'superseded' WHERE id = ?",
                (supersedes,),
            )

        db.commit()

        row = db.execute(
            "SELECT * FROM subjects WHERE subject_id = ? AND version = ?",
            (subject_id, version),
        ).fetchone()
        return dict(row)

    except Exception:
        db.rollback()
        raise


def get_subject(
    db: sqlite3.Connection,
    subject_id: str,
    version: int | None = None,
) -> dict[str, Any] | None:
    if version is None:
        row = db.execute(
            "SELECT * FROM subjects"
            " WHERE subject_id = ? AND status = 'active'"
            " ORDER BY version DESC LIMIT 1",
            (subject_id,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM subjects WHERE subject_id = ? AND version = ?",
            (subject_id, version),
        ).fetchone()
    return dict(row) if row is not None else None


def list_subjects_from_db(
    db: sqlite3.Connection,
    status: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM subjects"
    where: list[str] = []
    params: list[Any] = []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if category is not None:
        where.append("category = ?")
        params.append(category)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY category, title"
    return [dict(row) for row in db.execute(query, tuple(params)).fetchall()]


def get_subject_sections(
    db: sqlite3.Connection,
    subject_id: str,
    version: int = 1,
) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT * FROM subject_sections"
        " WHERE subject_id = ? AND subject_version = ?"
        " ORDER BY sort_order",
        (subject_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_active_subjects(
    db: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return all active subjects with their sections and sources lists."""
    subject_rows = db.execute(
        "SELECT * FROM subjects WHERE status = 'active' ORDER BY category, title"
    ).fetchall()
    result = []
    for row in subject_rows:
        subject = dict(row)
        sections = db.execute(
            "SELECT * FROM subject_sections"
            " WHERE subject_id = ? AND subject_version = ?"
            " ORDER BY sort_order",
            (subject["subject_id"], subject["version"]),
        ).fetchall()
        sources = db.execute(
            """
            SELECT ss.*,
                   (SELECT COUNT(*) FROM subject_section_sources sss
                    WHERE sss.source_id = ss.id) > 0 AS has_section_instructions
            FROM subject_sources ss
            WHERE ss.subject_id = ? AND ss.subject_version = ?
            """,
            (subject["subject_id"], subject["version"]),
        ).fetchall()
        subject["sections"] = [dict(s) for s in sections]
        subject["sources"] = [dict(s) for s in sources]
        result.append(subject)
    return result


def delete_subject(db: sqlite3.Connection, subject_id: str) -> dict:
    """
    Delete a subject and all related rows from the catalog.
    Deletes all versions of the subject.

    Also reconciles the review queue: the subject's ``staged_artifacts`` rows
    (its subject_proposal proposals AND imported ``artifact`` rows) are
    hard-deleted too, so a delete can't leave an orphaned approved proposal that
    the staging UI / ``list_proposed_subjects`` would misread as "belongs in the
    catalog". (The shared approval path — ``execute_approval`` /
    ``reject_staged_artifact`` — is untouched; only rows are removed.)

    Raises ValueError if created_by = 'system'.
    Raises ValueError if subject not found.

    Returns {"deleted": subject_id, "versions_removed": int,
             "staging_rows_removed": int}
    """
    rows = db.execute(
        "SELECT id, created_by FROM subjects WHERE subject_id = ?",
        (subject_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"subject not found: {subject_id}")
    if any(row["created_by"] == "system" for row in rows):
        raise ValueError(f"system subjects cannot be deleted: {subject_id}")

    versions_removed = len(rows)

    source_ids = [
        r["id"]
        for r in db.execute(
            "SELECT id FROM subject_sources WHERE subject_id = ?",
            (subject_id,),
        ).fetchall()
    ]
    # Capture the rule ids this subject's bindings reference BEFORE the
    # bindings are deleted — the reap below is scoped to these candidates, so
    # a rule authored elsewhere but not yet bound is never touched.
    candidate_rule_ids = _referenced_rule_ids(db, source_ids)
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        db.execute(
            f"DELETE FROM subject_section_sources WHERE source_id IN ({placeholders})",
            source_ids,
        )

    db.execute("DELETE FROM subject_sources WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subject_sections WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subjects WHERE subject_id = ?", (subject_id,))
    # Reconcile the review queue so a delete never orphans staged rows (the gap
    # that left approved server_groups proposals with no catalog subject). Hard-
    # delete every staged_artifacts row for this subject — proposals and imported
    # artifacts alike — in the same transaction as the catalog/source rows.
    staging_rows_removed = db.execute(
        "DELETE FROM staged_artifacts WHERE subject_id = ?", (subject_id,)
    ).rowcount
    # Reap rules this deletion just orphaned: referenced by the deleted
    # subject's bindings, now bound to NO surviving subject and carrying NO
    # override. In-transaction (delete_rule commits mid-flight, so it is not
    # callable from here); the delete→rebuild workflow re-authors rules via
    # save_rule after re-approval, so reaping is compatible with it.
    rules_reaped = _reap_orphaned_rules(db, candidate_rule_ids)
    db.commit()

    return {
        "deleted": subject_id,
        "versions_removed": versions_removed,
        "staging_rows_removed": staging_rows_removed,
        "rules_reaped": rules_reaped,
    }


def _collect_rule_refs(node: Any, out: set[str]) -> None:
    """Collect every ``{"ref": <rule_id>}`` value anywhere in a binding's
    instruction JSON — covers ``evaluative.row_rules`` and the metric/card
    ref shapes alike (the same ref-from-binding model, ADR 0010)."""
    if isinstance(node, dict):
        ref = node.get("ref")
        if isinstance(ref, str):
            out.add(ref)
        for value in node.values():
            _collect_rule_refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_rule_refs(value, out)


def _referenced_rule_ids(
    db: sqlite3.Connection, source_ids: list[int]
) -> set[str]:
    """Rule ids referenced from the given sources' section bindings."""
    if not source_ids:
        return set()
    placeholders = ",".join("?" * len(source_ids))
    refs: set[str] = set()
    for row in db.execute(
        "SELECT extraction_instructions FROM subject_section_sources"
        f" WHERE source_id IN ({placeholders})"
        " AND extraction_instructions IS NOT NULL",
        source_ids,
    ).fetchall():
        try:
            instr = json.loads(row["extraction_instructions"])
        except (json.JSONDecodeError, TypeError):
            continue
        _collect_rule_refs(instr, refs)
    return refs


def _reap_orphaned_rules(
    db: sqlite3.Connection, candidate_rule_ids: set[str]
) -> list[str]:
    """Delete registry rules from ``candidate_rule_ids`` that have zero
    remaining bindings (across ALL subjects) and zero ``rule_overrides`` rows.
    Runs inside the caller's transaction — no commit here. Defensive against a
    pre-rules schema (returns [])."""
    if not candidate_rule_ids:
        return []
    try:
        still_bound: set[str] = set()
        for row in db.execute(
            "SELECT extraction_instructions FROM subject_section_sources"
            " WHERE extraction_instructions IS NOT NULL"
        ).fetchall():
            try:
                instr = json.loads(row["extraction_instructions"])
            except (json.JSONDecodeError, TypeError):
                continue
            _collect_rule_refs(instr, still_bound)
        overridden = {
            r["rule_id"]
            for r in db.execute("SELECT DISTINCT rule_id FROM rule_overrides").fetchall()
        }
    except sqlite3.OperationalError:
        return []

    reaped: list[str] = []
    for rule_id in sorted(candidate_rule_ids - still_bound - overridden):
        cur = db.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,))
        if cur.rowcount:
            reaped.append(rule_id)
    return reaped


def get_subject_sources(
    db: sqlite3.Connection,
    subject_id: str,
    version: int = 1,
) -> list[dict[str, Any]]:
    source_rows = db.execute(
        "SELECT * FROM subject_sources"
        " WHERE subject_id = ? AND subject_version = ?",
        (subject_id, version),
    ).fetchall()

    result = []
    for source_row in source_rows:
        source = dict(source_row)
        section_rows = db.execute(
            "SELECT section_id, extraction_instructions"
            " FROM subject_section_sources WHERE source_id = ?",
            (source["id"],),
        ).fetchall()
        sections: dict[str, Any] = {}
        for sec in section_rows:
            try:
                sections[sec["section_id"]] = (
                    json.loads(sec["extraction_instructions"])
                    if sec["extraction_instructions"]
                    else {}
                )
            except (json.JSONDecodeError, TypeError):
                sections[sec["section_id"]] = {}
        result.append({
            "source_type": source["source_type"],
            "extractable": bool(source["extractable"]),
            "non_extractable_reason": source["non_extractable_reason"],
            "recognition_hints": (
                json.loads(source["recognition_hints"])
                if source["recognition_hints"]
                else {}
            ),
            "sections": sections,
        })
    return result
