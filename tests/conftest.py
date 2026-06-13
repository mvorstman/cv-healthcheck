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


# A synthetic, PREFIXED-id subject used by the generic-extractor MACHINERY tests
# (single_table header scan, null_values, BOM, metadata-skip, html title-match).
# It deliberately follows the prefix convention so those tests stay decoupled from
# any real recipe's section-id choices — in particular from License Summary, whose
# canonical ids are bare (ADR-0017). Change a real recipe and these stay green.
_MACHINERY_SUBJECT_ID = "extractor_machinery"
_MACHINERY_NULLS = ["N/A", "-", ""]
_MACHINERY_OTHER = f"{_MACHINERY_SUBJECT_ID}.other_licenses"
_MACHINERY_AGENT = f"{_MACHINERY_SUBJECT_ID}.agent_feature_licenses"
_MACHINERY_OTHER_CM = [
    {"source": "License", "canonical": "license_name", "type": "string"},
    {"source": "Available Total", "canonical": "available_total_raw", "type": "string"},
    {"source": "Used", "canonical": "used_raw", "type": "string"},
]
_MACHINERY_AGENT_CM = [
    {"source": "License", "canonical": "license_name", "type": "string"},
    {"source": "Permanent Total", "canonical": "permanent_total_raw", "type": "string"},
    {"source": "Permanent Used", "canonical": "permanent_used_raw", "type": "string"},
    {"source": "Term Total", "canonical": "term_total_raw", "type": "string"},
    {"source": "Term Used", "canonical": "term_used_raw", "type": "string"},
]
_MACHINERY_PROPOSAL = {
    "subject_id": _MACHINERY_SUBJECT_ID,
    "version": 1,
    "title": "Extractor Machinery (test)",
    "description": "Synthetic prefixed-id subject for testing extractor machinery "
                   "decoupled from any real recipe.",
    "category": "operations",
    "sections": [
        {"section_id": _MACHINERY_OTHER, "title": "Other Licenses",
         "section_type": "table", "default_selected": True, "sort_order": 0},
        {"section_id": _MACHINERY_AGENT, "title": "Agent and Feature Licenses",
         "section_type": "table", "default_selected": True, "sort_order": 1},
    ],
    "extraction_instructions": {
        "csv": {"extractable": True, "sections": {
            _MACHINERY_OTHER: {"format": "single_table", "column_map": _MACHINERY_OTHER_CM,
                               "null_values": _MACHINERY_NULLS, "output_as": "table"},
            _MACHINERY_AGENT: {"format": "single_table", "column_map": _MACHINERY_AGENT_CM,
                               "null_values": _MACHINERY_NULLS, "output_as": "table"},
        }},
        "html": {"extractable": True, "sections": {
            _MACHINERY_OTHER: {"section_title_selector": ".reportstabletitle",
                               "section_title_match": "Other Licenses",
                               "column_map": _MACHINERY_OTHER_CM,
                               "null_values": _MACHINERY_NULLS, "output_as": "table"},
            _MACHINERY_AGENT: {"section_title_selector": ".reportstabletitle",
                               "section_title_match": "Agent and Feature Licenses",
                               "column_map": _MACHINERY_AGENT_CM,
                               "null_values": _MACHINERY_NULLS, "output_as": "table"},
        }},
    },
}


@pytest.fixture()
def machinery_subject(migrated_db_path: Path) -> str:
    """Publish the synthetic prefixed-id machinery subject into the migrated db and
    return its subject_id. Used by the generic-extractor tests so they exercise
    extractor machinery, not a real recipe's section-id contract."""
    import sqlite3

    from cvhealthcheck.db.subjects import create_subject_from_proposal

    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_subject_from_proposal(conn, _MACHINERY_PROPOSAL)
        conn.commit()
    finally:
        conn.close()
    return _MACHINERY_SUBJECT_ID


@pytest.fixture(autouse=True)
def _reset_token_store():
    """Clear the process-global held-token store around every test (ADR-0008 B).

    Tests now establish auth by populating the store, so a token set in one test must
    not leak into the next.
    """
    from cvhealthcheck import token_store
    token_store.clear_active_token()
    yield
    token_store.clear_active_token()


@pytest.fixture()
def authenticate():
    """Establish an authenticated session the ADR-0008 way: the held CommServe token
    goes to the in-process store; the non-secret customer/username markers go to the
    session cookie. Replaces the old ``session[SESSION_TOKEN_KEY] = ...`` poke — the
    cookie no longer carries the token.
    """
    from cvhealthcheck import token_store
    from cvhealthcheck.auth.commvault_auth import (
        SESSION_CUSTOMER_ID_KEY,
        SESSION_USERNAME_KEY,
    )

    def _auth(client, *, token: str = "test-token", customer_id=None, username=None):
        token_store.set_active_token(token, principal=username)
        if customer_id is not None or username is not None:
            with client.session_transaction() as sess:
                if customer_id is not None:
                    sess[SESSION_CUSTOMER_ID_KEY] = customer_id
                if username is not None:
                    sess[SESSION_USERNAME_KEY] = username

    return _auth


@pytest.fixture()
def explicit_context():
    """Explicitly select the active (customer, project) the D5 way — the same
    session entry set_active_project writes. Write-gated routes (collect,
    import, delete, pin, LS collect) require this; without it they refuse
    with the clean 'select a customer and project' response by design."""
    def _select(client, customer_id: str = "default", project_id: str = "default"):
        with client.session_transaction() as sess:
            sess["active_project"] = {
                "customer_id": customer_id,
                "project_id": project_id,
            }
    return _select
