"""ADR-0017 comparator equivalences in the LS parity harness.

D1 value/unit equivalence, D4/F4 empty≡absent, D6 mask-format-independence,
D4/F3 dedup tolerance — plus guards that the comparator still FAILS on genuine
differences (the equivalences must not make it an always-pass).
"""
from __future__ import annotations

from datetime import datetime, timezone

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

from ls_parity_harness import Outcome, compare_artifacts, unit_value_equal, _unit_token

_NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _table(sid, rows):
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    columns = [TableColumn(id=k, label=k) for k in (keys or ["license"])]
    return TableSection(type="table", id=sid, title=sid, columns=columns, items=rows)


def _artifact(sections, metrics=None):
    return CanonicalArtifact(
        artifact_type="license_summary",
        generated_at=_NOW,
        source=ArtifactSource(type=SourceType.csv_import),
        subject=ArtifactSubject(id="license_summary", title="LS"),
        summary=ArtifactSummary(status=ArtifactStatus.good, metrics=metrics or []),
        sections=sections,
    )


def _count_section(sid, value):
    return _table(sid, [{"value": value}])  # the shape extract_computed emits


# ── D1 — value/unit equivalence (the function) ───────────────────────────────

def test_d1_flat_pair_equals_nested():
    assert unit_value_equal((25, "TB"), {"value": 25, "unit": "TB"})
    assert unit_value_equal((500, None), {"value": 500, "unit": None})


def test_d1_string_flat_equals_nested():
    assert unit_value_equal("500 VMs", {"value": 500, "unit": "VMs"})
    assert unit_value_equal("100", {"value": 100, "unit": None})


def test_d1_different_value_or_unit_not_equal():
    assert not unit_value_equal((25, "TB"), {"value": 30, "unit": "TB"})
    assert not unit_value_equal((25, "TB"), {"value": 25, "unit": "GB"})


# ── D1 — through the comparator (flat bespoke vs nested generic) ──────────────

def test_d1_other_licenses_flat_vs_nested_passes():
    flat = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": 25, "used": 10, "unit": "TB"}])])
    nested = _artifact([_table("other_licenses", [
        {"license": "L1",
         "available_total": {"value": 25, "unit": "TB"},
         "used": {"value": 10, "unit": "TB"}}])])
    report = compare_artifacts("f", flat, nested)
    assert not report.failed
    assert any(r.field == "available_total" and r.outcome is Outcome.PASS
               for r in report.passed)


def test_d1_workload_entitlement_text_vs_nested_passes():
    flat = _artifact([_table("workload", [{"license": "L1", "entitlement_value": "500 VMs"}])])
    nested = _artifact([_table("workload", [
        {"license": "L1", "entitlement_value": {"value": 500, "unit": "VMs"}}])])
    assert not compare_artifacts("f", flat, nested).failed


def test_d1_value_difference_fails():
    flat = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": 25, "unit": "TB"}])])
    nested = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": {"value": 30, "unit": "TB"}}])])
    report = compare_artifacts("f", flat, nested)
    assert any(r.field == "available_total" and r.outcome is Outcome.FAIL
               for r in report.failed)


# ── B2 — unit trailing-token equivalence ─────────────────────────────────────

def test_b2_unit_token_extraction():
    assert _unit_token("source VMs") == "VMs"
    assert _unit_token("target VMs") == "VMs"
    assert _unit_token("VMs") == "VMs"
    assert _unit_token("") is None
    assert _unit_token(None) is None


def test_b2_qualifier_ignored_positive():
    # the qualifier before the unit token is ignored (qualifies quantity, not unit)
    assert unit_value_equal((0, "source VMs"), (0, "VMs"))
    assert unit_value_equal((0, "target VMs"), (0, "VMs"))
    assert unit_value_equal((0, "source VMs"), (0, "target VMs"))


def test_b2_unit_respected_negative():
    # the unit token itself is respected — NOT collapsed
    assert not unit_value_equal((0, "VMs"), (0, "TB"))
    assert not unit_value_equal((0, "VMs"), (0, "users"))
    assert not unit_value_equal((0, "TB"), (0, "users"))


def test_b2_value_still_matters():
    # equal only when BOTH value and trailing token match
    assert not unit_value_equal((0, "VMs"), (5, "source VMs"))
    assert unit_value_equal((5, "VMs"), (5, "source VMs"))


def test_b2_null_empty_unit_safe():
    assert unit_value_equal((0, None), (0, ""))      # both → None token
    assert not unit_value_equal((0, None), (0, "VMs"))


def test_b2_through_comparator_other_licenses():
    # bespoke flat (value + trailing-word unit "VMs") ≡ generic nested with a
    # qualifier-bearing unit "source VMs"
    bespoke = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": 0, "used": 0, "unit": "VMs"}])])
    generic = _artifact([_table("other_licenses", [
        {"license": "L1",
         "available_total": {"value": 0, "unit": "source VMs"},
         "used": {"value": 0, "unit": "source VMs"}}])])
    assert not compare_artifacts("f", bespoke, generic).failed


# ── D4/F4 — empty section ≡ absent section ────────────────────────────────────

def test_d4_empty_section_equals_absent():
    with_empty = _artifact([
        _table("other_licenses", [{"license": "L1"}]),
        _table("workload_x", []),
    ])
    without = _artifact([_table("other_licenses", [{"license": "L1"}])])
    assert not compare_artifacts("f", with_empty, without).failed


def test_d4_nonempty_section_vs_absent_fails():
    with_rows = _artifact([_table("workload_x", [{"license": "L1"}])])
    without = _artifact([])
    report = compare_artifacts("f", with_rows, without)
    assert any(r.outcome is Outcome.FAIL for r in report.failed)


# ── D6 — sensitive: both-masked + raw-absent, not byte-identical ─────────────

def test_d6_both_masked_different_format_equal():
    a = _artifact([_table("t", [{"license": "L1", "registration_code": "ABCD********WXYZ"}])])
    b = _artifact([_table("t", [{"license": "L1", "registration_code": "****-****-****-WXYZ"}])])
    report = compare_artifacts("f", a, b)
    assert not report.failed
    assert any(r.field == "registration_code" and r.outcome is Outcome.PASS
               for r in report.passed)


def test_d6_one_side_raw_fails():
    a = _artifact([_table("t", [{"license": "L1", "registration_code": "ABCD12345678WXYZ"}])])  # raw
    b = _artifact([_table("t", [{"license": "L1", "registration_code": "****-****-****-WXYZ"}])])
    report = compare_artifacts("f", a, b)
    assert any(r.field == "registration_code" and r.outcome is Outcome.FAIL
               for r in report.failed)


# ── D4/F3 — dedup tolerance on agent_feature_licenses ────────────────────────

def test_f3_same_distinct_set_extra_dupes_equal():
    base = _artifact([_table("agent_feature_licenses", [
        {"license": "A", "permanent_total": 1}, {"license": "B", "permanent_total": 2}])])
    cand = _artifact([_table("agent_feature_licenses", [
        {"license": "A", "permanent_total": 1}, {"license": "B", "permanent_total": 2},
        {"license": "A", "permanent_total": 1}])])  # extra duplicate of A
    assert not compare_artifacts("f", base, cand).failed


def test_f3_different_distinct_set_fails():
    base = _artifact([_table("agent_feature_licenses", [
        {"license": "A"}, {"license": "B"}])])
    cand = _artifact([_table("agent_feature_licenses", [
        {"license": "A"}, {"license": "C"}])])  # B vs C — distinct set differs
    report = compare_artifacts("f", base, cand)
    assert any(r.outcome is Outcome.FAIL for r in report.failed)


# ── B1: table vs same-id workload section are not cross-compared ──────────────

def test_b1_table_and_workload_other_licenses_not_cross_compared():
    # bespoke "Other Licenses" workload (entitlement_value/status) and the
    # other_licenses TABLE (available_total/used) share the id 'other_licenses'
    # via _to_snake — they must NOT be field-cross-compared.
    workload = _artifact([_table("other_licenses", [
        {"license": "L1", "entitlement_value": "0", "status": "License not purchased"}])])
    table = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": 25, "used": 10}])])
    report = compare_artifacts("f", workload, table)
    fields = {r.field for r in report.results}
    # no field-level cross-compare of workload fields against table fields
    assert "entitlement_value" not in fields
    assert "available_total" not in fields
    # each is handled at the SECTION level as a distinct key (not cross-compared);
    # one of them (the bespoke-only workload) is D8-accepted, the other a real diff.
    section_results = [r for r in report.results if r.field == "<section>"]
    assert len(section_results) == 2


def test_b1_reflexive_collision_both_sections_compared_equal():
    # an artifact carrying BOTH a table and a workload 'other_licenses' compares
    # equal to itself — both are kept (distinct keys), neither dropped/collapsed.
    art = _artifact([
        _table("other_licenses", [{"license": "L1", "available_total": 25, "used": 10}]),
        _table("other_licenses", [{"license": "WL", "entitlement_value": "5", "status": "ok"}]),
    ])
    report = compare_artifacts("f", art, art)
    assert not report.failed


# ── D7 — generic-present masked registration_code ≡ bespoke-absent ───────────

def test_d7_generic_only_masked_registration_code_accepted():
    bespoke = _artifact([_table("other_licenses", [{"license": "L1", "available_total": 1}])])
    generic = _artifact([
        _table("other_licenses", [{"license": "L1", "available_total": 1}]),
        _table("commcell_meta", [{"registration_code": "***-***-E34D"}]),
    ])
    report = compare_artifacts("f", bespoke, generic)
    assert not report.failed  # the generic-only masked-sensitive section is accepted
    assert any(r.section == "commcell_meta" and r.outcome is Outcome.PASS
               for r in report.passed)


def test_d7_generic_only_raw_registration_code_fails():
    bespoke = _artifact([_table("other_licenses", [{"license": "L1", "available_total": 1}])])
    generic = _artifact([
        _table("other_licenses", [{"license": "L1", "available_total": 1}]),
        _table("commcell_meta", [{"registration_code": "ABCD1234EFGH"}]),  # RAW
    ])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.section == "commcell_meta" and r.outcome is Outcome.FAIL
               for r in report.failed)


def test_d7_is_directional_bespoke_only_sensitive_still_fails():
    # a BESPOKE-only masked-sensitive section is NOT auto-accepted — there the
    # generic dropped data (less faithful), which is a real difference.
    bespoke = _artifact([
        _table("other_licenses", [{"license": "L1", "available_total": 1}]),
        _table("commcell_meta", [{"registration_code": "***-***-E34D"}]),
    ])
    generic = _artifact([_table("other_licenses", [{"license": "L1", "available_total": 1}])])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.section == "commcell_meta" and r.outcome is Outcome.FAIL
               for r in report.failed)


# ── D3/F5 — summary-metric ≡ same-named computed-section ──────────────────────

def test_d3_summary_metric_equals_computed_section_same_value():
    bespoke = _artifact([], metrics=[SummaryMetric(id="other_license_count", label="Other", value=16)])
    generic = _artifact([_count_section("other_license_count", 16)])
    report = compare_artifacts("f", bespoke, generic)
    assert not report.failed  # placement (metric vs section) equated when value matches
    assert any(r.field == "other_license_count" and r.outcome is Outcome.PASS
               for r in report.passed)


def test_d3_different_count_value_fails():
    bespoke = _artifact([], metrics=[SummaryMetric(id="c", label="C", value=16)])
    generic = _artifact([_count_section("c", 99)])  # same name, different value
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.field == "c" and r.outcome is Outcome.FAIL for r in report.failed)


def test_d3_metric_with_no_matching_section_fails():
    # a bespoke metric absent on the generic side (no metric, no section) → real difference
    bespoke = _artifact([], metrics=[SummaryMetric(id="orphan", label="O", value=5)])
    generic = _artifact([])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.field == "orphan" and r.outcome is Outcome.FAIL for r in report.failed)


def test_d3_computed_section_with_no_matching_metric_fails():
    # a generic count-section absent on the bespoke side → real difference (not blanket-passed)
    bespoke = _artifact([])
    generic = _artifact([_count_section("orphan", 5)])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.field == "orphan" and r.outcome is Outcome.FAIL for r in report.failed)


# ── D8 — workload "Other Licenses" id-collision quirk (scoped acceptance) ─────

def test_d8_bespoke_only_workload_other_licenses_accepted():
    # bespoke has a workload "Other Licenses" (entitlement_value → workload tag);
    # the generic target does not preserve the id-collision quirk
    bespoke = _artifact([_table("other_licenses", [
        {"license": "WL", "entitlement_value": "5", "status": "ok"}])])
    generic = _artifact([])
    report = compare_artifacts("f", bespoke, generic)
    assert not report.failed
    assert any(r.section == "other_licenses" and r.outcome is Outcome.PASS
               for r in report.passed)


def test_d8_scoped_unrelated_bespoke_only_section_still_fails():
    # an UNRELATED bespoke-only section is NOT auto-accepted
    bespoke = _artifact([_table("agent_feature_licenses", [{"license": "A"}])])
    generic = _artifact([])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.section == "agent_feature_licenses" and r.outcome is Outcome.FAIL
               for r in report.failed)


def test_d8_scoped_bespoke_only_other_licenses_TABLE_still_fails():
    # a bespoke-only other_licenses TABLE (default tag, not workload) still FAILS —
    # D8 is scoped to the workload-tagged collision, not the table
    bespoke = _artifact([_table("other_licenses", [
        {"license": "L1", "available_total": 1, "used": 0}])])
    generic = _artifact([])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.section == "other_licenses" and r.outcome is Outcome.FAIL
               for r in report.failed)


def test_d8_scoped_other_workload_section_id_still_fails():
    # a bespoke-only workload section with a DIFFERENT id (capacity_licenses) still
    # FAILS — D8 is scoped to "other_licenses", not any workload section
    bespoke = _artifact([_table("capacity_licenses", [
        {"license": "C", "entitlement_value": "5", "status": "ok"}])])
    generic = _artifact([])
    report = compare_artifacts("f", bespoke, generic)
    assert any(r.section == "capacity_licenses" and r.outcome is Outcome.FAIL
               for r in report.failed)


# ── guards: the equivalences must not make it an always-pass ──────────────────

def test_still_fails_on_plain_value_difference():
    a = _artifact([_table("t", [{"license": "L1", "permanent_total": 5}])])
    b = _artifact([_table("t", [{"license": "L1", "permanent_total": 9}])])
    report = compare_artifacts("f", a, b)
    assert any(r.field == "permanent_total" and r.outcome is Outcome.FAIL
               for r in report.failed)


def test_still_fails_on_missing_field():
    a = _artifact([_table("t", [{"license": "L1", "extra": "x"}])])
    b = _artifact([_table("t", [{"license": "L1"}])])
    report = compare_artifacts("f", a, b)
    assert any(r.field == "extra" and r.outcome is Outcome.FAIL for r in report.failed)


def test_still_fails_on_wrong_section_content():
    a = _artifact([_table("t", [{"license": "L1", "status": "good"}])])
    b = _artifact([_table("t", [{"license": "L1", "status": "bad"}])])
    report = compare_artifacts("f", a, b)
    assert any(r.field == "status" and r.outcome is Outcome.FAIL for r in report.failed)
