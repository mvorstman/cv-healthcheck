from __future__ import annotations

import json
from pathlib import Path

from cvhealthcheck.reportsplus.catalog import collected_at
from cvhealthcheck.security_assessment.artifact import build_security_assessment_artifact
from cvhealthcheck.security_assessment.models import (
    ArtifactRecord,
    CommCellContext,
    CustomerContext,
    ImportRun,
)
from cvhealthcheck.security_assessment.registry import SecurityAssessmentArtifactRegistry
from cvhealthcheck.security_assessment.service import (
    export_security_assessment_registry,
    load_active_security_assessment_artifact,
    persist_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.validate import (
    filter_valid_findings,
    is_valid_canonical_finding,
)


def test_canonical_finding_validation_accepts_expected_shape() -> None:
    assert is_valid_canonical_finding(
        {
            "section": "Access Security",
            "parameter": "MFA enabled",
            "status": "Critical",
            "remarks": "Missing for admin users",
            "action": "Enable MFA",
            "source_type": "html",
            "source_file": "/tmp/in.html",
            "imported_at": collected_at(),
        }
    )


def test_invalid_findings_are_filtered_outside_normalization() -> None:
    imported_at = collected_at()
    findings = filter_valid_findings(
        [
            {
                "section": "Hardening",
                "parameter": "Unused ports",
                "status": "Critical",
                "remarks": "Close unused ports",
                "action": "Restrict listeners",
                "source_type": "html",
                "source_file": "/tmp/a.html",
                "imported_at": imported_at,
            },
            {
                "section": "Detailed Checks",
                "parameter": "Parameter Status Remarks Action",
                "status": "Info",
                "remarks": "1 to 3 of 3 entries",
                "action": "Detailed Checks",
                "source_type": "html",
                "source_file": "/tmp/a.html",
                "imported_at": imported_at,
            },
        ]
    )

    assert len(findings) == 1
    assert findings[0].parameter == "Unused ports"


def test_registry_insert_and_active_read(tmp_path) -> None:
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")
    import_run = ImportRun(
        import_run_id="imprun_1",
        customer_id="cust_100",
        commcell_id="cc_200",
        imported_at=collected_at(),
        report_stream_id="stream_1",
        report_run_id="run_1",
        executed_at="2026-05-17T08:00:00+00:00",
        run_sequence=1,
    )
    artifact = ArtifactRecord(
        artifact_id="artifact_1",
        import_run_id="imprun_1",
        artifact_type="security_assessment",
        source_type="csv",
        source_file="/tmp/a.csv",
        file_path="/tmp/artifact_1.json",
        customer_id="cust_100",
        commcell_id="cc_200",
        imported_at=import_run.imported_at,
        report_stream_id="stream_1",
        report_run_id="run_1",
        executed_at="2026-05-17T08:00:00+00:00",
        run_sequence=1,
        is_active=True,
    )

    registry.register_artifact(import_run, artifact)
    active = registry.get_active_artifact(
        "security_assessment",
        customer_id="cust_100",
        commcell_id="cc_200",
        source_type="csv",
        report_stream_id="stream_1",
    )

    assert active is not None
    assert active.artifact_id == "artifact_1"
    assert active.customer_id == "cust_100"
    assert active.report_run_id == "run_1"


def test_latest_json_compatibility_still_works(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="html",
        source_file="/tmp/security-assessment.html",
    )

    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    latest = json.loads((tmp_path / "catalog" / "latest.json").read_text(encoding="utf-8"))
    latest_source = json.loads((tmp_path / "catalog" / "latest_html.json").read_text(encoding="utf-8"))

    assert latest["artifact_id"] == persisted["artifact_id"]
    assert latest_source["artifact_id"] == persisted["artifact_id"]
    assert persisted["artifact_paths"]["artifact"].endswith(".json")


def test_multiple_report_runs_same_day_are_supported(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Info",
                "remarks": "Enabled",
                "action": "",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    first = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        report_stream=None,
        report_run=None,
    )
    second = persist_security_assessment_artifact(
        {
            **artifact,
            "imported_at": "2026-05-17T12:30:00+00:00",
            "executed_at": "2026-05-17T12:30:00+00:00",
            "report_run_id": "run_2",
            "run_sequence": 2,
        },
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")
    records = registry.list_artifacts("security_assessment")

    assert len(records) == 2
    assert first["artifact_id"] != second["artifact_id"]
    assert records[0].imported_at != records[1].imported_at
    active = load_active_security_assessment_artifact(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    assert active["artifact_id"] == second["artifact_id"]


def test_import_creates_unique_artifact_file_registry_row_and_compatibility_files(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            }
        ],
        source_type="csv",
        source_file="/tmp/security-assessment.csv",
    )

    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")
    record = registry.get_artifact(persisted["artifact_id"])

    assert record is not None
    assert Path(record.file_path).exists()
    assert (tmp_path / "catalog" / "latest.json").exists()
    assert (tmp_path / "catalog" / "latest_csv.json").exists()
    loaded = json.loads(Path(record.file_path).read_text(encoding="utf-8"))
    assert loaded["artifact_id"] == persisted["artifact_id"]
    assert loaded["source_file"] == "/tmp/security-assessment.csv"


def test_customer_scope_keeps_active_artifacts_separate(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing",
                "action": "Enable MFA",
            }
        ],
        source_type="html",
    )
    customer_a = CustomerContext(customer_id="cust_a", customer_name="Customer A")
    customer_b = CustomerContext(customer_id="cust_b", customer_name="Customer B")
    commcell_a = CommCellContext(
        commcell_id="cc_shared",
        commcell_name="CommCell A",
        customer_id="cust_a",
    )
    commcell_b = CommCellContext(
        commcell_id="cc_shared",
        commcell_name="CommCell B",
        customer_id="cust_b",
    )

    first = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer_a,
        commcell_context=commcell_a,
    )
    second = persist_security_assessment_artifact(
        {**artifact, "imported_at": "2026-05-17T12:30:00+00:00"},
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer_b,
        commcell_context=commcell_b,
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")

    active_a = registry.get_active_artifact(
        "security_assessment",
        customer_id="cust_a",
        commcell_id="cc_shared",
        source_type="html",
    )
    active_b = registry.get_active_artifact(
        "security_assessment",
        customer_id="cust_b",
        commcell_id="cc_shared",
        source_type="html",
    )

    assert active_a is not None and active_a.artifact_id == first["artifact_id"]
    assert active_b is not None and active_b.artifact_id == second["artifact_id"]


def test_commcell_scope_keeps_active_artifacts_separate_within_customer(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Hardening",
                "parameter": "Unused ports",
                "status": "Warning",
                "remarks": "Review listeners",
                "action": "Restrict listeners",
            }
        ],
        source_type="rest",
    )
    customer = CustomerContext(customer_id="cust_a", customer_name="Customer A")
    first = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=CommCellContext(
            commcell_id="cc_1",
            commcell_name="CommCell 1",
            customer_id="cust_a",
        ),
    )
    second = persist_security_assessment_artifact(
        {**artifact, "imported_at": "2026-05-17T15:30:00+00:00"},
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=CommCellContext(
            commcell_id="cc_2",
            commcell_name="CommCell 2",
            customer_id="cust_a",
        ),
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")

    active_1 = registry.get_active_artifact(
        "security_assessment",
        customer_id="cust_a",
        commcell_id="cc_1",
        source_type="rest",
    )
    active_2 = registry.get_active_artifact(
        "security_assessment",
        customer_id="cust_a",
        commcell_id="cc_2",
        source_type="rest",
    )

    assert active_1 is not None and active_1.artifact_id == first["artifact_id"]
    assert active_2 is not None and active_2.artifact_id == second["artifact_id"]


def test_missing_active_file_recovers_to_previous_registry_artifact(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Capabilities",
                "parameter": "Ransomware protection",
                "status": "Info",
                "remarks": "Feature available",
                "action": "Assess rollout",
            }
        ],
        source_type="csv",
    )
    first = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    second = persist_security_assessment_artifact(
        {**artifact, "imported_at": "2026-05-17T18:30:00+00:00"},
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    Path(second["file_path"]).unlink()

    loaded = load_active_security_assessment_artifact(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")
    active = registry.get_active_artifact(
        "security_assessment",
        customer_id="unknown_customer",
        commcell_id="unknown_commcell",
        source_type="csv",
    )

    assert loaded["artifact_id"] == first["artifact_id"]
    assert active is not None and active.artifact_id == first["artifact_id"]


def test_latest_json_fallback_is_used_when_registry_entry_missing(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Good",
                "remarks": "Enabled",
                "action": "",
            }
        ],
        source_type="html",
    )
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    loaded = load_active_security_assessment_artifact(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "missing-registry.sqlite3",
    )

    assert loaded["artifact_id"] == persisted["artifact_id"]
    assert loaded["loaded_from_path"] == str(tmp_path / "catalog" / "latest.json")


def test_registry_export_to_json_includes_all_records(tmp_path) -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            }
        ],
        source_type="csv",
    )
    persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    export_path = tmp_path / "exports" / "security_assessment_registry.json"
    payload = export_security_assessment_registry(
        registry_path=tmp_path / "registry.sqlite3",
        export_path=export_path,
    )

    assert payload["record_count"] == 1
    assert export_path.exists()
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["record_count"] == 1
    assert exported["records"][0]["artifact_type"] == "security_assessment"
