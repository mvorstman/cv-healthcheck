"""
Tests for the generic HTML extractor and result_to_artifact converter.

HTML is built inline using helper functions that produce minimal but
structurally correct Commvault-style HTML — no files from data/imports/
are read here.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

from cvhealthcheck.artifacts.models import CanonicalArtifact, FindingsSection, TableSection
from cvhealthcheck.extractors.html import ExtractionResult, HTMLExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

def build_security_assessment_html(sections: list[dict]) -> str:
    """
    sections: list of {title: str, rows: list[{parameter, status, remarks, action}]}

    Produces minimal Commvault-style security assessment HTML.
    Each section is a .panel-table-title div followed by a table, wrapped
    in a common parent div (mirroring the react-grid-item structure).
    """
    parts: list[str] = []
    for section in sections:
        rows_html = "\n".join(
            "<tr>"
            f"<td>{r['parameter']}</td>"
            f"<td>{r['status']}</td>"
            f"<td>{r.get('remarks', '')}</td>"
            f"<td>{r.get('action', '')}</td>"
            "</tr>"
            for r in section["rows"]
        )
        parts.append(
            f'<div class="exportTable">'
            f'<div class="panel-table-title">{section["title"]}</div>'
            f"<table>"
            f"<thead><tr>"
            f"<th>Parameter</th><th>Status</th><th>Remarks</th><th>Action</th>"
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
            f"</div>"
        )
    return "<html><body>" + "".join(parts) + "</body></html>"


def build_license_summary_html(sections: list[dict]) -> str:
    """
    sections: list of {title: str, columns: list[str], rows: list[dict]}

    Produces minimal Commvault-style license summary HTML.
    Each section is a .reportstabletitle div followed by a table, wrapped
    in a parent div.
    """
    parts: list[str] = []
    for section in sections:
        cols = section["columns"]
        headers_html = "".join(f"<th>{c}</th>" for c in cols)
        rows_html = ""
        for row in section["rows"]:
            cells = "".join(f"<td>{row.get(c, '')}</td>" for c in cols)
            rows_html += f"<tr>{cells}</tr>"
        parts.append(
            f'<div class="exportTable">'
            f'<div class="reportstabletitle">{section["title"]}</div>'
            f"<table>"
            f"<thead><tr>{headers_html}</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
            f"</div>"
        )
    return "<html><body>" + "".join(parts) + "</body></html>"


# ---------------------------------------------------------------------------
# Constants matching the DB extraction instructions (from migration 0003)
# ---------------------------------------------------------------------------

_SA_SECTION_TITLES = [
    "Access Security",
    "Auditing",
    "Platform Security",
    "Company and Owners Security",
    "Capabilities",
    "Hardening",
]

_SA_SECTION_IDS = [
    "security_assessment.access_security",
    "security_assessment.auditing",
    "security_assessment.platform_security",
    "security_assessment.company_and_owners_security",
    "security_assessment.capabilities",
    "security_assessment.hardening",
]

_SA_DATA_ROWS = [
    {"parameter": "Two-factor auth",  "status": "Critical", "remarks": "Disabled",   "action": "Enable"},
    {"parameter": "Firewall rule",    "status": "Warning",  "remarks": "Permissive",  "action": "Tighten"},
    {"parameter": "Encryption at rest","status": "Good",    "remarks": "Enabled",     "action": ""},
]

_LS_OTHER_ROWS = [
    {"License": "Metallic",   "Available Total": "0 TB",  "Used": "4 clients"},
    {"License": "SaaS",       "Available Total": "N/A",   "Used": "-"},
]

_LS_AGENT_ROWS = [
    {
        "License": "Server File System",
        "Permanent Total": "10", "Permanent Used": "5",
        "Term Total": "0",       "Term Used": "0",
        "Client": "1",           "Agent": "1",
        "Install Date": "2024-01-01",
    }
]

_LS_COLUMNS_OTHER = ["License", "Available Total", "Used"]
_LS_COLUMNS_AGENT = [
    "License", "Permanent Total", "Permanent Used",
    "Term Total", "Term Used", "Client", "Agent", "Install Date",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def extractor_db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def extractor(extractor_db: sqlite3.Connection) -> HTMLExtractor:
    return HTMLExtractor(extractor_db)


def _write_html(tmp_path: Path, content: str, name: str = "test.html") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test 1 — security_assessment, populated tables
# ---------------------------------------------------------------------------

def test_security_assessment_extract_populated(extractor: HTMLExtractor, tmp_path: Path) -> None:
    html = build_security_assessment_html([
        {"title": t, "rows": _SA_DATA_ROWS} for t in _SA_SECTION_TITLES
    ])
    html_path = _write_html(tmp_path, html)

    result = extractor.extract(html_path, "security_assessment")

    assert not result.errors, f"Unexpected errors: {result.errors}"
    assert set(result.sections.keys()) == set(_SA_SECTION_IDS)
    for sec_id in _SA_SECTION_IDS:
        rows = result.sections[sec_id]
        assert len(rows) == len(_SA_DATA_ROWS)

    # Severity mapping applied
    first_section_rows = result.sections[_SA_SECTION_IDS[0]]
    assert first_section_rows[0]["severity"] == "critical"
    assert first_section_rows[1]["severity"] == "warning"
    assert first_section_rows[2]["severity"] == "good"


# ---------------------------------------------------------------------------
# Test 2 — security_assessment, empty tables
# ---------------------------------------------------------------------------

def test_security_assessment_extract_empty(extractor: HTMLExtractor, tmp_path: Path) -> None:
    html = build_security_assessment_html([
        {"title": t, "rows": []} for t in _SA_SECTION_TITLES
    ])
    html_path = _write_html(tmp_path, html)

    result = extractor.extract(html_path, "security_assessment")

    assert not result.errors, f"Unexpected errors: {result.errors}"
    for sec_id in _SA_SECTION_IDS:
        assert result.sections[sec_id] == []
    empty_table_warnings = [w for w in result.warnings if "no data rows" in w]
    assert len(empty_table_warnings) == len(_SA_SECTION_IDS)


# ---------------------------------------------------------------------------
# Test 3 — license_summary, populated tables
# ---------------------------------------------------------------------------

def test_license_summary_extract_populated(
    extractor: HTMLExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    html = build_license_summary_html([
        {"title": "Other Licenses",            "columns": _LS_COLUMNS_OTHER, "rows": _LS_OTHER_ROWS},
        {"title": "Agent and Feature Licenses", "columns": _LS_COLUMNS_AGENT, "rows": _LS_AGENT_ROWS},
    ])
    html_path = _write_html(tmp_path, html)

    result = extractor.extract(html_path, machinery_subject)

    other_id = f"{machinery_subject}.other_licenses"
    agent_id = f"{machinery_subject}.agent_feature_licenses"
    assert not result.errors, f"Unexpected errors: {result.errors}"
    assert other_id in result.sections
    assert agent_id in result.sections

    other = result.sections[other_id]
    assert len(other) == 2
    assert other[0]["license_name"] == "Metallic"
    assert other[0]["available_total_raw"] == "0 TB"

    # null_values applied: "N/A" and "-" map to None
    assert other[1]["available_total_raw"] is None
    assert other[1]["used_raw"] is None

    agent = result.sections[agent_id]
    assert len(agent) == 1
    assert agent[0]["license_name"] == "Server File System"


# ---------------------------------------------------------------------------
# Test 4 — license_summary, empty tables
# ---------------------------------------------------------------------------

def test_license_summary_extract_empty(
    extractor: HTMLExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    html = build_license_summary_html([
        {"title": "Other Licenses",            "columns": _LS_COLUMNS_OTHER, "rows": []},
        {"title": "Agent and Feature Licenses", "columns": _LS_COLUMNS_AGENT, "rows": []},
    ])
    html_path = _write_html(tmp_path, html)

    result = extractor.extract(html_path, machinery_subject)

    assert not result.errors, f"Unexpected errors: {result.errors}"
    assert result.sections[f"{machinery_subject}.other_licenses"] == []
    assert result.sections[f"{machinery_subject}.agent_feature_licenses"] == []
    empty_warnings = [w for w in result.warnings if "no data rows" in w]
    assert len(empty_warnings) == 2


# ---------------------------------------------------------------------------
# Test 5 — missing section produces an error; others still extracted
# ---------------------------------------------------------------------------

def test_section_not_found(extractor: HTMLExtractor, tmp_path: Path) -> None:
    # All SA sections except "Hardening"
    html = build_security_assessment_html([
        {"title": t, "rows": _SA_DATA_ROWS[:1]}
        for t in _SA_SECTION_TITLES
        if t != "Hardening"
    ])
    html_path = _write_html(tmp_path, html)

    result = extractor.extract(html_path, "security_assessment")

    hardening_errors = [e for e in result.errors if "Hardening" in e]
    assert hardening_errors, f"Expected error for missing 'Hardening' section, got: {result.errors}"

    # Other sections extracted correctly
    assert "security_assessment.access_security" in result.sections
    assert len(result.sections["security_assessment.access_security"]) == 1
    assert "security_assessment.hardening" not in result.sections


# ---------------------------------------------------------------------------
# Test 6 — result_to_artifact: findings section
# ---------------------------------------------------------------------------

def _findings_result() -> ExtractionResult:
    result = ExtractionResult(subject_id="security_assessment")
    sec_id = "security_assessment.access_security"
    result.sections[sec_id] = [
        {"parameter": "Two-factor auth", "status": "Critical", "remarks": "Disabled",
         "action": "Enable", "severity": "critical"},
        {"parameter": "Firewall",        "status": "Warning",  "remarks": "Weak",
         "action": "",      "severity": "warning"},
        {"parameter": "Encryption",      "status": "Good",     "remarks": "On",
         "action": "",      "severity": "good"},
    ]
    result.section_output_types[sec_id] = "findings"
    result.section_titles[sec_id] = "Access Security"
    return result


def test_result_to_artifact_findings(tmp_path: Path) -> None:
    result = _findings_result()
    artifact = result_to_artifact(
        result, "security_assessment", "Security Assessment", tmp_path / "t.html"
    )

    CanonicalArtifact.model_validate(artifact.model_dump())

    assert artifact.artifact_type == "security_assessment"
    assert len(artifact.sections) == 1

    sec = artifact.sections[0]
    assert isinstance(sec, FindingsSection)
    assert len(sec.items) == 3

    f0 = sec.items[0]
    expected_id = hashlib.sha256(
        b"security_assessment.access_security:Two-factor auth"
    ).hexdigest()[:12]
    assert f0.id == expected_id
    assert f0.severity.value == "critical"
    assert f0.title == "Two-factor auth"
    assert f0.description == "Disabled"
    assert f0.recommendation == "Enable"

    assert artifact.summary.status.value == "critical"
    metric_ids = {m.id for m in artifact.summary.metrics}
    assert "critical_count" in metric_ids
    assert "warning_count" in metric_ids

    critical_metric = next(m for m in artifact.summary.metrics if m.id == "critical_count")
    assert critical_metric.value == 1


def test_result_to_artifact_findings_preserves_vendor_keys(tmp_path: Path) -> None:
    """Vendor-stable identifiers (vendor_key, vendor_id) must round-trip from
    the canonical row dict into the Finding model. Rule overrides under
    ADR 0004's evaluative face need a stable identifier; free-text Parameter
    can be renamed by Commvault between releases. Migration 0008 wires
    SA's column_map to populate vendor_key from attrName and vendor_id
    from PARAMID; _build_finding copies them onto the Finding.
    """
    result = ExtractionResult(subject_id="security_assessment")
    sec_id = "security_assessment.access_security"
    result.sections[sec_id] = [
        {
            "parameter": "Two-factor authentication",
            "status": "2_Info",
            "remarks": "Disabled",
            "action": "How to enable",
            "severity": "info",
            "vendor_key": "2FAEnabled",
            "vendor_id": "2501",
        },
        {
            "parameter": "Ransomware protection",
            "status": "1_Good",
            "remarks": "Secured",
            "action": "",
            "severity": "good",
            "vendor_key": "SecureMountPaths-Secure",
            "vendor_id": "25013",
        },
    ]
    result.section_output_types[sec_id] = "findings"
    result.section_titles[sec_id] = "Access Security"

    artifact = result_to_artifact(
        result, "security_assessment", "Security Assessment", tmp_path / "t.html"
    )

    sec = artifact.sections[0]
    assert isinstance(sec, FindingsSection)
    assert sec.items[0].vendor_key == "2FAEnabled"
    assert sec.items[0].vendor_id == "2501"
    assert sec.items[1].vendor_key == "SecureMountPaths-Secure"
    assert sec.items[1].vendor_id == "25013"


def test_result_to_artifact_findings_vendor_keys_default_none(tmp_path: Path) -> None:
    """Backwards compatibility: rows without vendor_key/vendor_id (older
    artifacts, or sources without the new column_map entries) must still
    produce a valid Finding — both fields default to None.
    """
    result = ExtractionResult(subject_id="security_assessment")
    sec_id = "security_assessment.access_security"
    result.sections[sec_id] = [
        {"parameter": "Old finding", "status": "Info",
         "remarks": "x", "action": "y", "severity": "info"},
    ]
    result.section_output_types[sec_id] = "findings"
    result.section_titles[sec_id] = "Access Security"

    artifact = result_to_artifact(
        result, "security_assessment", "Security Assessment", tmp_path / "t.html"
    )
    sec = artifact.sections[0]
    assert isinstance(sec, FindingsSection)
    assert sec.items[0].vendor_key is None
    assert sec.items[0].vendor_id is None


# ---------------------------------------------------------------------------
# Test 7 — result_to_artifact: table section
# ---------------------------------------------------------------------------

def _table_result() -> ExtractionResult:
    result = ExtractionResult(subject_id="license_summary")
    sec_id = "license_summary.other_licenses"
    result.sections[sec_id] = [
        {"license_name": "Metallic", "available_total_raw": "0 TB", "used_raw": "4 clients"},
        {"license_name": "SaaS",     "available_total_raw": None,   "used_raw": None},
    ]
    result.section_output_types[sec_id] = "table"
    result.section_titles[sec_id] = "Other Licenses"
    return result


def test_result_to_artifact_table(tmp_path: Path) -> None:
    result = _table_result()
    artifact = result_to_artifact(
        result, "license_summary", "License Summary", tmp_path / "t.html"
    )

    CanonicalArtifact.model_validate(artifact.model_dump())

    assert len(artifact.sections) == 1
    sec = artifact.sections[0]
    assert isinstance(sec, TableSection)
    assert len(sec.items) == 2
    assert sec.items[0]["license_name"] == "Metallic"
    assert sec.items[1]["available_total_raw"] is None

    # Table-only subject with data: good status (data present, no severity assessment)
    assert artifact.summary.status.value == "good"
    assert artifact.summary.metrics == []


# ---------------------------------------------------------------------------
# Test 8 — result_to_artifact: mixed findings + table
# ---------------------------------------------------------------------------

def test_result_to_artifact_mixed(tmp_path: Path) -> None:
    result = ExtractionResult(subject_id="mixed_subject")
    findings_id = "mixed_subject.checks"
    table_id = "mixed_subject.data"

    result.sections[findings_id] = [
        {"parameter": "Check A", "status": "Warning", "remarks": "Issues found",
         "action": "Fix it", "severity": "warning"},
    ]
    result.sections[table_id] = [
        {"col_a": "val1", "col_b": "val2"},
    ]
    result.section_output_types[findings_id] = "findings"
    result.section_output_types[table_id] = "table"
    result.section_titles[findings_id] = "Checks"
    result.section_titles[table_id] = "Data Table"

    artifact = result_to_artifact(
        result, "mixed_subject", "Mixed Subject", tmp_path / "t.html"
    )
    CanonicalArtifact.model_validate(artifact.model_dump())

    types_present = {type(s).__name__ for s in artifact.sections}
    assert "FindingsSection" in types_present
    assert "TableSection" in types_present
    assert artifact.summary.status.value == "warning"


# ---------------------------------------------------------------------------
# Test 8b — result_to_artifact: ADR 0004 template_version provenance
# ---------------------------------------------------------------------------

def test_result_to_artifact_records_template_version(tmp_path: Path) -> None:
    """Every artifact records the subject_id it was collected under."""
    result = _findings_result()
    artifact = result_to_artifact(
        result, "capacity_license", "Capacity Licenses", tmp_path / "t.html"
    )
    CanonicalArtifact.model_validate(artifact.model_dump())
    assert artifact.source.template_version == "capacity_license"


def test_result_to_artifact_rest_sets_collected_at(tmp_path: Path) -> None:
    """REST collection records collected_at; file imports leave it None."""
    rest_result = ExtractionResult(subject_id="capacity_license", source_type="rest")
    rest_result.sections["capacity_license.table"] = [{"month": "2024-08", "clients": 5}]
    rest_result.section_output_types["capacity_license.table"] = "table"
    rest_result.section_titles["capacity_license.table"] = "Monthly"
    rest_artifact = result_to_artifact(rest_result, "capacity_license_v2", "Capacity Licenses")
    assert rest_artifact.source.collected_at is not None
    assert rest_artifact.source.imported_at is not None
    # The version-bearing subject_id flows through verbatim.
    assert rest_artifact.source.template_version == "capacity_license_v2"

    html_result = _findings_result()
    html_artifact = result_to_artifact(
        html_result, "security_assessment", "Security Assessment", tmp_path / "t.html"
    )
    assert html_artifact.source.collected_at is None
    assert html_artifact.source.imported_at is not None


def test_artifact_without_template_version_loads_cleanly() -> None:
    """Artifacts predating ADR 0004 (no template_version) must still validate."""
    legacy = {
        "artifact_type": "capacity_license",
        "generated_at": "2026-01-01T00:00:00Z",
        "source": {"type": "html_import"},
        "subject": {"id": "capacity_license", "title": "Capacity Licenses"},
        "summary": {"status": "good"},
        "sections": [],
    }
    artifact = CanonicalArtifact.model_validate(legacy)
    assert artifact.source.template_version is None


# ---------------------------------------------------------------------------
# Test 9 — unknown column header → warning, other columns extracted
# ---------------------------------------------------------------------------

def test_unknown_column_header(extractor: HTMLExtractor) -> None:
    html = """<table>
        <thead><tr><th>Parameter</th><th>Status</th></tr></thead>
        <tbody><tr><td>Test param</td><td>Good</td></tr></tbody>
    </table>"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")

    column_map = [
        {"source": "Parameter", "canonical": "parameter", "type": "string"},
        {"source": "Status",    "canonical": "status",    "type": "string"},
        {"source": "Remarks",   "canonical": "remarks",   "type": "string"},  # absent
    ]

    rows, warnings = extractor._extract_table_rows(
        table,
        column_map=column_map,
        null_values=[],
        section_title_match="Test Section",
    )

    assert len(rows) == 1
    assert rows[0]["parameter"] == "Test param"
    assert rows[0]["status"] == "Good"
    assert "remarks" not in rows[0]
    assert any("Remarks" in w for w in warnings)


# ---------------------------------------------------------------------------
# Test 10 — type coercion
# ---------------------------------------------------------------------------

def test_type_coercion(extractor: HTMLExtractor) -> None:
    html = """<table>
        <thead><tr><th>Name</th><th>Count</th><th>Rate</th></tr></thead>
        <tbody>
            <tr><td>Item A</td><td>42</td><td>3.14</td></tr>
            <tr><td>Item B</td><td>N/A</td><td>not_a_number</td></tr>
            <tr><td></td><td>0</td><td>0.0</td></tr>
        </tbody>
    </table>"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")

    column_map = [
        {"source": "Name",  "canonical": "name",  "type": "string"},
        {"source": "Count", "canonical": "count", "type": "integer"},
        {"source": "Rate",  "canonical": "rate",  "type": "float"},
    ]

    rows, warnings = extractor._extract_table_rows(
        table,
        column_map=column_map,
        null_values=["N/A"],
        section_title_match="Test Section",
    )

    assert len(rows) == 3

    # Row 0: valid values
    assert rows[0]["name"] == "Item A"
    assert rows[0]["count"] == 42
    assert rows[0]["rate"] == pytest.approx(3.14)

    # Row 1: N/A → null (null_values), invalid float → None + warning
    assert rows[1]["count"] is None   # N/A is in null_values
    assert rows[1]["rate"] is None    # "not_a_number" can't be float

    # Row 2: empty string name (not in null_values → ""), int 0, float 0.0
    assert rows[2]["name"] == ""
    assert rows[2]["count"] == 0
    assert rows[2]["rate"] == pytest.approx(0.0)

    coerce_warnings = [w for w in warnings if "coerce" in w.lower() or "float" in w.lower()]
    assert coerce_warnings, f"Expected a float coercion warning, got: {warnings}"
