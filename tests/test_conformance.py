"""Tests for ADR 0004 conformance checking (extractors/conformance.py) and
its section-grained emission through result_to_artifact.

The conformance record shape is fixed by ADR 0004 §"Conformance failures and
the AI-rebuild bridge" and consumed verbatim by a successor ADR — these tests
pin that shape.
"""
from cvhealthcheck.extractors.conformance import (
    REASON_CARDINALITY_MISMATCH,
    REASON_MISSING_REQUIRED_FIELD,
    REASON_TYPE_MISMATCH,
    REASON_UNKNOWN_ENUM_VALUE,
    check_conformance,
)
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# ── No-op cases ──

def test_no_conformance_block_passes():
    assert check_conformance([{"a": 1}], None) is None
    assert check_conformance([{"a": 1}], {}) is None


def test_conforming_data_passes():
    conformance = {
        "required_fields": ["JobId", "Status"],
        "field_types": {"JobId": "int", "Status": "string"},
        "enums": {"Status": ["Completed", "Failed"]},
        "cardinality": {"min": 1, "max": 10},
    }
    rows = [
        {"JobId": 1, "Status": "Completed"},
        {"JobId": 2, "Status": "Failed"},
    ]
    assert check_conformance(rows, conformance) is None


# ── Missing required field (ADR's headline example) ──

def test_missing_required_field_record_shape():
    # Mirrors the ADR §"Conformance failures" worked example.
    conformance = {"required_fields": ["JobId", "ClientName", "Status", "StartTime"]}
    rows = [{"JobStatus": "ok", "JobId": 1, "SizeofApplication": 100}]
    record = check_conformance(rows, conformance)

    assert record is not None
    assert record["reason"] == REASON_MISSING_REQUIRED_FIELD
    assert record["expected"] == {"fields": ["JobId", "ClientName", "Status", "StartTime"]}
    assert set(record["actual"]["fields"]) == {"JobStatus", "JobId", "SizeofApplication"}
    assert record["delta"]["missing"] == ["ClientName", "Status", "StartTime"]
    assert set(record["delta"]["unexpected"]) == {"JobStatus", "SizeofApplication"}
    assert "drifted" in record["hint"]
    # Exactly the ADR-fixed key set, nothing more.
    assert set(record.keys()) == {"reason", "expected", "actual", "delta", "hint"}


# ── Type mismatch ──

def test_type_mismatch():
    conformance = {"required_fields": ["JobId"], "field_types": {"JobId": "int"}}
    record = check_conformance([{"JobId": "not-an-int"}], conformance)
    assert record is not None
    assert record["reason"] == REASON_TYPE_MISMATCH
    assert "JobId" in record["hint"]


def test_int_field_rejects_bool():
    # bool subclasses int — an int field must not silently accept True.
    conformance = {"required_fields": ["JobId"], "field_types": {"JobId": "int"}}
    record = check_conformance([{"JobId": True}], conformance)
    assert record is not None and record["reason"] == REASON_TYPE_MISMATCH


def test_null_value_is_not_a_type_error():
    conformance = {"required_fields": ["JobId"], "field_types": {"JobId": "int"}}
    assert check_conformance([{"JobId": None}], conformance) is None


# ── Unknown enum value ──

def test_unknown_enum_value():
    conformance = {
        "required_fields": ["Status"],
        "enums": {"Status": ["Completed", "Failed"]},
    }
    record = check_conformance([{"Status": "Exploded"}], conformance)
    assert record is not None
    assert record["reason"] == REASON_UNKNOWN_ENUM_VALUE
    assert "Exploded" in record["hint"]


# ── Cardinality ──

def test_cardinality_exact():
    conformance = {"required_fields": ["m"], "cardinality": {"exact": 13}}
    rows = [{"m": i} for i in range(12)]
    record = check_conformance(rows, conformance)
    assert record is not None and record["reason"] == REASON_CARDINALITY_MISMATCH
    assert check_conformance([{"m": i} for i in range(13)], conformance) is None


def test_cardinality_min_max():
    # No required_fields here — otherwise empty rows would fail the
    # (higher-priority) required-field check before cardinality is reached.
    conformance = {"cardinality": {"min": 1, "max": 3}}
    assert check_conformance([], conformance)["reason"] == REASON_CARDINALITY_MISMATCH
    assert check_conformance([{"m": i} for i in range(5)], conformance)["reason"] == (
        REASON_CARDINALITY_MISMATCH
    )
    assert check_conformance([{"m": 1}], conformance) is None


def test_required_field_takes_priority_over_cardinality():
    # Empty data with a required field declared reports the missing field,
    # not the (also-true) cardinality violation — detection priority order.
    conformance = {"required_fields": ["m"], "cardinality": {"min": 1}}
    assert check_conformance([], conformance)["reason"] == REASON_MISSING_REQUIRED_FIELD


# ── Section-grained emission through the artifact ──

def test_conformance_failure_emitted_onto_artifact():
    result = ExtractionResult(subject_id="backup_job_summary", source_type="rest")
    # One healthy section, one failed section — the failure must not abort the
    # healthy one (section-grained, not fail-whole).
    result.sections["bjs.totals"] = [{"total": 5}]
    result.section_output_types["bjs.totals"] = "table"
    result.section_titles["bjs.totals"] = "Totals"
    result.section_failures["bjs.jobs"] = {
        "reason": REASON_MISSING_REQUIRED_FIELD,
        "expected": {"fields": ["JobId", "ClientName"]},
        "actual": {"fields": ["JobStatus"]},
        "delta": {"missing": ["JobId", "ClientName"], "unexpected": ["JobStatus"]},
        "hint": "Schema appears to have drifted from the template's declaration.",
    }

    artifact = result_to_artifact(result, "backup_job_summary", "Backup Job Summary")

    # Healthy section still present.
    assert any(s.id == "bjs.totals" for s in artifact.sections)
    # Failure record carried verbatim on the artifact metadata, keyed by section.
    failures = artifact.metadata["conformance_failures"]
    assert "bjs.jobs" in failures
    assert failures["bjs.jobs"]["reason"] == REASON_MISSING_REQUIRED_FIELD
    assert failures["bjs.jobs"]["delta"]["missing"] == ["JobId", "ClientName"]


def test_no_failures_means_no_conformance_metadata():
    result = ExtractionResult(subject_id="capacity_license", source_type="rest")
    result.sections["cl.table"] = [{"month": "2024-08"}]
    result.section_output_types["cl.table"] = "table"
    result.section_titles["cl.table"] = "Table"
    artifact = result_to_artifact(result, "capacity_license", "Capacity Licenses")
    assert "conformance_failures" not in artifact.metadata
