from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cvhealthcheck.reportsplus.catalog import CATALOG_DIR, collected_at, read_json, write_json
from cvhealthcheck.reportsplus.client import ReportsPlusClient

METRICS_CATALOG_DIR = CATALOG_DIR / "metrics"
REPORT_318_ID = "318"


def execute_dataset(
    dataset_guid: str,
    client: ReportsPlusClient | None = None,
    limit: int | None = 100,
) -> tuple[Any, list[dict[str, Any]]]:
    reports_client = client or ReportsPlusClient()
    result = reports_client.get_dataset_data(dataset_guid, limit=limit)
    return result, rows_from_payload(result.data)


def rows_from_payload(data: Any) -> list[dict[str, Any]]:
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


def load_metric_artifact(name: str) -> dict[str, Any]:
    return read_json(f"{name}.json", catalog_dir=METRICS_CATALOG_DIR)


def write_metric_artifact(
    name: str,
    source: dict[str, Any],
    records: list[dict[str, Any]],
    result: Any | None = None,
) -> dict[str, Any]:
    payload = {
        "collected_at": collected_at(),
        "source": source,
        "http_status": getattr(result, "status_code", None),
        "ok": getattr(result, "ok", True),
        "record_count": len(records),
        "history_range": history_range(records),
        "records": records,
    }
    write_json(f"{name}.json", payload, catalog_dir=METRICS_CATALOG_DIR)
    return payload


def history_range(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    months = sorted(
        {
            record["month"]
            for record in records
            if isinstance(record.get("month"), str) and record.get("month")
        }
    )
    if not months:
        return None
    return {"start": months[0], "end": months[-1], "points": len(months)}


def normalize_month(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value > 100000000:
        return datetime.fromtimestamp(value, tz=UTC).strftime("%Y-%m")
    text = str(value).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError:
            pass
    if len(text) == 7 and text[4] == "-":
        return text
    return text or None


def normalize_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
