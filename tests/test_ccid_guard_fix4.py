"""Fix 4 — declared-vs-wire CommCell ID guard (PROVENANCE, not workflow).

The guard compares normalize(declared customer.commcell_id) vs normalize(wire
commcell.commCellId) and records a verdict on ArtifactSource.verification_*.
It NEVER blocks, prompts, or alters collection beyond the stamp — collect
always succeeds; the verdict is evidence.

Import-verification slice (#2 resolver): the per-source resolver decides what
wire value a source can provide; verify_commcell_id only compares. A wire that
resolves to None means the source offered no identity — attested, not
unverifiable.

Four verdicts, attested ≠ unverifiable (never merged):
  verified     both present, normalized-equal
  mismatch     both present, differ
  attested     declared present; the source offered NO wire identity (no proof
               possible) — the normal import case AND non-identity CC-API
               endpoints (server_groups, storage_policies, … carry no CCID)
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


# ── pure verdict function ─────────────────────────────────────────────────────

def test_equal_is_verified():
    v = verify_commcell_id("337f", 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "verified"


def test_differ_is_mismatch():
    v = verify_commcell_id("337f", 2,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "mismatch"


def test_declared_none_is_unverifiable():
    # Nothing declared to compare against — even with a wire value present.
    v = verify_commcell_id(None, 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "unverifiable"


def test_declared_unnormalizable_is_unverifiable():
    # SMOKE-TEST-CS -> normalize None, even with a wire value present.
    v = verify_commcell_id("SMOKE-TEST-CS", 13183,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "unverifiable"


def test_no_wire_value_is_attested():
    # Declared present, the source offered no identity to compare -> attested
    # (no proof possible). This is the normal import case.
    v = verify_commcell_id("337f", None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_status"] == "attested"


def test_wire_missing_is_attested_not_unverifiable():
    """Q3 fix: a wire value that resolves to None is attested, NOT unverifiable
    — the source simply offered no identity. unverifiable is reserved for a
    missing DECLARED value. Keeps the Q3 misclassification closed (non-identity
    CC-API endpoints used to land unverifiable)."""
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
    assert "337f" in v["verification_notes"]            # declared normalized
    assert "2" in v["verification_notes"]               # wire normalized
    assert "declared_normalized" in v["verification_notes"]
    assert "wire_normalized" in v["verification_notes"]
    assert v["verification_sources"] == ["commserv:commcell.commCellId"]
    assert v["verified_at"] == _NOW


def test_sources_empty_when_no_wire_value():
    # No wire value resolved -> nothing was looked at -> no source recorded,
    # even if a source label was offered.
    v = verify_commcell_id("337f", None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert v["verification_sources"] == []


def test_unparseable_inputs_record_none_in_notes():
    v = verify_commcell_id(None, None,
                           wire_source="commserv:commcell.commCellId", now=_NOW)
    assert "declared_normalized=none" in v["verification_notes"]
    assert "wire_normalized=none" in v["verification_notes"]


# ── integration through result_to_artifact (CC-API tier) ──────────────────────

def _cc_api_result(commcell_id_value):
    """A CC-API ExtractionResult whose single card record carries the wire
    commcell.commCellId (the environment shape)."""
    res = ExtractionResult(subject_id="environment", source_type="rest_command_center_api")
    record = {"commcell": {"commCellName": "cs01", "commCellId": commcell_id_value}}
    res.sections["environment.metadata"] = [record]
    res.section_output_types["environment.metadata"] = "card"
    res.section_card_specs["environment.metadata"] = {"items": []}
    res.section_titles["environment.metadata"] = "Metadata"
    return res


def test_cc_api_match_stamps_verified():
    artifact = result_to_artifact(
        _cc_api_result(13183), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    assert artifact.source.verification_status == "verified"
    assert "337f" in artifact.source.verification_notes


def test_cc_api_mismatch_stamps_mismatch_and_still_persists(tmp_path):
    """ON MISMATCH: the artifact is still assembled AND persists — no block."""
    artifact = result_to_artifact(
        _cc_api_result(2), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    assert artifact.source.verification_status == "mismatch"
    # still a complete, persistable artifact
    store = ArtifactStore("c", "p", base_dir=tmp_path / "s")
    store.save_artifact(artifact)
    loaded = store.load_latest_artifact("environment")
    assert loaded.source.verification_status == "mismatch"
    assert loaded.source.verification_sources == ["commserv:commcell.commCellId"]
    assert "declared_normalized=337f" in loaded.source.verification_notes
    assert "wire_normalized=2" in loaded.source.verification_notes


def test_cc_api_declared_none_is_unverifiable():
    artifact = result_to_artifact(
        _cc_api_result(13183), subject_id="environment", subject_title="Env",
        commcell_id=None,
    )
    assert artifact.source.verification_status == "unverifiable"


def test_cc_api_non_identity_endpoint_is_attested():
    """Q3 fix at the integration seam: a CC-API result whose records carry NO
    commcell.commCellId (a non-identity endpoint like server_groups) offers no
    wire identity -> attested, not unverifiable. Before the resolver, the
    source-type-coarse wire_available flag marked every rest_commserve result
    as wire-capable and these landed unverifiable."""
    res = ExtractionResult(subject_id="server_groups", source_type="rest_command_center_api")
    res.sections["server_groups.list"] = [{"name": "sg1"}, {"name": "sg2"}]
    res.section_output_types["server_groups.list"] = "table"
    res.section_titles["server_groups.list"] = "Server Groups"
    artifact = result_to_artifact(
        res, subject_id="server_groups", subject_title="Server Groups",
        commcell_id="337f",
    )
    assert artifact.source.verification_status == "attested"


def test_csv_metrics_is_attested_when_declared_present():
    res = ExtractionResult(subject_id="capacity_license", source_type="csv")
    res.sections["rows"] = [{"month": "2026-05"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    artifact = result_to_artifact(
        res, subject_id="capacity_license", subject_title="Cap", commcell_id="337f",
    )
    assert artifact.source.verification_status == "attested"   # csv carries no identity


# ── extractor-surfaced wire CCID (the #3 resolver seam) ───────────────────────
# HTML metricsCommcellInfo extraction is deferred, but the resolver already
# consults result.wire_commcell_id. These pin the seam so when an extractor
# surfaces a CCID (the deferred #3), result_to_artifact verifies it — including
# the demonstrated wrong-customer case (337f file into a different customer ->
# mismatch).

def test_extractor_surfaced_wire_ccid_verified():
    res = ExtractionResult(subject_id="report", source_type="html")
    res.sections["rows"] = [{"a": "1"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    res.wire_commcell_id = 13183                       # what #3 will surface
    res.wire_commcell_source = "html:metricsCommcellInfo"
    artifact = result_to_artifact(
        res, subject_id="report", subject_title="Report", commcell_id="337f",
    )
    assert artifact.source.verification_status == "verified"
    assert artifact.source.verification_sources == ["html:metricsCommcellInfo"]


def test_extractor_surfaced_wire_ccid_mismatch_is_the_demonstrated_gap():
    # 337f-sourced HTML imported under a customer declared as a different
    # CommCell (here 'f1', != 337f) -> mismatch once #3 surfaces the CCID.
    res = ExtractionResult(subject_id="report", source_type="html")
    res.sections["rows"] = [{"a": "1"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"
    res.wire_commcell_id = "337f"                      # the file's real CommCell
    res.wire_commcell_source = "html:metricsCommcellInfo"
    artifact = result_to_artifact(
        res, subject_id="report", subject_title="Report", commcell_id="f1",
    )
    assert artifact.source.verification_status == "mismatch"
    assert "declared_normalized=f1" in artifact.source.verification_notes
    assert "wire_normalized=337f" in artifact.source.verification_notes


def test_verdict_round_trips_and_writes_only_artifact_source(tmp_path):
    artifact = result_to_artifact(
        _cc_api_result(13183), subject_id="environment", subject_title="Env",
        commcell_id="337f",
    )
    payload = artifact.model_dump(mode="json")
    # the verdict lives ONLY on source — not on subject/summary/sections/metadata
    assert payload["source"]["verification_status"] == "verified"
    assert "verification_status" not in payload.get("subject", {})
    assert "verification_status" not in payload.get("summary", {})
    assert all("verification_status" not in s for s in payload.get("sections", []))
