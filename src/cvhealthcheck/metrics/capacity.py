from __future__ import annotations

from typing import Any

from cvhealthcheck.reportsplus.client import ReportsPlusClient

from .common import (
    REPORT_318_ID,
    clean_string,
    execute_dataset,
    load_metric_artifact,
    normalize_float,
    normalize_month,
    write_metric_artifact,
)

CAPACITY_LICENSE_USAGE_SOURCE = {
    "report_id": REPORT_318_ID,
    "widget_name": "Capacity License Usage",
    "dataset_id": "2266",
    "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
    "dataset_name": "Capacity License Usage",
}


def get_capacity_license_usage(
    client: ReportsPlusClient | None = None,
    limit: int | None = 100,
    live: bool = True,
) -> dict[str, Any]:
    if not live:
        return load_metric_artifact("capacity_license_usage")
    result, rows = execute_dataset(
        CAPACITY_LICENSE_USAGE_SOURCE["dataset_guid"],
        client,
        limit=limit,
    )
    records = [_normalize_capacity_license_row(row) for row in rows]
    return write_metric_artifact(
        "capacity_license_usage",
        CAPACITY_LICENSE_USAGE_SOURCE,
        records,
        result,
    )


def _normalize_capacity_license_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "month": normalize_month(row.get("Month")),
        "entity_name": clean_string(row.get("Entity Name")),
        "used_capacity": normalize_float(row.get("Used Capacity")),
        "purchased_capacity": normalize_float(row.get("Purchased Capacity")),
        "data_source": clean_string(row.get("Data Source")),
    }
