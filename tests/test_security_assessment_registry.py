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
    ReportStream,
)
from cvhealthcheck.security_assessment.registry import SecurityAssessmentArtifactRegistry
from cvhealthcheck.security_assessment.service import (
    SecurityAssessmentService,
    export_security_assessment_registry,
    load_active_security_assessment_artifact,
    list_security_assessment_artifacts,
    persist_security_assessment_artifact,
)
from cvhealthcheck.web.app import create_app
from cvhealthcheck.security_assessment.validate import (
    filter_valid_findings,
    is_valid_canonical_finding,
)
from cvhealthcheck.auth.commvault_auth import SESSION_TOKEN_KEY


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


def test_registry_latest_artifact_and_run_listings(tmp_path) -> None:
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
    stream_id = "stream_1"
    persist_security_assessment_artifact(
        {
            **artifact,
            "imported_at": "2026-05-17T09:00:00+00:00",
            "report_run_id": "run_1",
            "executed_at": "2026-05-17T09:00:00+00:00",
            "run_sequence": 1,
        },
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        report_stream=ReportStream(
            report_stream_id=stream_id,
            customer_id="unknown_customer",
            commcell_id="unknown_commcell",
            cadence="daily",
        ),
    )
    latest = persist_security_assessment_artifact(
        {
            **artifact,
            "imported_at": "2026-05-17T10:00:00+00:00",
            "report_run_id": "run_2",
            "executed_at": "2026-05-17T10:00:00+00:00",
            "run_sequence": 2,
        },
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        report_stream=ReportStream(
            report_stream_id=stream_id,
            customer_id="unknown_customer",
            commcell_id="unknown_commcell",
            cadence="daily",
        ),
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")

    latest_record = registry.get_latest_artifact(
        "security_assessment",
        customer_id="unknown_customer",
        commcell_id="unknown_commcell",
        source_type="rest",
        report_stream_id=stream_id,
    )
    report_runs = registry.list_report_runs(
        customer_id="unknown_customer",
        commcell_id="unknown_commcell",
        report_stream_id=stream_id,
    )
    import_runs = registry.list_import_runs(
        customer_id="unknown_customer",
        commcell_id="unknown_commcell",
        report_stream_id=stream_id,
    )

    assert latest_record is not None
    assert latest_record.artifact_id == latest["artifact_id"]
    assert len(report_runs) == 2
    assert len(import_runs) == 2


def test_service_can_retrieve_artifact_by_all_supported_keys(tmp_path) -> None:
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
    persisted = persist_security_assessment_artifact(
        {
            **artifact,
            "report_run_id": "run_retrieve",
            "executed_at": "2026-05-17T11:00:00+00:00",
        },
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    service = SecurityAssessmentService(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    by_artifact = service.get_artifact(artifact_id=persisted["artifact_id"])
    by_import_run = service.get_artifact(import_run_id=persisted["import_run_id"])
    by_report_run = service.get_artifact(report_run_id="run_retrieve")

    assert by_artifact is not None and by_artifact["artifact_id"] == persisted["artifact_id"]
    assert by_import_run is not None and by_import_run["artifact_id"] == persisted["artifact_id"]
    assert by_report_run is not None and by_report_run["artifact_id"] == persisted["artifact_id"]
    assert by_artifact["last_accessed_at"]


def test_service_history_and_list_helper_return_scoped_records(tmp_path) -> None:
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
    customer = CustomerContext(customer_id="cust_hist", customer_name="Customer Hist")
    commcell = CommCellContext(
        commcell_id="cc_hist",
        commcell_name="CommCell Hist",
        customer_id="cust_hist",
    )
    first = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=commcell,
    )
    persist_security_assessment_artifact(
        {**artifact, "imported_at": "2026-05-17T13:00:00+00:00"},
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=commcell,
    )
    service = SecurityAssessmentService(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    history = service.get_history(customer_id="cust_hist", commcell_id="cc_hist")
    records = list_security_assessment_artifacts(
        registry_path=tmp_path / "registry.sqlite3",
        customer_id="cust_hist",
        commcell_id="cc_hist",
    )

    assert len(history["artifacts"]) == 2
    assert len(history["import_runs"]) == 2
    assert records[-1]["artifact_id"] == first["artifact_id"] or records[0]["artifact_id"] == first["artifact_id"]


def test_persisted_artifact_tracks_provenance_and_retention_metadata(tmp_path) -> None:
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
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        imported_by="tester",
        import_method="upload",
        retention_policy="keep",
    )
    registry = SecurityAssessmentArtifactRegistry(tmp_path / "registry.sqlite3")
    record = registry.get_artifact(persisted["artifact_id"])

    assert persisted["created_at"] == persisted["imported_at"]
    assert persisted["imported_by"] == "tester"
    assert persisted["import_method"] == "upload"
    assert persisted["retention_policy"] == "keep"
    assert persisted["source_metadata"]["type"] == "csv"
    assert record is not None
    assert record.imported_by == "tester"
    assert record.import_method == "upload"


def test_hidden_history_and_registry_export_endpoints_work(tmp_path, monkeypatch) -> None:
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
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.security_assessment.service as service_module
    import cvhealthcheck.reportsplus.security_assessment as security_assessment_module
    import cvhealthcheck.security_assessment.artifact as artifact_module

    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_REGISTRY_PATH", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(security_assessment_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(artifact_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"

    history_response = client.get("/security-assessment/history")
    artifact_response = client.get(
        f"/security-assessment/history?artifact_id={persisted['artifact_id']}"
    )
    export_response = client.get("/security-assessment/registry-export")

    assert history_response.status_code == 200
    assert '"artifacts"' in history_response.get_data(as_text=True)
    assert '"internal_only": true' in history_response.get_data(as_text=True)
    assert artifact_response.status_code == 200
    assert persisted["artifact_id"] in artifact_response.get_data(as_text=True)
    assert export_response.status_code == 200
    assert '"record_count"' in export_response.get_data(as_text=True)


def test_internal_registry_routes_require_login(tmp_path, monkeypatch) -> None:
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

    import cvhealthcheck.security_assessment.service as service_module
    import cvhealthcheck.reportsplus.security_assessment as security_assessment_module
    import cvhealthcheck.security_assessment.artifact as artifact_module

    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_REGISTRY_PATH", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(security_assessment_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(artifact_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")

    app = create_app()
    client = app.test_client()

    history_response = client.get("/security-assessment/history")
    export_response = client.get("/security-assessment/registry-export")
    viewer_response = client.get("/development/security-assessment-registry")

    assert history_response.status_code == 302
    assert "/login" in history_response.headers["Location"]
    assert export_response.status_code == 302
    assert "/login" in export_response.headers["Location"]
    assert viewer_response.status_code == 302
    assert "/login" in viewer_response.headers["Location"]


def test_internal_registry_view_renders_artifact_table(tmp_path, monkeypatch) -> None:
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
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.security_assessment.service as service_module
    import cvhealthcheck.reportsplus.security_assessment as security_assessment_module
    import cvhealthcheck.security_assessment.artifact as artifact_module

    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_REGISTRY_PATH", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(security_assessment_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(artifact_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "catalog")

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"

    response = client.get("/development/security-assessment-registry?source_type=csv")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Internal debug/admin view" in body
    assert persisted["artifact_id"] in body
    assert persisted["file_path"] in body
