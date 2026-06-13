"""ADR-0017 LS recipe — first parity SIGNAL (not green).

Confirms the generic recipe publishes through the compile gate, the generic
candidate produces an artifact for every fixture, and the generic-vs-bespoke
comparison runs over the corpus. The pass/fail breakdown is the report
deliverable (read together before any fix); these tests pin the machinery, not
green parity.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

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
from cvhealthcheck.extractors.html import HTMLExtractor

from ls_generic_recipe import (
    GENERIC_SUBJECT_ID,
    _OBSERVED_SECTION,
    _enrich_commcell_info,
    generic_candidate,
    publish_ls_recipe,
    run_signal,
)
from ls_parity_harness import bespoke_canonical, discover_ls_fixtures

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _art_with_observed(observed_row):
    sections = []
    if observed_row is not None:
        sections.append(TableSection(
            type="table", id=_OBSERVED_SECTION, title="obs",
            columns=[TableColumn(id=k, label=k) for k in observed_row],
            items=[observed_row]))
    return CanonicalArtifact(
        artifact_type="x", generated_at=_NOW,
        source=ArtifactSource(type=SourceType.html_import),
        subject=ArtifactSubject(id="license_summary_generic", title="LS"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=[]),
        sections=sections)


def _commcell_info(artifact):
    ci = [s for s in artifact.sections if s.id == "commcell_info"]
    return {it.id: it.value for it in ci[0].items} if ci else None

_TABLE_AND_WORKLOAD_HTML = (
    "<html><body>"
    '<div><div class="reportstabletitle">Other Licenses - current usage details</div>'
    "<table><thead><tr><th>License</th><th>Available Total</th><th>Used</th></tr></thead>"
    "<tbody><tr><td>HyperScale</td><td>25 TB</td><td>10 TB</td></tr></tbody></table></div>"
    '<div><div class="reportstabletitle">Other Licenses</div>'
    "<table><thead><tr><th>License</th><th>Available Total</th><th>Summary</th></tr></thead>"
    "<tbody><tr><td>WL1</td><td>5</td><td>ok</td></tr></tbody></table></div>"
    "</body></html>"
)
_WORKLOAD_ONLY_HTML = (
    "<html><body>"
    '<div><div class="reportstabletitle">Other Licenses</div>'
    "<table><thead><tr><th>License</th><th>Available Total</th><th>Summary</th></tr></thead>"
    "<tbody><tr><td>WL1</td><td>5</td><td>ok</td></tr></tbody></table></div>"
    "</body></html>"
)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_ls_recipe_publishes_through_compile_gate(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        created = publish_ls_recipe(conn)  # raises ProposalCompileError if rejected
        assert created["subject_id"] == GENERIC_SUBJECT_ID
    finally:
        conn.close()


def test_generic_candidate_runs_over_corpus_and_signal_is_produced(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        signal = run_signal(conn)
    finally:
        conn.close()
    # The generic candidate produced a CanonicalArtifact for every fixture (no crashes).
    assert signal["candidate_errors"] == []
    # ADR-0017: unit fields are actively compared (no quarantine left).
    assert signal["totals"]["pending"] == 0
    # The comparison ran and produced real pass results (sections that match).
    assert signal["totals"]["pass"] > 0
    # First-signal slice — genuine differences exist and are reported, not hidden.
    assert signal["totals"]["fail"] > 0
    assert len(signal["failure_classes"]) > 0


# ── "Other Licenses" disambiguation — the recipe matches the table by full title ─

def test_other_licenses_table_matched_by_full_title_not_workload(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        html_path = migrated_db_path.parent / "both.html"
        html_path.write_text(_TABLE_AND_WORKLOAD_HTML, encoding="utf-8")
        result = HTMLExtractor(conn).extract(html_path, GENERIC_SUBJECT_ID)
    finally:
        conn.close()
    rows = result.sections.get("other_licenses")
    # the TABLE (full title) is extracted, not the bare-"Other Licenses" workload
    assert rows and rows[0]["license"] == "HyperScale"
    assert rows[0]["available_total"] == {"value": 25, "unit": "TB"}


def test_other_licenses_bare_workload_not_grabbed_as_table(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        html_path = migrated_db_path.parent / "wl.html"
        html_path.write_text(_WORKLOAD_ONLY_HTML, encoding="utf-8")
        result = HTMLExtractor(conn).extract(html_path, GENERIC_SUBJECT_ID)
    finally:
        conn.close()
    # full-title table absent → generic does NOT mis-grab the workload as a
    # degenerate other_licenses table (the pre-fix bug)
    assert not result.sections.get("other_licenses")


# ── D2 — commcell_info mixed-source enrichment ───────────────────────────────

def test_d2_context_identity_beats_evidence():
    art = _art_with_observed({"commcell_name": "CommServe A", "commcell_version": "11.40"})
    out = _enrich_commcell_info(art, {"commserve_name": "DeclaredCS"})
    ci = _commcell_info(out)
    assert ci["commcell_name"] == "DeclaredCS"        # context > evidence
    assert ci["commcell_version"] == "11.40"           # observational from evidence
    assert all(s.id != _OBSERVED_SECTION for s in out.sections)  # staging consumed


def test_d2_evidence_name_when_no_context():
    art = _art_with_observed({"commcell_name": "CommServe A"})
    ci = _commcell_info(_enrich_commcell_info(art, None))
    assert ci["commcell_name"] == "CommServe A"        # evidence > placeholder


def test_d2_placeholder_when_no_context_no_evidence():
    art = _art_with_observed(None)
    ci = _commcell_info(_enrich_commcell_info(art, None))
    assert ci == {"commcell_name": "Unknown CommCell"}  # placeholder only


def test_d2_observational_from_evidence_na_preserved():
    art = _art_with_observed({
        "commcell_version": "11.40.47", "license_expiry": "N/A",
        "last_collection": "May 27, 2026, 12:00:00 AM"})
    ci = _commcell_info(_enrich_commcell_info(art, None))
    assert ci["commcell_version"] == "11.40.47"
    assert ci["license_expiry"] == "N/A"               # not null-coerced
    assert ci["last_collection"] == "May 27, 2026, 12:00:00 AM"
    assert ci["commcell_name"] == "Unknown CommCell"


def test_d2_end_to_end_commcell_info_matches_bespoke(migrated_db_path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        target = next(
            p for p in discover_ls_fixtures()
            if any(s.id == "commcell_info" and len(s.items) >= 4
                   for s in bespoke_canonical(p).sections)
        )
        gen = generic_candidate(target, conn)
        bes = bespoke_canonical(target)
    finally:
        conn.close()
    assert _commcell_info(gen) == _commcell_info(bes)
