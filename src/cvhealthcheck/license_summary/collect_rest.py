from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from cvhealthcheck.reportsplus.extract_report import extract_report

from .artifact import build_license_summary_artifact, write_license_summary_artifact
from .import_csv import _artifact_from_rows
from .normalize import normalize_agent_feature_record, normalize_other_license_record

LICENSE_SUMMARY_REPORT_ID = "206"


def collect_license_summary_rest(
    *,
    execute: bool = True,
    sample_limit: int = 500,
    write_artifact: bool = True,
) -> dict[str, Any]:
    extraction = extract_report(LICENSE_SUMMARY_REPORT_ID, execute=execute, sample_limit=sample_limit)
    artifact = normalize_license_summary_rest_extraction(extraction)
    if write_artifact:
        artifact["artifact_paths"] = write_license_summary_artifact(artifact)
    return {
        "extraction": extraction,
        "normalized": artifact,
        "artifact": artifact.get("artifact_paths", {}).get("latest"),
    }


def normalize_license_summary_rest_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    summary = extraction.get("summary", {})
    datasets = extraction.get("datasets", [])
    executions = extraction.get("executions", [])
    other_licenses: list[dict[str, Any]] = []
    agent_feature_licenses: list[dict[str, Any]] = []
    metadata = _metadata_from_execution_rows(executions)
    for mapping, execution in zip(datasets, executions, strict=False):
        if execution.get("status") != "EXECUTABLE":
            continue
        rows = execution.get("sample_rows") or []
        normalized_rows = [_normalize_rest_row(row) for row in rows if isinstance(row, dict)]
        dataset_name = str(mapping.get("dataset_name") or execution.get("dataset_name") or "")
        header_kind = _rest_dataset_kind(dataset_name, normalized_rows)
        if header_kind == "other":
            other_licenses.extend(normalize_other_license_record(row) for row in normalized_rows)
        elif header_kind == "agent":
            agent_feature_licenses.extend(normalize_agent_feature_record(row) for row in normalized_rows)

    return build_license_summary_artifact(
        source_type="rest",
        generated_on=summary.get("collected_at"),
        source={
            "report_id": LICENSE_SUMMARY_REPORT_ID,
            "report_name": summary.get("report_name") or "License summary",
            "source_endpoint": extraction.get("report", {}).get("url"),
            "http_status": summary.get("report_http_status"),
            "ok": summary.get("report_ok"),
        },
        metadata=metadata,
        other_licenses=other_licenses,
        agent_feature_licenses=agent_feature_licenses,
        extra={
            "artifacts": extraction.get("artifacts", {}),
            "datasets": datasets,
            "source_metadata": {
                "report_id": LICENSE_SUMMARY_REPORT_ID,
                "executions": executions,
            },
        },
    )


def import_license_summary_xlsx_recording(
    file_path: str | Path,
    *,
    write_artifact: bool = True,
) -> dict[str, Any]:
    path = Path(file_path)
    artifact = parse_license_summary_xlsx_recording(
        path.read_bytes(),
        source_file=str(path),
    )
    if write_artifact:
        artifact["artifact_paths"] = write_license_summary_artifact(artifact)
    return artifact


def parse_license_summary_xlsx_recording(
    workbook_bytes: bytes,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    rows = _xlsx_rows(workbook_bytes)
    artifact = _artifact_from_rows(rows, source_type="rest", source_file=source_file)
    artifact["source"] = {
        **dict(artifact.get("source") or {}),
        "title": dict(artifact.get("source") or {}).get("title") or "License summary",
        "recording_type": "xlsx",
    }
    return artifact


def _metadata_from_execution_rows(executions: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for execution in executions:
        for row in execution.get("sample_rows") or []:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_rest_row(row)
            for key, value in normalized.items():
                lowered = str(key).strip().lower()
                if lowered == "commcell name" and value:
                    metadata.setdefault("commcell_name", value)
                elif lowered == "commcell version" and value:
                    metadata.setdefault("commcell_version", value)
                elif lowered == "timezone" and value:
                    metadata.setdefault("timezone", value)
                elif lowered == "last collection time" and value:
                    metadata.setdefault("last_collection_time", value)
                elif lowered == "license expiry" and value:
                    metadata.setdefault("license_expiry", value)
                elif lowered == "last generation time" and value:
                    metadata.setdefault("last_generation_time", value)
                elif lowered == "last application time" and value:
                    metadata.setdefault("last_application_time", value)
    return metadata


def _rest_dataset_kind(dataset_name: str, rows: list[dict[str, Any]]) -> str | None:
    lowered_name = dataset_name.lower()
    if "other licenses" in lowered_name:
        return "other"
    if "agent and feature licenses" in lowered_name:
        return "agent"
    if rows:
        keys = {str(key).strip().lower() for key in rows[0]}
        if {"license", "available total", "used"}.issubset(keys):
            return "other"
        if {"license", "permanent total", "permanent used", "term total", "term used"}.issubset(keys):
            return "agent"
    return None


def _normalize_rest_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        text_key = str(key).replace("_", " ").strip()
        normalized[text_key.title() if text_key.islower() else text_key] = value
    return normalized


def _xlsx_rows(workbook_bytes: bytes) -> list[list[str]]:
    with zipfile.ZipFile(BytesIO(workbook_bytes)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        rows: list[list[str]] = []
        for sheet_name in sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")):
            root = ET.fromstring(archive.read(sheet_name))
            namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for row in root.findall(".//main:sheetData/main:row", namespace):
                values: list[str] = []
                for cell in row.findall("main:c", namespace):
                    values.append(_xlsx_cell_value(cell, shared_strings, namespace))
                rows.append(values)
        return rows


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("main:si", namespace):
        text_fragments = [
            node.text or ""
            for node in item.findall(".//main:t", namespace)
        ]
        values.append("".join(text_fragments))
    return values


def _xlsx_cell_value(
    cell: ET.Element,
    shared_strings: list[str],
    namespace: dict[str, str],
) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", namespace)).strip()
    value_node = cell.find("main:v", namespace)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError):
            return value
    return value
