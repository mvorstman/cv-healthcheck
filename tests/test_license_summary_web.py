from __future__ import annotations

import io

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.auth.commvault_auth import SESSION_TOKEN_KEY
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.web.app import create_app


CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A

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


def test_quick_hc_license_summary_page_renders_registry_backed_artifact(tmp_path, monkeypatch) -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    client = app.test_client()

    response = client.get("/quick-hc/license-summary")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "License Summary" in body
    assert "Collect via REST" in body
    assert "Import License Summary" in body
    assert "CommServe A" in body
    assert "Capacity Licenses" in body
    assert "Backup and Recovery" in body
    assert "Cloud Storage" in body
    assert "Virtual Server" in body
    assert "N/A" in body


def test_quick_hc_index_includes_license_summary_link(tmp_path, monkeypatch) -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    client = app.test_client()

    response = client.get("/quick-hc")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/quick-hc/license-summary" in body
    assert "1 other licenses" in body
    assert '"title": "Agent / Feature Licenses table"' in body
    assert '"Virtual Server"' in body


def test_quick_hc_license_summary_upload_imports_csv_and_redirects(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_IMPORTS_DIR",
        tmp_path / "imports",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/quick-hc/license-summary/import",
        data={
            "license_summary_file": (
                io.BytesIO(CSV_SAMPLE.encode("utf-8")),
                "license-summary.csv",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "import completed" in body
    assert "Backup and Recovery" in body
    assert "Cloud Storage" in body
    assert "Virtual Server" in body


def test_quick_hc_license_summary_upload_rejects_unsupported_type(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/quick-hc/license-summary/import",
        data={
            "license_summary_file": (
                io.BytesIO(b"not used"),
                "license-summary.txt",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Unsupported file type" in response.get_data(as_text=True)


def test_quick_hc_license_summary_collect_calls_service_and_redirects(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    called: dict[str, object] = {}

    def fake_collect_from_rest(self, *, client=None, **kwargs):
        called["client"] = client
        return {
            "artifact": str(tmp_path / "catalog" / "latest.json"),
            "normalized": {
                "source": {"http_status": 200},
                "workload_summary_sections": [
                    {
                        "section_name": "Capacity Licenses",
                        "rows": [{"license": "Backup and Recovery"}],
                    }
                ],
                "other_licenses": [{"license": "Cloud Storage"}],
                "agent_feature_licenses": [{"license": "Virtual Server"}],
            },
        }

    monkeypatch.setattr(
        license_summary_service_module.LicenseSummaryService,
        "collect_from_rest",
        fake_collect_from_rest,
    )

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session[SESSION_TOKEN_KEY] = "test-token"

    response = client.post(
        "/quick-hc/license-summary/collect",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert called["client"] is not None
    body = response.get_data(as_text=True)
    assert "REST collection completed" in body


def test_quick_hc_license_summary_page_renders_na_for_missing_license_expiry(tmp_path, monkeypatch) -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    artifact["license_expiry"] = None
    persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )

    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_REGISTRY_PATH",
        tmp_path / "registry.sqlite3",
    )
    monkeypatch.setattr(
        license_summary_service_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )
    monkeypatch.setattr(
        license_summary_artifact_module,
        "LICENSE_SUMMARY_CATALOG_DIR",
        tmp_path / "catalog",
    )

    app = create_app()
    client = app.test_client()

    response = client.get("/quick-hc/license-summary")

    assert response.status_code == 200
    assert "N/A" in response.get_data(as_text=True)


def test_quick_hc_license_summary_collect_requires_login() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post("/quick-hc/license-summary/collect")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
