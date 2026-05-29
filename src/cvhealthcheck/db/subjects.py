from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

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

    _LABELS = {
        "identity": "Identity",
        "security": "Security",
        "licensing": "Licensing",
        "performance": "Performance",
        "operations": "Operations",
        "storage": "Storage",
    }
    category_label = _LABELS.get(category, category.title())

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
            recognition_hints = source_info.get("recognition_hints", {})
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

    Raises ValueError if created_by = 'system'.
    Raises ValueError if subject not found.

    Returns {"deleted": subject_id, "versions_removed": int}
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
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        db.execute(
            f"DELETE FROM subject_section_sources WHERE source_id IN ({placeholders})",
            source_ids,
        )

    db.execute("DELETE FROM subject_sources WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subject_sections WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subjects WHERE subject_id = ?", (subject_id,))
    db.commit()

    return {"deleted": subject_id, "versions_removed": versions_removed}


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
