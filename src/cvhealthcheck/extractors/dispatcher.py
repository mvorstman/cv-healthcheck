"""
cvhealthcheck.extractors.dispatcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Identifies an uploaded file and dispatches it to the appropriate extractor.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import HTMLExtractor
from cvhealthcheck.extractors.recognition import (
    RecognitionEngine,
    RecognitionResult,
    _detect_source_type,
)
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


@dataclass
class DispatchResult:
    recognized: bool
    subject_id: str | None
    version: int | None
    source_type: str | None
    extractable: bool
    non_extractable_reason: str | None
    artifact: CanonicalArtifact | None
    extraction_errors: list[str] = field(default_factory=list)
    extraction_warnings: list[str] = field(default_factory=list)
    recognition_result: RecognitionResult | None = None
    # True when the best available source is REST but no live session was provided.
    # The caller should use the collect route instead of this file-based dispatcher.
    rest_required: bool = False


def extract_file(
    file_path: Path,
    db_conn: sqlite3.Connection,
    subject_id: str | None = None,
    version: int | None = None,
    declared_commcell_id: str | None = None,
) -> DispatchResult:
    """
    Identify the file and run the appropriate extractor.

    If subject_id is provided, skip recognition and use it directly.

    ``declared_commcell_id`` (import-verification slice #1) is the active
    customer's CommCell ID, threaded from the upload route so the canonical
    artifact stamps a declared-vs-wire verdict (PROVENANCE, never blocks)
    instead of being blanket-unverifiable. None when no customer CCID is set.
    """
    if subject_id is not None:
        # Resolve the subject's ACTIVE version when the caller doesn't pin one.
        # The old `version or 1` default silently read a superseded v1's
        # extraction instructions once a v2 existed (the upload route never
        # passes a version). The recognition path below and the /collect route
        # already resolve by status='active'; this branch now matches them.
        v = version if version is not None else _get_active_version(db_conn, subject_id)
        if v is None:
            return DispatchResult(
                recognized=False,
                subject_id=subject_id,
                version=None,
                source_type=None,
                extractable=False,
                non_extractable_reason=None,
                artifact=None,
                extraction_errors=[
                    f"No active version found for subject '{subject_id}'"
                    " (and no explicit version was given)"
                ],
            )
        title = _get_subject_title(db_conn, subject_id, v)
        source_type = _detect_source_type(file_path)
        if source_type in ("html", "csv"):
            extractable, reason = _get_extractability(db_conn, subject_id, v, source_type)
        else:
            extractable, reason = True, None
        rec = RecognitionResult(
            subject_id=subject_id,
            version=v,
            source_type=source_type or "unknown",
            extractable=extractable,
            non_extractable_reason=reason,
            title=title,
        )
    else:
        engine = RecognitionEngine(db_conn)
        rec = engine.identify(file_path)
        if rec is None:
            return DispatchResult(
                recognized=False,
                subject_id=None,
                version=None,
                source_type=None,
                extractable=False,
                non_extractable_reason=None,
                artifact=None,
            )

    if not rec.extractable:
        return DispatchResult(
            recognized=True,
            subject_id=rec.subject_id,
            version=rec.version,
            source_type=rec.source_type,
            extractable=False,
            non_extractable_reason=rec.non_extractable_reason,
            artifact=None,
            recognition_result=rec,
        )

    if rec.source_type == "html":
        extractor: HTMLExtractor | CSVExtractor = HTMLExtractor(db_conn)
    elif rec.source_type == "csv":
        extractor = CSVExtractor(db_conn)
    elif rec.source_type == "rest":
        # REST extraction requires a live session — use the collect route.
        return DispatchResult(
            recognized=True,
            subject_id=rec.subject_id,
            version=rec.version,
            source_type=rec.source_type,
            extractable=False,
            non_extractable_reason="REST source requires an authenticated collect session",
            artifact=None,
            recognition_result=rec,
            rest_required=True,
        )
    else:
        return DispatchResult(
            recognized=True,
            subject_id=rec.subject_id,
            version=rec.version,
            source_type=rec.source_type,
            extractable=False,
            non_extractable_reason=f"unsupported source_type: {rec.source_type}",
            artifact=None,
            recognition_result=rec,
        )

    result = extractor.extract(file_path, rec.subject_id, rec.version)

    if result.errors:
        return DispatchResult(
            recognized=True,
            subject_id=rec.subject_id,
            version=rec.version,
            source_type=rec.source_type,
            extractable=True,
            non_extractable_reason=None,
            artifact=None,
            extraction_errors=list(result.errors),
            extraction_warnings=list(result.warnings),
            recognition_result=rec,
        )

    artifact = result_to_artifact(
        result,
        subject_id=rec.subject_id,
        subject_title=rec.title,
        file_path=file_path,
        commcell_id=declared_commcell_id,
    )
    return DispatchResult(
        recognized=True,
        subject_id=rec.subject_id,
        version=rec.version,
        source_type=rec.source_type,
        extractable=True,
        non_extractable_reason=None,
        artifact=artifact,
        extraction_errors=[],
        extraction_warnings=list(result.warnings),
        recognition_result=rec,
    )


def _get_active_version(
    db_conn: sqlite3.Connection, subject_id: str
) -> int | None:
    """The subject's active version number (highest active row), or None.

    Same selection rule as ``db.subjects.get_subject(version=None)`` and the
    recognition engine's ``s.status = 'active'`` join — the dispatcher's
    explicit-subject branch must not diverge from those two."""
    row = db_conn.execute(
        "SELECT version FROM subjects"
        " WHERE subject_id = ? AND status = 'active'"
        " ORDER BY version DESC LIMIT 1",
        (subject_id,),
    ).fetchone()
    return row["version"] if row else None


def _get_subject_title(
    db_conn: sqlite3.Connection, subject_id: str, version: int
) -> str:
    row = db_conn.execute(
        "SELECT title FROM subjects WHERE subject_id = ? AND version = ?",
        (subject_id, version),
    ).fetchone()
    return row["title"] if row else subject_id


def _get_extractability(
    db_conn: sqlite3.Connection,
    subject_id: str,
    version: int,
    source_type: str,
) -> tuple[bool, str | None]:
    row = db_conn.execute(
        "SELECT extractable, non_extractable_reason FROM subject_sources"
        " WHERE subject_id = ? AND subject_version = ? AND source_type = ?",
        (subject_id, version, source_type),
    ).fetchone()
    if row is None:
        return True, None
    return bool(row["extractable"]), row["non_extractable_reason"]
