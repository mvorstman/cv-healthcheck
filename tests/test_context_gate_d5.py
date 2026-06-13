"""D5 — Context Integrity enforcement primitive (ADR-0015).

require_active_context() returns (customer_id, project_id) ONLY when the
operator explicitly selected it this session, and raises the typed
NoExplicitContextError otherwise. It never falls through to the Default
project — the read-path fallback can never satisfy a write.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.context import NoExplicitContextError
from cvhealthcheck.web.active_project import (
    get_active_project,
    require_active_context,
    resolve_default_project,
    set_active_project,
)
from cvhealthcheck.web.app import create_app


@pytest.fixture()
def app():
    return create_app()


def test_require_raises_outside_request_context():
    with pytest.raises(NoExplicitContextError):
        require_active_context()


def test_require_raises_in_request_without_selection(app):
    """The Default project EXISTS (migrations seed it) — and must still not
    satisfy the write primitive. Explicit means session-selected, full stop."""
    with app.test_request_context("/"):
        with pytest.raises(NoExplicitContextError):
            require_active_context()


def test_require_returns_pair_after_explicit_selection(app):
    with app.test_request_context("/"):
        set_active_project("cust_x", "proj_y")
        assert require_active_context() == ("cust_x", "proj_y")


def test_require_rejects_malformed_session_entry(app):
    from flask import session
    with app.test_request_context("/"):
        session["active_project"] = {"customer_id": "cust_x"}  # no project_id
        with pytest.raises(NoExplicitContextError):
            require_active_context()


def test_read_path_fallback_unchanged(app, migrated_db_path):
    """get_active_project (READ) keeps the Default fallback — the split is
    write-only enforcement, not a read regression."""
    import sqlite3
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    try:
        with app.test_request_context("/"):
            assert get_active_project(db) == resolve_default_project(db)
            set_active_project("cust_x", "proj_y")
            assert get_active_project(db) == ("cust_x", "proj_y")
    finally:
        db.close()


def test_error_message_is_actionable():
    err = NoExplicitContextError()
    assert "select a customer" in str(err).lower()


# ── THE NINE WRITE GATES (D5 (b)) ─────────────────────────────────────────────
#
# Route-level: no explicit context -> the one clean message, NOTHING written;
# with explicit context -> the write lands in exactly (customer, project).
# Reads (workspace render etc.) keep the Default fallback untouched.

import sqlite3

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

CLEAN_MSG = "Select a customer and project"


def _client():
    return create_app().test_client()


def _set_context(client, customer_id, project_id):
    with client.session_transaction() as sess:
        sess["active_project"] = {
            "customer_id": customer_id, "project_id": project_id,
        }


def _flashed(client):
    with client.session_transaction() as sess:
        return " | ".join(str(m) for _, m in sess.get("_flashes", []))


def _store_artifact_exists(customer_id, project_id, subject_id) -> bool:
    try:
        ArtifactStore(customer_id, project_id).load_latest_artifact(subject_id)
        return True
    except FileNotFoundError:
        return False


def _mk_artifact(subject_id="capacity_license"):
    res = ExtractionResult(subject_id=subject_id, source_type="csv")
    res.sections["rows"] = [{"col": "v"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    return result_to_artifact(res, subject_id=subject_id, subject_title=subject_id)


# 1 — collect save
def test_collect_without_context_yields_clean_prompt(monkeypatch):
    client = _client()
    called = {"extract": False}
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(
        route_module, "get_active_customer",
        lambda *a, **k: pytest.fail("collect consulted ambient customer before the gate"),
    )
    resp = client.post("/quick-hc/capacity_license/collect")
    assert resp.status_code == 302
    assert CLEAN_MSG in _flashed(client)


def test_collect_with_context_lands_scoped(monkeypatch, authenticate):
    client = _client()
    _set_context(client, "default", "proj_ctx_test")
    authenticate(client, customer_id="default")

    res = ExtractionResult(subject_id="capacity_license", source_type="rest")
    res.sections["rows"] = [{"col": "v"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"

    import cvhealthcheck.web.routes.quick_hc as route_module

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return res

    monkeypatch.setattr(route_module, "RESTExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "CommvaultSession",
                        lambda *a, **k: __import__("contextlib").nullcontext())
    resp = client.post("/quick-hc/capacity_license/collect")
    assert resp.status_code == 302
    assert _store_artifact_exists("default", "proj_ctx_test", "capacity_license")
    assert not _store_artifact_exists("default", "default", "capacity_license")


# 2 — fixture-collect save
def test_fixture_collect_without_context_yields_clean_prompt():
    client = _client()
    resp = client.post("/quick-hc/_card_test/collect-fixture")
    assert resp.status_code == 302
    assert CLEAN_MSG in _flashed(client)


def test_fixture_collect_with_context_lands_scoped():
    client = _client()
    _set_context(client, "cust_fx", "proj_fx")
    resp = client.post("/quick-hc/_card_test/collect-fixture")
    assert resp.status_code == 302
    assert _store_artifact_exists("cust_fx", "proj_fx", "_card_test")


# 3 — import save
def test_import_without_context_yields_clean_prompt():
    import io
    client = _client()
    resp = client.post(
        "/quick-hc/storage_policies/import",
        data={"file": (io.BytesIO(b"<html></html>"), "x.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert resp.status_code == 409
    assert CLEAN_MSG in resp.get_json()["error"]


def test_import_with_context_lands_scoped(monkeypatch):
    import io
    from cvhealthcheck.extractors.dispatcher import DispatchResult
    from cvhealthcheck.extractors.recognition import RecognitionResult
    client = _client()
    _set_context(client, "cust_imp", "proj_imp")
    artifact = _mk_artifact("storage_policies")
    rec = RecognitionResult(
        subject_id="storage_policies", version=1, source_type="html",
        extractable=True, non_extractable_reason=None, title="Storage Policies",
    )
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(
        route_module, "extract_file",
        lambda *a, **k: DispatchResult(
            recognized=True, subject_id="storage_policies", version=1,
            source_type="html", extractable=True, non_extractable_reason=None,
            artifact=artifact, recognition_result=rec,
        ),
    )
    resp = client.post(
        "/quick-hc/storage_policies/import",
        data={"file": (io.BytesIO(b"<html></html>"), "x.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert _store_artifact_exists("cust_imp", "proj_imp", "storage_policies")


# 4 — artifact delete
def test_delete_without_context_yields_clean_prompt(monkeypatch):
    client = _client()
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(
        route_module, "delete_subject",
        lambda *a, **k: pytest.fail("catalog delete ran before the context gate"),
    )
    resp = client.post("/quick-hc/storage_policies/delete")
    assert resp.status_code == 302
    assert CLEAN_MSG in _flashed(client)


def test_delete_with_context_deletes_from_that_store(monkeypatch):
    client = _client()
    _set_context(client, "cust_del", "proj_del")
    ArtifactStore("cust_del", "proj_del").save_artifact(_mk_artifact("storage_policies"))
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(route_module, "get_subject", lambda *a, **k: {"title": "SP"})
    monkeypatch.setattr(route_module, "delete_subject", lambda *a, **k: {"deleted": "storage_policies"})
    resp = client.post("/quick-hc/storage_policies/delete")
    assert resp.status_code == 302
    assert not _store_artifact_exists("cust_del", "proj_del", "storage_policies")


# 5 — LS scoped saves (service-level gate; raise propagates to LS routes)
def test_ls_require_store_raises_without_context():
    from cvhealthcheck.license_summary.service import _require_project_store
    with pytest.raises(NoExplicitContextError):
        _require_project_store()


def test_ls_require_store_binds_explicit_context(app):
    from cvhealthcheck.license_summary.service import _require_project_store
    with app.test_request_context("/"):
        set_active_project("cust_ls", "proj_ls")
        store = _require_project_store()
    assert (store.customer_id, store.project_id) == ("cust_ls", "proj_ls")


def test_ls_collect_route_without_context_yields_clean_prompt(authenticate):
    client = _client()
    authenticate(client, customer_id="default")
    resp = client.post("/quick-hc/license-summary/collect")
    assert resp.status_code == 302
    assert CLEAN_MSG in _flashed(client)


# 8 — version pin
def test_pin_without_context_yields_clean_prompt(monkeypatch):
    client = _client()
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(
        route_module, "set_pinned_subject_id",
        lambda *a, **k: pytest.fail("pin wrote before the context gate"),
    )
    resp = client.post("/quick-hc/capacity_license/pin-version", data={"version": "x"})
    assert resp.status_code == 302
    assert CLEAN_MSG in _flashed(client)


def test_pin_with_context_pins_for_that_customer(monkeypatch):
    client = _client()
    _set_context(client, "cust_pin", "proj_pin")
    calls = {}
    import cvhealthcheck.web.routes.quick_hc as route_module
    monkeypatch.setattr(route_module, "list_family_versions", lambda db, fam: ["capacity_license"])
    monkeypatch.setattr(
        route_module, "set_pinned_subject_id",
        lambda db, cust, fam, chosen: calls.update(cust=cust, fam=fam, chosen=chosen),
    )
    resp = client.post(
        "/quick-hc/capacity_license/pin-version", data={"version": "capacity_license"}
    )
    assert resp.status_code == 302
    assert calls == {"cust": "cust_pin", "fam": "capacity_license", "chosen": "capacity_license"}


# 7 — MCP delete_subject: artifact half requires explicit, validated params
def test_mcp_delete_without_context_refuses(monkeypatch, migrated_db_path):
    import cvhealthcheck.mcp.server as mcp
    def _db():
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(mcp, "get_db", _db)
    from cvhealthcheck.db.subjects import create_subject_from_proposal
    db = _db()
    create_subject_from_proposal(db, {
        "subject_id": "_d5_del", "version": 1, "title": "t", "description": "",
        "category": "operations",
        "sections": [{"section_id": "s", "title": "S", "section_type": "table",
                      "default_selected": True, "sort_order": 0}],
        "extraction_instructions": {"html": {"extractable": True, "sections": {"s": {}}}},
    })
    db.close()
    with pytest.raises(NoExplicitContextError):
        mcp.delete_subject("_d5_del")
    db = _db()
    assert db.execute(
        "SELECT COUNT(*) FROM subjects WHERE subject_id='_d5_del'"
    ).fetchone()[0] == 1, "catalog row must be untouched on refusal"
    db.close()


def test_mcp_delete_with_unknown_customer_refuses(monkeypatch, migrated_db_path):
    import cvhealthcheck.mcp.server as mcp
    from cvhealthcheck.context import UnknownContextError
    def _db():
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(mcp, "get_db", _db)
    from cvhealthcheck.db.subjects import create_subject_from_proposal
    db = _db()
    create_subject_from_proposal(db, {
        "subject_id": "_d5_del2", "version": 1, "title": "t", "description": "",
        "category": "operations",
        "sections": [{"section_id": "s", "title": "S", "section_type": "table",
                      "default_selected": True, "sort_order": 0}],
        "extraction_instructions": {"html": {"extractable": True, "sections": {"s": {}}}},
    })
    db.close()
    with pytest.raises(UnknownContextError):
        mcp.delete_subject("_d5_del2", customer_id="ghost", project_id="ghost_p")
    db = _db()
    assert db.execute(
        "SELECT COUNT(*) FROM subjects WHERE subject_id='_d5_del2'"
    ).fetchone()[0] == 1
    db.close()


def test_mcp_delete_with_valid_context_deletes_catalog_and_scoped_artifact(
    monkeypatch, migrated_db_path
):
    import cvhealthcheck.mcp.server as mcp
    def _db():
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(mcp, "get_db", _db)
    from cvhealthcheck.db.subjects import create_subject_from_proposal
    db = _db()
    create_subject_from_proposal(db, {
        "subject_id": "_d5_del3", "version": 1, "title": "t", "description": "",
        "category": "operations",
        "sections": [{"section_id": "s", "title": "S", "section_type": "table",
                      "default_selected": True, "sort_order": 0}],
        "extraction_instructions": {"html": {"extractable": True, "sections": {"s": {}}}},
    })
    customer_id, project_id = resolve_default_project(db)
    db.close()
    ArtifactStore(customer_id, project_id).save_artifact(_mk_artifact("_d5_del3"))

    result = mcp.delete_subject("_d5_del3", customer_id=customer_id, project_id=project_id)
    assert result["deleted"] == "_d5_del3"
    db = _db()
    assert db.execute(
        "SELECT COUNT(*) FROM subjects WHERE subject_id='_d5_del3'"
    ).fetchone()[0] == 0
    db.close()
    assert not _store_artifact_exists(customer_id, project_id, "_d5_del3")


# ── STAGING STAMPS + APPROVAL CONTEXT (D5 (c)+(d)) ────────────────────────────

from cvhealthcheck.context import ContextMismatchError, UnknownContextError
from cvhealthcheck.db.staging import create_staged_artifact, execute_approval


def _stage_artifact_row(db, stage_id, subject_id="storage_policies", customer_id=None):
    return create_staged_artifact(
        db, stage_id, subject_id,
        _mk_artifact(subject_id).model_dump_json(),
        source_type="html", customer_id=customer_id,
    )


def _migrated_conn(migrated_db_path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_proposal_approval_needs_no_context(migrated_db_path):
    """Catalog-global by design (Catalog Purity): subject proposals carry no
    customer context and approve without one."""
    db = _migrated_conn(migrated_db_path)
    try:
        from cvhealthcheck.mcp.server import propose_new_subject
        import cvhealthcheck.mcp.server as mcp
        # stage via the db directly (propose_new_subject uses its own get_db)
        import json as _json
        db.execute(
            "INSERT INTO staged_artifacts (stage_id, subject_id, artifact_type,"
            " subject_version, source_type, status, artifact_json, created_at)"
            " VALUES ('st_prop', '_d5_prop', 'subject_proposal', 1, 'ai', 'pending', ?,"
            " strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
            (_json.dumps({
                "subject_id": "_d5_prop", "version": 1, "title": "P",
                "description": "", "category": "operations",
                "sections": [{"section_id": "s", "title": "S",
                              "section_type": "table", "default_selected": True,
                              "sort_order": 0}],
                "extraction_instructions": {"html": {"extractable": True,
                                                     "sections": {"s": {}}}},
            }),),
        )
        db.commit()
        result = execute_approval(db, "st_prop", reviewed_by="test")
        assert result["type"] == "subject_proposal"
    finally:
        db.close()


