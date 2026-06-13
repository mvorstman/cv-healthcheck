"""ADR-0016 License-Summary parity harness — tests.

Proves (1) the real-export corpus is discovered, (2) the current bespoke pipeline
produces a CanonicalArtifact for every fixture, (3) the semantic comparator is
reflexive on bespoke-vs-bespoke AND genuinely detects differences / quarantines
unit fields / flags unmasked sensitive values (so the green run is meaningful,
not vacuous), and (4) the candidate seam is pluggable.

Harness only — no transform layer, no LS conversion, no bespoke deletion.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    SummaryMetric,
    TableColumn,
    TableSection,
)

from ls_parity_harness import (  # sibling module (tests/ is on sys.path)
    Outcome,
    bespoke_canonical,
    bespoke_candidate,
    compare_artifacts,
    discover_ls_fixtures,
    fixture_format,
    run_baseline,
)

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)

# The ADR-0016 acceptance corpus = DISTINCT real exports (discover_ls_fixtures
# dedups byte-identical re-uploads and drops the 5 named titleless fixtures). Pin
# the distinct count so any genuine corpus change is a deliberate, reviewed event.
# 9 distinct = 7 LS-bearing exports + 2 non-LS (a stray Security-Assessment HTML +
# the cv_redesign mock, which carry no LS rows and are filtered by run_signal).
EXPECTED_CORPUS = 9
EXPECTED_CSV = 3
EXPECTED_HTML = 6


def _table_artifact(rows: list[dict], *, other_count: int = 0) -> CanonicalArtifact:
    return CanonicalArtifact(
        artifact_type="license_summary",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="license_summary", title="License Summary"),
        summary=ArtifactSummary(
            status=ArtifactStatus.good,
            metrics=[SummaryMetric(id="other_license_count", label="Other", value=other_count)],
        ),
        sections=[
            TableSection(
                type="table", id="other_licenses", title="Other Licenses",
                columns=[
                    TableColumn(id="license", label="License"),
                    TableColumn(id="permanent_total", label="Permanent Total"),
                    TableColumn(id="used", label="Used"),
                    TableColumn(id="registration_code", label="Reg"),
                ],
                items=rows,
            ),
        ],
    )


# ── deliverable 1: fixture discovery ─────────────────────────────────────────

def test_fixture_discovery_count_and_formats():
    fixtures = discover_ls_fixtures()
    assert len(fixtures) == EXPECTED_CORPUS, (
        f"ADR-0016 acceptance corpus drifted: found {len(fixtures)}, expected "
        f"{EXPECTED_CORPUS}. Update EXPECTED_CORPUS deliberately if the corpus changed."
    )
    assert all(fixture_format(p) in ("csv", "html") for p in fixtures)
    assert sum(1 for p in fixtures if fixture_format(p) == "csv") == EXPECTED_CSV
    assert sum(1 for p in fixtures if fixture_format(p) == "html") == EXPECTED_HTML


# ── deliverable 3: baseline — bespoke produces a CanonicalArtifact for each ───

def test_baseline_bespoke_produces_canonical_for_every_fixture():
    results = run_baseline(discover_ls_fixtures())
    parse_errors = [(r.file, r.error) for r in results if not r.produced]
    assert parse_errors == [], f"bespoke parse failures (corpus finding): {parse_errors}"
    assert all(r.produced for r in results)
    # Corpus finding (documented, not a failure): a few files carry no LS license
    # rows — two stray Security-Assessment HTML exports + the cv_redesign mock.
    license_bearing = [r for r in results if r.license_rows > 0]
    assert len(license_bearing) >= EXPECTED_CORPUS - 3


# ── deliverable 2: comparator is reflexive on bespoke-vs-bespoke ──────────────

def test_comparator_reflexive_no_failures_across_corpus():
    for path in discover_ls_fixtures():
        base = bespoke_canonical(path)
        cand = bespoke_candidate(path)
        report = compare_artifacts(path.name, base, cand)
        assert report.ok, (
            f"unexpected parity FAILs for {path.name}:\n"
            + "\n".join(r.as_row() for r in report.failed)
        )


def test_corpus_comparison_no_fail_and_pending_dropped():
    # ADR-0017 D1: unit/value fields are now actively compared (no longer
    # quarantined), so PENDING-UNIT has dropped to zero while pass/fail stays
    # honest (reflexive bespoke-vs-bespoke → all pass, no fail).
    total_pass = total_pending = total_fail = 0
    for path in discover_ls_fixtures():
        report = compare_artifacts(
            path.name, bespoke_canonical(path), bespoke_candidate(path)
        )
        total_pass += len(report.passed)
        total_pending += len(report.pending)
        total_fail += len(report.failed)
    assert total_fail == 0
    assert total_pass > 0
    assert total_pending == 0  # D1 lifted the unit fields out of PENDING-UNIT


# ── the comparator genuinely detects differences (green is meaningful) ────────

def test_comparator_detects_value_difference():
    a = _table_artifact([{"license": "L1", "permanent_total": 5}])
    b = _table_artifact([{"license": "L1", "permanent_total": 9}])
    report = compare_artifacts("f", a, b)
    assert any(
        r.field == "permanent_total" and r.outcome is Outcome.FAIL for r in report.failed
    )


def test_comparator_detects_missing_section():
    a = _table_artifact([{"license": "L1", "permanent_total": 5}])
    b = a.model_copy(update={"sections": []})
    report = compare_artifacts("f", a, b)
    assert any(r.outcome is Outcome.FAIL for r in report.failed)


def test_comparator_detects_summary_count_difference():
    a = _table_artifact([{"license": "L1", "permanent_total": 5}], other_count=2)
    b = _table_artifact([{"license": "L1", "permanent_total": 5}], other_count=9)
    report = compare_artifacts("f", a, b)
    assert any(
        r.section == "summary" and r.field == "other_license_count"
        and r.outcome is Outcome.FAIL
        for r in report.failed
    )


# ── ADR-0017 D1: unit/value fields are now ACTIVELY compared (not quarantined) ─

def test_comparator_unit_value_actively_compared_and_fails_on_difference():
    a = _table_artifact([{"license": "L1", "used": 5}])
    b = _table_artifact([{"license": "L1", "used": 9}])  # genuinely differs
    report = compare_artifacts("f", a, b)
    assert not report.pending, "unit fields are no longer quarantined (D1)"
    assert any(
        r.field == "used" and r.outcome is Outcome.FAIL for r in report.failed
    ), "a differing unit value must now FAIL (actively compared)"


# ── sensitive-field masking enforced on both sides ───────────────────────────

def test_comparator_fails_when_sensitive_value_is_raw():
    raw = _table_artifact([{"license": "L1", "registration_code": "ABCD12345678WXYZ"}])
    masked = _table_artifact([{"license": "L1", "registration_code": "ABCD********WXYZ"}])
    report = compare_artifacts("f", raw, masked)  # expected side carries a RAW code
    assert any(
        r.field == "registration_code" and r.outcome is Outcome.FAIL
        for r in report.failed
    ), "a raw (unmasked) sensitive value must FAIL, not pass"


def test_comparator_passes_when_both_sides_masked_and_equal():
    m1 = _table_artifact([{"license": "L1", "registration_code": "ABCD********WXYZ"}])
    m2 = _table_artifact([{"license": "L1", "registration_code": "ABCD********WXYZ"}])
    report = compare_artifacts("f", m1, m2)
    reg = [r for r in report.results if r.field == "registration_code"]
    assert reg and all(r.outcome is Outcome.PASS for r in reg)


# ── deliverable 4: the candidate seam is pluggable ───────────────────────────

def test_candidate_seam_is_pluggable_and_detects_divergence():
    """The future generic candidate plugs into compare_artifacts as the second
    arg. A degraded candidate (a row dropped) must be detected — proving the
    comparator is not wired to always agree with bespoke."""
    fixtures = discover_ls_fixtures()
    target = next(
        (p for p in fixtures if len(bespoke_canonical(p).sections) >= 1
         and any(getattr(s, "items", []) for s in bespoke_canonical(p).sections)),
        None,
    )
    assert target is not None, "expected at least one fixture with section items"
    base = bespoke_canonical(target)
    # Drop the last row of the first non-empty table section.
    degraded = base.model_copy(deep=True)
    for sec in degraded.sections:
        if getattr(sec, "type", None) == "table" and sec.items:
            sec.items.pop()
            break
    report = compare_artifacts(target.name, base, degraded)
    assert report.failed, "dropping a candidate row must be detected as a FAIL"
