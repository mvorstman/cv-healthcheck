"""Acceptance tests for project-scoped artifact storage (ADR 0002 phase 2).

These pin the project-scoping contract:
- Artifacts written under different projects produce distinct files
  on disk and don't collide.
- The session's active project determines which artifact ArtifactStore
  reads through the make_active_project_store helper.
- An artifact written under one project doesn't appear in another
  project's workspace.
"""
from __future__ import annotations

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
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.web.active_project import (
    make_active_project_store,
    set_active_project,
)
from cvhealthcheck.web.app import create_app


def _artifact(subject_id: str, *, status: ArtifactStatus = ArtifactStatus.good) -> CanonicalArtifact:
    now = datetime.now(timezone.utc)
    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=now,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id=subject_id, title="Test"),
        summary=ArtifactSummary(status=status),
        sections=[],
    )


def test_artifacts_under_different_projects_are_isolated(tmp_path: Path) -> None:
    """Two projects (same customer) — each store reads back only its own artifact."""
    store_a = ArtifactStore("acme", "p_a", base_dir=tmp_path / "artifacts")
    store_b = ArtifactStore("acme", "p_b", base_dir=tmp_path / "artifacts")

    store_a.save_artifact(_artifact("security_assessment", status=ArtifactStatus.good))
    store_b.save_artifact(_artifact("security_assessment", status=ArtifactStatus.warning))

    a_loaded = store_a.load_latest_artifact("security_assessment")
    b_loaded = store_b.load_latest_artifact("security_assessment")

    assert a_loaded.summary.status == ArtifactStatus.good
    assert b_loaded.summary.status == ArtifactStatus.warning

    # On-disk paths are distinct.
    a_path = tmp_path / "artifacts" / "acme" / "p_a" / "working" / "security_assessment" / "latest.json"
    b_path = tmp_path / "artifacts" / "acme" / "p_b" / "working" / "security_assessment" / "latest.json"
    assert a_path.exists()
    assert b_path.exists()
    assert a_path.read_text() != b_path.read_text()


def test_active_project_switch_changes_which_store_reads(tmp_path: Path) -> None:
    """make_active_project_store reflects whatever the session says is active."""
    app = create_app()

    # Seed two artifacts in two different project stores (explicit base_dir,
    # so we can find them later from the helper's tmp-isolated default).
    # Use the autouse fixture's _DEFAULT_BASE_DIR via direct knowledge:
    # the helper constructs ArtifactStore(c, p) with that default base_dir.
    import cvhealthcheck.artifacts.store as store_module
    base_dir = store_module._DEFAULT_BASE_DIR

    direct_a = ArtifactStore("acme", "p_a", base_dir=base_dir)
    direct_b = ArtifactStore("acme", "p_b", base_dir=base_dir)
    direct_a.save_artifact(_artifact("license_summary", status=ArtifactStatus.good))
    direct_b.save_artifact(_artifact("license_summary", status=ArtifactStatus.warning))

    with app.test_request_context("/"):
        set_active_project("acme", "p_a")
        store = make_active_project_store()
        loaded = store.load_latest_artifact("license_summary")
        assert loaded.summary.status == ArtifactStatus.good

        set_active_project("acme", "p_b")
        store = make_active_project_store()
        loaded = store.load_latest_artifact("license_summary")
        assert loaded.summary.status == ArtifactStatus.warning


def test_artifact_written_under_one_project_is_invisible_to_another(tmp_path: Path) -> None:
    """An artifact saved to project A's working directory does not appear in
    project B's load path."""
    store_a = ArtifactStore("acme", "p_a", base_dir=tmp_path / "artifacts")
    store_b = ArtifactStore("acme", "p_b", base_dir=tmp_path / "artifacts")

    store_a.save_artifact(_artifact("security_assessment"))

    # Same subject, different project — must raise FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        store_b.load_latest_artifact("security_assessment")


def test_artifact_paths_use_customer_then_project_then_working(tmp_path: Path) -> None:
    """Path structure pin: <base>/<customer>/<project>/working/<subject>/latest.json."""
    store = ArtifactStore("acme_corp", "p_2026_042", base_dir=tmp_path / "artifacts")
    path = store.save_artifact(_artifact("security_assessment"))

    parts = path.parts
    assert "acme_corp" in parts
    assert "p_2026_042" in parts
    assert "working" in parts
    # Order: ... acme_corp / p_2026_042 / working / security_assessment / latest.json
    customer_idx = parts.index("acme_corp")
    assert parts[customer_idx + 1] == "p_2026_042"
    assert parts[customer_idx + 2] == "working"
    assert parts[customer_idx + 3] == "security_assessment"
    assert path.name == "latest.json"


def test_artifact_store_requires_non_empty_customer_and_project() -> None:
    with pytest.raises(ValueError):
        ArtifactStore("", "p_a")
    with pytest.raises(ValueError):
        ArtifactStore("acme", "")
