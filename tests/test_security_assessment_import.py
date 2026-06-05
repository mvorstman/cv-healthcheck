from __future__ import annotations

import io
import json

import pytest

from cvhealthcheck.auth.commvault_auth import SESSION_TOKEN_KEY
from cvhealthcheck.security_assessment.import_csv import parse_security_assessment_csv
from cvhealthcheck.security_assessment.import_html import parse_security_assessment_html
from cvhealthcheck.security_assessment.normalize import (
    CANONICAL_FINDING_KEYS,
    build_security_assessment_artifact,
    write_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.service import (
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    import_security_assessment_upload,
)
from cvhealthcheck.web.app import create_app


def _sa_panel_html() -> str:
    """A Security-Assessment HTML export shaped for the GENERIC extractor's
    catalog bindings (.panel-table-title + a Parameter/Status/Remarks/Action
    table per section). All six catalog sections present — the dispatcher
    fail-whole's on any missing section. Used by the post-SA-migration upload
    tests (the generic path, unlike the bespoke parser, keys on .panel-table-title)."""
    sections = ["Access Security", "Auditing", "Platform Security",
                "Company and Owners Security", "Capabilities", "Hardening"]
    blocks = "\n".join(
        f'<div class="panel"><div class="panel-table-title">{s}</div>'
        '<table><thead><tr><th>Parameter</th><th>Status</th><th>Remarks</th>'
        '<th>Action</th></tr></thead><tbody><tr>'
        f'<td>{s} check</td><td>Good</td><td>ok</td><td></td></tr></tbody></table></div>'
        for s in sections
    )
    return f'<html><head><title>Security Assessment</title></head><body>{blocks}</body></html>'


SA_PANEL_HTML = _sa_panel_html()


HTML_SAMPLE = """\
<html>
  <head><title>Security Assessment</title></head>
  <body>
    <h1>Security Assessment</h1>
    <div>Generated on: May 17, 2026 07:00:14 PM</div>
    <h2>Access Security</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>MFA enabled</td><td>Critical</td><td>Missing for admin users</td><td>Enable MFA</td></tr>
      </tbody>
    </table>
    <h2>Auditing</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>Audit retention</td><td>Info</td><td>30 days</td><td>Review retention</td></tr>
      </tbody>
    </table>
    <h2>Platform Security</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>TLS version</td><td>Good</td><td>TLS 1.2 enforced</td><td></td></tr>
      </tbody>
    </table>
    <h2>Company and Owners Security</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>Owner review</td><td>Warning</td><td>Annual review overdue</td><td>Schedule review</td></tr>
      </tbody>
    </table>
    <h2>Capabilities</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>Ransomware protection</td><td>Info</td><td>Feature available</td><td>Assess rollout</td></tr>
      </tbody>
    </table>
    <h2>Hardening</h2>
    <table>
      <thead>
        <tr><th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td>Unused ports</td><td>Critical</td><td>Close unused ports</td><td>Restrict listeners</td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


NOISY_HTML_SAMPLE = """\
<html>
  <head><title>Security Assessment</title></head>
  <body>
    <h1>Security Assessment</h1>
    <div>Generated on: May 17, 2026 07:00:14 PM</div>
    <h3>Detailed Checks</h3>
    <div class="dataTables_wrapper">
      <div class="dataTables_filter">Parameter Status Remarks Action</div>
      <div class="section-panel">
        <h4>Hardening</h4>
        <table>
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Status</th>
              <th>Remarks</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Unused ports</td>
              <td>Critical</td>
              <td>Close unused ports</td>
              <td>- Restrict listeners
- Remove legacy ports</td>
            </tr>
            <tr>
              <td>Unused ports</td>
              <td>Critical</td>
              <td>Close unused ports</td>
              <td>- Restrict listeners
- Remove legacy ports</td>
            </tr>
            <tr>
              <td colspan="4">1 to 3 of 3 entries</td>
            </tr>
            <tr>
              <td>Parameter</td>
              <td>Status</td>
              <td>Remarks</td>
              <td>Action</td>
            </tr>
            <tr>
              <td>Disable legacy auth</td>
              <td>Warning</td>
              <td>Legacy auth remains enabled</td>
              <td>Review settings</td>
            </tr>
            <tr>
              <td></td>
              <td></td>
              <td></td>
              <td></td>
            </tr>
          </tbody>
          <tfoot>
            <tr><td colspan="4">1 to 3 of 3 entries</td></tr>
          </tfoot>
        </table>
      </div>
    </div>
  </body>
</html>
"""


CSV_SAMPLE = """\
Security Assessment
Generated on: May 17, 2026 07:00:14 PM
Access Security
"Parameter","Status","Remarks","Action"
"MFA enabled","Critical","Missing for admin users
- local admin
- service account","Enable MFA"
Auditing
"Parameter","Status","Remarks","Action"
"Audit retention","Info","30 days","Review retention"
"""


def test_parse_security_assessment_html_extracts_all_sections() -> None:
    artifact = parse_security_assessment_html(
        HTML_SAMPLE,
        source_file="/tmp/security-assessment.html",
    )

    assert artifact["artifact_type"] == "security_assessment"
    assert artifact["source_type"] == "html"
    assert artifact["source_file"] == "/tmp/security-assessment.html"
    assert artifact["generated_on"] == "May 17, 2026 07:00:14 PM"
    assert artifact["sections"] == [
        "Access Security",
        "Auditing",
        "Platform Security",
        "Company and Owners Security",
        "Capabilities",
        "Hardening",
    ]
    assert artifact["finding_count"] == 6
    assert artifact["status_counts"]["Critical"] == 2
    assert artifact["status_counts"]["Warning"] == 1
    assert artifact["status_counts"]["Info"] == 2
    assert artifact["status_counts"]["Good"] == 1
    assert artifact["findings"][0]["parameter"] == "MFA enabled"
    assert artifact["findings"][0]["action"] == "Enable MFA"


def test_parse_security_assessment_html_ignores_rendered_page_noise() -> None:
    artifact = parse_security_assessment_html(
        NOISY_HTML_SAMPLE,
        source_file="/tmp/security-assessment-noisy.html",
    )

    assert artifact["sections"] == ["Hardening"]
    assert artifact["finding_count"] == 2
    assert [finding["parameter"] for finding in artifact["findings"]] == [
        "Unused ports",
        "Disable legacy auth",
    ]
    assert artifact["findings"][0]["section"] == "Hardening"
    assert artifact["findings"][0]["action"] == "- Restrict listeners\n- Remove legacy ports"

    flattened = "\n".join(
        "\n".join(
            [
                finding["parameter"],
                finding["status"],
                finding["remarks"],
                finding["action"],
            ]
        )
        for finding in artifact["findings"]
    )
    assert "1 to 3 of 3 entries" not in flattened
    assert "Parameter Status Remarks Action" not in flattened
    assert "Detailed Checks" not in flattened
    for finding in artifact["findings"]:
        assert tuple(finding.keys()) == CANONICAL_FINDING_KEYS


def test_build_security_assessment_artifact_rejects_noisy_flattened_findings() -> None:
    artifact = build_security_assessment_artifact(
        [
            {
                "section": "Hardening",
                "parameter": "Unused ports",
                "status": "Critical",
                "remarks": "Close unused ports",
                "action": "Restrict listeners",
                "raw_text": "should not persist",
            },
            {
                "section": "Detailed Checks",
                "parameter": "Parameter Status Remarks Action",
                "status": "Info",
                "remarks": "1 to 3 of 3 entries",
                "action": "Detailed Checks",
                "raw_text": "flattened UI blob",
            },
        ],
        source_type="html",
        source_file="/tmp/security-assessment.html",
    )

    assert artifact["finding_count"] == 1
    assert artifact["findings"][0]["parameter"] == "Unused ports"
    assert tuple(artifact["findings"][0].keys()) == CANONICAL_FINDING_KEYS
    rendered = "\n".join(str(value) for value in artifact["findings"][0].values())
    assert "raw_text" not in rendered
    assert "Parameter Status Remarks Action" not in rendered


def test_parse_security_assessment_csv_preserves_multiline_remarks() -> None:
    artifact = parse_security_assessment_csv(
        CSV_SAMPLE,
        source_file="/tmp/security-assessment.csv",
    )

    assert artifact["artifact_type"] == "security_assessment"
    assert artifact["source_type"] == "csv"
    assert artifact["source_file"] == "/tmp/security-assessment.csv"
    assert artifact["generated_on"] == "May 17, 2026 07:00:14 PM"
    assert artifact["sections"] == ["Access Security", "Auditing"]
    assert artifact["finding_count"] == 2
    assert artifact["status_counts"]["Critical"] == 1
    assert artifact["status_counts"]["Info"] == 1
    assert artifact["findings"][0]["remarks"] == "Missing for admin users\n- local admin\n- service account"
    assert artifact["findings"][1]["parameter"] == "Audit retention"


def test_writer_updates_latest_json_artifacts(tmp_path) -> None:
    artifact = parse_security_assessment_html(
        HTML_SAMPLE,
        source_file="/tmp/security-assessment.html",
    )

    paths = write_security_assessment_artifact(artifact, catalog_dir=tmp_path)

    latest_html = tmp_path / "latest_html.json"
    latest = tmp_path / "latest.json"
    assert paths["latest_source"] == str(latest_html)
    assert paths["latest"] == str(latest)
    assert latest_html.exists()
    assert latest.exists()
    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["source_type"] == "html"
    assert latest_payload["finding_count"] == 6


# The dev /security-assessment/import route that used to drive these was
# retired with the whole dev SA surface; the workspace SA upload now uses the
# generic extractor, so import_security_assessment_upload is route-orphaned.
# These unit-test the importer's behavior directly (returned artifact, raw file
# saved, legacy-not-written) — the old "HTML/CSV import completed" success
# string was the dev route's flash, not the importer's, so it falls away with
# the route round-trip.
def test_html_upload_imports_and_persists(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    artifact = import_security_assessment_upload(
        io.BytesIO(HTML_SAMPLE.encode("utf-8")),
        original_filename="assessment.html",
    )

    assert artifact["source_type"] == "html"
    assert int(artifact.get("finding_count") or 0) > 0
    # Option A — fresh imports no longer write the legacy per-domain store.
    assert not (tmp_path / "catalog" / "latest_html.json").exists()
    assert not (tmp_path / "catalog" / "latest.json").exists()
    # Raw upload is saved to the imports dir.
    saved_files = list((tmp_path / "imports").glob("*.html"))
    assert len(saved_files) == 1


def test_csv_upload_imports_and_persists(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    artifact = import_security_assessment_upload(
        io.BytesIO(CSV_SAMPLE.encode("utf-8")),
        original_filename="assessment.csv",
    )

    assert artifact["source_type"] == "csv"
    assert int(artifact.get("finding_count") or 0) > 0
    # Option A — fresh imports no longer write the legacy per-domain store.
    assert not (tmp_path / "catalog" / "latest_csv.json").exists()
    assert not (tmp_path / "catalog" / "latest.json").exists()
    saved_files = list((tmp_path / "imports").glob("*.csv"))
    assert len(saved_files) == 1


def test_quick_hc_security_assessment_page_shows_standard_import_panel(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    app = create_app()
    response = app.test_client().get("/quick-hc/security-assessment")

    assert response.status_code == 302
    assert "/quick-hc" in response.headers["Location"]


def test_quick_hc_security_assessment_upload_imports_html_and_redirects(
    tmp_path, monkeypatch
) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    app = create_app()
    # Session 4 deleted the legacy /quick-hc/security-assessment/import
    # route; this URL-coupled test now uses the unified route.
    response = app.test_client().post(
        "/quick-hc/security_assessment/import",
        data={
            "assessment_file": (io.BytesIO(HTML_SAMPLE.encode("utf-8")), "assessment.html")
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200


# The bespoke /quick-hc/security-assessment/collect route, the
# /security-assessment?refresh=1 REST refresh path, and the
# extract_security_assessment helper were all retired in ADR 0003
# phase 4. SA now collects via the generic /quick-hc/<subject_id>/collect
# route — coverage for that path lives in tests/test_rest_extractor.py
# (the generic catalog-driven extractor's behavior).


def test_fresh_security_assessment_import_creates_no_legacy_artifact_files(
    tmp_path, monkeypatch
) -> None:
    """Regression test for Option A, updated for the SA migration (PR2).

    A fresh Security Assessment HTML import now goes through the generic
    workspace route (/quick-hc/security_assessment/import, "file" field) and the
    generic dispatcher — it writes ONLY the canonical store, never the bespoke
    legacy artifact JSON in ``data/catalog/security_assessment/``.

    The contract this test pins:
        - No ``data/catalog/security_assessment/*.json`` files are produced.
        - The canonical store has the new artifact.
    """
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    # The generic dispatcher writes via make_active_project_store; patch it to a
    # tmp store to inspect it.
    import cvhealthcheck.web.routes.quick_hc as _qhc
    from cvhealthcheck.artifacts.store import ArtifactStore
    _store = ArtifactStore("default", "default", base_dir=tmp_path / "data" / "catalog" / "artifacts")
    monkeypatch.setattr(_qhc, "make_active_project_store", lambda *a, **k: _store)

    app = create_app()
    response = app.test_client().post(
        "/quick-hc/security_assessment/import",
        data={"file": (io.BytesIO(SA_PANEL_HTML.encode("utf-8")), "assessment.html")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    legacy_artifact_files = list((tmp_path / "catalog").rglob("*.json"))
    assert legacy_artifact_files == [], (
        f"generic SA upload wrote bespoke legacy artifact files "
        f"{legacy_artifact_files}"
    )

    # Confirm the canonical store received the artifact instead.
    canonical_files = list((tmp_path / "data" / "catalog" / "artifacts").rglob("*.json"))
    assert canonical_files, "canonical store should have received the artifact"


def test_upload_rejects_missing_file(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    with pytest.raises(SecurityAssessmentImportError, match="No file selected."):
        import_security_assessment_upload(io.BytesIO(b""), original_filename="")


def test_upload_rejects_unsupported_extension(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    with pytest.raises(SecurityAssessmentImportError, match="Unsupported file type."):
        import_security_assessment_upload(
            io.BytesIO(b"not valid"), original_filename="assessment.txt"
        )


def test_upload_rejects_empty_findings(tmp_path, monkeypatch) -> None:
    _patch_security_assessment_paths(tmp_path, monkeypatch)

    empty_html = b"<html><head><title>Security Assessment</title></head><body></body></html>"
    with pytest.raises(
        SecurityAssessmentImportError, match="HTML import produced no findings."
    ):
        import_security_assessment_upload(
            io.BytesIO(empty_html), original_filename="assessment.html"
        )


def _patch_security_assessment_paths(tmp_path, monkeypatch) -> None:
    catalog_dir = tmp_path / "catalog"
    imports_dir = tmp_path / "imports"
    registry_path = tmp_path / "registry.sqlite3"

    import cvhealthcheck.security_assessment.artifact as artifact_module
    import cvhealthcheck.reportsplus.security_assessment as security_assessment_module
    import cvhealthcheck.security_assessment.normalize as normalize_module
    import cvhealthcheck.security_assessment.service as service_module

    monkeypatch.setattr(artifact_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(normalize_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(security_assessment_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_IMPORTS_DIR", imports_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_CATALOG_DIR", catalog_dir)
    monkeypatch.setattr(service_module, "SECURITY_ASSESSMENT_REGISTRY_PATH", registry_path)
