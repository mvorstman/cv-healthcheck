from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from cvhealthcheck.reportsplus.client import ReportsPlusClient
from cvhealthcheck.reportsplus.inventory import parse_content_field

from .artifact import build_license_summary_artifact, write_license_summary_artifact
from .import_csv import _artifact_from_rows
from .normalize import (
    normalize_agent_feature_record,
    normalize_other_license_record,
    parse_number,
)

LICENSE_SUMMARY_REPORT_ID = "206"
OTHER_LICENSE_SECTION_TITLE = "Other Licenses - current usage details"
AGENT_FEATURE_SECTION_TITLE = "Agent and Feature Licenses - current usage details"


def collect_license_summary_rest(
    *,
    client: ReportsPlusClient | None = None,
    sample_limit: int = 500,
    write_artifact: bool = True,
) -> dict[str, Any]:
    reports_client = client or ReportsPlusClient()
    report = reports_client.get_report(LICENSE_SUMMARY_REPORT_ID)
    if not report.ok:
        artifact = build_license_summary_artifact(
            source_type="rest",
            generated_on=None,
            source={
                "report_id": LICENSE_SUMMARY_REPORT_ID,
                "report_name": "License summary",
                "source_endpoint": report.url,
                "http_status": report.status_code,
                "ok": report.ok,
                "error": report.error,
            },
            metadata={},
            other_licenses=[],
            agent_feature_licenses=[],
            extra={
                "datasets": [],
                "source_metadata": {
                    "report_id": LICENSE_SUMMARY_REPORT_ID,
                    "executions": [],
                },
            },
        )
        if write_artifact:
            artifact["artifact_paths"] = write_license_summary_artifact(artifact)
        extraction = {
            "report_id": LICENSE_SUMMARY_REPORT_ID,
            "report": {
                "ok": report.ok,
                "http_status": report.status_code,
                "url": report.url,
                "data": report.data,
                "error": report.error,
            },
            "definition": None,
            "datasets": [],
            "executions": [],
            "summary": {
                "report_id": LICENSE_SUMMARY_REPORT_ID,
                "report_name": "License summary",
                "report_ok": report.ok,
                "report_http_status": report.status_code,
                "collected_at": None,
            },
        }
        return {
            "extraction": extraction,
            "normalized": artifact,
            "artifact": artifact.get("artifact_paths", {}).get("latest"),
        }
    definition = parse_content_field(report.data)
    page = _find_license_summary_page(definition)
    if page is None:
        raise ValueError("License Summary detail page was not found in report 206.")

    dataset_specs = _license_summary_dataset_specs(page)
    org_spec = _required_dataset_spec(dataset_specs, "organization")
    other_spec = _required_dataset_spec(dataset_specs, "other")
    agent_spec = _required_dataset_spec(dataset_specs, "agent")
    metadata_spec = _required_dataset_spec(dataset_specs, "metadata")

    organization_execution = _execute_dataset_spec(
        reports_client,
        org_spec,
        parameters={},
        sample_limit=sample_limit,
    )
    org_rows = organization_execution.get("sample_rows") or []
    org_guid_candidates = _organization_guid_candidates(org_rows)

    metadata_execution = _execute_with_guid_candidates(
        reports_client,
        metadata_spec,
        org_guid_candidates,
        sample_limit=sample_limit,
    )
    other_execution = _execute_with_guid_candidates(
        reports_client,
        other_spec,
        org_guid_candidates,
        sample_limit=sample_limit,
    )
    agent_execution = _execute_with_guid_candidates(
        reports_client,
        agent_spec,
        org_guid_candidates,
        sample_limit=sample_limit,
    )

    execution_by_kind = {
        "organization": organization_execution,
        "metadata": metadata_execution,
        "other": other_execution,
        "agent": agent_execution,
    }
    extraction = {
        "report_id": LICENSE_SUMMARY_REPORT_ID,
        "report": {
            "ok": report.ok,
            "http_status": report.status_code,
            "url": report.url,
            "data": report.data,
            "error": report.error,
        },
        "definition": definition,
        "datasets": dataset_specs,
        "executions": [
            execution_by_kind.get(str(spec.get("kind") or ""), {})
            for spec in dataset_specs
        ],
        "summary": {
            "report_id": LICENSE_SUMMARY_REPORT_ID,
            "report_name": _report_name(report.data) or "License summary",
            "report_ok": report.ok,
            "report_http_status": report.status_code,
            "collected_at": metadata_execution.get("collected_at"),
        },
    }
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
        header_kind = str(mapping.get("kind") or execution.get("kind") or "")
        if header_kind == "other":
            other_licenses.extend(_normalize_live_other_license_row(row) for row in rows if isinstance(row, dict))
            continue
        if header_kind == "agent":
            agent_feature_licenses.extend(_normalize_live_agent_feature_row(row) for row in rows if isinstance(row, dict))
            continue

        normalized_rows = [_normalize_rest_row(row) for row in rows if isinstance(row, dict)]
        dataset_name = str(mapping.get("dataset_name") or execution.get("dataset_name") or "")
        legacy_kind = _rest_dataset_kind(dataset_name, normalized_rows)
        if legacy_kind == "other":
            other_licenses.extend(normalize_other_license_record(row) for row in normalized_rows)
        elif legacy_kind == "agent":
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
                elif lowered == "version" and value:
                    metadata.setdefault("commcell_version", value)
                elif lowered == "timezone" and value:
                    metadata.setdefault("timezone", value)
                elif lowered == "time zone" and value:
                    metadata.setdefault("timezone", value)
                elif lowered == "last collection time" and value:
                    metadata.setdefault("last_collection_time", value)
                elif lowered == "license expiry" and value:
                    metadata.setdefault("license_expiry", value)
                elif lowered == "last generation time" and value:
                    metadata.setdefault("last_generation_time", value)
                elif lowered == "last application time" and value:
                    metadata.setdefault("last_application_time", value)
                elif lowered == "commcell" and value:
                    metadata.setdefault("commcell_name", value)
                elif lowered == "commcellid" and value:
                    metadata.setdefault("commcell_id", str(value))
                elif lowered == "data source" and value:
                    metadata.setdefault("commcell_name", value)
    return metadata


def _find_license_summary_page(definition: Any) -> dict[str, Any] | None:
    if not isinstance(definition, dict):
        return None
    for page in definition.get("pages", []):
        if not isinstance(page, dict):
            continue
        components = (
            page.get("body", {}).get("reportComponents", [])
            if isinstance(page.get("body"), dict)
            else []
        )
        titles = {
            str(component.get("title", {}).get("text") or "").strip()
            for component in components
            if isinstance(component, dict)
        }
        if {
            OTHER_LICENSE_SECTION_TITLE,
            AGENT_FEATURE_SECTION_TITLE,
        }.issubset(titles):
            return page
    return None


def _license_summary_dataset_specs(page: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    datasets = page.get("dataSets", {}).get("dataSet", [])
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        fields = _dataset_fields(dataset)
        kind = _page_dataset_kind(fields)
        if kind is None:
            continue
        specs.append(
            {
                "kind": kind,
                "dataset_guid": dataset.get("guid"),
                "dataset_name": dataset.get("dataSet", {}).get("dataSetName"),
                "fields": fields,
                "parameter_names": [
                    str(parameter.get("name"))
                    for parameter in dataset.get("GetOperation", {}).get("parameters", [])
                    if isinstance(parameter, dict) and parameter.get("name")
                ],
            }
        )
    return specs


def _dataset_fields(dataset: dict[str, Any]) -> list[str]:
    fields = dataset.get("fields")
    names: list[str] = []
    if not isinstance(fields, list):
        return names
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = field.get("name") or field.get("dataField")
        if name:
            names.append(str(name))
    return names


def _page_dataset_kind(fields: list[str]) -> str | None:
    field_set = set(fields)
    if {"OrgGUID", "Organization"}.issubset(field_set):
        return "organization"
    if {"Last Collection Time", "License Expiry"}.issubset(field_set):
        return "metadata"
    if {"Dial", "Purchased", "PermTotal", "Eval", "Usage"}.issubset(field_set):
        return "other"
    if {
        "License",
        "Permanent Total",
        "Permanent Used",
        "Evaluation Total",
        "Evaluation Used",
        "Client",
        "Agent",
    }.issubset(field_set):
        return "agent"
    return None


def _required_dataset_spec(specs: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for spec in specs:
        if spec.get("kind") == kind:
            return spec
    raise ValueError(f"License Summary report is missing the {kind} dataset definition.")


def _execute_with_guid_candidates(
    client: ReportsPlusClient,
    spec: dict[str, Any],
    guid_candidates: list[str],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    parameter_name = _guid_parameter_name(spec)
    if parameter_name is None:
        return _execute_dataset_spec(client, spec, parameters={}, sample_limit=sample_limit)

    attempts: list[dict[str, Any]] = []
    for guid in guid_candidates:
        execution = _execute_dataset_spec(
            client,
            spec,
            parameters={f"parameter.{parameter_name}": guid},
            sample_limit=sample_limit,
        )
        attempts.append(execution)
        if execution.get("sample_rows"):
            execution["attempts"] = [_attempt_summary(item) for item in attempts]
            return execution
    if attempts:
        attempts[-1]["attempts"] = [_attempt_summary(item) for item in attempts]
        return attempts[-1]
    return _execute_dataset_spec(client, spec, parameters={}, sample_limit=sample_limit)


def _guid_parameter_name(spec: dict[str, Any]) -> str | None:
    parameter_names = spec.get("parameter_names") or []
    for name in parameter_names:
        if str(name).upper() == "GUID":
            return str(name)
    return str(parameter_names[0]) if parameter_names else None


def _execute_dataset_spec(
    client: ReportsPlusClient,
    spec: dict[str, Any],
    *,
    parameters: dict[str, str],
    sample_limit: int,
) -> dict[str, Any]:
    dataset_guid = str(spec.get("dataset_guid") or "")
    result = client.get_dataset_data(
        dataset_guid,
        parameters=parameters,
        limit=sample_limit,
    )
    rows = _rows_from_payload(result.data) if result.ok else []
    return {
        "kind": spec.get("kind"),
        "dataset_guid": dataset_guid,
        "dataset_name": spec.get("dataset_name"),
        "status": "EXECUTABLE" if result.ok else "FAILS",
        "http_status": result.status_code,
        "record_count": len(rows),
        "sample_rows": rows[:sample_limit],
        "parameters": parameters,
        "error": result.error,
        "collected_at": result.data.get("timestamp") if isinstance(result.data, dict) else None,
        "raw_data": result.data,
    }


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "rows", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
    return []


def _attempt_summary(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_guid": execution.get("dataset_guid"),
        "dataset_name": execution.get("dataset_name"),
        "http_status": execution.get("http_status"),
        "record_count": execution.get("record_count"),
        "parameters": dict(execution.get("parameters") or {}),
        "error": execution.get("error"),
    }


def _organization_guid_candidates(rows: list[dict[str, Any]]) -> list[str]:
    preferred: list[str] = []
    fallback: list[str] = []
    for row in rows:
        guid = str(row.get("OrgGUID") or "").strip()
        if not guid or guid in preferred or guid in fallback:
            continue
        organization = str(row.get("Organization") or "").strip().lower()
        if guid == "-1" or organization == "commcell":
            preferred.append(guid)
        else:
            fallback.append(guid)
    return preferred + fallback


def _normalize_live_other_license_row(row: dict[str, Any]) -> dict[str, Any]:
    license_usage_type = parse_number(row.get("LicUsageType"))
    available_total = _format_other_license_value(row.get("Purchased"), license_usage_type)
    used = _format_other_license_value(row.get("Usage"), license_usage_type)
    record = normalize_other_license_record(
        {
            "License": row.get("Dial"),
            "Available Total": available_total,
            "Used": used,
        }
    )
    record["raw_fields"] = dict(row)
    return record


def _normalize_live_agent_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    record = normalize_agent_feature_record(
        {
            "License": row.get("License"),
            "Permanent Total": _stringify_numeric_or_unlimited(row.get("Permanent Total")),
            "Permanent Used": row.get("Permanent Used"),
            "Term Total": _stringify_numeric_or_unlimited(row.get("Evaluation Total")),
            "Term Used": row.get("Evaluation Used"),
            "Client": row.get("Client"),
            "Agent": row.get("Agent"),
            "Install Date": row.get("Install Date"),
        }
    )
    record["raw_fields"] = dict(row)
    return record


def _format_other_license_value(value: Any, license_usage_type: int | None) -> str:
    number = _stringify_numeric_or_unlimited(value)
    unit = _license_usage_unit(license_usage_type)
    return f"{number} {unit}".strip() if unit else number


def _stringify_numeric_or_unlimited(value: Any) -> str:
    number = parse_number(value)
    if number == -1:
        return "Unlimited"
    if number is not None:
        return str(number)
    text = "" if value is None else str(value).strip()
    return text


def _license_usage_unit(license_usage_type: int | None) -> str | None:
    if license_usage_type in {100031, 100016, 100015, -1}:
        return "TB"
    if license_usage_type in {200003, 100027, 200001, 100021}:
        return "VMs"
    if license_usage_type in {100030, 200002, 100029, 200017}:
        return "clients"
    if license_usage_type in {100026, 100025}:
        return "users"
    if license_usage_type == 100017:
        return "millions"
    if license_usage_type == 200016:
        return "source VMs"
    if license_usage_type in {100019, 100033}:
        return "instances"
    return None


def _report_name(data: Any) -> str | None:
    if isinstance(data, dict):
        nested = data.get("report")
        if isinstance(nested, dict):
            value = nested.get("customReportName") or nested.get("reportName")
            if value:
                return str(value)
        value = data.get("reportName") or data.get("customReportName") or data.get("name")
        return str(value) if value else None
    return None


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
