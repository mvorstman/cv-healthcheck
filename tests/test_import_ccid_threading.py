"""Import-verification slice #1 — the active customer's DECLARED CommCell ID is
threaded into the GENERIC upload path so imports stamp an honest declared-vs-wire
verdict (attested when the file carries no identity) instead of being blanket
unverifiable.

Scope guard: only the generic dispatcher path (_unified_dispatcher_upload ->
extract_file -> result_to_artifact) is wired. The bespoke License Summary upload
handler is a SEPARATE path and is deliberately untouched here (its verification
lands later with the LS de-bespoke conversion).
"""
from __future__ import annotations

import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.extractors import dispatcher as disp
from cvhealthcheck.extractors.dispatcher import DispatchResult
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.recognition import RecognitionResult
import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.web.app import create_app

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _insert_ai_subject(db_path: Path, subject_id: str = "my_ai_report") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO subjects (subject_id, version, title, description,"
            " category, category_label, status, created_by)"
            " VALUES (?, 1, ?, '', 'storage', 'Storage', 'active', 'ai')",
            (subject_id, f"AI {subject_id}"),
        )
        conn.commit()
    finally:
        conn.close()


def _dispatch_success(subject_id: str = "my_ai_report") -> DispatchResult:
    artifact = CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id=subject_id, title=f"AI {subject_id}"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[],
    )
    return DispatchResult(
        recognized=True, subject_id=subject_id, version=1, source_type="html",
        extractable=True, non_extractable_reason=None, artifact=artifact,
        recognition_result=RecognitionResult(
            subject_id=subject_id, version=1, source_type="html",
            extractable=True, non_extractable_reason=None, title=f"AI {subject_id}",
        ),
    )


def _client_with_db(monkeypatch, db_path: Path):
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)

    class _FakeStore:
        def __init__(self, *a, **k) -> None:
            pass

        def save_artifact(self, artifact):  # noqa: ANN001
            return Path("/tmp/fake.json")

    monkeypatch.setattr(quick_hc_routes, "ArtifactStore", _FakeStore)

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "default", "project_id": "default"}
    return client


def test_generic_upload_threads_declared_ccid(monkeypatch, migrated_db_path):
    """The route reads the active customer's commcell_id, normalizes it, and
    passes it to extract_file as declared_commcell_id."""
    _insert_ai_subject(migrated_db_path)
    client = _client_with_db(monkeypatch, migrated_db_path)
    # get_active_customer -> get_customer opens its own DB connection (not the
    # monkeypatched test get_db), so stub it directly — the same approach the
    # collect-flash test uses. F9EE5 (hex) normalizes to f9ee5.
    monkeypatch.setattr(
        quick_hc_routes, "get_active_customer",
        lambda *a, **k: {"customer_id": "default", "commcell_id": "F9EE5"},
    )

    captured: dict = {}

    def fake_extract_file(*a, **k):
        captured.update(k)
        return _dispatch_success()

    monkeypatch.setattr(quick_hc_routes, "extract_file", fake_extract_file)

    client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
    )

    assert captured.get("declared_commcell_id") == "f9ee5"


def test_generic_upload_threads_none_when_customer_has_no_ccid(monkeypatch, migrated_db_path):
    """No declared CCID on the customer -> None threaded (the artifact then
    stamps unverifiable, not a crash)."""
    _insert_ai_subject(migrated_db_path)
    client = _client_with_db(monkeypatch, migrated_db_path)
    monkeypatch.setattr(
        quick_hc_routes, "get_active_customer",
        lambda *a, **k: {"customer_id": "default", "commcell_id": None},
    )

    captured: dict = {}

    def fake_extract_file(*a, **k):
        captured.update(k)
        return _dispatch_success()

    monkeypatch.setattr(quick_hc_routes, "extract_file", fake_extract_file)

    client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
    )

    assert "declared_commcell_id" in captured
    assert captured["declared_commcell_id"] is None


def test_extract_file_threads_declared_into_artifact_attested(monkeypatch, migrated_db_path, tmp_path):
    """End-to-end through the real extract_file -> result_to_artifact: the
    declared CCID lands on the artifact, and a CSV (no identity in the file)
    stamps ATTESTED — the demonstrated flip from blanket unverifiable."""
    _insert_ai_subject(migrated_db_path, "csv_subject")
    conn = sqlite3.connect(str(migrated_db_path))
    conn.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type, extractable)"
        " VALUES ('csv_subject', 1, 'csv', 1)"
    )
    conn.commit()
    conn.close()

    class _FakeCSV:
        def __init__(self, *a, **k) -> None:
            pass

        def extract(self, *a, **k) -> ExtractionResult:
            r = ExtractionResult(subject_id="csv_subject", source_type="csv")
            r.sections["rows"] = [{"a": "1"}]
            r.section_output_types["rows"] = "table"
            r.section_titles["rows"] = "Rows"
            return r

    monkeypatch.setattr(disp, "CSVExtractor", _FakeCSV)

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a\n1\n")
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    try:
        dispatch = disp.extract_file(
            csv_file, db, subject_id="csv_subject", declared_commcell_id="337f",
        )
    finally:
        db.close()

    assert dispatch.artifact is not None
    assert dispatch.artifact.source.commcell_id == "337f"
    assert dispatch.artifact.source.verification_status == "attested"


def test_inline_import_surfaces_attested_verification(monkeypatch, migrated_db_path):
    """Counterpart to the collect-silent rule: on IMPORT, attested IS visible.
    The inline (X-Inline) workspace import returns the verdict in the JSON so
    the JS can show it beneath the import result."""
    _insert_ai_subject(migrated_db_path, "csv_subject")
    conn = sqlite3.connect(str(migrated_db_path))
    conn.execute(
        "INSERT INTO subject_sources (subject_id, subject_version, source_type, extractable)"
        " VALUES ('csv_subject', 1, 'csv', 1)"
    )
    conn.commit()
    conn.close()
    client = _client_with_db(monkeypatch, migrated_db_path)
    monkeypatch.setattr(
        quick_hc_routes, "get_active_customer",
        lambda *a, **k: {"customer_id": "default", "commcell_id": "337f"},
    )

    class _FakeCSV:
        def __init__(self, *a, **k) -> None:
            pass

        def extract(self, *a, **k) -> ExtractionResult:
            r = ExtractionResult(subject_id="csv_subject", source_type="csv")
            r.sections["rows"] = [{"a": "1"}]
            r.section_output_types["rows"] = "table"
            r.section_titles["rows"] = "Rows"
            return r

    monkeypatch.setattr(disp, "CSVExtractor", _FakeCSV)

    resp = client.post(
        "/quick-hc/csv_subject/import",
        data={"file": (io.BytesIO(b"a\n1\n"), "data.csv")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["verification"]["status"] == "attested"
    assert body["verification"]["severity"] == "info"
