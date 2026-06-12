from __future__ import annotations

from io import BytesIO
import zipfile

from cvhealthcheck.api_client import ApiResult
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
CommCell ID,2
Registration Code,ABCD-1234-EFGH-5678
CommCell Version,11.36
Timezone,UTC
Last Collection Time,2026-05-18T08:55:00+00:00
License Expiry,2027-01-01
Last Generation Time,2026-05-18T09:00:00+00:00
Last Application Time,2026-05-17T21:00:00+00:00

Capacity Licenses
License,Available Total (TB),Permanent Purchased (TB),Term Purchased (TB),Used (TB),Used %,Summary
Backup and Recovery,100,100,0,0.00,0%,0%

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
    <div>CommCell ID: 2</div>
    <div>Registration Code: ABCD-1234-EFGH-5678</div>
    <div>CommCell Version: 11.36</div>
    <div>Timezone: UTC</div>
    <div>Last Collection Time: 2026-05-18T08:55:00+00:00</div>
    <div>License Expiry: 2027-01-01</div>
    <div>Last Generation Time: 2026-05-18T09:00:00+00:00</div>
    <div>Last Application Time: 2026-05-17T21:00:00+00:00</div>
    <h2>Capacity Licenses</h2>
    <table>
      <thead>
        <tr>
          <th>License</th><th>Available Total (TB)</th><th>Permanent Purchased (TB)</th><th>Term Purchased (TB)</th>
          <th>Used (TB)</th><th>Used %</th><th>Summary</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Backup and Recovery</td><td>100</td><td>100</td><td>0</td><td>0.00</td><td>0%</td><td>0%</td></tr>
      </tbody>
    </table>
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
    assert artifact["commcell_id"] == "2"
    assert artifact["commcell_version"] == "11.36"
    assert artifact["masked_registration_code"] == "ABCD***********5678"
    assert artifact["timezone"] == "UTC"
    assert artifact["last_collection_time"] == "2026-05-18T08:55:00+00:00"
    assert artifact["license_expiry"] == "2027-01-01"
    assert len(artifact["workload_summary_sections"]) == 1
    assert artifact["workload_summary_sections"][0]["section_name"] == "Capacity Licenses"
    assert artifact["workload_summary_sections"][0]["rows"][0]["license"] == "Backup and Recovery"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 2
    assert artifact["other_licenses"][1]["unit"] == "TB"
    # Combined-cell row in the CSV ("25 TB" / "10 TB") — same fix as HTML
    # applies because both paths go through normalize_other_license_record.
    assert artifact["other_licenses"][1]["available_total"] == 25
    assert artifact["other_licenses"][1]["used"] == 10
    assert artifact["agent_feature_licenses"][0]["license"] == "Virtual Server"


def test_parse_license_summary_html_extracts_canonical_records() -> None:
    artifact = parse_license_summary_html(HTML_SAMPLE, source_file="/tmp/license-summary.html")

    assert artifact["artifact_type"] == "license_summary"
    assert artifact["source_type"] == "html"
    assert artifact["generated_on"] == "May 18, 2026 09:15:00 AM"
    assert artifact["commcell_name"] == "CommServe A"
    assert artifact["masked_registration_code"] == "ABCD***********5678"
    assert len(artifact["workload_summary_sections"]) == 1
    assert artifact["workload_summary_sections"][0]["rows"][0]["usage_percent"] == "0%"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 1
    assert artifact["other_licenses"][0]["available_total"] == 100
    assert artifact["agent_feature_licenses"][0]["permanent_used"] == 12
    # Combined-cell row ("25 TB" / "10 TB") — was previously dropped by
    # parse_number's float-parse-the-whole-string path. The numeric
    # prefix must be extracted now.
    assert artifact["other_licenses"][1]["available_total"] == 25
    assert artifact["other_licenses"][1]["used"] == 10
    assert artifact["other_licenses"][1]["unit"] == "TB"


def test_parse_license_summary_html_extracts_value_and_unit_combined_cell() -> None:
    """Matches the user-reported real-world row shape: cells like
    "500 VMs" / "0 VMs" (value + space + unit in one <td>).

    Without the parse_number regex-extraction fix, both available_total
    and used would be None and only the unit would survive — exactly
    the symptom the user reported (Other Licenses table renders blank
    columns for value/used).
    """
    html = """
    <html><body>
      <h2>Other Licenses - current usage details</h2>
      <table>
        <thead><tr><th>License</th><th>Available Total</th><th>Used</th></tr></thead>
        <tbody>
          <tr><td>VM Sockets</td><td>0 sockets</td><td>0 sockets</td></tr>
          <tr><td>Auto Recovery</td><td>500 VMs</td><td>0 VMs</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    artifact = parse_license_summary_html(html, source_file="/tmp/x.html")

    rows = artifact["other_licenses"]
    assert len(rows) == 2

    assert rows[0]["license"] == "VM Sockets"
    assert rows[0]["available_total"] == 0
    assert rows[0]["used"] == 0
    assert rows[0]["unit"] == "sockets"

    assert rows[1]["license"] == "Auto Recovery"
    assert rows[1]["available_total"] == 500
    assert rows[1]["used"] == 0
    assert rows[1]["unit"] == "VMs"


def test_parse_license_summary_html_handles_commvault_export_markup_shape() -> None:
    """Real Commvault HTML exports wrap section titles in
    <span class="component-title-text"> inside nested <div> wrappers,
    not in <h2>/<h3> headings. The original find_previous heuristic
    returned the table's own concatenated text as the section_name —
    no match against SUMMARY_SECTION_NAMES — so every workload section
    was silently dropped. In addition, when workload tables omit unit
    qualifiers ("Available Total" / "Used" rather than "Available
    Total (TB)" / "Used (TB)"), the header-only classifier returns
    "other" and the rows get mis-bucketed into other_licenses. Both
    must be fixed together: section_name resolution must walk past
    nested divs to find the real title span, and the parse-loop must
    route section_name-in-SUMMARY_SECTION_NAMES tables to the
    workload bucket regardless of classifier output.
    """
    html = """
    <html><body>
      <h1>License summary</h1>
      <div class="section">
        <div class="component-title">
          <span class="input-title tileHelpLabels component-title-text">Capacity Licenses</span>
        </div>
        <div class="component-body">
          <div class="exportTable">
            <table>
              <thead><tr>
                <th>License</th><th>Available Total (TB)</th><th>Used (TB)</th><th>Summary</th>
              </tr></thead>
              <tbody>
                <tr><td>Backup and Recovery</td><td>100</td><td>0</td><td>0%</td></tr>
                <tr><td>Snapshot</td><td>500</td><td>0</td><td>0%</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="section">
        <div class="component-title">
          <span class="input-title tileHelpLabels component-title-text">Virtualization Licenses</span>
        </div>
        <div class="component-body">
          <div class="exportTable">
            <table>
              <thead><tr>
                <th>License</th><th>Available Total</th><th>Used</th><th>Summary</th>
              </tr></thead>
              <tbody>
                <tr><td>VM Sockets</td><td>0 sockets</td><td>0 sockets</td><td>License not purchased</td></tr>
                <tr><td>Auto Recovery</td><td>500 VMs</td><td>0 VMs</td><td>0%</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="section">
        <div class="component-title">
          <span class="input-title tileHelpLabels component-title-text">Other Licenses</span>
        </div>
        <div class="component-body">
          <div class="exportTable">
            <table>
              <thead><tr>
                <th>License</th><th>Available Total</th><th>Used</th><th>Summary</th>
              </tr></thead>
              <tbody>
                <tr><td>E-Discovery For Files</td><td>100 TB</td><td>0</td><td>0%</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </body></html>
    """
    artifact = parse_license_summary_html(html, source_file="/tmp/real-shape.html")

    # All three workload tables resolve to their correct titles.
    sections_by_name = {
        section["section_name"]: section
        for section in artifact["workload_summary_sections"]
    }
    assert set(sections_by_name) == {
        "Capacity Licenses",
        "Virtualization Licenses",
        "Other Licenses",
    }

    # Row counts per section.
    assert len(sections_by_name["Capacity Licenses"]["rows"]) == 2
    assert len(sections_by_name["Virtualization Licenses"]["rows"]) == 2
    assert len(sections_by_name["Other Licenses"]["rows"]) == 1

    # Virtualization Licenses uses bare "Available Total" / "Used"
    # headers — without the parse-loop fix, the classifier returns
    # "other" and these rows would end up in other_licenses. Pin both
    # invariants: rows land in the right section, and other_licenses
    # is empty.
    assert artifact["other_licenses"] == []
    assert artifact["agent_feature_licenses"] == []

    virt_rows = {
        row["license"]: row
        for row in sections_by_name["Virtualization Licenses"]["rows"]
    }
    assert "VM Sockets" in virt_rows
    assert "Auto Recovery" in virt_rows
    assert virt_rows["Auto Recovery"]["entitlement_value"] == "500 VMs"
    assert virt_rows["Auto Recovery"]["used"] == "0 VMs"
    assert virt_rows["Auto Recovery"]["status"] == "0%"

    cap_rows = {
        row["license"]: row
        for row in sections_by_name["Capacity Licenses"]["rows"]
    }
    assert cap_rows["Backup and Recovery"]["entitlement_value"] == "100"
    assert cap_rows["Backup and Recovery"]["used"] == "0"


def test_parse_license_summary_html_does_not_cross_wire_section_titles() -> None:
    """Cross-wire guard: if a single preceding section title sits before
    two adjacent tables, only the first table should claim that title.
    The second table should fall through to the classifier-based
    bucketing (or be dropped) — it must NOT silently inherit the
    first table's section_name and pile its rows onto a section they
    don't belong to. Without the claimed-titles guard, the second
    table's find_all_previous walk would still match the first
    title, cross-wiring its rows.
    """
    html = """
    <html><body>
      <div class="section">
        <div class="component-title">
          <span class="input-title tileHelpLabels component-title-text">Capacity Licenses</span>
        </div>
      </div>
      <div class="exportTable">
        <table>
          <thead><tr>
            <th>License</th><th>Available Total (TB)</th><th>Used (TB)</th><th>Summary</th>
          </tr></thead>
          <tbody>
            <tr><td>Backup and Recovery</td><td>100</td><td>0</td><td>0%</td></tr>
          </tbody>
        </table>
      </div>
      <div class="exportTable">
        <table>
          <thead><tr>
            <th>License</th><th>Available Total (TB)</th><th>Used (TB)</th><th>Summary</th>
          </tr></thead>
          <tbody>
            <tr><td>Should Not Cross Wire</td><td>50</td><td>10</td><td>0%</td></tr>
          </tbody>
        </table>
      </div>
    </body></html>
    """
    artifact = parse_license_summary_html(html, source_file="/tmp/cross-wire.html")

    sections_by_name = {
        section["section_name"]: section
        for section in artifact["workload_summary_sections"]
    }

    assert "Capacity Licenses" in sections_by_name
    licenses_in_capacity = {
        row["license"] for row in sections_by_name["Capacity Licenses"]["rows"]
    }
    assert licenses_in_capacity == {"Backup and Recovery"}
    assert "Should Not Cross Wire" not in licenses_in_capacity


def test_parse_license_summary_xlsx_recording_extracts_rest_artifact() -> None:
    workbook = _build_xlsx(
        [
            ["License summary"],
            ["Generated on: May 18, 2026 09:15:00 AM"],
            ["CommCell Name", "CommServe A"],
            ["CommCell Version", "11.36"],
            ["Timezone", "UTC"],
            [],
            ["Capacity Licenses"],
            ["License", "Available Total (TB)", "Permanent Purchased (TB)", "Term Purchased (TB)", "Used (TB)", "Used %", "Summary"],
            ["Backup and Recovery", "100", "100", "0", "0.00", "0%", "0%"],
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
    assert len(artifact["workload_summary_sections"]) == 1
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
            {"kind": "summary", "section_name": "Capacity Licenses", "dataset_name": "GetLicenseSummaryCapacityV3"},
            {"dataset_name": "Other Licenses - current usage details"},
            {"dataset_name": "Agent and Feature Licenses - current usage details"},
        ],
        "executions": [
            {
                "status": "EXECUTABLE",
                "sample_rows": [
                    {
                        "Dial": "Backup and Recovery",
                        "LicUsageType": 100031,
                        "Purchased": "100",
                        "Usage": "0.00",
                        "Used %": "0%",
                        "Summary": "0%",
                    }
                ],
            },
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
    assert len(artifact["workload_summary_sections"]) == 1
    assert artifact["workload_summary_sections"][0]["section_name"] == "Capacity Licenses"
    assert len(artifact["other_licenses"]) == 2
    assert len(artifact["agent_feature_licenses"]) == 1
    assert artifact["other_licenses"][1]["unit"] == "TB"
    assert artifact["source"]["report_id"] == "206"


def test_collect_license_summary_rest_uses_page_dataset_definitions_for_live_report() -> None:
    page = {
        "body": {
            "reportComponents": [
                {"title": {"text": "Other Licenses - current usage details"}},
                {"title": {"text": "Agent and Feature Licenses - current usage details"}},
            ]
        },
        "dataSets": {
            "dataSet": [
                {
                    "guid": "outer-other-guid",
                    "GetOperation": {"parameters": [{"name": "GUID", "values": ["=input.orgGUID"]}]},
                    "dataSet": {"dataSetGuid": "inner-other-guid", "dataSetName": "usageBasedLicenses"},
                    "fields": [
                        {"name": "Data Source"},
                        {"name": "LicUsageType"},
                        {"name": "Dial"},
                        {"name": "Purchased"},
                        {"name": "PermTotal"},
                        {"name": "Eval"},
                        {"name": "Usage"},
                        {"name": "TermDate"},
                        {"name": "EvalExpiryDate"},
                    ],
                },
                {
                    "guid": "outer-agent-guid",
                    "GetOperation": {"parameters": [{"name": "GUID", "values": ["=input.orgGUID"]}]},
                    "dataSet": {"dataSetGuid": "inner-agent-guid", "dataSetName": "agentFeatureLicenses"},
                    "fields": [
                        {"name": "License"},
                        {"name": "Permanent Total"},
                        {"name": "Permanent Used"},
                        {"name": "Evaluation Total"},
                        {"name": "Evaluation Used"},
                        {"name": "Client"},
                        {"name": "Agent"},
                        {"name": "Install Date"},
                    ],
                },
                {
                    "guid": "outer-meta-guid",
                    "GetOperation": {"parameters": [{"name": "GUID", "values": ["=input.orgGUID"]}]},
                    "dataSet": {"dataSetGuid": "inner-meta-guid", "dataSetName": "lastCollection"},
                    "fields": [
                        {"name": "Last Collection Time"},
                        {"name": "License Expiry"},
                        {"name": "CommCell"},
                        {"name": "Version"},
                        {"name": "TimeZone"},
                    ],
                },
                {
                    "guid": "outer-org-guid",
                    "GetOperation": {},
                    "dataSet": {"dataSetGuid": "inner-org-guid", "dataSetName": "organization"},
                    "fields": [
                        {"name": "OrgGUID"},
                        {"name": "Organization"},
                    ],
                },
            ]
        },
    }

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str]]] = []

        def get_report(self, report_id_or_guid: str) -> ApiResult:
            return ApiResult(
                ok=True,
                status_code=200,
                url=f"/reports/{report_id_or_guid}",
                data={"reportName": "License summary", "pages": [page]},
                text="",
            )

        def get_dataset_data(
            self,
            dataset_guid: str,
            *,
            parameters: dict[str, str] | None = None,
            limit: int | None = None,
            **_: object,
        ) -> ApiResult:
            params = parameters or {}
            self.calls.append((dataset_guid, params))
            timestamp = "2026-05-18T09:15:00+00:00"
            if dataset_guid == "outer-org-guid":
                return ApiResult(
                    ok=True,
                    status_code=200,
                    url=f"/datasets/{dataset_guid}/data",
                    data={
                        "timestamp": timestamp,
                        "records": [{"OrgGUID": "-1", "Organization": "Commcell"}],
                    },
                    text="",
                )
            if params != {"parameter.GUID": "-1"}:
                return ApiResult(
                    ok=False,
                    status_code=400,
                    url=f"/datasets/{dataset_guid}/data",
                    data=None,
                    text="bad params",
                    error="bad params",
                )
            payloads = {
                "outer-other-guid": {
                    "timestamp": timestamp,
                    "records": [
                        {
                            "Dial": "Advanced VM",
                            "LicUsageType": 200003,
                            "Purchased": 0,
                            "PermTotal": 0,
                            "Eval": 0,
                            "Usage": 0,
                            "TermDate": "Jan 1, 1970, 12:00:00 AM",
                            "EvalExpiryDate": "01 Jan 1970",
                        }
                    ],
                },
                "outer-agent-guid": {
                    "timestamp": timestamp,
                    "records": [
                        {
                            "License": "Server File System",
                            "Permanent Total": -1,
                            "Permanent Used": 4,
                            "Evaluation Total": 0,
                            "Evaluation Used": 0,
                            "Client": "dev02",
                            "Agent": "Windows File System",
                            "Install Date": "Apr 23, 2026, 03:17:48 PM",
                        }
                    ],
                },
                "outer-meta-guid": {
                    "timestamp": timestamp,
                    "records": [
                        {
                            "Last Collection Time": "2026-05-18T08:55:00+00:00",
                            "License Expiry": "2027-05-19",
                            "CommCell": "CommServe A",
                            "Version": "11.36",
                            "TimeZone": "UTC",
                        }
                    ],
                },
            }
            payload = payloads.get(dataset_guid)
            if payload is None:
                return ApiResult(
                    ok=False,
                    status_code=404,
                    url=f"/datasets/{dataset_guid}/data",
                    data=None,
                    text="not found",
                    error="not found",
                )
            return ApiResult(
                ok=True,
                status_code=200,
                url=f"/datasets/{dataset_guid}/data",
                data=payload,
                text="",
            )

    client = FakeClient()

    collected = collect_license_summary_rest(client=client, write_artifact=False)
    artifact = collected["normalized"]

    assert artifact["generated_on"] == "2026-05-18T09:15:00+00:00"
    assert artifact["commcell_name"] == "CommServe A"
    assert artifact["commcell_version"] == "11.36"
    assert artifact["license_expiry"] == "2027-05-19"
    assert len(artifact["other_licenses"]) == 1
    assert artifact["other_licenses"][0]["license"] == "Advanced VM"
    assert artifact["other_licenses"][0]["raw_available_total"] == "0 VMs"
    assert artifact["other_licenses"][0]["raw_used"] == "0 VMs"
    assert len(artifact["agent_feature_licenses"]) == 1
    assert artifact["agent_feature_licenses"][0]["license"] == "Server File System"
    assert [guid for guid, _ in client.calls] == [
        "outer-org-guid",
        "outer-meta-guid",
        "outer-other-guid",
        "outer-agent-guid",
    ]


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


def test_license_summary_service_collect_from_rest_writes_canonical_only(
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
            "workload_summary_sections": [
                {
                    "section_name": "Capacity Licenses",
                    "rows": [
                        {
                            "license": "Backup and Recovery",
                            "entitlement_value": "100 TB",
                            "used": "0 TB",
                            "usage_percent": "0%",
                            "status": "0%",
                            "raw_fields": {},
                        }
                    ],
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
    # D5: the scoped save requires explicit context; select one for the test.
    from cvhealthcheck.web.app import create_app
    from cvhealthcheck.web.active_project import set_active_project
    with create_app().test_request_context("/"):
        set_active_project("default", "default")
        result = service.collect_from_rest()

    # Option A — REST collection writes canonical only, not the legacy store.
    assert result["normalized"]["source_type"] == "rest"
    assert result["normalized"]["source"]["report_id"] == "206"
    assert result["normalized"]["license_expiry"] is None
    assert len(result["normalized"]["workload_summary_sections"]) == 1
    assert len(result["normalized"]["other_licenses"]) == 1
    assert not (tmp_path / "catalog" / "latest.json").exists()
    assert not (tmp_path / "catalog" / "registry.sqlite3").exists()
    from cvhealthcheck.artifacts.store import ArtifactStore
    canonical = ArtifactStore("default", "default").load_latest_artifact("license_summary")
    assert canonical.artifact_type == "license_summary"


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
