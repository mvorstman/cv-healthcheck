"""Fix 4 surfacing (display only) — the stamped identity verdict is shown, never
acted on: artifact_to_view exposes it, evaluate_subject returns it, the collect
flash is loud on mismatch but does not block.

The verdict is now GUID-driven (namespace-precision fix); the shared verdict
display (_ccid_verdict_display) is unchanged, so mismatch stays the loud
error banner, attested stays silent on collect, verified stays a quiet success.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _guid_mismatch_artifact():
    """A GUID-driven mismatch artifact (declared aaaa vs wire bbbb)."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.list"] = [{"name": "x"}]
    res.section_output_types["environment.list"] = "table"
    res.section_titles["environment.list"] = "List"
    res.wire_commserve_guid = "bbbb"
    res.wire_commserve_guid_source = "session:commserv.csGUID"
    return result_to_artifact(
        res, subject_id="environment", subject_title="Env",
        commcell_id="337f", commserve_guid="aaaa",
    )


def test_artifact_to_view_exposes_verification():
    from cvhealthcheck.quickhc.canonical_view import artifact_to_view
    view = artifact_to_view(_guid_mismatch_artifact())
    assert view["verification"]["status"] == "mismatch"
    assert "declared_normalized=aaaa" in view["verification"]["notes"]


def test_legacy_artifact_view_verification_none():
    """An artifact whose source has no verdict (pre-Fix-4) surfaces None."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.list"] = [{"name": "x"}]
    res.section_output_types["environment.list"] = "table"
    res.section_titles["environment.list"] = "List"
    artifact = result_to_artifact(
        res, subject_id="environment", subject_title="Env", commcell_id="337f",
    )
    bare = artifact.source.model_copy(update={"verification_status": None})
    artifact = artifact.model_copy(update={"source": bare})
    from cvhealthcheck.quickhc.canonical_view import artifact_to_view
    assert artifact_to_view(artifact)["verification"] is None


def test_evaluate_subject_surfaces_verification(migrated_db_path, tmp_path):
    import sqlite3
    from cvhealthcheck.evaluative.subject_eval import evaluate_subject
    store = ArtifactStore("c", "p", base_dir=tmp_path / "s")
    store.save_artifact(_guid_mismatch_artifact())
    db = sqlite3.connect(str(migrated_db_path)); db.row_factory = sqlite3.Row
    try:
        result = evaluate_subject(db, "environment", store=store)
    finally:
        db.close()
    assert result["verification"]["status"] == "mismatch"


# ── collect-route surfacing (GUID-driven) ─────────────────────────────────────

def _table_result():
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.list"] = [{"name": "x"}]
    res.section_output_types["environment.list"] = "table"
    res.section_titles["environment.list"] = "List"
    return res


def _collect(monkeypatch, *, result, declared_guid, probe_guid):
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    saved: dict = {}

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact): saved["a"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return result

    def probe(*a, **k):
        if probe_guid is None:
            return {"http_status": 401, "ok": False, "raw": {}}
        return {"http_status": 200, "ok": True, "identity": {"csGUID": probe_guid}}

    monkeypatch.setattr(route_module, "get_active_customer", lambda *a, **k: {
        "customer_id": "c", "customer_name": "Acme",
        "connection_url": "https://h:4433", "commcell_hostname": None,
        "commserve_name": "CS01", "commcell_id": "337f",
        "commserve_csguid": declared_guid,
    })
    monkeypatch.setattr(route_module, "is_authenticated_for", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "_current_token", lambda *a, **k: "t")
    monkeypatch.setattr(route_module, "_has_command_center_source", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "CommandCenterExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "ArtifactStore", FakeStore)
    monkeypatch.setattr(route_module, "get_commcell_identity", probe)
    monkeypatch.setattr(route_module, "learn_commserve_csguid", lambda *a, **k: True)

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    resp = client.post("/quick-hc/environment/collect")
    with client.session_transaction() as sess:
        flashes = " | ".join(str(m) for _, m in sess.get("_flashes", []))
    return resp.status_code, saved.get("a"), flashes


def test_mismatch_collect_flashes_does_not_block(monkeypatch, migrated_db_path):
    """A GUID mismatch produces a loud flash but the collect still completes (302,
    artifact saved) — provenance, not workflow."""
    code, art, flashes = _collect(
        monkeypatch, result=_table_result(), declared_guid="aaaa", probe_guid="bbbb",
    )
    assert code == 302                                   # not blocked
    assert art.source.verification_status == "mismatch"  # persisted
    assert "MISMATCH" in flashes


def test_attested_collect_is_silent_but_persists(monkeypatch, migrated_db_path):
    """attested on COLLECT must NOT flash. Probe returns no csGUID -> attested."""
    code, art, flashes = _collect(
        monkeypatch, result=_table_result(), declared_guid="aaaa", probe_guid=None,
    )
    assert code == 302
    assert art.source.verification_status == "attested"  # persisted
    assert "trusted, not verified" not in flashes        # silent on collect
    assert "could not be verified" not in flashes
