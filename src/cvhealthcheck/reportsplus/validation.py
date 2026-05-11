from __future__ import annotations

from typing import Any

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.auth import load_login_token

from .catalog import collected_at
from .client import DATASETS_PATH


def validate_candidates(
    candidates: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    priority: str = "HIGH",
    limit: int = 5,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    datasets_by_guid = {
        str(dataset.get("guid") or _nested_dataset(dataset).get("dataSetGuid")): dataset
        for dataset in datasets
        if dataset.get("guid") or _nested_dataset(dataset).get("dataSetGuid")
    }
    selected = _select_candidates(candidates, priority, limit, include_all)
    client = _dataset_execution_client()
    results: list[dict[str, Any]] = []
    for candidate in selected:
        results.append(_validate_candidate(candidate, datasets_by_guid, client))
    return results


def validation_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    statuses = ("EXECUTABLE", "NEEDS_PARAMS", "FAILS", "SKIPPED")
    return {
        status: sum(1 for record in records if record.get("status") == status)
        for status in statuses
    }


def _select_candidates(
    candidates: list[dict[str, Any]],
    priority: str,
    limit: int,
    include_all: bool,
) -> list[dict[str, Any]]:
    filtered = candidates if include_all else [
        candidate for candidate in candidates if candidate.get("priority") == priority
    ]
    datasets = [candidate for candidate in filtered if candidate.get("source_type") == "dataset"]
    reports = [candidate for candidate in filtered if candidate.get("source_type") != "dataset"]
    ordered = datasets + reports
    return ordered if include_all else ordered[:limit]


def _validate_candidate(
    candidate: dict[str, Any],
    datasets_by_guid: dict[str, dict[str, Any]],
    client: CommvaultApiClient,
) -> dict[str, Any]:
    now = collected_at()
    base = {
        "candidate_name": candidate.get("name"),
        "source_type": candidate.get("source_type"),
        "priority": candidate.get("priority"),
        "mapped_health_area": candidate.get("mapped_health_area"),
        "dataset_id": None,
        "dataset_guid": candidate.get("guid"),
        "dataset_name": None,
        "attempted_endpoint": None,
        "parameters_used": {},
        "status": "SKIPPED",
        "http_status": None,
        "record_count": None,
        "returned_fields": [],
        "error_summary": None,
        "validation_time": now,
    }
    if candidate.get("source_type") != "dataset":
        base["error_summary"] = "Candidate is not a dataset."
        return base
    dataset_guid = str(candidate.get("guid") or "")
    if not dataset_guid:
        base["error_summary"] = "Dataset candidate has no GUID."
        return base
    dataset = datasets_by_guid.get(dataset_guid)
    if not dataset:
        base["status"] = "FAILS"
        base["error_summary"] = "Dataset metadata not found in datasets catalog."
        return base

    nested = _nested_dataset(dataset)
    base["dataset_id"] = nested.get("dataSetId")
    base["dataset_name"] = nested.get("dataSetName") or candidate.get("name")
    endpoint = f"{DATASETS_PATH}/{dataset_guid}/data"
    base["attempted_endpoint"] = endpoint

    parameter_state = _parameters_from_dataset(dataset)
    base["parameters_used"] = parameter_state["parameters"]
    if parameter_state["missing"]:
        base["status"] = "NEEDS_PARAMS"
        base["error_summary"] = (
            "Missing required parameter values: "
            + ", ".join(parameter_state["missing"])
        )
        return base

    params = {
        "format": "object",
        "includeOther": "false",
        "limit": "10",
        **parameter_state["parameters"],
    }
    result = client.get(endpoint, params=params)
    base["http_status"] = result.status_code
    if not result.ok:
        base["status"] = "FAILS"
        base["error_summary"] = _error_summary(result)
        return base

    fields = _returned_fields(result.data)
    base["returned_fields"] = fields
    base["record_count"] = _record_count(result.data)
    if fields:
        base["status"] = "EXECUTABLE"
    else:
        base["status"] = "FAILS"
        base["error_summary"] = "Response did not include returned fields."
    return base


def _dataset_execution_client() -> CommvaultApiClient:
    login_token = load_login_token()
    if login_token:
        return CommvaultApiClient(token=login_token)
    return CommvaultApiClient()


def _parameters_from_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    operation = dataset.get("GetOperation")
    if not isinstance(operation, dict):
        return {"parameters": {}, "missing": []}
    parameters: dict[str, str] = {}
    missing: list[str] = []
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("name")
        if not name:
            continue
        literal = _literal_value(parameter)
        if literal is not None:
            parameters[f"parameter.{name}"] = literal
        elif parameter.get("required") is True:
            missing.append(str(name))
    return {"parameters": parameters, "missing": missing}


def _literal_value(parameter: dict[str, Any]) -> str | None:
    values = parameter.get("values")
    if not isinstance(values, list) or not values:
        return None
    first = values[0]
    if first is None:
        return None
    value = str(first)
    if value.startswith("=input."):
        return None
    return value


def _returned_fields(data: Any) -> list[str]:
    if isinstance(data, dict):
        columns = data.get("columns")
        if isinstance(columns, list):
            fields = []
            for column in columns:
                if isinstance(column, dict):
                    fields.append(str(column.get("name") or column.get("dataField") or ""))
            return [field for field in fields if field]
        records = data.get("records")
        if isinstance(records, list) and records and isinstance(records[0], dict):
            return sorted(str(key) for key in records[0].keys())
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return sorted(str(key) for key in data[0].keys())
    return []


def _record_count(data: Any) -> int | None:
    if isinstance(data, dict):
        for key in ("recordsCount", "record_count", "totalRecordCount"):
            value = data.get(key)
            if isinstance(value, int):
                return value
        records = data.get("records")
        if isinstance(records, list):
            return len(records)
    if isinstance(data, list):
        return len(data)
    return None


def _error_summary(result: Any) -> str:
    if result.error:
        return str(result.error)[:300]
    if result.text:
        return result.text[:300]
    return "Request failed."


def _nested_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    nested = dataset.get("dataSet")
    return nested if isinstance(nested, dict) else {}
