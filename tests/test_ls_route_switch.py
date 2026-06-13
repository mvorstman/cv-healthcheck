"""ADR-0017 LS promotion commit 4b — route switch + field align.

The LS CSV/HTML upload now routes through the GENERIC dispatcher (extract_file ->
result_to_artifact + D2 enrichment), not the bespoke handler. These tests include
the required ROUTE-IDENTITY PROOF: the generic dispatcher ran and the bespoke
handler branch (_handle_system_upload -> import_license_summary_upload) was NOT
taken — "import succeeded" alone is insufficient (bespoke-success previously
masqueraded as generic-success).
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import cvhealthcheck.web.routes.quick_hc as quick_hc_routes
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.web.app import create_app

_LS_DIR = Path("data/imports/license_summary")
_WORKLOAD_HTML = sorted(_LS_DIR.glob("License20summary_2026-05-28-11-12-42-*.html"))

_LS_CSV = (
    "License summary\n"
    "\n"
    "Other Licenses\n"
    "License,Available Total,Used\n"
    "Lic A,10 TB,4 clients\n"
)


@pytest.fixture()
def ls_route_client(monkeypatch: pytest.MonkeyPatch, migrated_db_path: Path):
    """Flask client wired to the migrated test DB (recipe + recognition live),
    with the canonical store faked to capture saves and a controlled active
    customer (so the declared CommServe name is deterministic). The bespoke
    handler branch is rigged to FAIL if taken — the route-identity guard."""
    def open_db() -> sqlite3.Connection:
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(quick_hc_routes, "get_db", open_db)

    saved: list[Any] = []

    class _FakeStore:
        def __init__(self, *a, **k) -> None:
            pass

        def save_artifact(self, artifact: Any) -> Path:
            saved.append(artifact)
            return Path("/tmp/fake.json")

    monkeypatch.setattr(quick_hc_routes, "ArtifactStore", _FakeStore)
    # Controlled declared identity (get_customer otherwise reads the global DB).
    monkeypatch.setattr(
        quick_hc_routes, "get_active_customer",
        lambda db: {"commcell_id": "cc-decl", "commserve_name": "DeclaredCS"},
    )
    # ROUTE-IDENTITY GUARD: the bespoke handler branch must NEVER run for LS.
    monkeypatch.setattr(
        quick_hc_routes, "_handle_system_upload",
        lambda handler: pytest.fail("bespoke _handle_system_upload was invoked for LS"),
    )

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["active_project"] = {"customer_id": "default", "project_id": "default"}
        yield c, saved


def _commcell_info(artifact: CanonicalArtifact):
    ci = [s for s in artifact.sections if s.id == "commcell_info"]
    return {it.id: it.value for it in ci[0].items} if ci else None


# ── ROUTE-IDENTITY PROOF: workload HTML imports via the GENERIC path ──────────

@pytest.mark.skipif(not _WORKLOAD_HTML, reason="workload fixture missing")
def test_workload_html_imports_via_generic_not_bespoke(ls_route_client):
    client, saved = ls_route_client
    payload = _WORKLOAD_HTML[0].read_bytes()

    resp = client.post(
        "/quick-hc/license_summary/import",
        data={"file": (io.BytesIO(payload), "License summary_2026-05-28-11-12-42.html")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )

    # generic-path JSON marker: the generic dispatcher returns "title"; the bespoke
    # _handle_system_upload success body does NOT (and it is rigged to fail anyway).
    assert resp.status_code == 200 and resp.is_json
    body = resp.get_json()
    assert body["success"] is True
    assert "title" in body  # generic dispatcher marker

    # the generic dispatcher produced + saved the artifact
    assert len(saved) == 1
    art = saved[0]
    assert isinstance(art, CanonicalArtifact)
    assert art.subject.id == "license_summary"
    # workload sections extracted (the file bespoke REJECTS)
    assert any(s.id == "capacity_licenses" for s in art.sections)
    # gate 7: commcell_info present WITH the declared name (D2 top tier, threaded 4a)
    ci = _commcell_info(art)
    assert ci is not None and ci["commcell_name"] == "DeclaredCS"


# ── gate 5: CSV imports via the generic path ──────────────────────────────────

def test_csv_imports_via_generic(ls_route_client):
    client, saved = ls_route_client

    resp = client.post(
        "/quick-hc/license_summary/import",
        data={"file": (io.BytesIO(_LS_CSV.encode()), "license.csv")},
        content_type="multipart/form-data",
        headers={"X-Inline": "1"},
    )

    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert "title" in resp.get_json()  # generic marker
    assert len(saved) == 1
    assert saved[0].subject.id == "license_summary"
    assert any(s.id == "other_licenses" for s in saved[0].sections)


# ── gate 3: the UI ships the generic "file" upload field ──────────────────────

def test_upload_field_aligned_to_file():
    from cvhealthcheck.quickhc.subject_data_service import _provenance_to_tile_sources

    sources = _provenance_to_tile_sources(
        "license_summary",
        [{"source_type": "html", "status": "available", "label": "HTML", "description": ""}],
    )
    upload_actions = [a for s in sources for a in s.get("actions", []) if a.get("kind") == "upload"]
    assert upload_actions, "no upload action built for license_summary html"
    assert upload_actions[0]["importField"] == "file"


# ── gate 1 / route fall-through: handler unregistered, retained for revert ─────

def test_ls_handler_unregistered_but_retained():
    from cvhealthcheck.web.routes import upload_dispatch as ud

    assert "license_summary" not in ud.UPLOAD_HANDLERS
    assert ud.get_handler("license_summary") is None
    # safety net: the handler object survives for a one-line revert
    assert ud._LICENSE_SUMMARY_BESPOKE_HANDLER.import_fn.__name__ == "import_license_summary_upload"


# ── gate 9/10: REST collect still bespoke; no shared/bespoke code deleted ──────

def test_rest_collect_path_untouched():
    # The REST collect route is still wired to the bespoke LicenseSummaryService.
    from cvhealthcheck.quickhc.subject_data_service import _DISPATCH_REST_COLLECT_URLS

    assert _DISPATCH_REST_COLLECT_URLS.get("license_summary") == "/quick-hc/license-summary/collect"
    from cvhealthcheck.license_summary.service import LicenseSummaryService
    assert hasattr(LicenseSummaryService, "collect_from_rest")


def test_no_shared_or_bespoke_code_deleted():
    # Commit 4b deletes nothing — the bespoke upload + REST + shared code all import.
    from cvhealthcheck.adapters.license_summary import adapt  # noqa: F401
    from cvhealthcheck.license_summary import normalize, models  # noqa: F401
    from cvhealthcheck.license_summary.collect_rest import collect_license_summary_rest  # noqa: F401
    from cvhealthcheck.license_summary.service import (  # noqa: F401
        import_license_summary_upload,
        persist_license_summary_artifact,
    )
