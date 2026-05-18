from __future__ import annotations

import io

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.web.app import create_app


CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
License Expiry,2027-01-01

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
    assert "CommServe A" in body
    assert "Cloud Storage" in body
    assert "Virtual Server" in body
    assert "2027-01-01" in body


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
    assert "1 agent/feature licenses" in body


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
