from __future__ import annotations

import json
from pathlib import Path

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.quickhc.models import TileDefinition
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID
from cvhealthcheck.quickhc.report_service import QuickHcReportService
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.reportsplus.backup_job_summary import write_backup_job_summary_artifact
from cvhealthcheck.security_assessment.artifact import build_security_assessment_artifact
from cvhealthcheck.security_assessment.service import persist_security_assessment_artifact
from cvhealthcheck.extractors.html import ExtractionResult as _SAExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact as _sa_result_to_artifact


def _sa_canonical_from_findings(findings, *, source_type="html"):
    """Build an SA canonical artifact from a findings list via the generic path
    (result_to_artifact) — the post-cut canonical shape. Used by the SA test
    shim below to populate the canonical store the report reads."""
    import re as _re
    from collections import OrderedDict as _OD
    r = _SAExtractionResult(subject_id="security_assessment", source_type=source_type)
    grouped = _OD()
    for f in findings:
        grouped.setdefault(f.get("section") or "Other", []).append(f)
    for name, items in grouped.items():
        sid = "security_assessment." + _re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
        r.sections[sid] = [
            {
                "parameter": it.get("parameter"), "status": it.get("status"),
                "severity": str(it.get("status") or "info").lower(),
                "remarks": it.get("remarks", ""), "action": it.get("action", ""),
            }
            for it in items
        ]
        r.section_output_types[sid] = "findings"
        r.section_titles[sid] = name
    return _sa_result_to_artifact(r, "security_assessment", "Security Assessment")
from cvhealthcheck.web.app import create_app


LICENSE_CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
CommCell ID,commcell-01
Customer ID,customer-01
License Expiry,Dec 31, 2026

Capacity Licenses
License,Available Total (TB),Permanent Purchased (TB),Term Purchased (TB),Used (TB),Used %,Summary
Backup and Recovery,100,100,0,0.00,0%,0%

Other Licenses - current usage details
License,Available Total,Used
Cloud Storage,100,40

Agent and Feature Licenses - current usage details
License,Permanent Total,Permanent Used,Term Total,Term Used,Client,Agent,Install Date
Virtual Server,50,12,10,3,Client A,Agent A,2026-05-01
"""


LICENSE_CSV_WITH_UNPURCHASED = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
CommCell ID,commcell-01
Customer ID,customer-01
License Expiry,Dec 31, 2026

Capacity Licenses
License,Available Total (TB),Permanent Purchased (TB),Term Purchased (TB),Used (TB),Used %,Summary
Backup and Recovery,100,100,0,0.00,0%,0%

Other Licenses - current usage details
License,Available Total,Used
Cloud Storage,100,40
Archive,0,0

Agent and Feature Licenses - current usage details
License,Permanent Total,Permanent Used,Term Total,Term Used,Client,Agent,Install Date
Virtual Server,50,12,10,3,Client A,Agent A,2026-05-01
"""


def _patch_security_assessment_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.security_assessment.service as security_assessment_service_module
    import cvhealthcheck.security_assessment.artifact as security_assessment_artifact_module
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module
    from cvhealthcheck.artifacts.store import ArtifactStore

    monkeypatch.setattr(
        security_assessment_service_module,
        "SECURITY_ASSESSMENT_REGISTRY_PATH",
        tmp_path / "security_registry.sqlite3",
    )
    monkeypatch.setattr(
        security_assessment_service_module,
        "SECURITY_ASSESSMENT_CATALOG_DIR",
        tmp_path / "security_catalog",
    )
    monkeypatch.setattr(
        security_assessment_artifact_module,
        "SECURITY_ASSESSMENT_CATALOG_DIR",
        tmp_path / "security_catalog",
    )
    _sa_canonical_store = ArtifactStore(
        "default", "default", base_dir=tmp_path / "canonical_artifacts"
    )
    monkeypatch.setattr(
        subject_data_service_module,
        "_canonical_store",
        _sa_canonical_store,
    )
    # SA migration: the report now reads get_canonical() ->
    # _active_project_store(); persist writes the canonical artifact through the
    # same call. Patch it to the tmp store so the report finds what persist wrote
    # (previously the report read get_current() / the bespoke per-domain store).
    monkeypatch.setattr(
        security_assessment_service_module,
        "_active_project_store",
        lambda: _sa_canonical_store,
    )
    # SA migration (PR2): persist() no longer writes the canonical artifact —
    # production canonical now comes from the generic extractor (upload / REST).
    # These tests use persist() as a shortcut to populate SA, so wrap it to also
    # write the canonical store via the generic path, mirroring what the
    # production generic upload does.
    import sys as _sys
    _real_persist = persist_security_assessment_artifact

    def _persist_then_canonical(artifact, **kwargs):
        result = _real_persist(artifact, **kwargs)
        _sa_canonical_store.save_artifact(
            _sa_canonical_from_findings(
                artifact.get("findings") or [],
                source_type=str(artifact.get("source_type") or "html"),
            )
        )
        return result

    monkeypatch.setattr(
        _sys.modules[__name__],
        "persist_security_assessment_artifact",
        _persist_then_canonical,
    )


def _patch_license_summary_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module
    from cvhealthcheck.artifacts.store import ArtifactStore

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "license_registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "license_catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "license_catalog",
    )
    monkeypatch.setattr(
        subject_data_service_module,
        "_canonical_store",
        ArtifactStore("default", "default", base_dir=tmp_path / "canonical_artifacts"),
    )


def _patch_metrics_paths(tmp_path, monkeypatch) -> Path:
    import cvhealthcheck.metrics.common as metrics_common_module

    metrics_dir = tmp_path / "metrics_catalog"
    monkeypatch.setattr(
        metrics_common_module,
        "METRICS_CATALOG_DIR",
        metrics_dir,
    )
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


def _write_metric_artifact(metrics_dir: Path, name: str, payload: dict) -> None:
    (metrics_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _patch_backup_job_summary_paths(tmp_path, monkeypatch) -> Path:
    import cvhealthcheck.reportsplus.backup_job_summary as backup_job_summary_module

    catalog_dir = tmp_path / "quickhc_catalog"
    monkeypatch.setattr(
        backup_job_summary_module,
        "QUICKHC_CATALOG_DIR",
        catalog_dir,
    )
    catalog_dir.mkdir(parents=True, exist_ok=True)
    return catalog_dir


CLIENT_GROWTH_ARTIFACT = {
    "collected_at": "2026-05-18T21:00:00Z",
    "source": {
        "report_id": "318",
        "dataset_id": "2281",
        "dataset_guid": "8ac30a77-3de2-4968-86c1-ade4b02c85a4",
        "dataset_name": "Client Growth Summary",
        "widget_name": "Summary",
    },
    "http_status": 200,
    "ok": True,
    "record_count": 2,
    "history_range": {"start": "2026-04", "end": "2026-05", "points": 2},
    "records": [
        {"month": "2026-04", "total_clients": 120, "added": 4, "removed": 1, "data_source": "CommServe A"},
        {"month": "2026-05", "total_clients": 125, "added": 7, "removed": 2, "data_source": "CommServe A"},
    ],
}

CAPACITY_LICENSE_ARTIFACT = {
    "collected_at": "2026-05-18T21:05:00Z",
    "source": {
        "report_id": "318",
        "dataset_id": "2266",
        "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
        "dataset_name": "Capacity License Usage",
        "widget_name": "Capacity License Usage",
    },
    "http_status": 200,
    "ok": True,
    "record_count": 2,
    "history_range": {"start": "2026-05", "end": "2026-05", "points": 1},
    "records": [
        {"month": "2026-05", "entity_name": "CommServe A", "used_capacity": 18.5, "purchased_capacity": 40.0, "data_source": "CommServe A"},
        {"month": "2026-05", "entity_name": "CommServe B", "used_capacity": 11.0, "purchased_capacity": 20.0, "data_source": "CommServe B"},
    ],
}

BACKUP_JOB_SUMMARY_ARTIFACT = {
    "generated_at": "2026-05-20T10:30:00Z",
    "source_report_name": "Backup Job Summary",
    "source_dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "source_related_dataset_guid": "ce01fc88-d2bd-46cc-ba41-1d967c7fa4a2",
    "total_jobs": 12,
    "completed_jobs": 8,
    "failed_jobs": 2,
    "completed_with_errors_or_warnings": 1,
    "running_jobs": 1,
    "killed_jobs": 0,
    "other_jobs": 0,
    "protected_clients_seen": 5,
    "status_breakdown": {
        "Completed": 8,
        "Failed": 2,
        "Completed with errors/warnings": 1,
        "Running": 1,
    },
    "recent_failures": [
        {
            "job_id": "9002",
            "client": "client-b",
            "company": "Tenant B",
            "workload": "File System",
            "agent": "FS",
            "backup_type": "Incremental",
            "start_time": "2026-05-20 08:00:00",
            "end_time": "2026-05-20 08:20:00",
            "duration": "00:20:00",
            "status": "Failed",
            "failure_reason": "Media issue",
            "storage_policy": "Gold",
            "media_agent": "ma-1",
            "size": "100 GB",
            "throughput": "80 MB/s",
            "schedule_policy": "Daily",
            "schedule_name": "Nightly",
        }
    ],
    "recent_jobs": [
        {
            "job_id": "9003",
            "client": "client-c",
            "company": "Tenant C",
            "workload": "VMware",
            "agent": "VSA",
            "backup_type": "Full",
            "start_time": "2026-05-20 09:00:00",
            "end_time": "2026-05-20 09:40:00",
            "duration": "00:40:00",
            "status": "Completed",
            "failure_reason": None,
            "storage_policy": "Silver",
            "media_agent": "ma-2",
            "size": "250 GB",
            "throughput": "120 MB/s",
            "schedule_policy": "Weekly",
            "schedule_name": "Weekend",
        }
    ],
}


def test_quick_hc_report_route_loads_without_artifacts() -> None:
    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Quick HealthCheck Report" in body
    assert "Environment" in body
    assert "Security Assessment" in body
    assert "License Summary" in body
    assert "Backup Job Summary" in body
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body


def test_quick_hc_report_includes_security_assessment_summary(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            },
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            },
        ],
        source_type="html",
        source_file="/tmp/security-assessment.html",
        generated_on="May 17, 2026 07:00:14 PM",
    )
    persisted = persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    report = QuickHcReportService().build_report()

    assert report["security_assessment"]["available"] is True
    assert report["security_assessment"]["total_checks"] == 2
    assert report["security_assessment"]["critical"] == 1
    assert report["security_assessment"]["info"] == 1
    # SA migration: the report reads the canonical artifact now, which carries no
    # bespoke per-domain file path — loaded_from_path is no longer the legacy
    # store path. (persist still writes that path for the held #36 registry.)
    assert report["security_assessment"]["loaded_from_path"] is None


def test_quick_hc_report_includes_license_summary_summary(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    report = QuickHcReportService().build_report()

    assert report["license_summary"]["available"] is True
    assert report["license_summary"]["license_expiry"] == "Dec 31"
    assert report["license_summary"]["workload_summary_section_count"] == 1
    assert report["license_summary"]["other_license_row_count"] == 1
    assert report["license_summary"]["agent_feature_license_row_count"] == 1
    assert report["license_summary"]["other_license_rows"][0]["usage_percent_label"] == "40%"
    assert report["license_summary"]["other_license_rows"][0]["usage_has_bar"] is True
    assert report["environment"]["commcell_name"] == "CommServe A"


def test_quick_hc_report_route_renders_both_summaries_when_artifacts_exist(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body
    assert "License Summary" in body
    assert "Open Quick HC overview" in body
    assert "View License Summary" in body
    assert "Cloud Storage" not in body
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body


def test_quick_hc_report_route_uses_service(monkeypatch) -> None:
    called: dict[str, bool] = {"used": False}

    def fake_build_report(self):
        called["used"] = True
        return {
            "title": "Quick HealthCheck Report",
            "generated_at": "2026-05-18T20:00:00Z",
            "environment": {
                "customer_id": None,
                "commcell_id": None,
                "commcell_name": None,
                "generated_at": "2026-05-18T20:00:00Z",
            },
            "security_assessment": {
                "available": False,
                "message": "Not collected yet",
                "detail_url": "/quick-hc/security-assessment",
            },
            "license_summary": {
                "available": False,
                "requested": False,
                "has_content": False,
                "message": "Not collected yet",
                "detail_url": "/quick-hc/license-summary",
            },
            "client_growth": {
                "available": False,
                "requested": False,
                "has_content": False,
                "record_count": 0,
                "message": "Not collected yet",
                "detail_url": "/metrics/client-growth",
            },
            "capacity_license": {
                "available": False,
                "requested": False,
                "has_content": False,
                "record_count": 0,
                "message": "Not collected yet",
                "detail_url": "/metrics/capacity-license",
            },
            "backup_job_summary": {
                "available": False,
                "requested": False,
                "has_content": False,
                "total_jobs": 0,
                "message": "No Backup Job Summary artifact available yet.",
                "detail_url": "/quick-hc",
            },
            "evidence": [],
        }

    monkeypatch.setattr(QuickHcReportService, "build_report", fake_build_report)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    assert called["used"] is True


def test_quick_hc_report_service_uses_registry_detail_urls_and_client_growth_has_no_stale_message(
    tmp_path, monkeypatch
) -> None:
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    with app.test_request_context():
        report = QuickHcReportService().build_report()

    assert report["security_assessment"]["detail_url"] == "/quick-hc"
    assert report["license_summary"]["detail_url"] == "/quick-hc"
    # ADR 0004 #25 / phase 6.5: client_growth & capacity_license render
    # canonically in the workspace now, so their detail link opens /quick-hc
    # (like SA/LS) — the dev /metrics/* pages were retired.
    assert report["client_growth"]["detail_url"] == "/quick-hc"
    assert report["capacity_license"]["detail_url"] == "/quick-hc"
    assert report["backup_job_summary"]["detail_url"] == "/quick-hc/backup-job-summary"
    assert "message" not in report["client_growth"]


def test_quick_hc_overview_shows_report_selection_checkboxes(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    # reportsplus.security_assessment holds its own module-level copy of
    # SECURITY_ASSESSMENT_CATALOG_DIR (imported at load time), so patch it too.
    import cvhealthcheck.reportsplus.security_assessment as rp_sa_module
    monkeypatch.setattr(rp_sa_module, "SECURITY_ASSESSMENT_CATALOG_DIR", tmp_path / "security_catalog")

    sa_catalog = tmp_path / "security_catalog"
    sa_catalog.mkdir(parents=True, exist_ok=True)
    artifact = build_security_assessment_artifact(
        [
            {"section": "Access Security", "parameter": "MFA enabled", "status": "Critical", "remarks": "Missing", "action": "Enable MFA"},
            {"section": "Auditing", "parameter": "Audit retention", "status": "Info", "remarks": "30 days", "action": "Review retention"},
            {"section": "Platform Security", "parameter": "Threat Indicator", "status": "Critical", "remarks": "Disabled", "action": "Enable"},
            {"section": "Company and Owners Security", "parameter": "Owner review", "status": "Good", "remarks": "Done", "action": "None"},
            {"section": "Capabilities", "parameter": "Feature lockdown", "status": "Warning", "remarks": "Review", "action": "Tighten"},
            {"section": "Hardening", "parameter": "DR backup", "status": "Warning", "remarks": "Missing", "action": "Configure"},
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        artifact,
        catalog_dir=sa_catalog,
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()

    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "window.QUICK_HC_INITIAL_DATA" in body
    assert "/static/quick_hc.css" in body
    assert "/static/quick_hc.js" in body
    assert "quick_hc.css?v=" in body
    assert "quick_hc.js?v=" in body
    assert 'id="left-catalog"' in body
    assert 'id="right-body"' in body
    assert 'id="report-form"' in body
    assert '"id": "environment"' in body
    assert '"id": "security_assessment"' in body
    assert '"id": "license_summary"' in body
    assert '"id": "client_growth"' in body
    assert '"id": "capacity_license"' in body
    assert '"id": "backup_job_summary"' in body
    assert '"id": "security_assessment.metadata"' in body
    assert '"id": "security_assessment.highlights"' in body
    assert '"id": "security_assessment.access_security"' in body
    assert '"id": "security_assessment.auditing"' in body
    assert '"id": "security_assessment.platform_security"' in body
    assert '"id": "security_assessment.company_and_owners_security"' in body
    assert '"id": "security_assessment.capabilities"' in body
    assert '"id": "security_assessment.hardening"' in body
    assert "CommCell Details" in body
    assert "Client Growth" in body
    assert "Capacity Licenses" in body
    assert "Backup Job Summary" in body
    assert "cvthing-logo-dark.png" in body
    assert "data-theme-toggle" in body
    assert "Generate Report" in body
    assert "Dashboard" not in body
    assert "Open full details" not in body
    assert "Full detail page" not in body
    assert "Not yet persisted" not in body
    assert "dataset_guid" not in body
    assert "HTTP status" not in body
    assert "data/catalog/" not in body


def test_quick_hc_subjects_always_emit_registry_description() -> None:
    import cvhealthcheck.quickhc.description_service as description_service_module

    temp_dir = Path("/tmp/test_quick_hc_subjects_always_emit_registry_description")
    temp_dir.mkdir(parents=True, exist_ok=True)
    for child in temp_dir.glob("*.json"):
        child.unlink()

    original_dir = description_service_module.DESCRIPTION_CATALOG_DIR
    description_service_module.DESCRIPTION_CATALOG_DIR = temp_dir
    app = create_app()
    try:
        with app.test_request_context("/quick-hc"):
            initial_data = build_subject_initial_data()
    finally:
        description_service_module.DESCRIPTION_CATALOG_DIR = original_dir

    subjects = {
        subject["id"]: subject
        for category in initial_data["cats"]
        for subject in category["subjects"]
    }
    assert set(subjects) == set(QUICK_HC_TILE_BY_ID)
    for tile_id, tile in QUICK_HC_TILE_BY_ID.items():
        assert subjects[tile_id]["description"] == tile.description
        assert subjects[tile_id]["description"]


def test_quick_hc_subject_initial_data_uses_registry_tile_order_and_explicit_dispatch(
    monkeypatch,
) -> None:
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module

    custom_tiles = (
        TileDefinition(
            id="security_assessment",
            title="Security Assessment",
            subtitle="Security",
            source_type="reportsplus",
            source_service="security_assessment_service",
            artifact_type="security_assessment",
            preview_renderer="security_assessment_preview",
            report_renderer="security_assessment_report",
            sources=(),
            sections=(),
            category="security",
            category_label="Security",
        ),
        TileDefinition(
            id="unknown_tile",
            title="Unknown Tile",
            subtitle="Unknown",
            source_type="unknown",
            source_service="unknown_service",
            artifact_type="unknown_artifact",
            preview_renderer="unknown_preview",
            report_renderer="unknown_report",
            sources=(),
            sections=(),
            category="security",
            category_label="Security",
        ),
        TileDefinition(
            id="environment",
            title="CommCell Details",
            subtitle="Environment",
            source_type="rest",
            source_service="commcell_identity",
            artifact_type="commcell",
            preview_renderer="commcell_preview",
            report_renderer="environment_report",
            sources=(),
            sections=(),
            category="identity",
            category_label="Identity",
        ),
    )

    monkeypatch.setattr(subject_data_service_module, "list_tiles", lambda: custom_tiles)
    monkeypatch.setattr(
        subject_data_service_module,
        "_legacy_loaders",
        lambda: {
            "security_assessment": lambda: {"payload": "security"},
            "environment": lambda: {"payload": "environment"},
        },
    )
    monkeypatch.setattr(
        subject_data_service_module,
        "_legacy_builders",
        lambda: {
            "security_assessment": lambda payload: {"id": "security_assessment", "payload": payload},
            # environment is dispatched with the db connection (it reads its card
            # rules from the catalog binding); accept and ignore it in the mock.
            "environment": lambda payload, db=None: {"id": "environment", "payload": payload},
        },
    )
    monkeypatch.setattr(
        subject_data_service_module,
        "_build_commcell_header",
        lambda payload: {"exists": bool(payload), "name": "header"},
    )

    app = create_app()
    with app.test_request_context("/quick-hc"):
        initial_data = build_subject_initial_data()

    assert [category["id"] for category in initial_data["cats"]] == ["security", "identity"]
    assert [subject["id"] for subject in initial_data["cats"][0]["subjects"]] == [
        "security_assessment"
    ]
    assert [subject["id"] for subject in initial_data["cats"][1]["subjects"]] == [
        "environment"
    ]
    assert initial_data["cats"][0]["subjects"][0]["payload"] == {"payload": "security"}
    assert initial_data["cats"][1]["subjects"][0]["payload"] == {"payload": "environment"}
    assert initial_data["commcell"] == {"exists": True, "name": "header"}


def test_quick_hc_workspace_sections_match_registry_contract_for_all_tiles(
    tmp_path, monkeypatch
) -> None:
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module

    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)

    monkeypatch.setattr(
        subject_data_service_module,
        "read_json",
        lambda *_args, **_kwargs: {
            "identity": {
                "hostName": "CommServe A",
                "csGUID": "commcell-01",
                "csVersionInfo": "11 SP40.47",
                "timeZone": "UTC",
            }
        },
    )

    security_artifact = build_security_assessment_artifact(
        [
            {"section": "Access Security", "parameter": "MFA enabled", "status": "Critical", "remarks": "Missing", "action": "Enable MFA"},
            {"section": "Auditing", "parameter": "Audit retention", "status": "Info", "remarks": "30 days", "action": "Review retention"},
            {"section": "Platform Security", "parameter": "Threat Indicator alert", "status": "Critical", "remarks": "Disabled", "action": "Enable alert"},
            {"section": "Company and Owners Security", "parameter": "Owner review", "status": "Good", "remarks": "Completed", "action": "None"},
            {"section": "Capabilities", "parameter": "Feature lockdown", "status": "Warning", "remarks": "Review", "action": "Tighten scope"},
            {"section": "Hardening", "parameter": "DR backup", "status": "Warning", "remarks": "Cloud copy missing", "action": "Configure backup"},
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    with app.test_request_context("/quick-hc"):
        initial_data = build_subject_initial_data()

    subjects = {
        subject["id"]: subject
        for category in initial_data["cats"]
        for subject in category["subjects"]
    }
    assert set(subjects) == set(QUICK_HC_TILE_BY_ID)
    for tile_id, tile in QUICK_HC_TILE_BY_ID.items():
        actual_section_ids = tuple(section["id"] for section in subjects[tile_id]["sections"])
        assert actual_section_ids == tile.section_ids


def test_quick_hc_renderer_has_no_redundant_commcell_identity_grid() -> None:
    """The header-CC identity grid (CommCell Name/Version/Timezone/ID from the
    CC object) was removed — it duplicated the environment card SECTION and showed
    the dirty "0:0:" timezone + GUID-as-ID. The expanded environment card is now
    the single CommCell Details display."""
    app = create_app()
    response = app.test_client().get("/static/quick_hc.js")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # the old per-CC-object identity grid block is gone
    assert "s.id === 'environment' && CC.exists" not in body
    assert "shown for all subjects" not in body


def test_quick_hc_renderer_removes_redundant_workspace_include_toggle() -> None:
    app = create_app()
    response = app.test_client().get("/static/quick_hc.js")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # Include toggle lives in config panel (toggle-switch), not as overview/sidebar checkboxes.
    assert 'class="toggle-track"' in body
    assert "toggleInclude('" in body
    assert "toggleSec('" in body
    assert "inp.name = 'selection_ids'; inp.value = s.id;" in body
    assert "si.name = 'selection_ids'; si.value = sec.id;" in body


def test_quick_hc_renderer_removes_full_detail_page_actions() -> None:
    app = create_app()
    response = app.test_client().get("/static/quick_hc.js")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Open full details" not in body
    assert "Full detail page" not in body
    assert "Import via detail page" not in body
    assert "rf-link" not in body
    assert "setActiveSrc(this.dataset.subj,this.dataset.src)" in body


def test_quick_hc_renderer_uses_shared_data_source_card_structure() -> None:
    app = create_app()
    response = app.test_client().get("/static/quick_hc.js")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "src-meta-panel" in body
    assert "src-meta-desc" in body
    assert "src-meta-empty" in body
    assert "No source metadata is available yet." in body
    assert "rest_command_center_api" in body
    assert "rest_reports_plus" in body
    assert "json_import" in body
    assert "csv_import" in body
    assert "html_import" in body
    assert "uploadAction" in body


def test_quick_hc_renderer_does_not_repeat_subject_title_in_report_sections_panel() -> None:
    app = create_app()
    response = app.test_client().get("/static/quick_hc.js")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '<div class="cfg-sec-title">Report Sections</div>' in body
    assert "sections available" not in body
    assert '<div style="font-size:13px;font-weight:600">${esc(s.name)}</div>' not in body
    assert "${secTiles}" in body
    assert "${esc(s.description || '')}" in body
    assert "${esc(s.subtitle || '')}</textarea>" not in body
    assert "saveDescription('" in body
    assert "Description saved." in body
    assert "Not yet persisted" not in body
    assert 'oninput="autoResizeDescription(this)"' in body
    # bindDescriptionEditor is still invoked post-render via requestAnimationFrame
    # (ADR 0004 phase 3 also mounts charts in the same rAF callback).
    assert "requestAnimationFrame(" in body
    assert "bindDescriptionEditor()" in body


def test_quick_hc_workspace_sources_use_standardized_shape_and_labels(
    tmp_path, monkeypatch
) -> None:
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module

    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)

    monkeypatch.setattr(
        subject_data_service_module,
        "read_json",
        lambda *_args, **_kwargs: {
            "identity": {
                "hostName": "CommServe A",
                "csGUID": "commcell-01",
                "csVersionInfo": "11 SP40.47",
                "timeZone": "UTC",
            }
        },
    )

    security_artifact = build_security_assessment_artifact(
        [{"section": "Access Security", "parameter": "MFA enabled", "status": "Critical", "remarks": "Missing", "action": "Enable MFA"}],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    with app.test_request_context("/quick-hc"):
        initial_data = build_subject_initial_data()

    subjects = {
        subject["id"]: subject
        for category in initial_data["cats"]
        for subject in category["subjects"]
    }

    expected_source_ids = [
        "rest_command_center_api",
        "rest_reports_plus",
        "json_import",
        "csv_import",
        "html_import",
    ]
    expected_source_names = [
        "REST / Command Center API",
        "REST / Reports Plus",
        "JSON import",
        "CSV import",
        "HTML import",
    ]

    for subject in subjects.values():
        assert subject["sources"]
        assert [source["id"] for source in subject["sources"]] == expected_source_ids
        assert [source["name"] for source in subject["sources"]] == expected_source_names
        for source in subject["sources"]:
            assert set(source).issuperset({"id", "name", "desc", "status", "meta", "actions"})
            assert source["status"] in {"v", "a", "n", "ni"}
            assert isinstance(source["meta"], list)
            assert isinstance(source["actions"], list)

    assert subjects["security_assessment"]["activeSource"] == "rest_reports_plus"
    assert subjects["license_summary"]["activeSource"] == "csv_import"
    # Session 3 of the unified-upload refactor switched the importUrl
    # from the hyphenated per-subject form to the underscored unified
    # form. Old hyphenated routes still work (session 4 deletes them).
    assert subjects["security_assessment"]["sources"][3]["actions"][0]["importUrl"] == "/quick-hc/security_assessment/import"
    assert subjects["security_assessment"]["sources"][4]["actions"][0]["importUrl"] == "/quick-hc/security_assessment/import"
    assert subjects["license_summary"]["sources"][3]["actions"][0]["importUrl"] == "/quick-hc/license_summary/import"
    assert subjects["license_summary"]["sources"][4]["actions"][0]["importUrl"] == "/quick-hc/license_summary/import"


def test_quick_hc_overview_license_summary_previews_real_fields(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '"id": "license_summary.metadata"' in body
    assert '"k": "SOURCE", "v": "CSV"' in body
    assert '"k": "IMPORTED"' in body
    assert '"k": "GENERATED ON"' in body
    assert '"k": "LICENSE EXPIRY"' in body
    assert '"title": "Other Licenses table"' in body
    assert '"title": "Agent / Feature Licenses table"' in body
    assert '"Cloud Storage"' in body
    assert '"Virtual Server"' in body
    assert '"pct": 0' in body
    assert "dataset_guid" not in body
    assert "HTTP status" not in body


def test_quick_hc_overview_renders_commcell_report_section_values(monkeypatch) -> None:
    import cvhealthcheck.quickhc.subject_data_service as subject_data_service_module

    # The real GET CommServ response shape (the .raw block) — the builder reads
    # card fields directly from it. commCellId 13183 renders hex "337f".
    monkeypatch.setattr(
        subject_data_service_module,
        "read_json",
        lambda *_args, **_kwargs: {
            "raw": {
                "commcell": {"commCellId": 13183, "commCellName": "CommServe A",
                             "csGUID": "C0FF-EE00-GUID"},
                "csTimeZone": {"TimeZoneID": 5, "TimeZoneName": "UTC"},
                "csVersionInfo": "11 SP40.47",
                "currentSPVersion": 40,
                "installedSPVersion": 40,
                "hostName": "commserve-a",
                "osType": "Windows",
                "releaseId": 16,
                "timeZone": "0:0:UTC",
            }
        },
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # The environment card is built through the shared per-field card path, fields
    # read directly from the real GET CommServ response. Rules (binding 0023):
    # Version presence -> good; Name format / Timezone enum -> safe good with no
    # spec; CommCell ID is hex(commCellId) and informational (bare).
    assert '"id": "environment.metadata"' in body
    assert '"label": "CommCell Name", "reason": "CommCell Name: no format pattern configured", "sev": "good", "unit": "", "value": "CommServe A"' in body
    assert '"label": "CommCell ID", "reason": "", "sev": null, "unit": "", "value": "337f"' in body   # hex(13183), not the GUID
    assert '"label": "CommCell GUID", "reason": "", "sev": null, "unit": "", "value": "C0FF-EE00-GUID"' in body
    assert '"label": "Version", "reason": "Version is set", "sev": "good", "unit": "", "value": "11 SP40.47"' in body
    assert '"label": "Timezone", "reason": "Timezone: no allowed-set configured", "sev": "good", "unit": "", "value": "UTC"' in body
    assert '"label": "Hostname", "reason": "", "sev": null, "unit": "", "value": "commserve-a"' in body


def test_quick_hc_overview_renders_security_assessment_report_section_values(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Platform Security",
                "parameter": "Threat Indicator alert",
                "status": "Critical",
                "remarks": "Disabled",
                "action": "Enable alert",
            },
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Warning",
                "remarks": "Recommended for admins",
                "action": "Enable MFA",
            },
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            },
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '"id": "security_assessment.summary"' in body
    assert '{"k": "TOTAL CHECKS", "v": "3"}' in body
    assert '{"cls": "err", "k": "CRITICAL", "v": "1"}' in body
    assert '{"cls": "warn", "k": "WARNING", "v": "1"}' in body
    assert '{"k": "INFO", "v": "1"}' in body
    assert '"id": "security_assessment.highlights"' in body
    assert '"title": "Threat Indicator alert"' in body
    assert '"title": "MFA enabled"' in body
    assert '"id": "security_assessment.platform_security"' in body
    assert '"id": "security_assessment.access_security"' in body
    assert '"id": "security_assessment.auditing"' in body
    assert '"title": "Platform Security"' in body
    assert '"title": "Access Security"' in body
    assert '"title": "Auditing"' in body
    assert '[["Threat Indicator alert", "Critical", "Disabled", "Enable alert"]]' in body
    assert '[["MFA enabled", "Warning", "Recommended for admins", "Enable MFA"]]' in body
    assert '[["Audit retention", "Info", "30 days", "Review retention"]]' in body


def test_quick_hc_security_assessment_detail_renders_all_artifact_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    artifact = build_security_assessment_artifact(
        [
            {"section": "Access Security", "parameter": "MFA enabled", "status": "Critical", "remarks": "Missing", "action": "Enable MFA"},
            {"section": "Auditing", "parameter": "Audit retention", "status": "Info", "remarks": "30 days", "action": "Review retention"},
            {"section": "Platform Security", "parameter": "Threat Indicator alert", "status": "Critical", "remarks": "Disabled", "action": "Enable alert"},
            {"section": "Company and Owners Security", "parameter": "Owner review", "status": "Good", "remarks": "Completed", "action": "None"},
            {"section": "Capabilities", "parameter": "Feature lockdown", "status": "Warning", "remarks": "Review", "action": "Tighten scope"},
            {"section": "Hardening", "parameter": "DR backup", "status": "Warning", "remarks": "Cloud copy missing", "action": "Configure backup"},
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().get("/quick-hc/security-assessment")

    assert response.status_code == 302
    assert "/quick-hc" in response.headers["Location"]


def test_quick_hc_overview_handles_missing_backup_job_summary_artifact(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    _patch_backup_job_summary_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert '"id": "backup_job_summary"' in body
    assert '"state": "nodata"' in body
    assert '"subtitle": "Not collected"' in body


def test_quick_hc_overview_renders_backup_job_summary_preview(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    response = app.test_client().get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert '"meta": "12 jobs"' in body
    assert '{"k": "TOTAL JOBS", "v": "12"}' in body
    assert '{"cls": "err", "k": "FAILED", "v": "2"}' in body
    assert '"meta": "1 failures"' in body
    assert '"title": "Recent jobs"' in body
    assert "dataset_guid" not in body


def test_quick_hc_report_post_license_summary_only_excludes_security_assessment(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["license_summary"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" not in body


def test_quick_hc_report_renders_selected_backup_job_summary_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)
    backup_catalog_dir = _patch_backup_job_summary_paths(tmp_path, monkeypatch)
    write_backup_job_summary_artifact(
        BACKUP_JOB_SUMMARY_ARTIFACT,
        catalog_dir=backup_catalog_dir,
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "backup_job_summary",
                "backup_job_summary.summary",
                "backup_job_summary.recent_failures",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Backup Job Summary" in body
    assert "Source Report" in body
    assert "Backup Job Summary" in body
    assert "Recent Failures" in body
    assert "Media issue" in body
    assert "Status Breakdown" not in body
    assert "Recent Jobs" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body
    assert "MFA enabled" not in body


def test_quick_hc_report_post_security_assessment_only_excludes_license_summary(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["security_assessment"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "MFA enabled" in body
    assert "License Summary" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body


def test_quick_hc_report_post_license_summary_workload_only_excludes_detail_tables(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "license_summary",
                "license_summary.workload_sections",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "License Summary" in body
    assert "Capacity Licenses" in body
    assert "Other Licenses" not in body
    assert "Agent and Feature Licenses" not in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body


def test_quick_hc_report_renders_license_summary_usage_visualization(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_WITH_UNPURCHASED,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "license_summary",
                "license_summary.other_licenses",
                "license_summary.agent_feature_licenses",
                "license_summary.workload_sections",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<th>Summary</th>" in body
    assert 'class="usage-summary-bar"' in body
    assert 'class="usage-summary-bar-fill"' in body
    assert "40%" in body
    assert "License not purchased" in body
    agent_table_idx = body.index("<h4>Agent and Feature Licenses</h4>")
    agent_client_agent_idx = body.index("<th>Client / Agent</th>", agent_table_idx)
    agent_status_idx = body.index("<th>Status</th>", agent_table_idx)
    assert agent_table_idx < agent_client_agent_idx < agent_status_idx
    assert body.find('class="usage-summary-bar"', agent_table_idx, body.index("</table>", agent_table_idx)) == -1
    assert "dataset_guid" not in body
    assert "HTTP status" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body


def test_quick_hc_report_post_security_assessment_summary_only_excludes_findings(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            },
            {
                "section": "Auditing",
                "parameter": "Audit retention",
                "status": "Info",
                "remarks": "30 days",
                "action": "Review retention",
            },
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "security_assessment",
                "security_assessment.summary",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body
    assert "Total checks" in body
    assert "Generated On" not in body
    assert "<th>Report</th>" not in body
    assert "Critical / Warning findings" not in body
    assert "Detailed Checks" not in body
    assert "MFA enabled" not in body
    assert "Audit retention" not in body


def test_quick_hc_report_post_security_assessment_selected_detail_sections_render(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            },
            {
                "section": "Platform Security",
                "parameter": "Threat Indicator alert",
                "status": "Warning",
                "remarks": "Disabled",
                "action": "Enable alert",
            },
            {
                "section": "Hardening",
                "parameter": "DR backup",
                "status": "Info",
                "remarks": "Cloud copy missing",
                "action": "Configure backup",
            },
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "security_assessment",
                "security_assessment.summary",
                "security_assessment.access_security",
                "security_assessment.hardening",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" in body
    assert "Detailed Checks" in body
    assert "Access Security" in body
    assert "Hardening" in body
    assert "Platform Security" not in body
    assert "MFA enabled" in body
    assert "DR backup" in body
    assert "Threat Indicator alert" not in body


def test_quick_hc_report_post_client_growth_only_excludes_other_optional_subjects(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["client_growth"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Client Growth History" in body
    assert "Latest Total Clients" in body
    assert "Net Growth Over Period" in body
    assert "Monthly Summary" in body
    assert "125" in body
    assert "2026-04 to 2026-05" in body
    assert 'id="client-growth-history-chart"' in body
    assert '"labels": ["2026-04", "2026-05"]' in body
    assert '"label": "Total clients"' in body
    assert "dataset_guid" not in body
    assert "Source report" not in body
    assert "Source dataset" not in body
    assert "Source widget" not in body
    assert "HTTP status" not in body
    assert "Normalized fields" not in body
    assert "Sample rows" not in body
    assert "Evidence / Sources" not in body
    assert "Artifact sources" not in body
    assert "data/catalog/" not in body
    assert "/tmp/" not in body
    assert "Security Assessment" not in body
    assert "License Summary" not in body
    assert "Capacity License" not in body


def test_quick_hc_report_post_client_growth_chart_only_excludes_monthly_table(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={
            "selection_ids": [
                "client_growth",
                "client_growth.chart",
            ]
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Client Growth History" in body
    assert 'id="client-growth-history-chart"' in body
    assert "Monthly Summary" not in body
    assert "Latest Total Clients" not in body
    assert "<th>Month</th>" not in body


def test_quick_hc_report_post_capacity_license_only_excludes_other_optional_subjects(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["capacity_license"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Capacity License" in body
    assert "CommServe A" in body
    assert "CommServe B" in body
    assert "Security Assessment" not in body
    assert "License Summary" not in body
    assert "Client Growth" not in body


def test_quick_hc_report_selected_missing_metric_subject_renders_gracefully(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    _patch_metrics_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["client_growth"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Client Growth" in body
    assert "Not collected yet" in body
    assert "Latest Total Clients" not in body


def test_quick_hc_report_post_unchecked_subject_omits_child_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/report",
        data={"selection_ids": ["security_assessment.summary"]},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Security Assessment" not in body
    assert "Total checks" not in body


def test_quick_hc_report_get_still_uses_default_sections(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)
    metrics_dir = _patch_metrics_paths(tmp_path, monkeypatch)

    security_artifact = build_security_assessment_artifact(
        [
            {
                "section": "Access Security",
                "parameter": "MFA enabled",
                "status": "Critical",
                "remarks": "Missing for admin users",
                "action": "Enable MFA",
            }
        ],
        source_type="rest",
        source={"report_id": "336"},
    )
    persist_security_assessment_artifact(
        security_artifact,
        catalog_dir=tmp_path / "security_catalog",
        registry_path=tmp_path / "security_registry.sqlite3",
    )
    license_artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persist_license_summary_artifact(
        license_artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )
    _write_metric_artifact(metrics_dir, "client_growth_summary", CLIENT_GROWTH_ARTIFACT)
    _write_metric_artifact(metrics_dir, "capacity_license_usage", CAPACITY_LICENSE_ARTIFACT)

    app = create_app()
    response = app.test_client().get("/quick-hc/report")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Environment" in body
    assert "Security Assessment" in body
    assert "Source Metadata" in body
    assert "Total checks" in body
    assert "Critical / Warning findings" in body
    assert "Detailed Checks" in body
    assert "License Summary" in body
    assert "Workload Summary Sections" in body
    assert "Cloud Storage" not in body
    assert "Virtual Server" not in body
    assert "Client Growth" in body
    assert "Monthly Summary" in body
    assert "Capacity License" in body
    assert "Latest Capacity Summary" in body


def test_quick_hc_report_builder_route_removed() -> None:
    app = create_app()

    response = app.test_client().get("/quick-hc/report/builder")

    assert response.status_code == 404
