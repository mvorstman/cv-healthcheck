from __future__ import annotations

import json
from typing import Any

REPORT_SUMMARY_FIELDS = [
    "reportId",
    "reportName",
    "guid",
    "deployed",
    "viewable",
    "editable",
    "isMetrics",
]

DATASET_SUMMARY_FIELDS = [
    "dataSetId",
    "dataSetName",
    "dataSetGuid",
    "guid",
    "deployed",
    "endpoint",
]

LOGIN_TOKEN_REQUIRED_MESSAGE = (
    "Reports Plus inventory requires a Login API token. "
    "Create .login_token or set CV_LOGIN_TOKEN."
)


def extract_records(value: Any, preferred_keys: tuple[str, ...] = ()) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []

    for key in preferred_keys:
        child = value.get(key)
        if isinstance(child, list):
            return child
        if isinstance(child, dict):
            nested = extract_records(child, preferred_keys)
            if nested:
                return nested

    for key in ("records", "items", "data", "reports", "datasets", "dataSet", "rows"):
        child = value.get(key)
        if isinstance(child, list):
            return child
        if isinstance(child, dict):
            nested = extract_records(child, preferred_keys)
            if nested:
                return nested

    if any(key in value for key in REPORT_SUMMARY_FIELDS + DATASET_SUMMARY_FIELDS):
        return [value]

    return []


def summarize_records(records: list[Any], fields: list[str]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        summary.append({field: _field_value(record, field) for field in fields})
    return summary


def _field_value(record: dict[str, Any], field: str) -> Any:
    value = record.get(field)
    if value is not None:
        return value
    nested_dataset = record.get("dataSet")
    if isinstance(nested_dataset, dict):
        return nested_dataset.get(field)
    return None


def filter_reports(
    records: list[Any],
    name: str | None = None,
    metrics_only: bool = False,
    deployed: bool | None = None,
    viewable: bool | None = None,
) -> list[Any]:
    filtered: list[Any] = []
    needle = name.lower() if name else None
    for record in records:
        if not isinstance(record, dict):
            continue
        if needle and needle not in str(record.get("reportName", "")).lower():
            continue
        if metrics_only and record.get("isMetrics") is not True:
            continue
        if deployed is not None and record.get("deployed") is not deployed:
            continue
        if viewable is not None and record.get("viewable") is not viewable:
            continue
        filtered.append(record)
    return filtered


def parse_content_field(report: Any) -> Any:
    if not isinstance(report, dict) or "content" not in report:
        return None
    content = report.get("content")
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def find_report_content_clues(content: Any) -> dict[str, list[Any]]:
    clues = {
        "dataset_references": [],
        "dataset_guids": [],
        "chart_definitions": [],
        "metrics_references": [],
        "query_structures": [],
    }
    _collect_clues(content, clues)
    return clues


def _collect_clues(value: Any, clues: dict[str, list[Any]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower()
            if "dataset" in normalized:
                clues["dataset_references"].append({key: child})
            if "guid" in normalized and "dataset" in normalized:
                clues["dataset_guids"].append(child)
            if "chart" in normalized:
                clues["chart_definitions"].append({key: child})
            if "metric" in normalized:
                clues["metrics_references"].append({key: child})
            if normalized in {"query", "sql", "querytext", "datasource", "datasources"}:
                clues["query_structures"].append({key: child})
            _collect_clues(child, clues)
    elif isinstance(value, list):
        for child in value:
            _collect_clues(child, clues)
