"""ADR-0017 D2 (commit 2) — commcell_info enrichment at the LIVE result_to_artifact seam.

Covers the load-bearing gates:
  - GATE 4: result_to_artifact stays CALLER-FED — it assembles commcell_info from
    its params only, with NO db / session / active-context lookup.
  - GATE 5: non-LS artifacts pass through byte-unchanged (enrichment is additive
    and only fires when the recipe's staging section is present).
  - the placeholder-as-absence precedence (ADR-0017 D2 clarification).
"""
from __future__ import annotations

from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    TableColumn,
    TableSection,
)
from cvhealthcheck.extractors.commcell_enrich import (
    COMMCELL_OBSERVED_SECTION,
    enrich_commcell_info,
)
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

_NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)


def _artifact(sections) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="x", generated_at=_NOW,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id="x", title="X"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=sections,
    )


def _observed(row: dict | None) -> TableSection:
    keys = list(row) if row else ["commcell_name"]
    return TableSection(
        type="table", id=COMMCELL_OBSERVED_SECTION, title="obs",
        columns=[TableColumn(id=k, label=k) for k in keys],
        items=[row] if row is not None else [],
    )


def _commcell_info(artifact: CanonicalArtifact):
    ci = [s for s in artifact.sections if s.id == "commcell_info"]
    return {it.id: it.value for it in ci[0].items} if ci else None


# ── enrich() unit behavior ───────────────────────────────────────────────────

def test_real_context_beats_evidence():
    out = enrich_commcell_info(_artifact([_observed({"commcell_name": "CommServe A"})]), "DeclaredCS")
    assert _commcell_info(out)["commcell_name"] == "DeclaredCS"


def test_placeholder_context_is_absence_evidence_wins():
    # "Unknown CommCell" is the placeholder — NOT authoritative; evidence beats it.
    out = enrich_commcell_info(_artifact([_observed({"commcell_name": "CommServe A"})]), "Unknown CommCell")
    assert _commcell_info(out)["commcell_name"] == "CommServe A"


def test_placeholder_only_when_no_context_no_evidence():
    out = enrich_commcell_info(_artifact([_observed(None)]), None)
    assert _commcell_info(out) == {"commcell_name": "Unknown CommCell"}


def test_observational_from_evidence_na_preserved():
    out = enrich_commcell_info(
        _artifact([_observed({"commcell_version": "11.40.47", "license_expiry": "N/A",
                              "last_collection": "May 27, 2026, 12:00:00 AM"})]),
        None,
    )
    ci = _commcell_info(out)
    assert ci["commcell_version"] == "11.40.47"
    assert ci["license_expiry"] == "N/A"  # not null-coerced (null_values=[] upstream)
    assert ci["last_collection"] == "May 27, 2026, 12:00:00 AM"


# ── GATE 5: non-LS artifact byte-unchanged (no staging → SAME object) ─────────

def test_non_ls_artifact_passes_through_unchanged_same_object():
    art = _artifact([TableSection(
        type="table", id="some_table", title="t",
        columns=[TableColumn(id="a", label="a")], items=[{"a": "1"}])])
    out = enrich_commcell_info(art, "DeclaredCS")  # context fed, but no staging section
    assert out is art  # same object → byte-identical
    assert all(s.id != "commcell_info" for s in out.sections)


# ── GATE 4: result_to_artifact assembles commcell_info CALLER-FED (no db/session) ─

def test_result_to_artifact_assembles_commcell_info_caller_fed():
    er = ExtractionResult(subject_id="license_summary", source_type="html")
    er.sections[COMMCELL_OBSERVED_SECTION] = [
        {"commcell_name": "Evidence CS", "commcell_version": "11.40"}]
    er.section_output_types[COMMCELL_OBSERVED_SECTION] = "table"
    er.section_titles[COMMCELL_OBSERVED_SECTION] = "obs"

    # ONLY params — no db, no session, no active-context lookup anywhere.
    artifact = result_to_artifact(
        er, subject_id="license_summary", subject_title="License Summary",
        commcell_name="DeclaredCS",
    )

    ci = _commcell_info(artifact)
    assert ci["commcell_name"] == "DeclaredCS"   # caller-fed identity wins
    assert ci["commcell_version"] == "11.40"     # observational from evidence
    assert all(s.id != COMMCELL_OBSERVED_SECTION for s in artifact.sections)  # staging consumed


def test_result_to_artifact_evidence_name_when_no_context():
    er = ExtractionResult(subject_id="license_summary", source_type="html")
    er.sections[COMMCELL_OBSERVED_SECTION] = [{"commcell_name": "Evidence CS"}]
    er.section_output_types[COMMCELL_OBSERVED_SECTION] = "table"
    er.section_titles[COMMCELL_OBSERVED_SECTION] = "obs"
    artifact = result_to_artifact(
        er, subject_id="license_summary", subject_title="License Summary")  # no commcell_name
    assert _commcell_info(artifact)["commcell_name"] == "Evidence CS"


def test_result_to_artifact_non_ls_has_no_commcell_info():
    # No staging section → no enrichment, even with context fed (GATE 5 via the seam).
    er = ExtractionResult(subject_id="some_other", source_type="html")
    er.sections["some_other.table"] = [{"a": "1"}]
    er.section_output_types["some_other.table"] = "table"
    er.section_titles["some_other.table"] = "T"
    artifact = result_to_artifact(
        er, subject_id="some_other", subject_title="Other", commcell_name="DeclaredCS")
    assert all(s.id != "commcell_info" for s in artifact.sections)
