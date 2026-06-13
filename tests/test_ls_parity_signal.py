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
from ls_parity_harness import (
    EXCLUDED_SYNTHETIC_FIXTURES,
    LS_FIXTURE_DIR,
    bespoke_canonical,
    discover_ls_fixtures,
)

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

# Sample-style layout: section titles in classless <h2> siblings of their tables
# (no .reportstabletitle wrapper). The two tables are siblings under <body>, so a
# naive "walk up to a common ancestor" mis-assigns the second section to the first
# table — the title must label the table that FOLLOWS it.
_H2_SIBLING_HTML = (
    "<html><body>"
    "<h1>License summary</h1>"
    "<h2>Other Licenses - current usage details</h2>"
    "<table><thead><tr><th>License</th><th>Available Total</th><th>Used</th></tr></thead>"
    "<tbody><tr><td>Deduplication</td><td>25 TB</td><td>10 TB</td></tr></tbody></table>"
    "<h2>Agent and Feature Licenses - current usage details</h2>"
    "<table><thead><tr><th>License</th><th>Permanent Total</th><th>Permanent Used</th>"
    "<th>Term Total</th><th>Term Used</th><th>Client</th><th>Agent</th><th>Install Date</th>"
    "</tr></thead>"
    "<tbody><tr><td>Database</td><td>25</td><td>8</td><td>5</td><td>2</td>"
    "<td>Client B</td><td>Agent B</td><td>2026-04-15</td></tr></tbody></table>"
    "</body></html>"
)
# A bare, untitled table (no .reportstabletitle, no <h2>) — the extension broadens
# WHERE a title may live, it does NOT match untitled tables by header shape.
_TITLELESS_TABLE_HTML = (
    "<html><body>"
    "<table><thead><tr><th>License</th><th>Available Total</th><th>Used</th></tr></thead>"
    "<tbody><tr><td>SomeLicense</td><td>10</td><td>5</td></tr></tbody></table>"
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
    # ADR-0017 residual (b): the 5 named titleless fixtures are scoped out, so the
    # parity corpus is GREEN — every remaining (real-export) fail must be zero.
    assert signal["totals"]["fail"] == 0


# ── ADR-0017 residual (b): the named titleless-fixture scope-out is intentional ──

def test_excluded_synthetic_fixtures_exist_on_disk_but_are_scoped_out():
    """Each named exclusion is a REAL file on disk (the list is not stale) and is
    EXACTLY the titleless classifier shape (no .reportstabletitle, no <h2>) — the
    documented basis for excluding it — and is omitted from the discovered corpus.
    This pins the scope-out as an explicit, per-file, classified decision — not a
    broad "drop untitled files" rule."""
    from bs4 import BeautifulSoup

    discovered = {p.name for p in discover_ls_fixtures()}
    assert EXCLUDED_SYNTHETIC_FIXTURES, "the named exclusion list must not be empty"
    for name in EXCLUDED_SYNTHETIC_FIXTURES:
        path = LS_FIXTURE_DIR / name
        assert path.is_file(), f"named exclusion no longer on disk: {name}"
        # classification basis: titleless (no title markup of any kind)
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        assert not soup.select(".reportstabletitle"), f"{name} has .reportstabletitle"
        assert not soup.find_all("h2"), f"{name} has an <h2> title"
        assert name not in discovered, f"{name} should be scoped out of the corpus"


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


# ── <h2> title markup reachable (sample, Case A) — still title-anchored ────────

def test_h2_titled_tables_reached_without_cross_wiring(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        html_path = migrated_db_path.parent / "h2sample.html"
        html_path.write_text(_H2_SIBLING_HTML, encoding="utf-8")
        result = HTMLExtractor(conn).extract(html_path, GENERIC_SUBJECT_ID)
    finally:
        conn.close()
    other = result.sections.get("other_licenses")
    agent = result.sections.get("agent_feature_licenses")
    # both <h2>-titled tables are now reached (present-on-both)
    assert other and other[0]["license"] == "Deduplication"
    assert other[0]["available_total"] == {"value": 25, "unit": "TB"}
    # the agent <h2> resolves to ITS following table, not the first table under
    # <body> (no cross-wiring): a permanent_total field, not an other-licenses one
    assert agent and agent[0]["license"] == "Database"
    assert agent[0]["permanent_total"] == 25
    assert "available_total" not in agent[0]


def test_h2_extension_does_not_match_titleless_table(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        publish_ls_recipe(conn)
        html_path = migrated_db_path.parent / "titleless.html"
        html_path.write_text(_TITLELESS_TABLE_HTML, encoding="utf-8")
        result = HTMLExtractor(conn).extract(html_path, GENERIC_SUBJECT_ID)
    finally:
        conn.close()
    # the extension broadens WHERE a title may live (now also <h2>); it does NOT
    # match a bare, untitled table by header shape (no header-shape reach).
    assert not result.sections.get("other_licenses")


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
