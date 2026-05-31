"""Tests for the unified upload route POST /quick-hc/<subject_id>/import.

Originally landed in session 2 of the unified-upload refactor as
parity tests against the OLD per-subject + generic routes. Session 4
deleted those old routes; the parity-comparison halves of tests 2-4
were dropped, leaving direct outcome assertions on the unified route.

Dispatch branches covered:
  - Unknown subject_id → 404.
  - 'system' security_assessment → SA upload path (assessment_file
    form field).
  - 'system' license_summary → LS upload path (license_summary_file
    form field; extension pre-check).
  - 'system' but no upload path (environment, etc.) → 404.
  - 'ai' or 'user' → dispatcher branch with X-Inline: 1 and ?stage=1
    features.

The branch-dispatch FIXMEs in quick_hc.py point at the session-5
work that will fold the duplicated bodies back together.
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
)
from cvhealthcheck.extractors.dispatcher import DispatchResult
from cvhealthcheck.extractors.recognition import RecognitionResult
import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.web.app import create_app


# Reuse the SA-HTML and LS-CSV builders from the existing tests so the
# new route is exercised against the same input shapes the old routes
# already pass. The `tests/` directory is on sys.path during pytest
# collection (no `tests/__init__.py`), so the sibling test modules are
# imported directly by name rather than via a `tests.` package prefix.
from test_security_assessment_import import HTML_SAMPLE, SA_PANEL_HTML
from test_license_summary_web import CSV_SAMPLE


# ---------------------------------------------------------------------------
# Helpers — copied from tests/test_security_assessment_import.py and
# tests/test_license_summary_web.py so this test file is self-contained.
# Touching those files is out of scope; copying is the price.
# ---------------------------------------------------------------------------

def _patch_security_assessment_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog_dir = tmp_path / "catalog"
    imports_dir = tmp_path / "imports"
    registry_path = tmp_path / "registry.sqlite3"
    import cvhealthcheck.security_assessment.artifact as artifact_module
    import cvhealthcheck.reportsplus.security_assessment as security_assessment_module
    import cvhealthcheck.security_assessment.normalize as normalize_module
    import cvhealthcheck.security_assessment.service as service_module
    monkeypatch.setattr(artifact_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(normalize_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(security_assessment_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_IMPORTS_DIR", imports_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_REGISTRY_PATH", registry_path)


def _patch_license_summary_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import cvhealthcheck.license_summary.service as service_module
    import cvhealthcheck.license_summary.artifact as artifact_module
    monkeypatch.setattr(service_module, "LICENSE_SUMMARY_REGISTRY_PATH", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(service_module, "LICENSE_SUMMARY_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(service_module, "LICENSE_SUMMARY_IMPORTS_DIR", tmp_path / "imports")
    monkeypatch.setattr(artifact_module, "LICENSE_SUMMARY_CATALOG_DIR", tmp_path / "catalog")


def _insert_ai_subject(db_path: Path, subject_id: str = "my_ai_report") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO subjects (subject_id, version, title, description,"
            " category, category_label, status, created_by)"
            " VALUES (?, 1, ?, '', 'storage', 'Storage', 'active', 'ai')",
            (subject_id, f"AI Subject {subject_id}"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def ai_subject_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Test client with the test DB wired in + one AI subject seeded.

    Mirrors the import_client fixture from tests/test_recognition.py but
    also INSERTs an AI subject so the unified route's get_subject() call
    finds something to dispatch on.
    """
    _insert_ai_subject(migrated_db_path)

    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)

    saved: list[Any] = []

    class _FakeArtifactStore:
        def save_artifact(self, artifact: Any) -> Path:
            saved.append(artifact)
            return Path("/tmp/fake.json")

        def delete_artifact(self, artifact_type: str) -> bool:
            return False

    monkeypatch.setattr(
        quick_hc_routes, "make_active_project_store", lambda: _FakeArtifactStore()
    )

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c, saved, migrated_db_path


def _fake_dispatch_success(subject_id: str = "my_ai_report") -> DispatchResult:
    """A DispatchResult that mirrors what the dispatcher would return on
    a successful HTML extraction. Used to fake extract_file in the
    AI-branch tests so neither route depends on real extraction
    instructions for the AI subject — what we're testing is route
    dispatch, not extraction."""
    artifact = CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=__import__("datetime").datetime(2026, 5, 31, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id=subject_id, title=f"AI Subject {subject_id}"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[],
    )
    return DispatchResult(
        recognized=True,
        subject_id=subject_id,
        version=1,
        source_type="html",
        extractable=True,
        non_extractable_reason=None,
        artifact=artifact,
        recognition_result=RecognitionResult(
            subject_id=subject_id,
            version=1,
            source_type="html",
            extractable=True,
            non_extractable_reason=None,
            title=f"AI Subject {subject_id}",
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unified_route_returns_404_for_unknown_subject(ai_subject_client) -> None:
    """Test 1 — Unknown subject_id → 404."""
    client, _saved, _db = ai_subject_client
    response = client.post(
        "/quick-hc/does_not_exist_anywhere/import",
        data={"file": (io.BytesIO(b"<html/>"), "x.html")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


def test_unified_route_ai_branch_saves_artifact(
    ai_subject_client, monkeypatch
) -> None:
    """Test 2 — AI branch: POST to the unified route saves the
    dispatcher's artifact to the canonical store with the correct
    subject_id propagated end-to-end.

    Session 4 dropped the old-route POST half of this test (the OLD
    /quick-hc/import?subject_id=… route no longer exists).
    """
    client, saved, _db = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert len(saved) == 1
    assert saved[0].artifact_type == "my_ai_report"
    assert saved[0].subject.id == "my_ai_report"


def test_unified_route_ai_branch_supports_x_inline(
    ai_subject_client, monkeypatch
) -> None:
    """Test 3 — X-Inline: 1 returns JSON success body.

    Session 4 dropped the old-route POST half of this test.
    """
    client, saved, _db = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    resp = client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )

    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert body["success"] is True
    assert body["title"] == "AI Subject my_ai_report"


def test_unified_route_ai_branch_supports_stage_query(
    ai_subject_client, monkeypatch
) -> None:
    """Test 4 — ?stage=1 routes the upload through staged_artifacts
    instead of saving canonically.

    Session 4 dropped the old-route POST half of this test.
    """
    client, saved, db_path = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    client.post(
        "/quick-hc/my_ai_report/import?stage=1",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    # Canonical save NOT called (stage=1 routes to staging instead).
    assert saved == []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT subject_id, artifact_type, status FROM staged_artifacts"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


def test_unified_route_security_assessment_no_legacy_artifact_files(
    tmp_path, monkeypatch
) -> None:
    """Test 5 — Option A regression for the new SA route.

    POSTing to /quick-hc/security_assessment/import (underscore — the
    unified route's URL) must produce zero legacy artifact JSON files
    in data/catalog/security_assessment/. Mirror of the existing
    test_fresh_security_assessment_import_creates_no_legacy_artifact_files
    which targets the legacy /security-assessment/import route.
    """
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    # SA migration (PR2): SA uploads route through the generic dispatcher, which
    # writes the canonical store via make_active_project_store and uses the "file"
    # form field. Patch that store to a tmp location to inspect it; the legacy
    # bespoke store must remain untouched.
    import cvhealthcheck.web.routes.quick_hc as _qhc
    from cvhealthcheck.artifacts.store import ArtifactStore
    _store = ArtifactStore("default", "default", base_dir=tmp_path / "data" / "catalog" / "artifacts")
    monkeypatch.setattr(_qhc, "make_active_project_store", lambda *a, **k: _store)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/security_assessment/import",
        data={"file": (io.BytesIO(SA_PANEL_HTML.encode("utf-8")), "assessment.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    legacy_artifact_files = list((tmp_path / "catalog").rglob("*.json"))
    assert legacy_artifact_files == [], (
        f"generic SA upload wrote bespoke legacy artifact files {legacy_artifact_files}"
    )
    canonical_files = list((tmp_path / "data" / "catalog" / "artifacts").rglob("*.json"))
    assert canonical_files, "canonical store should have received the artifact"


def test_unified_route_license_summary_no_legacy_artifact_files(
    tmp_path, monkeypatch
) -> None:
    """Test 6 — Option A regression for License Summary (new test the
    2026-05-27 HANDOVER flagged as missing).

    POSTing to /quick-hc/license_summary/import (underscore) must
    produce zero legacy artifact JSON files in data/catalog/license_summary/.
    """
    _patch_license_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/license_summary/import",
        data={
            "license_summary_file": (
                io.BytesIO(CSV_SAMPLE.encode("utf-8")),
                "license-summary.csv",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    legacy_artifact_files = list((tmp_path / "catalog").rglob("*.json"))
    assert legacy_artifact_files == [], (
        f"Option A violated via unified route (license_summary): wrote legacy "
        f"artifact files {legacy_artifact_files}"
    )
    canonical_files = list((tmp_path / "data" / "catalog" / "artifacts").rglob("*.json"))
    assert canonical_files, "canonical store should have received the artifact"


def test_unified_route_returns_404_for_system_subject_without_upload(
    ai_subject_client,
) -> None:
    """Test 7 — System subject with no upload path → 404.

    'environment' is a system subject (created_by='system') but is
    REST-only — it has no upload route in the old layout either. The
    unified route's 'system' sub-branch only handles security_assessment
    and license_summary; everything else returns 404.
    """
    client, _saved, _db = ai_subject_client
    response = client.post(
        "/quick-hc/environment/import",
        data={"file": (io.BytesIO(b"<html/>"), "x.html")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Inline-mode (X-Inline: 1) tests for the system-subject upload branch
# (security_assessment + license_summary).
#
# Latent bug fixed 2026-05-27: _handle_system_upload used to flash+redirect
# unconditionally, even when X-Inline:1 was set, causing the JS to receive
# an HTML 302 response and fail JSON-parsing it. The fix mirrored the
# inline branch from _unified_dispatcher_upload (the AI-branch tests
# above already cover the inline-mode behavior of THAT branch).
# ---------------------------------------------------------------------------

def test_system_upload_inline_returns_json_on_success(tmp_path, monkeypatch) -> None:
    """Test 8 — X-Inline:1 + valid file → 200 JSON {"success": True, ...}.
    Covers LS; SA's identical because the handler shape is shared.
    """
    _patch_license_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/license_summary/import",
        data={
            "license_summary_file": (
                io.BytesIO(CSV_SAMPLE.encode("utf-8")),
                "license-summary.csv",
            )
        },
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert response.status_code == 200
    assert response.is_json
    body = response.get_json()
    assert body["success"] is True
    assert "license" in body["message"].lower()


def test_system_upload_inline_returns_400_when_no_file(tmp_path, monkeypatch) -> None:
    """Test 9 — X-Inline:1 + no file → 400 JSON {"success": False, "error": "No file selected."}."""
    _patch_license_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/license_summary/import",
        data={},  # no file
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert response.status_code == 400
    assert response.is_json
    body = response.get_json()
    assert body == {"success": False, "error": "No file selected."}


def test_system_upload_inline_returns_422_on_handler_error_class(
    tmp_path, monkeypatch
) -> None:
    """Test 10 — X-Inline:1 + import that raises handler.error_class
    (LicenseSummaryImportError) → 422 JSON with the exception message.

    Triggered by uploading a file with an unsupported extension, which
    import_license_summary_upload rejects with LicenseSummaryImportError.
    """
    _patch_license_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/license_summary/import",
        data={
            "license_summary_file": (io.BytesIO(b"junk"), "report.txt"),  # .txt rejected
        },
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert response.status_code == 422
    assert response.is_json
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported file type" in body["error"]


def test_system_upload_inline_returns_500_on_generic_exception(
    tmp_path, monkeypatch
) -> None:
    """Test 11 — X-Inline:1 + import_fn raising a non-handler.error_class
    Exception → 500 JSON with "Import failed: <msg>".
    """
    _patch_license_summary_paths(tmp_path, monkeypatch)

    # Patch the upload handler's import_fn to raise a generic Exception.
    import cvhealthcheck.web.routes.upload_dispatch as dispatch_module

    def _boom(stream, *, original_filename):
        raise RuntimeError("upstream crashed")

    original = dispatch_module.UPLOAD_HANDLERS["license_summary"]
    patched = dispatch_module.UploadHandler(
        form_field=original.form_field,
        import_fn=_boom,
        error_class=original.error_class,
        success_format=original.success_format,
        redirect_endpoint=original.redirect_endpoint,
    )
    monkeypatch.setitem(dispatch_module.UPLOAD_HANDLERS, "license_summary", patched)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/license_summary/import",
        data={
            "license_summary_file": (
                io.BytesIO(CSV_SAMPLE.encode("utf-8")),
                "license-summary.csv",
            )
        },
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert response.status_code == 500
    assert response.is_json
    body = response.get_json()
    assert body["success"] is False
    assert "upstream crashed" in body["error"]
    assert body["error"].startswith("Import failed:")


# ---------------------------------------------------------------------------
# Contract test: the action dict shipped to the JS must declare the same
# field name the server-side handler reads from request.files.
#
# Catches the 2026-05-25 → 2026-05-28 field-name mismatch bug: the JS
# correctly forwards uploadAction.importField verbatim, but
# _provenance_to_tile_sources hardcoded import_field="file" while the
# corresponding _handle_system_upload(handler) reads
# request.files[handler.form_field] which is "license_summary_file" /
# "assessment_file". Result: silent "No file selected." errors after
# the first successful collect of an SA/LS subject (which triggers the
# provenance path instead of the nodata path).
# ---------------------------------------------------------------------------

def test_upload_action_field_matches_handler_form_field() -> None:
    """The action dict's importField must equal handler.form_field for
    each system subject with a registered upload handler. Pin the
    invariant directly — the existing inline-upload tests hardcoded
    the field name on both sides and so couldn't catch this mismatch.
    """
    from cvhealthcheck.quickhc.subject_data_service import _provenance_to_tile_sources
    from cvhealthcheck.web.routes.upload_dispatch import get_handler

    # SA migration (PR2): security_assessment no longer has a bespoke upload
    # handler (it routes through the generic dispatcher). Only license_summary
    # remains handler-based, so the importField==form_field invariant applies
    # to it alone.
    for subject_id in ("license_summary",):
        provenance_items = [
            {"source_type": "html", "status": "available", "label": "HTML import", "description": ""},
            {"source_type": "csv",  "status": "available", "label": "CSV import",  "description": ""},
        ]
        sources = _provenance_to_tile_sources(subject_id, provenance_items)
        handler = get_handler(subject_id)
        assert handler is not None, f"{subject_id!r} should have an upload handler registered"

        upload_actions = [
            action
            for source in sources
            for action in source.get("actions", [])
            if action.get("kind") == "upload"
        ]
        assert upload_actions, (
            f"{subject_id!r} provenance path should produce at least one upload action"
        )
        for action in upload_actions:
            assert action["importField"] == handler.form_field, (
                f"action.importField={action['importField']!r} for {subject_id!r} differs "
                f"from handler.form_field={handler.form_field!r} — the JS would submit "
                f"under the wrong field name; _handle_system_upload would respond "
                f"'No file selected.'"
            )
