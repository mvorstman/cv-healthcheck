"""Fix 4 — csGUID comparand (namespace-precision fix).

The identity verdict now compares the CommServe **csGUID** — a single stable
namespace already in the /CommServ payload — instead of the cross-namespace
CommCell ID (declared LICENSED `337f` vs wire INTERNAL `2`, which false-mismatched
the legitimate HomeLab customer).

- `verify_commcell_guid` mirrors `verify_commcell_id`'s shape but with the GUID
  ladder: either side unset -> attested; equal (case-insensitive) -> verified;
  differ -> mismatch. Never raises, never blocks.
- `result_to_artifact` drives the stamped verdict from the GUID; the licensed
  `commcell_id` is retained as DISPLAYED-not-verified provenance (still stamped on
  the source, no longer the verdict driver).
- the live collect route probes the session /CommServ csGUID once, TOFU-learns it
  on the customer (set-once) when unset, and passes declared+wire GUID through.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.identity import verify_commcell_guid

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
_GUID = "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"


# ── pure verdict function (mirrors verify_commcell_id shape) ──────────────────

def test_guid_equal_case_insensitive_is_verified():
    v = verify_commcell_guid(_GUID, _GUID.lower(),
                             wire_source="session:commserv.csGUID", now=_NOW)
    assert v["verification_status"] == "verified"


def test_guid_differ_is_mismatch():
    v = verify_commcell_guid(_GUID, "0000-different-guid", now=_NOW)
    assert v["verification_status"] == "mismatch"


def test_declared_guid_unset_is_attested():
    # GUID ladder differs from CCID: declared unset -> attested (not unverifiable).
    v = verify_commcell_guid(None, _GUID, now=_NOW)
    assert v["verification_status"] == "attested"


def test_wire_guid_unset_is_attested():
    v = verify_commcell_guid(_GUID, None, now=_NOW)
    assert v["verification_status"] == "attested"


def test_both_unset_is_attested():
    assert verify_commcell_guid(None, None, now=_NOW)["verification_status"] == "attested"


def test_notes_and_sources_recorded():
    v = verify_commcell_guid(_GUID, _GUID.lower(),
                             wire_source="session:commserv.csGUID", now=_NOW)
    assert "declared_normalized=" + _GUID.lower() in v["verification_notes"]
    assert "wire_normalized=" + _GUID.lower() in v["verification_notes"]
    assert v["verification_sources"] == ["session:commserv.csGUID"]
    assert v["verified_at"] == _NOW


def test_sources_empty_when_no_wire():
    v = verify_commcell_guid(_GUID, None,
                             wire_source="session:commserv.csGUID", now=_NOW)
    assert v["verification_sources"] == []


# ── result_to_artifact: verdict now GUID-driven, CCID is provenance ───────────

def _cc_result(wire_guid=None, subject_id="clients"):
    res = ExtractionResult(subject_id=subject_id, source_type="rest_command_center_api")
    res.sections["client_list"] = [{"clientName": "h1"}, {"clientName": "h2"}]
    res.section_output_types["client_list"] = "table"
    res.section_titles["client_list"] = "Clients"
    if wire_guid is not None:
        res.wire_commserve_guid = wire_guid
        res.wire_commserve_guid_source = "session:commserv.csGUID"
    return res


def test_r2a_guid_match_verified_and_ccid_still_stamped():
    art = result_to_artifact(
        _cc_result(_GUID.lower()), subject_id="clients", subject_title="Clients",
        commcell_id="337f", commserve_guid=_GUID,
    )
    assert art.source.verification_status == "verified"
    assert art.source.commcell_id == "337f"   # licensed CCID = displayed provenance


def test_r2a_guid_differ_is_mismatch():
    art = result_to_artifact(
        _cc_result("bbbb"), subject_id="clients", subject_title="Clients",
        commcell_id="337f", commserve_guid="aaaa",
    )
    assert art.source.verification_status == "mismatch"


def test_r2a_no_wire_guid_is_attested():
    art = result_to_artifact(
        _cc_result(None), subject_id="clients", subject_title="Clients",
        commcell_id="337f", commserve_guid="aaaa",
    )
    assert art.source.verification_status == "attested"


def test_r2a_no_declared_guid_is_attested():
    art = result_to_artifact(
        _cc_result(_GUID), subject_id="clients", subject_title="Clients",
        commcell_id="337f", commserve_guid=None,
    )
    assert art.source.verification_status == "attested"


def test_r2a_licensed_ccid_no_longer_drives_verdict_false_mismatch_gone():
    """The bug: declared LICENSED 337f + wire INTERNAL commCellId=2 in the card
    section, no GUID -> attested (was a FALSE 'mismatch'). CCID is out of the
    verdict path entirely now."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.metadata"] = [{"commcell": {"commCellId": 2, "commCellName": "CS01"}}]
    res.section_output_types["environment.metadata"] = "card"
    res.section_card_specs["environment.metadata"] = {"items": []}
    res.section_titles["environment.metadata"] = "Metadata"
    art = result_to_artifact(
        res, subject_id="environment", subject_title="Env", commcell_id="337f",
    )  # no commserve_guid
    assert art.source.verification_status == "attested"   # NOT mismatch


def test_r2a_import_html_no_guid_is_attested():
    res = ExtractionResult(subject_id="x", source_type="html")
    res.sections["rows"] = [{"a": "1"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    art = result_to_artifact(res, subject_id="x", subject_title="X", commcell_id="337f")
    assert art.source.verification_status == "attested"
    assert art.source.commcell_id == "337f"


# ── db: TOFU set-once + manual override ───────────────────────────────────────

def test_learn_commserve_csguid_is_set_once(migrated_db_path):
    from cvhealthcheck.db.customers import (
        create_customer, get_customer, learn_commserve_csguid,
    )
    create_customer("Acme", customer_id="acme", db_path=migrated_db_path)
    # first learn writes; second does NOT overwrite (a changed GUID is a signal).
    assert learn_commserve_csguid("acme", "GUID-1", db_path=migrated_db_path) is True
    assert get_customer("acme", db_path=migrated_db_path)["commserve_csguid"] == "GUID-1"
    assert learn_commserve_csguid("acme", "GUID-2", db_path=migrated_db_path) is False
    assert get_customer("acme", db_path=migrated_db_path)["commserve_csguid"] == "GUID-1"


def test_manual_override_can_change_guid(migrated_db_path):
    from cvhealthcheck.db.customers import (
        create_customer, get_customer, update_customer,
    )
    create_customer("Acme2", customer_id="acme2", db_path=migrated_db_path)
    update_customer("acme2", commserve_csguid="GUID-A", db_path=migrated_db_path)
    update_customer("acme2", commserve_csguid="GUID-B", db_path=migrated_db_path)
    assert get_customer("acme2", db_path=migrated_db_path)["commserve_csguid"] == "GUID-B"


# ── live CC-API collect route: csGUID probe + TOFU + loud mismatch ────────────

def _probe_identity(csguid):
    def _p(*a, **k):
        return {"http_status": 200, "ok": True,
                "identity": {"csGUID": csguid, "hostName": "cs01"},
                "raw": {"commcell": {"commCellId": 2}}}
    return _p


def _probe_raises(*a, **k):
    raise RuntimeError("token expired")


def _run_collect(monkeypatch, *, result, declared_guid, probe):
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    saved: dict = {}
    learn_calls: list = []

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact): saved["a"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return result

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
    monkeypatch.setattr(route_module, "learn_commserve_csguid",
                        lambda cid, guid, **k: learn_calls.append((cid, guid)) or True)

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    resp = client.post("/quick-hc/environment/collect")
    with client.session_transaction() as sess:
        flashes = " | ".join(str(m) for _, m in sess.get("_flashes", []))
    return resp.status_code, saved.get("a"), flashes, learn_calls


def _ai_result():
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["client_list"] = [{"clientName": "h1"}]
    res.section_output_types["client_list"] = "table"
    res.section_titles["client_list"] = "Clients"
    return res


def test_collect_guid_match_is_verified(monkeypatch, migrated_db_path):
    code, art, flashes, learn = _run_collect(
        monkeypatch, result=_ai_result(), declared_guid=_GUID, probe=_probe_identity(_GUID.lower()),
    )
    assert code == 302
    assert art.source.verification_status == "verified"
    assert art.source.verification_sources == ["session:commserv.csGUID"]
    assert learn == []                       # declared already set -> no TOFU


def test_collect_guid_differ_is_loud_mismatch_not_blocked(monkeypatch, migrated_db_path):
    code, art, flashes, learn = _run_collect(
        monkeypatch, result=_ai_result(), declared_guid="DECLARED-AAAA",
        probe=_probe_identity(_GUID.lower()),
    )
    assert code == 302                        # not blocked
    assert art.source.verification_status == "mismatch"
    assert "MISMATCH" in flashes              # loud
    assert learn == []                        # set-once: never overwrite on mismatch


def test_collect_tofu_learns_when_unset_and_verdict_is_attested(monkeypatch, migrated_db_path):
    """First connect with unset declared GUID: TOFU records it for NEXT time, and
    THIS collect is attested (we had nothing to verify against — the false 337f-vs-2
    banner is GONE)."""
    code, art, flashes, learn = _run_collect(
        monkeypatch, result=_ai_result(), declared_guid=None, probe=_probe_identity(_GUID.lower()),
    )
    assert code == 302
    assert art.source.verification_status == "attested"
    assert "MISMATCH" not in flashes
    assert learn == [("c", _GUID.lower())]    # learned for next time


def test_collect_probe_failure_falls_back_to_attested(monkeypatch, migrated_db_path):
    code, art, flashes, learn = _run_collect(
        monkeypatch, result=_ai_result(), declared_guid=_GUID, probe=_probe_raises,
    )
    assert code == 302
    assert art.source.verification_status == "attested"
    assert "MISMATCH" not in flashes
    assert learn == []


def test_collect_after_tofu_is_verified(monkeypatch, migrated_db_path):
    """The 'after one connect' state: declared GUID now matches the wire -> verified."""
    code, art, flashes, learn = _run_collect(
        monkeypatch, result=_ai_result(), declared_guid=_GUID.lower(),
        probe=_probe_identity(_GUID.lower()),
    )
    assert art.source.verification_status == "verified"
