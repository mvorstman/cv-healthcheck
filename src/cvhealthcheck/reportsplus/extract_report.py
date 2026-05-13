from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from cvhealthcheck.output.json_report import to_pretty_json

from .catalog import CATALOG_DIR, collected_at, write_json
from .client import DATASETS_PATH, ReportsPlusClient
from .inventory import parse_content_field

REPORTSPLUS_CATALOG_DIR = CATALOG_DIR / "reportsplus"


def extract_report(
    report_id: str | int,
    client: ReportsPlusClient | None = None,
    execute: bool = True,
    sample_limit: int = 25,
) -> dict[str, Any]:
    report_id_value = str(report_id)
    reports_client = client or ReportsPlusClient()
    artifacts: dict[str, str] = {}

    report_result = reports_client.get_report(report_id_value)
    report_payload = _result_payload(report_result)
    artifacts["metadata"] = _write_report_artifact(
        report_id_value,
        "metadata",
        {
            "collected_at": collected_at(),
            "source_endpoint": report_result.url,
            "http_status": report_result.status_code,
            "ok": report_result.ok,
            "report": report_result.data,
            "error": report_result.error,
        },
    )

    definition = parse_content_field(report_result.data)
    artifacts["definition"] = _write_report_artifact(
        report_id_value,
        "definition",
        {
            "collected_at": collected_at(),
            "source_endpoint": report_result.url,
            "definition": definition,
        },
    )

    widgets = discover_widgets(definition)
    dataset_refs = discover_dataset_references(definition)
    dataset_map = build_dataset_map(reports_client, report_id_value, widgets, dataset_refs)
    artifacts["dataset_map"] = _write_report_artifact(
        report_id_value,
        "dataset_map",
        {
            "collected_at": collected_at(),
            "report_id": report_id_value,
            "widgets": widgets,
            "datasets": dataset_map,
        },
    )

    executions = []
    if execute:
        for mapping in dataset_map:
            execution = execute_mapping(
                reports_client,
                report_id_value,
                mapping,
                sample_limit=sample_limit,
            )
            executions.append(execution)
            raw_artifact = execution.get("raw_artifact")
            if raw_artifact:
                artifacts[f"raw_{mapping['artifact_key']}"] = raw_artifact

    summary = {
        "collected_at": collected_at(),
        "report_id": report_id_value,
        "report_ok": report_result.ok,
        "report_http_status": report_result.status_code,
        "report_name": _report_name(report_result.data),
        "widget_count": len(widgets),
        "dataset_count": len(dataset_map),
        "execution_count": len(executions),
        "executions_ok": sum(1 for item in executions if item.get("status") == "EXECUTABLE"),
        "artifacts": artifacts,
        "executions": executions,
    }
    artifacts["execution_summary"] = _write_report_artifact(
        report_id_value,
        "execution_summary",
        summary,
    )
    summary["artifacts"] = artifacts

    return {
        "report_id": report_id_value,
        "report": report_payload,
        "definition": definition,
        "widgets": widgets,
        "datasets": dataset_map,
        "executions": executions,
        "summary": summary,
        "artifacts": artifacts,
    }


def get_report_definition(report_id: str | int, client: ReportsPlusClient | None = None) -> Any:
    return parse_content_field((client or ReportsPlusClient()).get_report(str(report_id)).data)


def get_report_datasets(report_id: str | int, client: ReportsPlusClient | None = None) -> list[dict[str, Any]]:
    reports_client = client or ReportsPlusClient()
    definition = get_report_definition(report_id, reports_client)
    return build_dataset_map(
        reports_client,
        str(report_id),
        discover_widgets(definition),
        discover_dataset_references(definition),
    )


def execute_dataset(
    dataset_guid: str,
    parameters: dict[str, str] | None = None,
    client: ReportsPlusClient | None = None,
    limit: int = 25,
) -> Any:
    return (client or ReportsPlusClient()).get_dataset_data(
        dataset_guid=dataset_guid,
        parameters=parameters or {},
        limit=limit,
    )


def discover_widgets(definition: Any) -> list[dict[str, Any]]:
    widgets: list[dict[str, Any]] = []
    for path, node in _walk(definition):
        if not isinstance(node, dict) or not _looks_like_widget(node):
            continue
        dataset_info = _dataset_info(node)
        widgets.append(
            {
                "path": path,
                "title": _title_text(_first_key_value(node, ("title", "name", "displayName", "label"))),
                "type": _first_string(node, ("type", "chartType", "widgetType", "componentType")),
                "dataset_guid": dataset_info.get("dataset_guid"),
                "dataset_id": dataset_info.get("dataset_id"),
                "dataset_name": dataset_info.get("dataset_name"),
                "selected_fields": _component_fields(node),
                "filters": _first_key_value(node, ("filters", "filter", "where")),
                "sorting": _first_key_value(node, ("sort", "sorting", "orderBy", "orderby")),
                "limit": _first_key_value(node, ("limit", "top", "rowLimit")),
            }
        )
    return widgets


def discover_dataset_references(definition: Any) -> list[dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for path, node in _walk(definition):
        if not isinstance(node, dict):
            continue
        dataset_info = _dataset_info(node)
        guid = dataset_info.get("dataset_guid")
        dataset_id = dataset_info.get("dataset_id")
        dataset_name = dataset_info.get("dataset_name")
        if not guid and not dataset_id and not dataset_name:
            continue
        identity = str(guid or dataset_id or dataset_name or path)
        refs.setdefault(
            identity,
            {
                "path": path,
                "dataset_guid": guid,
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "selected_fields": _component_fields(node),
                "filters": _first_key_value(node, ("filters", "filter", "where")),
                "sorting": _first_key_value(node, ("sort", "sorting", "orderBy", "orderby")),
                "limit": _first_key_value(node, ("limit", "top", "rowLimit")),
            },
        )
    return list(refs.values())


def build_dataset_map(
    client: ReportsPlusClient,
    report_id: str,
    widgets: list[dict[str, Any]],
    dataset_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source in [*widgets, *dataset_refs]:
        dataset_guid = source.get("dataset_guid")
        dataset_id = source.get("dataset_id")
        dataset_name = source.get("dataset_name")
        if not dataset_guid and not dataset_id and not dataset_name:
            continue
        key = str(dataset_guid or dataset_id or dataset_name)
        mapping = merged.setdefault(
            key,
            {
                "report_id": report_id,
                "dataset_guid": dataset_guid,
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "artifact_key": _safe_artifact_key(str(dataset_guid or dataset_id or dataset_name)),
                "used_by": [],
                "required_parameters": [],
                "default_parameters": {},
                "available_fields": [],
                "selected_fields": [],
                "filters": [],
                "sorting": [],
                "limits": [],
                "execution_endpoint": (
                    f"{DATASETS_PATH}/{dataset_guid}/data" if dataset_guid else None
                ),
                "metadata_status": "NOT_FETCHED",
                "metadata_http_status": None,
            },
        )
        mapping["used_by"].append(_usage(source))
        _extend_unique(mapping["selected_fields"], source.get("selected_fields") or [])
        _append_if_present(mapping["filters"], source.get("filters"))
        _append_if_present(mapping["sorting"], source.get("sorting"))
        _append_if_present(mapping["limits"], source.get("limit"))

    for mapping in merged.values():
        dataset_guid = mapping.get("dataset_guid")
        if not dataset_guid:
            mapping["metadata_status"] = "MISSING_GUID"
            continue
        result = client.get_dataset_metadata(str(dataset_guid))
        mapping["metadata_http_status"] = result.status_code
        if not result.ok:
            mapping["metadata_status"] = "FAILED"
            mapping["metadata_error"] = result.error or result.text
            continue
        metadata = result.data
        mapping["metadata_status"] = "OK"
        mapping["dataset_name"] = mapping.get("dataset_name") or _dataset_name(metadata)
        mapping["dataset_id"] = mapping.get("dataset_id") or _dataset_id(metadata)
        mapping["available_fields"] = _metadata_fields(metadata)
        parameter_info = _metadata_parameters(metadata)
        mapping["required_parameters"] = parameter_info["required"]
        mapping["default_parameters"] = parameter_info["defaults"]

    return list(merged.values())


def execute_mapping(
    client: ReportsPlusClient,
    report_id: str,
    mapping: dict[str, Any],
    sample_limit: int = 25,
) -> dict[str, Any]:
    dataset_guid = mapping.get("dataset_guid")
    execution = {
        "dataset_guid": dataset_guid,
        "dataset_name": mapping.get("dataset_name"),
        "status": "SKIPPED",
        "http_status": None,
        "record_count": 0,
        "sample_rows": [],
        "raw_artifact": None,
        "error": None,
    }
    if not dataset_guid:
        execution["error"] = "Dataset GUID was not discovered."
        return execution
    required = set(mapping.get("required_parameters") or [])
    defaults = mapping.get("default_parameters") or {}
    missing = sorted(name for name in required if f"parameter.{name}" not in defaults)
    if missing:
        execution["status"] = "NEEDS_PARAMS"
        execution["error"] = "Missing required parameter values: " + ", ".join(missing)
        return execution

    result = execute_dataset(str(dataset_guid), defaults, client=client, limit=sample_limit)
    execution["http_status"] = result.status_code
    execution["raw_artifact"] = _write_raw_artifact(
        report_id,
        mapping["artifact_key"],
        {
            "collected_at": collected_at(),
            "dataset_guid": dataset_guid,
            "dataset_name": mapping.get("dataset_name"),
            "execution_endpoint": mapping.get("execution_endpoint"),
            "parameters": defaults,
            "http_status": result.status_code,
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
        },
    )
    if not result.ok:
        execution["status"] = "FAILS"
        execution["error"] = result.error or result.text
        return execution
    rows = _rows(result.data)
    execution["status"] = "EXECUTABLE"
    execution["record_count"] = len(rows)
    execution["sample_rows"] = rows[:sample_limit]
    return execution


def _walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _looks_like_widget(node: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in node}
    if any(key in keys for key in {"charttype", "widgettype", "componenttype"}):
        return True
    node_type = str(node.get("type", "")).lower()
    if node_type in {"chart", "table", "grid", "metric", "tile", "component"}:
        return True
    return "title" in keys and any(
        key in keys
        for key in {"dataset", "datafield", "dimensiondatafield", "measuredatafield"}
    )


def _first_key_value(node: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in node and node[key] not in (None, ""):
            return node[key]
    lowered = {str(key).lower(): key for key in node}
    for key in keys:
        actual = lowered.get(key.lower())
        if actual is not None and node[actual] not in (None, ""):
            return node[actual]
    return None


def _first_string(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_key_value(node, keys)
    return str(value) if value not in (None, "") else None


def _field_names(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                candidate = _first_key_value(
                    item,
                    ("name", "field", "dataField", "fieldName", "column", "label"),
                )
                if candidate:
                    names.append(str(candidate))
        return names
    if isinstance(value, dict):
        return _field_names(list(value.values()))
    return []


def _component_fields(node: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in (
        "fields",
        "columns",
        "selectedFields",
        "dimensionDataField",
        "measureDataField",
    ):
        _extend_unique(names, _field_names(_first_key_value(node, (key,))))
    return names


def _dataset_info(node: dict[str, Any]) -> dict[str, Any]:
    nested = node.get("dataSet")
    source = nested if isinstance(nested, dict) else node
    dataset_guid = _first_key_value(source, ("datasetGuid", "dataSetGuid"))
    if dataset_guid is None and (
        _first_key_value(source, ("datasetId", "dataSetId"))
        or _first_string(source, ("datasetName", "dataSetName"))
    ):
        dataset_guid = _first_key_value(source, ("guid",))
    return {
        "dataset_guid": dataset_guid,
        "dataset_id": _first_key_value(source, ("datasetId", "dataSetId")),
        "dataset_name": _first_string(source, ("datasetName", "dataSetName")),
    }


def _title_text(value: Any) -> str | None:
    if isinstance(value, dict):
        text = _first_key_value(value, ("text", "label", "name"))
        return str(text) if text not in (None, "") else None
    return str(value) if value not in (None, "") else None


def _usage(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": source.get("path"),
        "title": source.get("title"),
        "type": source.get("type"),
    }


def _extend_unique(target: list[Any], values: list[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _append_if_present(target: list[Any], value: Any) -> None:
    if value not in (None, "", [], {}) and value not in target:
        target.append(value)


def _metadata_fields(metadata: Any) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    fields = metadata.get("fields")
    return _field_names(fields)


def _metadata_parameters(metadata: Any) -> dict[str, Any]:
    required: list[str] = []
    defaults: dict[str, str] = {}
    if not isinstance(metadata, dict):
        return {"required": required, "defaults": defaults}
    operation = metadata.get("GetOperation")
    if not isinstance(operation, dict):
        return {"required": required, "defaults": defaults}
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("name")
        if not name:
            continue
        name_str = str(name)
        if parameter.get("required") is True:
            required.append(name_str)
        default = _parameter_default(parameter)
        if default is not None:
            defaults[f"parameter.{name_str}"] = default
    return {"required": required, "defaults": defaults}


def _parameter_default(parameter: dict[str, Any]) -> str | None:
    for key in ("defaultValue", "default", "value"):
        value = parameter.get(key)
        if value not in (None, ""):
            return str(value)
    values = parameter.get("values")
    if isinstance(values, list) and values:
        first = values[0]
        if first not in (None, "") and not str(first).startswith("=input."):
            return str(first)
    return None


def _dataset_name(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    nested = metadata.get("dataSet")
    if isinstance(nested, dict):
        value = nested.get("dataSetName")
        if value:
            return str(value)
    value = metadata.get("dataSetName")
    return str(value) if value else None


def _dataset_id(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    nested = metadata.get("dataSet")
    if isinstance(nested, dict):
        value = nested.get("dataSetId")
        if value is not None:
            return str(value)
    value = metadata.get("dataSetId")
    return str(value) if value is not None else None


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("records", "rows", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        for value in data.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
    return []


def _result_payload(result: Any) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "http_status": result.status_code,
        "url": result.url,
        "data": result.data,
        "error": result.error,
    }


def _report_name(data: Any) -> str | None:
    if isinstance(data, dict):
        value = data.get("reportName") or data.get("name")
        return str(value) if value else None
    return None


def _safe_artifact_key(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return safe[:120] or "unknown_dataset"


def _write_report_artifact(report_id: str, suffix: str, payload: Any) -> str:
    path = write_json(
        f"report_{report_id}_{suffix}.json",
        payload,
        catalog_dir=REPORTSPLUS_CATALOG_DIR,
    )
    return str(path)


def _write_raw_artifact(report_id: str, dataset_key: str, payload: Any) -> str:
    path = write_json(
        f"report_{report_id}_raw_{dataset_key}.json",
        payload,
        catalog_dir=REPORTSPLUS_CATALOG_DIR,
    )
    return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=25)
    args = parser.parse_args(argv)

    result = extract_report(
        args.report_id,
        execute=not args.no_execute,
        sample_limit=args.sample_limit,
    )
    print(to_pretty_json(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
