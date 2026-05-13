from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import CATALOG_DIR, collected_at, read_json, write_json

REPORTSPLUS_CATALOG_DIR = CATALOG_DIR / "reportsplus"


def build_report_metric_inventory(
    report_id: str | int,
    catalog_dir: Path = REPORTSPLUS_CATALOG_DIR,
) -> dict[str, Any]:
    report_id_value = str(report_id)
    dataset_map = read_json(
        f"report_{report_id_value}_dataset_map.json",
        catalog_dir=catalog_dir,
    )
    execution_summary = read_json(
        f"report_{report_id_value}_execution_summary.json",
        catalog_dir=catalog_dir,
    )

    executions_by_guid = {
        item.get("dataset_guid"): item
        for item in execution_summary.get("executions", [])
        if item.get("dataset_guid")
    }
    metrics = [
        _metric_entry(mapping, executions_by_guid.get(mapping.get("dataset_guid")), catalog_dir)
        for mapping in dataset_map.get("datasets", [])
    ]
    categories: dict[str, int] = {}
    usefulness: dict[str, int] = {}
    unclear = []
    for metric in metrics:
        categories[metric["category"]] = categories.get(metric["category"], 0) + 1
        usefulness[metric["healthcheck_usefulness"]] = (
            usefulness.get(metric["healthcheck_usefulness"], 0) + 1
        )
        if metric["category"] == "low-value / unclear":
            unclear.append(metric["dataset_name"])

    inventory = {
        "collected_at": collected_at(),
        "report_id": report_id_value,
        "report_name": execution_summary.get("report_name"),
        "source_artifacts": {
            "dataset_map": str(catalog_dir / f"report_{report_id_value}_dataset_map.json"),
            "execution_summary": str(
                catalog_dir / f"report_{report_id_value}_execution_summary.json"
            ),
        },
        "dataset_count": len(metrics),
        "categories": dict(sorted(categories.items())),
        "healthcheck_usefulness": dict(sorted(usefulness.items())),
        "unclear_datasets": unclear,
        "metrics": metrics,
    }
    write_json(
        f"report_{report_id_value}_metric_inventory.json",
        inventory,
        catalog_dir=catalog_dir,
    )
    return inventory


def load_report_metric_inventory(
    report_id: str | int,
    catalog_dir: Path = REPORTSPLUS_CATALOG_DIR,
) -> dict[str, Any]:
    return read_json(
        f"report_{report_id}_metric_inventory.json",
        catalog_dir=catalog_dir,
    )


def _metric_entry(
    mapping: dict[str, Any],
    execution: dict[str, Any] | None,
    catalog_dir: Path,
) -> dict[str, Any]:
    execution = execution or {}
    rows = _raw_rows(execution.get("raw_artifact"), catalog_dir)
    columns = _columns(rows, mapping)
    category = _classify(mapping, columns)
    return {
        "dataset_id": mapping.get("dataset_id"),
        "dataset_guid": mapping.get("dataset_guid"),
        "dataset_name": mapping.get("dataset_name"),
        "category": category,
        "widget_sections": _widget_sections(mapping),
        "returned_columns": columns,
        "record_count": execution.get("record_count", len(rows)),
        "sample_values": _sample_values(rows, columns),
        "time_range": _time_range(rows, columns),
        "healthcheck_usefulness": _usefulness(category, mapping, rows),
        "operational_question": _operational_question(category, mapping.get("dataset_name")),
        "execution_status": execution.get("status"),
        "http_status": execution.get("http_status"),
        "raw_artifact": execution.get("raw_artifact"),
    }


def _raw_rows(raw_artifact: str | None, catalog_dir: Path) -> list[dict[str, Any]]:
    if not raw_artifact:
        return []
    path = Path(raw_artifact)
    if not path.is_absolute() and not path.exists():
        path = catalog_dir / path.name
    if not path.exists():
        return []
    payload = read_json(path.name, catalog_dir=path.parent)
    return _rows(payload.get("data"))


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


def _columns(rows: list[dict[str, Any]], mapping: dict[str, Any]) -> list[str]:
    if rows:
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(str(key))
        return columns
    available = mapping.get("available_fields") or []
    selected = mapping.get("selected_fields") or []
    columns = []
    for value in [*available, *selected]:
        if value not in columns:
            columns.append(str(value))
    return columns


def _sample_values(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, list[Any]]:
    samples: dict[str, list[Any]] = {}
    for column in columns:
        values = []
        for row in rows:
            value = row.get(column)
            if value in (None, "") or value in values:
                continue
            values.append(value)
            if len(values) >= 3:
                break
        samples[column] = values
    return samples


def _time_range(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any] | None:
    time_columns = [column for column in columns if _looks_like_time_column(column)]
    for column in time_columns:
        values = [_coerce_time(row.get(column)) for row in rows]
        normalized = [value for value in values if value]
        if normalized:
            return {
                "column": column,
                "start": min(normalized),
                "end": max(normalized),
                "points": len(set(normalized)),
            }
    return None


def _coerce_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value > 100000000:
        return datetime.fromtimestamp(value, tz=UTC).date().isoformat()
    text = str(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def _looks_like_time_column(column: str) -> bool:
    normalized = column.lower()
    if any(term in normalized for term in ("growth", "change", "rate")):
        return False
    return normalized in {"month", "monthstart", "latest month", "firstdate"} or any(
        marker in normalized for marker in (" date", " time")
    )


def _widget_sections(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []
    for usage in mapping.get("used_by") or []:
        if not isinstance(usage, dict):
            continue
        sections.append(
            {
                "title": usage.get("title"),
                "type": usage.get("type"),
                "path": usage.get("path"),
            }
        )
    return sections


def _classify(mapping: dict[str, Any], columns: list[str]) -> str:
    name = str(mapping.get("dataset_name") or "").lower()
    if _is_low_value_selector(name, columns):
        return "low-value / unclear"
    text = " ".join(
        str(value)
        for value in [
            mapping.get("dataset_name"),
            *columns,
            *(mapping.get("selected_fields") or []),
            *(mapping.get("available_fields") or []),
        ]
        if value is not None
    ).lower()
    if any(term in text for term in ("dedupe", "dedup", "saving", "compression")):
        return "deduplication / compression"
    if "clientgrowth" in text:
        return "client growth"
    if "client growth" in text or (
        "client" in text and any(term in text for term in ("added", "removed", "total"))
    ):
        return "client growth"
    if any(term in text for term in ("capacity", "license", "purchased capacity")):
        return "capacity / growth"
    if any(term in text for term in ("library", "consumed space", "data written")):
        return "storage usage"
    if any(term in text for term in ("job", "backup", "restore")):
        return "job trend"
    if any(term in text for term in ("sla", "success")):
        return "SLA / success trend"
    if any(term in text for term in ("growth", "sizemb", "size", "monthly")):
        return "capacity / growth"
    if any(term in text for term in ("count", "added", "removed", "total")):
        return "activity volume"
    return "low-value / unclear"


def _is_low_value_selector(name: str, columns: list[str]) -> bool:
    if "input" in name:
        return True
    normalized_columns = {
        column.lower()
        for column in columns
        if column.lower() not in {"sys_rowid", "data source"}
    }
    selector_columns = {"entityname", "entity name", "library name"}
    if normalized_columns and normalized_columns.issubset(selector_columns):
        return True
    return name.endswith(" name")


def _usefulness(category: str, mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    name = str(mapping.get("dataset_name") or "").lower()
    if category == "low-value / unclear":
        return "low"
    if "input" in name or name.endswith(" name"):
        return "low"
    if rows:
        return "high"
    return "potential"


def _operational_question(category: str, dataset_name: Any) -> str:
    name = str(dataset_name or "This dataset")
    if category == "capacity / growth":
        return f"How is {name} capacity or protected data size changing over time?"
    if category == "client growth":
        return f"How is the client population changing over time according to {name}?"
    if category == "storage usage":
        return f"How is storage consumption or data written changing for {name}?"
    if category == "deduplication / compression":
        return f"What deduplication or compression savings trend is visible in {name}?"
    if category == "job trend":
        return f"What job volume or job outcome trend is represented by {name}?"
    if category == "SLA / success trend":
        return f"What SLA or success-rate trend is represented by {name}?"
    if category == "activity volume":
        return f"What activity volume or count trend is represented by {name}?"
    return f"What operational signal, if any, does {name} provide?"
