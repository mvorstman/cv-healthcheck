"""
Global test fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_canonical_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Prevent tests from touching the real canonical artifact store on disk.

    Monkeypatches the ArtifactStore module's _DEFAULT_BASE_DIR so any
    ArtifactStore(customer_id, project_id) constructed without an explicit
    base_dir writes under tmp_path. Tests that explicitly pass base_dir
    are unaffected.
    """
    import cvhealthcheck.artifacts.store as store_module
    # Mirror the production directory name ('artifacts' under 'catalog' under
    # 'data') so tests that assert on the path structure still pass.
    monkeypatch.setattr(
        store_module, "_DEFAULT_BASE_DIR", tmp_path / "data" / "catalog" / "artifacts"
    )


@pytest.fixture()
def migrated_db_path(tmp_path: Path) -> Path:
    """Isolated SQLite database with all migrations applied (including seed data)."""
    from cvhealthcheck.db.migrations import run_migrations
    path = tmp_path / "test.db"
    run_migrations(db_path=path)
    return path
