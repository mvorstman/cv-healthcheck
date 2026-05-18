from __future__ import annotations

from io import BytesIO
import zipfile

from cvhealthcheck.license_summary.collect_rest import (
    collect_license_summary_rest,
    normalize_license_summary_rest_extraction,
    parse_license_summary_xlsx_recording,
)
from cvhealthcheck.license_summary.import_csv import parse_license_summary_csv
from cvhealthcheck.license_summary.import_html import parse_license_summary_html
from cvhealthcheck.license_summary.service import (
    LicenseSummaryService,
    load_active_license_summary_artifact,
    persist_license_summary_artifact,
)
from cvhealthcheck.security_assessment.models import CommCellContext, CustomerContext


CSV_SAMPLE = """\
License summary
Generated on: May 18, 2026 09:15:00 AM
CommCell Name,CommServe A
CommCell Version,11.36
Timezone,UTC
Last Collection Time,2026-05-18T08:55:00+00:00
License Expiry,2027-01-01
Last Generation Time,2026-05-18T09:00:00+00:00
Last Application Time,2026-05-17T21:00:00+00:00

Other Licenses - current usage details
License,Available Total,Used
Cloud Storage,100,40
Deduplication,25 TB,10 TB

Agent and Feature Licenses - current usage details
License,Permanent Total,Permanent Used,Term Total,Term Used,Client,Agent,Install Date
Virtual Server,50,12,10,3,Client A,Agent A,2026-05-01
Database,25,8,5,2,Client B,Agent B,2026-04-15
"""


HTML_SAMPLE = """\
<html>
  <head><title>License summary</title></head>
  <body>
    <h1>License summary</h1>
    <div>Generated on: May 18, 2026 09:15:00 AM</div>
    <div>CommCell Name: CommServe A</div>
    <div>CommCell Version: 11.36</div>
    <div>Timezone: UTC</div>
    <div>Last Collection Time: 2026-05-18T08:55:00+00:00</div>
    <div>License Expiry: 2027-01-01</div>
    <div>Last Generation Time: 2026-05-18T09:00:00+00:00</div>
    <div>Last Application Time: 2026-05-17T21:00:00+00:00</div>
    <h2>Other Licenses - current usage details</h2>
    <table>
      <thead>
        <tr><th>License</th><th>Available Total</th><th>Used</th></tr>
      </thead>
      <tbody>
        <tr><td>Cloud Storage</td><td>100</td><td>40</td></tr>
        <tr><td>Deduplication</td><td>25 TB</td><td>10 TB</td></tr>
      </tbody>
    </table>
    <h2>Agent and Feature Licenses - current usage details</h2>
    <table>
      <thead>
        <tr>
          <th>License</th><th>Permanent Total</th><th>Permanent Used</th><th>Term Total</th>
          <th>Term Used</th><th>Client</th><th>Agent</th><th>Install Date</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Virtual Server</td><td>50</td><td>12</td><td>10</td><td>3</td><td>Client A</td><td>Agent A</td><td>2026-05-01</td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_license_summary_csv_extracts_sections_and_metadata() -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")

    assert artifact["artifact_type"] == "license_summary"
    assert artifact["source_type"] == "csv"
    assert artifact["generated_on"] == "May 18, 2026 09:15:00 AM"
    assert artifact["commcell_name"] == "CommServe A"
    assert artifact["commcell_version"] == "11.36"
    assert artifact["timezone"] == "UTC"
    assert artifact["last_collection_time"] == "2026-05-18T08:55:00+00:00"
    assert artifact["license_expiry"] == "2027-01-01"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 2
    assert artifact["other_licenses"][1]["unit"] == "TB"
    assert artifact["agent_feature_licenses"][0]["license"] == "Virtual Server"


def test_parse_license_summary_html_extracts_canonical_records() -> None:
    artifact = parse_license_summary_html(HTML_SAMPLE, source_file="/tmp/license-summary.html")

    assert artifact["artifact_type"] == "license_summary"
    assert artifact["source_type"] == "html"
    assert artifact["generated_on"] == "May 18, 2026 09:15:00 AM"
    assert artifact["commcell_name"] == "CommServe A"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 1
    assert artifact["other_licenses"][0]["available_total"] == 100
    assert artifact["agent_feature_licenses"][0]["permanent_used"] == 12


def test_parse_license_summary_xlsx_recording_extracts_rest_artifact() -> None:
    workbook = _build_xlsx(
        [
            ["License summary"],
            ["Generated on: May 18, 2026 09:15:00 AM"],
            ["CommCell Name", "CommServe A"],
            ["CommCell Version", "11.36"],
            ["Timezone", "UTC"],
            [],
            ["Other Licenses - current usage details"],
            ["License", "Available Total", "Used"],
            ["Cloud Storage", "100", "40"],
            [],
            ["Agent and Feature Licenses - current usage details"],
            [
                "License",
                "Permanent Total",
                "Permanent Used",
                "Term Total",
                "Term Used",
                "Client",
                "Agent",
                "Install Date",
            ],
            ["Virtual Server", "50", "12", "10", "3", "Client A", "Agent A", "2026-05-01"],
        ]
    )

    artifact = parse_license_summary_xlsx_recording(workbook, source_file="/tmp/license-summary.xlsx")

    assert artifact["artifact_type"] == "license_summary"
    assert artifact["source_type"] == "rest"
    assert artifact["generated_on"] == "May 18, 2026 09:15:00 AM"
    assert artifact["commcell_name"] == "CommServe A"
    assert len(artifact["other_licenses"]) == 1
    assert len(artifact["agent_feature_licenses"]) == 1


def test_normalize_license_summary_rest_extraction_builds_canonical_lists() -> None:
    extraction = {
        "report": {"url": "/commandcenter/api/cr/reportsplusengine/reports/206"},
        "summary": {
            "report_name": "License summary",
            "report_ok": True,
            "report_http_status": 200,
            "collected_at": "2026-05-18T09:15:00+00:00",
        },
        "artifacts": {"metadata": "/tmp/report_206_metadata.json"},
        "datasets": [
            {"dataset_name": "Other Licenses - current usage details"},
            {"dataset_name": "Agent and Feature Licenses - current usage details"},
        ],
        "executions": [
            {
                "status": "EXECUTABLE",
                "sample_rows": [
                    {"License": "Cloud Storage", "Available Total": "100", "Used": "40"},
                    {"License": "Deduplication", "Available Total": "25 TB", "Used": "10 TB"},
                ],
            },
            {
                "status": "EXECUTABLE",
                "sample_rows": [
                    {
                        "License": "Virtual Server",
                        "Permanent Total": "50",
                        "Permanent Used": "12",
                        "Term Total": "10",
                        "Term Used": "3",
                        "Client": "Client A",
                        "Agent": "Agent A",
                        "Install Date": "2026-05-01",
                    }
                ],
            },
        ],
    }

    artifact = normalize_license_summary_rest_extraction(extraction)

    assert artifact["artifact_type"] == "license_summary"
    assert artifact["source_type"] == "rest"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 1
    assert artifact["other_licenses"][1]["unit"] == "TB"
    assert artifact["source"]["report_id"] == "206"


def test_license_summary_registry_write_and_registry_first_read(tmp_path) -> None:
    artifact = parse_license_summary_csv(CSV_SAMPLE, source_file="/tmp/license-summary.csv")
    customer = CustomerContext(customer_id="cust_license", customer_name="Customer License")
    commcell = CommCellContext(
        commcell_id="cc_license",
        commcell_name="CommServe A",
        customer_id="cust_license",
    )

    persisted = persist_license_summary_artifact(
        artifact,
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=commcell,
    )
    loaded = load_active_license_summary_artifact(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
        customer_context=customer,
        commcell_context=commcell,
    )
    service = LicenseSummaryService(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    current = service.get_current(
        customer_context=customer,
        commcell_context=commcell,
    )

    assert persisted["artifact_id"] == loaded["artifact_id"] == current["artifact_id"]
    assert loaded["loaded_from_path"] == persisted["file_path"]
    assert current["commcell_name"] == "CommServe A"
    assert len(current["other_licenses"]) == 2


def test_license_summary_service_collect_from_rest_persists_registry_artifact(
    tmp_path,
    monkeypatch,
) -> None:
    collected = {
        "extraction": {
            "summary": {
                "report_http_status": 200,
                "report_name": "License summary",
            }
        },
        "normalized": {
            "artifact_type": "license_summary",
            "source_type": "rest",
            "imported_at": "2026-05-18T09:15:00+00:00",
            "generated_on": "2026-05-18T09:15:00+00:00",
            "source": {
                "report_id": "206",
                "report_name": "License summary",
                "http_status": 200,
                "ok": True,
            },
            "other_licenses": [
                {
                    "license": "Cloud Storage",
                    "available_total": 100,
                    "used": 40,
                    "unit": None,
                    "raw_available_total": "100",
                    "raw_used": "40",
                    "raw_fields": {},
                }
            ],
            "agent_feature_licenses": [
                {
                    "license": "Virtual Server",
                    "permanent_total": 50,
                    "permanent_used": 12,
                    "term_total": 10,
                    "term_used": 3,
                    "client": "Client A",
                    "agent": "Agent A",
                    "install_date": "2026-05-01",
                    "raw_fields": {},
                }
            ],
        },
    }

    import cvhealthcheck.license_summary.service as service_module

    monkeypatch.setattr(service_module, "collect_license_summary_rest", lambda **kwargs: collected)

    service = LicenseSummaryService(
        catalog_dir=tmp_path / "catalog",
        registry_path=tmp_path / "registry.sqlite3",
    )
    result = service.collect_from_rest()
    current = service.get_current()

    assert result["normalized"]["source_type"] == "rest"
    assert result["normalized"]["artifact_id"] == current["artifact_id"]
    assert current["source"]["report_id"] == "206"
    assert len(current["other_licenses"]) == 1


def _build_xlsx(rows: list[list[str]]) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            if value == "":
                continue
            column = chr(64 + column_index)
            escaped = (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            cells.append(
                f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>%s</sheetData>
</worksheet>""" % "".join(sheet_rows)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()
