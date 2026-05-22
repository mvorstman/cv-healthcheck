from __future__ import annotations

import json

from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.service import persist_license_summary_artifact
from cvhealthcheck.quickhc.description_service import (
    load_description_override,
    resolve_tile_description,
    save_description_override,
)
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID
from cvhealthcheck.web.app import create_app


LICENSE_CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
CommCell ID,commcell-01
Customer ID,customer-01
License Expiry,Dec 31, 2026

Other Licenses - current usage details
License,Available Total,Used
Cloud Storage,100,40
"""


def _patch_description_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.quickhc.description_service as description_service_module

    monkeypatch.setattr(
        description_service_module,
        "DESCRIPTION_CATALOG_DIR",
        tmp_path / "descriptions",
    )


def _patch_license_summary_paths(tmp_path, monkeypatch) -> None:
    import cvhealthcheck.license_summary.service as license_summary_service_module
    import cvhealthcheck.license_summary.artifact as license_summary_artifact_module

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


def test_resolve_tile_description_uses_registry_default_without_override(
    tmp_path, monkeypatch
) -> None:
    _patch_description_paths(tmp_path, monkeypatch)

    assert resolve_tile_description("security_assessment") == QUICK_HC_TILE_BY_ID["security_assessment"].description


def test_resolve_tile_description_prefers_saved_override(tmp_path, monkeypatch) -> None:
    _patch_description_paths(tmp_path, monkeypatch)

    saved = save_description_override("security_assessment", "Customer-safe override")

    assert saved["tile_id"] == "security_assessment"
    assert saved["description"] == "Customer-safe override"
    assert saved["version"] == 1
    assert load_description_override("security_assessment") == saved
    assert resolve_tile_description("security_assessment") == "Customer-safe override"


def test_quick_hc_description_save_endpoint_persists_override(tmp_path, monkeypatch) -> None:
    _patch_description_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().post(
        "/api/quick-hc/subject/security_assessment/description",
        json={"description": "Saved through API"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["tile_id"] == "security_assessment"
    assert payload["description"] == "Saved through API"
    assert payload["version"] == 1
    assert resolve_tile_description("security_assessment") == "Saved through API"


def test_saving_description_override_does_not_modify_canonical_artifact(
    tmp_path, monkeypatch
) -> None:
    _patch_description_paths(tmp_path, monkeypatch)
    _patch_license_summary_paths(tmp_path, monkeypatch)

    artifact = parse_license_summary_csv(
        LICENSE_CSV_SAMPLE,
        source_file="/tmp/license-summary.csv",
    )
    persisted = persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "license_catalog",
        registry_path=tmp_path / "license_registry.sqlite3",
    )
    artifact_path = persisted["artifact_paths"]["artifact"]
    before = json.loads(open(artifact_path, encoding="utf-8").read())

    save_description_override("license_summary", "Presentation override only")

    after = json.loads(open(artifact_path, encoding="utf-8").read())
    assert after == before
