"""Fix 4 — session-level wire CCID comparand for live CC-API collects.

A live CC-API collect runs against a real CommServe session, but only the
environment/CommCell-Details card hits /CommServ and self-reports its
``commcell.commCellId``. Every other CC-API subject (clients, users,
storage_policies, …) hits a non-identity endpoint, so its records carry no
identity and the Fix-4 verify would fall to "attested" — silently masking a
wrong-customer connection.

This slice probes the session's CommServ identity ONCE and supplies it as the
wire id when (and only when) the subject's own endpoint carried none, turning
attested into a real verified/mismatch. Endpoint-carried identity stays
authoritative (the environment card is unchanged); a probe failure falls back to
attested and never blocks (ADR-0008: current session token only, no mint).

These tests drive the real /quick-hc/<subject>/collect route with a faked
extractor + store + session probe. The subject_id only needs to exist in the
migrated catalog (we use "environment"); the *result* the faked extractor
returns is what drives the verdict — exactly the pattern in
test_ccid_guard_surfacing_fix4.py.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.extractors.html import ExtractionResult


# --- result shapes -------------------------------------------------------

def _ai_subject_result():
    """A live CC-API *table* collect whose records carry NO commcell identity —
    the AI-subject shape (/Client, /v2/storagepolicy, /v4/user …)."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["client_list"] = [{"clientName": "h1"}, {"clientName": "h2"}]
    res.section_output_types["client_list"] = "table"
    res.section_titles["client_list"] = "Clients"
    return res


def _environment_card_result(wire_value):
    """The bespoke environment subject: a *card* whose rows[0] IS the /CommServ
    identity payload, self-reporting commcell.commCellId."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    res.sections["environment.metadata"] = [
        {"commcell": {"commCellName": "cs01", "commCellId": wire_value}}
    ]
    res.section_output_types["environment.metadata"] = "card"
    res.section_card_specs["environment.metadata"] = {"items": []}
    res.section_titles["environment.metadata"] = "Metadata"
    return res


def _probe_returning(commcell_id_value):
    """A get_commcell_identity stand-in returning a CommServ payload whose
    raw.commcell.commCellId is ``commcell_id_value``."""
    def _probe(*a, **k):
        return {
            "collected_at": None, "source": None, "http_status": 200, "ok": True,
            "identity": {}, "raw": {"commcell": {"commCellId": commcell_id_value}},
            "error": None,
        }
    return _probe


def _probe_raising(*a, **k):
    raise RuntimeError("token expired / endpoint down")


def _probe_no_identity(*a, **k):
    """A reachable probe whose payload carries no commCellId (401 / error body)."""
    return {"http_status": 401, "ok": False, "raw": {"error": "unauthorized"}, "error": "401"}


# --- driver --------------------------------------------------------------

def _run_collect(monkeypatch, *, result, declared_ccid, probe):
    """POST /quick-hc/environment/collect with a faked extractor, store, and
    session probe. Returns (status_code, saved_artifact_or_None, flashes_str)."""
    from cvhealthcheck.web.app import create_app
    import cvhealthcheck.web.routes.quick_hc as route_module

    saved: dict = {}

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact): saved["a"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return result

    monkeypatch.setattr(route_module, "get_active_customer", lambda *a, **k: {
        "customer_id": "c", "customer_name": "Acme",
        "connection_url": "https://h:4433", "commcell_hostname": None,
        "commserve_name": "CS01", "commcell_id": declared_ccid,
    })
    monkeypatch.setattr(route_module, "is_authenticated_for", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "_current_token", lambda *a, **k: "t")
    monkeypatch.setattr(route_module, "_has_command_center_source", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "CommandCenterExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "ArtifactStore", FakeStore)
    monkeypatch.setattr(route_module, "get_commcell_identity", probe)

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    resp = client.post("/quick-hc/environment/collect")
    with client.session_transaction() as sess:
        flashes = " | ".join(str(m) for _, m in sess.get("_flashes", []))
    return resp.status_code, saved.get("a"), flashes


# --- tests ---------------------------------------------------------------

def test_ai_subject_session_wire_equals_declared_is_verified(monkeypatch, migrated_db_path):
    """A non-identity AI-subject collect whose session probe matches the
    declared CCID is now VERIFIED (was attested before this slice)."""
    code, art, flashes = _run_collect(
        monkeypatch,
        result=_ai_subject_result(),
        declared_ccid="337f",          # normalizes to 337f
        probe=_probe_returning(13183),  # decimal 13183 == hex 337f
    )
    assert code == 302
    assert art.source.verification_status == "verified"
    assert art.source.verification_sources == ["session:commserv.commCellId"]
    assert "verified against the source" in flashes


def test_ai_subject_session_wire_differs_is_loud_mismatch_but_not_blocked(monkeypatch, migrated_db_path):
    """The wrong-customer case (declared 19417 == 4bd9 vs wire 337f): MISMATCH,
    evidence STILL written (never-block), surfaced as the loud banner."""
    code, art, flashes = _run_collect(
        monkeypatch,
        result=_ai_subject_result(),
        declared_ccid="19417",          # decimal -> hex 4bd9
        probe=_probe_returning(13183),   # -> hex 337f
    )
    assert code == 302                                              # not blocked
    assert art is not None                                          # evidence written
    assert art.source.verification_status == "mismatch"
    assert art.source.verification_sources == ["session:commserv.commCellId"]
    assert "declared_normalized=4bd9" in art.source.verification_notes
    assert "wire_normalized=337f" in art.source.verification_notes
    assert "MISMATCH" in flashes                                    # loud


def test_probe_failure_falls_back_to_attested_and_does_not_block(monkeypatch, migrated_db_path):
    """A probe that raises must be indistinguishable in safety from today:
    fall back to attested (wire=None), persist, never crash or block."""
    code, art, flashes = _run_collect(
        monkeypatch,
        result=_ai_subject_result(),
        declared_ccid="337f",
        probe=_probe_raising,
    )
    assert code == 302
    assert art.source.verification_status == "attested"
    assert "MISMATCH" not in flashes
    assert "verified against the source" not in flashes  # attested is silent on collect


def test_probe_without_identity_falls_back_to_attested(monkeypatch, migrated_db_path):
    """A reachable probe whose payload carries no commCellId (401 / error body)
    also falls back to attested — never a spurious verdict."""
    code, art, _ = _run_collect(
        monkeypatch,
        result=_ai_subject_result(),
        declared_ccid="337f",
        probe=_probe_no_identity,
    )
    assert code == 302
    assert art.source.verification_status == "attested"
    assert art.source.verification_sources == []


def test_bespoke_environment_card_unchanged_probe_does_not_override(monkeypatch, migrated_db_path):
    """The environment card self-identifies via its own /CommServ read, so the
    session probe must NOT override it (endpoint identity is authoritative). Even
    when the probe would report a DIFFERENT id, the verdict and source stay the
    card's — no double-stamp, no conflict."""
    code, art, _ = _run_collect(
        monkeypatch,
        result=_environment_card_result(13183),  # card wire -> 337f
        declared_ccid="337f",                      # matches the card -> verified
        probe=_probe_returning(48059),             # probe would say abbb — ignored
    )
    assert code == 302
    assert art.source.verification_status == "verified"            # via the card, not the probe
    assert art.source.verification_sources == ["commserv:commcell.commCellId"]
    assert "wire_normalized=337f" in art.source.verification_notes


def test_import_path_stays_attested_unchanged(migrated_db_path):
    """File imports have no session to probe and must stay attested — the probe
    lives only on the collect route, so the import seam (result_to_artifact on an
    html_import result with a declared id and no wire) is unchanged."""
    from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

    res = ExtractionResult(subject_id="license_summary", source_type="html")
    res.sections["other_licenses"] = [{"name": "x"}]
    res.section_output_types["other_licenses"] = "table"
    res.section_titles["other_licenses"] = "Other"
    art = result_to_artifact(
        res, subject_id="license_summary", subject_title="LS", commcell_id="337f",
    )
    assert art.source.verification_status == "attested"
    assert art.source.verification_sources == []
