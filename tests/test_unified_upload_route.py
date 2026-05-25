"""Tests for the unified upload route POST /quick-hc/<subject_id>/import.

Session 2 of the unified-upload refactor. The new route lives alongside
the existing per-subject and generic import routes; the frontend has
NOT been flipped over yet (that's session 3). These tests verify that
the new route's behavior is equivalent to the old routes for every
dispatch branch:

  - Unknown subject_id → 404.
  - 'system' security_assessment → identical to the legacy
    /quick-hc/security-assessment/import.
  - 'system' license_summary → identical to the legacy
    /quick-hc/license-summary/import.
  - 'system' but no upload path (environment, etc.) → 404.
  - 'ai' or 'user' → identical to /quick-hc/import?subject_id=…,
    including X-Inline: 1 and ?stage=1 features.

The "identical" tests assert observable parity (artifact saved /
flash message present / response shape), not byte-for-byte
equivalence of every internal call. The branch-dispatch FIXMEs in
quick_hc.py point at the session-5/6 work that will fold the
duplicated bodies back together.
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
# already pass.
from tests.test_security_assessment_import import HTML_SAMPLE
from tests.test_license_summary_web import CSV_SAMPLE


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

    monkeypatch.setattr(quick_hc_routes, "ArtifactStore", _FakeArtifactStore)

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


def test_unified_route_ai_branch_produces_same_artifact_as_old_route(
    ai_subject_client, monkeypatch
) -> None:
    """Test 2 — AI branch parity: both new and old routes produce the
    same artifact for the same input."""
    client, saved, _db = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    # OLD route
    client.post(
        "/quick-hc/import?subject_id=my_ai_report",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    # NEW route
    client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert len(saved) == 2
    # Same canonical artifact type, same subject id — i.e. the new route
    # routed the upload to the same dispatcher path as the old one.
    assert saved[0].artifact_type == saved[1].artifact_type == "my_ai_report"
    assert saved[0].subject.id == saved[1].subject.id == "my_ai_report"


def test_unified_route_ai_branch_supports_x_inline(
    ai_subject_client, monkeypatch
) -> None:
    """Test 3 — X-Inline: 1 returns JSON, same as old route."""
    client, saved, _db = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    # OLD route with X-Inline
    old_resp = client.post(
        "/quick-hc/import?subject_id=my_ai_report",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    # NEW route with X-Inline
    new_resp = client.post(
        "/quick-hc/my_ai_report/import",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )

    assert old_resp.status_code == 200
    assert new_resp.status_code == 200
    assert old_resp.is_json
    assert new_resp.is_json
    # Both routes serialise the same fields with the same values.
    old_body = old_resp.get_json()
    new_body = new_resp.get_json()
    assert old_body == new_body
    assert new_body["success"] is True
    assert new_body["title"] == "AI Subject my_ai_report"


def test_unified_route_ai_branch_supports_stage_query(
    ai_subject_client, monkeypatch
) -> None:
    """Test 4 — ?stage=1 routes the upload through staged_artifacts,
    same as the old route."""
    client, saved, db_path = ai_subject_client

    monkeypatch.setattr(
        quick_hc_routes,
        "extract_file",
        lambda *a, **kw: _fake_dispatch_success("my_ai_report"),
    )

    # OLD route with ?stage=1
    client.post(
        "/quick-hc/import?subject_id=my_ai_report&stage=1",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    # NEW route with ?stage=1
    client.post(
        "/quick-hc/my_ai_report/import?stage=1",
        data={"file": (io.BytesIO(b"<html/>"), "report.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    # Neither route called ArtifactStore.save_artifact (because stage=1
    # routes to the staging table instead).
    assert saved == []

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT subject_id, artifact_type, status FROM staged_artifacts"
        " ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    # Both routes produced one row each.
    assert len(rows) == 2
    assert rows[0] == rows[1]  # same subject_id / artifact_type / status


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

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/security_assessment/import",
        data={
            "assessment_file": (io.BytesIO(HTML_SAMPLE.encode("utf-8")), "assessment.html")
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    legacy_artifact_files = list((tmp_path / "catalog").rglob("*.json"))
    assert legacy_artifact_files == [], (
        f"Option A violated via unified route: wrote legacy artifact files "
        f"{legacy_artifact_files}"
    )
    canonical_files = list((tmp_path / "canonical_artifacts").rglob("*.json"))
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
    canonical_files = list((tmp_path / "canonical_artifacts").rglob("*.json"))
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
