"""
Global test fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore


@pytest.fixture(autouse=True)
def _isolate_canonical_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Prevent tests from touching the real canonical artifact store.
    Each test gets its own isolated ArtifactStore backed by a temp directory.
    Covers both the write-side stores in service modules and the read-side
    store in subject_data_service.
    """
    import cvhealthcheck.security_assessment.service as sa_service
    import cvhealthcheck.license_summary.service as ls_service
    import cvhealthcheck.quickhc.subject_data_service as sds

    isolated = ArtifactStore(base_dir=tmp_path / "canonical_artifacts")
    monkeypatch.setattr(sa_service, "_artifact_store", isolated)
    monkeypatch.setattr(ls_service, "_artifact_store", isolated)
    monkeypatch.setattr(sds, "_canonical_store", isolated)


@pytest.fixture()
def migrated_db_path(tmp_path: Path) -> Path:
    """Isolated SQLite database with all migrations applied (including seed data)."""
    from cvhealthcheck.db.migrations import run_migrations
    path = tmp_path / "test.db"
    run_migrations(db_path=path)
    return path
