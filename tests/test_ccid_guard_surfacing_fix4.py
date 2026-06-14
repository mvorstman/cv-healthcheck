"""Fix 4 surfacing (display only) — the stamped CCID verdict is shown, never
acted on: artifact_to_view exposes it, evaluate_subject returns it, the collect
flash is loud on mismatch but does not block."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _cc_api_result(commcell_id_value):
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    record = {"commcell": {"commCellName": "cs01", "commCellId": commcell_id_value}}
    res.sections["environment.metadata"] = [record]
    res.section_output_types["environment.metadata"] = "card"
    res.section_card_specs["environment.metadata"] = {"items": []}
    res.section_titles["environment.metadata"] = "Metadata"
    return res


def _cc_api_result_no_identity():
    """A CC-API result whose records carry NO commcell.commCellId -> the source
    offers no wire identity -> attested (declared present)."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.list"] = [{"name": "x"}]
    res.section_output_types["environment.list"] = "table"
    res.section_titles["environment.list"] = "List"
    return res


def test_artifact_to_view_exposes_verification():
    from cvhealthcheck.quickhc.canonical_view import artifact_to_view
    artifact = result_to_artifact(
        _cc_api_result(2), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    view = artifact_to_view(artifact)
    assert view["verification"]["status"] == "mismatch"
    assert "declared_normalized=337f" in view["verification"]["notes"]


def test_legacy_artifact_view_verification_none():
    """An artifact whose source has no verdict (pre-Fix-4) surfaces None."""
    from cvhealthcheck.artifacts.models import ArtifactSource
    artifact = result_to_artifact(
        _cc_api_result(13183), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    bare = artifact.source.model_copy(update={"verification_status": None})
    artifact = artifact.model_copy(update={"source": bare})
    from cvhealthcheck.quickhc.canonical_view import artifact_to_view
    assert artifact_to_view(artifact)["verification"] is None


def test_evaluate_subject_surfaces_verification(migrated_db_path, tmp_path):
    import sqlite3
    from cvhealthcheck.evaluative.subject_eval import evaluate_subject
    store = ArtifactStore("c", "p", base_dir=tmp_path / "s")
    artifact = result_to_artifact(
        _cc_api_result(2), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    store.save_artifact(artifact)
    db = sqlite3.connect(str(migrated_db_path)); db.row_factory = sqlite3.Row
    try:
        result = evaluate_subject(db, "environment", store=store)
    finally:
        db.close()
    assert result["verification"]["status"] == "mismatch"


def test_mismatch_collect_flashes_does_not_block(monkeypatch, migrated_db_path):
    """A mismatch produces a loud flash but the collect still completes (302,
    artifact saved) — provenance, not workflow."""
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    res = _cc_api_result(2)   # wire 2 vs declared 337f -> mismatch
    saved = {}

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact): saved["a"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return res

    monkeypatch.setattr(route_module, "get_active_customer", lambda *a, **k: {
        "customer_id": "c", "customer_name": "Acme",
        "connection_url": "https://h:4433", "commcell_hostname": None,
        "commserve_name": "CS01", "commcell_id": "337f",
    })
    monkeypatch.setattr(route_module, "is_authenticated_for", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "_current_token", lambda *a, **k: "t")
    monkeypatch.setattr(route_module, "_has_command_center_source", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "CommandCenterExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "ArtifactStore", FakeStore)

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    resp = client.post("/quick-hc/environment/collect")

    assert resp.status_code == 302                    # not blocked
    assert saved["a"].source.verification_status == "mismatch"   # persisted
    with client.session_transaction() as sess:
        flashes = " | ".join(str(m) for _, m in sess.get("_flashes", []))
    assert "MISMATCH" in flashes


def test_attested_collect_is_silent_but_persists(monkeypatch, migrated_db_path):
    """attested on COLLECT must NOT flash — every non-identity collect is
    attested, so a banner there is blindness. The verdict still persists; only
    the surfacing is suppressed (mismatch always shows; this proves attested
    does not)."""
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    res = _cc_api_result_no_identity()   # declared 337f, no wire -> attested
    saved = {}

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact): saved["a"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return res

    monkeypatch.setattr(route_module, "get_active_customer", lambda *a, **k: {
        "customer_id": "c", "customer_name": "Acme",
        "connection_url": "https://h:4433", "commcell_hostname": None,
        "commserve_name": "CS01", "commcell_id": "337f",
    })
    monkeypatch.setattr(route_module, "is_authenticated_for", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "_current_token", lambda *a, **k: "t")
    monkeypatch.setattr(route_module, "_has_command_center_source", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "CommandCenterExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "ArtifactStore", FakeStore)
    # The result carries no endpoint identity, so the Fix-4 session-wire probe
    # fires; give it a no-identity payload so the verdict stays attested
    # deterministically (no real network call). See test_session_wire_ccid_fix4.
    monkeypatch.setattr(route_module, "get_commcell_identity",
                        lambda *a, **k: {"http_status": 401, "ok": False, "raw": {}})

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    resp = client.post("/quick-hc/environment/collect")

    assert resp.status_code == 302
    assert saved["a"].source.verification_status == "attested"     # persisted
    with client.session_transaction() as sess:
        flashes = " | ".join(str(m) for _, m in sess.get("_flashes", []))
    assert "trusted, not verified" not in flashes                  # silent on collect
    assert "could not be verified" not in flashes
