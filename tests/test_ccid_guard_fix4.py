"""Fix 4 — the pure declared-vs-wire CommCell ID verdict function.

`verify_commcell_id` is retained (its ladder is unchanged) but it is NO LONGER
the identity verdict driver: the namespace-precision fix moved the stamped verdict
to the CommServe csGUID (see test_csguid_comparand_fix4) because the CCID compare
was cross-namespace (declared LICENSED `337f` vs wire INTERNAL `2`) and
false-mismatched the legitimate customer. These tests pin the pure function's
ladder; the integration section below pins that the declared CCID is now
DISPLAYED-not-verified provenance.

Four verdicts, attested ≠ unverifiable (never merged):
  verified     both present, normalized-equal
  mismatch     both present, differ
  attested     declared present; the source offered NO wire identity
  unverifiable declared absent/un-normalizable — nothing to compare against
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.identity import verify_commcell_id

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


# ── pure verdict function (ladder unchanged; no longer the verdict driver) ────

def test_equal_is_verified():
    v = verify_commcell_id("337f", 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "verified"


def test_differ_is_mismatch():
    v = verify_commcell_id("337f", 2,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "mismatch"


def test_declared_none_is_unverifiable():
    v = verify_commcell_id(None, 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "unverifiable"


def test_declared_unnormalizable_is_unverifiable():
    v = verify_commcell_id("SMOKE-TEST-CS", 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "unverifiable"


def test_no_wire_value_is_attested():
    v = verify_commcell_id("337f", None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "attested"


def test_wire_missing_is_attested_not_unverifiable():
    attested = verify_commcell_id("337f", None, now=_NOW)
    unverifiable = verify_commcell_id(None, 13183, now=_NOW)
    assert attested["verification_status"] == "attested"
    assert unverifiable["verification_status"] == "unverifiable"


def test_attested_and_unverifiable_are_distinct():
    attested = verify_commcell_id("337f", None, now=_NOW)
    unverifiable = verify_commcell_id(None, None, now=_NOW)
    assert attested["verification_status"] == "attested"
    assert unverifiable["verification_status"] == "unverifiable"
    assert attested["verification_status"] != unverifiable["verification_status"]


def test_no_false_mismatch_hex_vs_decimal_int():
    v = verify_commcell_id("337f", 13183, now=_NOW)
    assert v["verification_status"] == "verified"      # hex declared == decimal wire int


def test_no_false_mismatch_case():
    v = verify_commcell_id("337F", "337f", now=_NOW)
    assert v["verification_status"] == "verified"


def test_both_normalized_inputs_are_persisted():
    v = verify_commcell_id("337F", 2,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert "337f" in v["verification_notes"]
    assert "2" in v["verification_notes"]
    assert "declared_normalized" in v["verification_notes"]
    assert "wire_normalized" in v["verification_notes"]
    assert v["verification_sources"] == ["commserv:commcell.commCellId"]
    assert v["verified_at"] == _NOW


def test_sources_empty_when_no_wire_value():
    v = verify_commcell_id("337f", None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_sources"] == []


def test_unparseable_inputs_record_none_in_notes():
    v = verify_commcell_id(None, None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert "declared_normalized=none" in v["verification_notes"]
    assert "wire_normalized=none" in v["verification_notes"]


# ── integration through result_to_artifact ────────────────────────────────────
# The stamped identity verdict is now GUID-driven (test_csguid_comparand_fix4);
# the declared CommCell ID is retained as DISPLAYED-not-verified PROVENANCE on the
# source and no longer drives the verdict. These pin that contract — including
# that the old false-mismatch source (a wire internal commCellId in the card) no
# longer produces a verdict.

def _cc_api_result(commcell_id_value):
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    record = {"commcell": {"commCellName": "cs01", "commCellId": commcell_id_value}}
    res.sections["environment.metadata"] = [record]
    res.section_output_types["environment.metadata"] = "card"
    res.section_card_specs["environment.metadata"] = {"items": []}
    res.section_titles["environment.metadata"] = "Metadata"
    return res


def test_declared_ccid_is_provenance_not_verdict():
    """The licensed CCID lands on source.commcell_id (provenance) but does NOT
    drive the verdict — with no GUID comparand the verdict is attested, even
    though a wire commCellId (the old false-mismatch source) is in the card."""
    artifact = result_to_artifact(
        _cc_api_result(2), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    assert artifact.source.commcell_id == "337f"               # provenance kept
    assert artifact.source.verification_status == "attested"   # CCID does not drive


def test_non_identity_endpoint_is_attested():
    res = ExtractionResult(subject_id="server_groups", source_type="rest_command_center_api")
    res.sections["server_groups.list"] = [{"name": "sg1"}, {"name": "sg2"}]
    res.section_output_types["server_groups.list"] = "table"
    res.section_titles["server_groups.list"] = "Server Groups"
    artifact = result_to_artifact(
        res, subject_id="server_groups", subject_title="Server Groups",
        commcell_id="337f",
    )
    assert artifact.source.verification_status == "attested"


def test_csv_import_is_attested():
    res = ExtractionResult(subject_id="capacity_license", source_type="csv")
    res.sections["rows"] = [{"month": "2026-05"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    artifact = result_to_artifact(
        res, subject_id="capacity_license", subject_title="Cap", commcell_id="337f",
    )
    assert artifact.source.verification_status == "attested"


def test_guid_verdict_persists_and_writes_only_artifact_source(tmp_path):
    """ON MISMATCH the artifact is still assembled AND persists (never-block), and
    the verdict lives ONLY on source — not subject/summary/sections."""
    res = _cc_api_result(2)
    res.wire_commserve_guid = "bbbb"
    res.wire_commserve_guid_source = "session:commserv.csGUID"
    artifact = result_to_artifact(
        res, subject_id="environment", subject_title="Env",
        commcell_id="337f", commserve_guid="aaaa",       # differ -> mismatch
    )
    assert artifact.source.verification_status == "mismatch"
    store = ArtifactStore("c", "p", base_dir=tmp_path / "s")
    store.save_artifact(artifact)
    loaded = store.load_latest_artifact("environment")
    assert loaded.source.verification_status == "mismatch"
    assert loaded.source.verification_sources == ["session:commserv.csGUID"]

    payload = artifact.model_dump(mode="json")
    assert payload["source"]["verification_status"] == "mismatch"
    assert "verification_status" not in payload.get("subject", {})
    assert "verification_status" not in payload.get("summary", {})
    assert all("verification_status" not in s for s in payload.get("sections", []))
