"""
Tests for the generic CSV extractor and result_to_artifact integration.

CSV is built inline using helper functions — no files from data/imports/
are read here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.models import CanonicalArtifact, TableSection
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


# ---------------------------------------------------------------------------
# CSV builders
# ---------------------------------------------------------------------------

def build_license_summary_csv(
    other_rows: list[tuple[str, str, str]] | None = None,
    agent_rows: list[tuple] | None = None,
) -> str:
    """
    Produces a minimal license_summary CSV matching the real Commvault export
    structure (UTF-8 BOM stripped at the string level; encoding tested
    separately via tmp_path bytes).

    other_rows: list of (license, available_total, used)
    agent_rows: list of (license, perm_total, perm_used, term_total, term_used,
                         client, agent, install_date)
    """
    if other_rows is None:
        other_rows = [
            ("License A", "10", "5"),
            ("License B", "N/A", "3"),
        ]
    if agent_rows is None:
        agent_rows = [
            ("Agent Lic 1", "20", "8", "5", "2", "1", "0", "2025-01-01"),
        ]

    lines = [
        "License summary",
        "Generated on: 2026-05-24",
        "",
        "Other Licenses - current usage details",
        '"License","Available Total","Used"',
    ]
    for r in other_rows:
        lines.append(f'"{r[0]}","{r[1]}","{r[2]}"')

    lines.append("")
    lines.append("Agent and Feature Licenses - current usage details")
    lines.append(
        '"License","Permanent Total","Permanent Used","Term Total",'
        '"Term Used","Client","Agent","Install Date"'
    )
    for r in agent_rows:
        lines.append(",".join(f'"{v}"' for v in r))

    lines.append("")
    return "\n".join(lines)


def build_growth_and_trends_csv(
    client_rows: list[tuple[str, str, str, str]] | None = None,
    capacity_rows: list[tuple[str, str, str]] | None = None,
    capacity_section_index: int = 6,
) -> str:
    """
    Produces a Growth and Trends multi-section CSV.

    The file has 7+ sections separated by blank lines:
      sections 0–5 are placeholder metadata/chart sections
      section labelled 'Clients Count' holds monthly client data
      section at capacity_section_index (default 6) holds capacity data

    client_rows: list of (month_start, none_total, none_removed, none_added)
    capacity_rows: list of (month, entity_name, used_capacity)
    """
    if client_rows is None:
        client_rows = [
            ("2026-01-01", "150", "5", "10"),
            ("2026-02-01", "155", "3", "8"),
        ]
    if capacity_rows is None:
        capacity_rows = [
            ("2026-01", "Entity A", "1024"),
            ("2026-02", "Entity A", "1100"),
        ]

    sections: list[str] = []

    # Sections 0–5: placeholder sections (simulate chart/metadata exports)
    for i in range(6):
        sections.append(f"Section {i}\nPlaceholder,Data\nvalue,1")

    # Clients Count section (label-based)
    client_lines = ["Clients Count", "MonthStart,None_Total,None_Removed,None_Added"]
    for r in client_rows:
        client_lines.append(",".join(r))
    sections.append("\n".join(client_lines))

    # Capacity section at index capacity_section_index (index-based)
    # Insert it at the right position so it lands at section_index=6
    capacity_lines = ["Capacity License Usage", "Month,Entity Name,Used Capacity"]
    for r in capacity_rows:
        capacity_lines.append(",".join(r))

    # Our sections list so far has 7 entries (0–6).
    # We want capacity at index 6, which is already sections[6].
    # But the client_rows section was just appended at index 6.
    # Adjust: place capacity at index 6 and shift client to 7.
    # Actually capacity_section_index=6 so capacity must be at position 6.
    # Rebuild: placeholders at 0-5, capacity at 6, clients at 7 (by label).

    sections_final = sections[:6]  # 0-5 placeholders
    sections_final.append("\n".join(capacity_lines))   # index 6 = capacity
    sections_final.append("\n".join(client_lines))     # index 7 = clients (by label)

    return "\n\n".join(sections_final) + "\n"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def extractor_db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture()
def extractor(extractor_db: sqlite3.Connection) -> CSVExtractor:
    return CSVExtractor(extractor_db)


# ---------------------------------------------------------------------------
# 1. single_table populated
# ---------------------------------------------------------------------------

def test_single_table_other_licenses_returns_rows(
    extractor: CSVExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    csv_path = tmp_path / "license.csv"
    csv_path.write_text(build_license_summary_csv(), encoding="utf-8")

    result = extractor.extract(csv_path, machinery_subject)

    sid = f"{machinery_subject}.other_licenses"
    assert sid in result.sections
    rows = result.sections[sid]
    assert len(rows) == 2
    assert rows[0]["license_name"] == "License A"
    assert rows[0]["available_total_raw"] == "10"
    assert rows[0]["used_raw"] == "5"


# ---------------------------------------------------------------------------
# 2. single_table empty section
# ---------------------------------------------------------------------------

def test_single_table_empty_section_warns(
    extractor: CSVExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    csv_path = tmp_path / "license.csv"
    csv_path.write_text(build_license_summary_csv(other_rows=[]), encoding="utf-8")

    result = extractor.extract(csv_path, machinery_subject)

    sid = f"{machinery_subject}.other_licenses"
    assert sid in result.sections
    assert result.sections[sid] == []
    assert any("no data rows" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 3. null_values → None
# ---------------------------------------------------------------------------

def test_single_table_null_values_become_none(
    extractor: CSVExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    csv_path = tmp_path / "license.csv"
    csv_path.write_text(
        build_license_summary_csv(other_rows=[("License X", "N/A", "-")]),
        encoding="utf-8",
    )

    result = extractor.extract(csv_path, machinery_subject)
    rows = result.sections[f"{machinery_subject}.other_licenses"]

    assert rows[0]["available_total_raw"] is None
    assert rows[0]["used_raw"] is None


# ---------------------------------------------------------------------------
# 4. multi_section by label — client_growth
# ---------------------------------------------------------------------------

def test_multi_section_by_label_returns_rows(extractor: CSVExtractor, tmp_path: Path) -> None:
    csv_path = tmp_path / "growth.csv"
    csv_path.write_text(build_growth_and_trends_csv(), encoding="utf-8")

    result = extractor.extract(csv_path, "client_growth")

    assert "client_growth.monthly_table" in result.sections
    rows = result.sections["client_growth.monthly_table"]
    assert len(rows) == 2
    assert rows[0]["month_start"] == "2026-01-01"


# ---------------------------------------------------------------------------
# 5. fuzzy_match — None_Total matched when headers use exact name
# ---------------------------------------------------------------------------

def test_multi_section_fuzzy_match_extracts_integer_columns(
    extractor: CSVExtractor, tmp_path: Path
) -> None:
    csv_path = tmp_path / "growth.csv"
    csv_path.write_text(build_growth_and_trends_csv(), encoding="utf-8")

    result = extractor.extract(csv_path, "client_growth")

    rows = result.sections["client_growth.monthly_table"]
    assert rows[0]["total"] == 150
    assert rows[0]["removed"] == 5
    assert rows[0]["added"] == 10


# ---------------------------------------------------------------------------
# 6. multi_section by index — capacity_license
# ---------------------------------------------------------------------------

def test_multi_section_by_index_returns_rows(extractor: CSVExtractor, tmp_path: Path) -> None:
    csv_path = tmp_path / "growth.csv"
    csv_path.write_text(build_growth_and_trends_csv(), encoding="utf-8")

    result = extractor.extract(csv_path, "capacity_license")

    assert "capacity_license.table" in result.sections
    rows = result.sections["capacity_license.table"]
    assert len(rows) == 2
    assert rows[0]["entity_name"] == "Entity A"
    assert rows[0]["used_capacity"] == 1024


# ---------------------------------------------------------------------------
# 7. missing section label produces warning
# ---------------------------------------------------------------------------

def test_multi_section_missing_label_warns(extractor: CSVExtractor, tmp_path: Path) -> None:
    # Build a CSV that has no "Clients Count" section
    csv_content = "Only Section\nHeader1,Header2\nA,B\n"
    csv_path = tmp_path / "growth.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    result = extractor.extract(csv_path, "client_growth")

    assert any("not found" in w for w in result.warnings)
    assert result.sections.get("client_growth.monthly_table") == []


# ---------------------------------------------------------------------------
# 8. UTF-8 BOM encoding
# ---------------------------------------------------------------------------

def test_utf8_bom_csv_is_read_correctly(
    extractor: CSVExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    csv_path = tmp_path / "license_bom.csv"
    # Write with BOM (utf-8-sig)
    csv_path.write_text(build_license_summary_csv(), encoding="utf-8-sig")

    result = extractor.extract(csv_path, machinery_subject)

    sid = f"{machinery_subject}.other_licenses"
    assert sid in result.sections
    rows = result.sections[sid]
    assert len(rows) == 2
    # BOM stripping is tested indirectly: if the first cell were '﻿License summary'
    # the header detection would fail and rows would be empty.


# ---------------------------------------------------------------------------
# 9. metadata rows before header are skipped
# ---------------------------------------------------------------------------

def test_single_table_skips_metadata_rows(
    extractor: CSVExtractor, machinery_subject: str, tmp_path: Path
) -> None:
    # The CSV builder puts "License summary" and "Generated on:..." before the header.
    csv_path = tmp_path / "license.csv"
    csv_path.write_text(build_license_summary_csv(), encoding="utf-8")

    result = extractor.extract(csv_path, machinery_subject)

    rows = result.sections[f"{machinery_subject}.other_licenses"]
    # If metadata rows were not skipped the extractor would find no matching
    # header and return []; assert we got actual data instead.
    assert len(rows) > 0
    # First row should be data, not "License summary" or "Generated on"
    assert rows[0]["license_name"] not in ("License summary", "Generated on: 2026-05-24")


# ---------------------------------------------------------------------------
# 10. unknown column header produces warning
# ---------------------------------------------------------------------------

def test_unknown_column_header_produces_warning(extractor: CSVExtractor, tmp_path: Path) -> None:
    # Write a CSV whose header does NOT include "Available Total" (required column).
    # The single_table header scan requires ALL column_map sources to be present;
    # when one is missing, no header row matches and a warning is emitted.
    csv_content = (
        "License summary\n"
        "\n"
        "Other Licenses - current usage details\n"
        '"License","Renamed Column","Used"\n'
        '"Lic A","10","5"\n'
    )
    csv_path = tmp_path / "license.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    result = extractor.extract(csv_path, "license_summary")

    assert any("no header row matching column_map found" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 11. result_to_artifact produces CanonicalArtifact from CSV result
# ---------------------------------------------------------------------------

def test_result_to_artifact_from_csv_result(tmp_path: Path) -> None:
    er = ExtractionResult(subject_id="license_summary", source_type="csv")
    er.sections["license_summary.other_licenses"] = [
        {"license_name": "Lic A", "available_total_raw": "10", "used_raw": "5"},
    ]
    er.section_output_types["license_summary.other_licenses"] = "table"
    er.section_titles["license_summary.other_licenses"] = "Other Licenses"

    artifact = result_to_artifact(
        er,
        subject_id="license_summary",
        subject_title="License Summary",
        file_path=tmp_path / "fake.csv",
    )

    assert isinstance(artifact, CanonicalArtifact)
    assert artifact.artifact_type == "license_summary"
    assert len(artifact.sections) == 1
    assert isinstance(artifact.sections[0], TableSection)
    assert artifact.sections[0].id == "license_summary.other_licenses"
    assert len(artifact.sections[0].items) == 1


# ---------------------------------------------------------------------------
# 12. integer coercion for capacity rows
# ---------------------------------------------------------------------------

def test_integer_coercion_for_capacity_rows(extractor: CSVExtractor, tmp_path: Path) -> None:
    csv_path = tmp_path / "growth.csv"
    csv_path.write_text(
        build_growth_and_trends_csv(
            capacity_rows=[
                ("2026-01", "Entity A", "2048"),
                ("2026-02", "Entity A", "-1"),  # sentinel → null via null_values
            ]
        ),
        encoding="utf-8",
    )

    result = extractor.extract(csv_path, "capacity_license")
    rows = result.sections["capacity_license.table"]

    assert rows[0]["used_capacity"] == 2048
    assert rows[1]["used_capacity"] is None  # "-1" is in null_values
