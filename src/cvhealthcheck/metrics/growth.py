from __future__ import annotations

from typing import Any

from cvhealthcheck.reportsplus.client import ReportsPlusClient

from .common import (
    REPORT_318_ID,
    clean_string,
    execute_dataset,
    load_metric_artifact,
    normalize_int,
    normalize_month,
    write_metric_artifact,
)

CLIENT_COUNT_SOURCE = {
    "report_id": REPORT_318_ID,
    "widget_name": "Clients Count",
    "dataset_id": "2265",
    "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    "dataset_name": "Client Count",
}
CLIENT_GROWTH_SUMMARY_SOURCE = {
    "report_id": REPORT_318_ID,
    "widget_name": "Summary",
    "dataset_id": "2281",
    "dataset_guid": "8ac30a77-3de2-4968-86c1-ade4b02c85a4",
    "dataset_name": "Client Growth Summary",
}
CLIENT_GROWTH_DETAILS_SOURCE = {
    "report_id": REPORT_318_ID,
    "widget_name": "Details",
    "dataset_id": "2282",
    "dataset_guid": "0d443f8e-60e9-44ec-d389-f1afdd104b9a",
    "dataset_name": "ClientGrowthDetails",
}


def get_client_count_history(
    client: ReportsPlusClient | None = None,
    limit: int | None = 100,
    live: bool = True,
) -> dict[str, Any]:
    if not live:
        return load_metric_artifact("client_count_history")
    result, rows = execute_dataset(CLIENT_COUNT_SOURCE["dataset_guid"], client, limit=limit)
    records = [_normalize_client_count_row(row) for row in rows]
    return write_metric_artifact("client_count_history", CLIENT_COUNT_SOURCE, records, result)


def get_client_growth_summary(
    client: ReportsPlusClient | None = None,
    limit: int | None = 100,
    live: bool = True,
) -> dict[str, Any]:
    if not live:
        return load_metric_artifact("client_growth_summary")
    result, rows = execute_dataset(
        CLIENT_GROWTH_SUMMARY_SOURCE["dataset_guid"],
        client,
        limit=limit,
    )
    records = [_normalize_client_count_row(row) for row in rows]
    return write_metric_artifact(
        "client_growth_summary",
        CLIENT_GROWTH_SUMMARY_SOURCE,
        records,
        result,
    )


def get_client_growth_details(
    client: ReportsPlusClient | None = None,
    limit: int | None = 100,
    live: bool = True,
) -> dict[str, Any]:
    if not live:
        return load_metric_artifact("client_growth_details")
    result, rows = execute_dataset(
        CLIENT_GROWTH_DETAILS_SOURCE["dataset_guid"],
        client,
        limit=limit,
    )
    records = [_normalize_client_growth_detail_row(row) for row in rows]
    return write_metric_artifact(
        "client_growth_details",
        CLIENT_GROWTH_DETAILS_SOURCE,
        records,
        result,
    )


def _normalize_client_count_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "month": normalize_month(row.get("MonthStart")),
        "total_clients": normalize_int(row.get("Total")),
        "added": normalize_int(row.get("Added")),
        "removed": normalize_int(row.get("Removed")),
        "data_source": clean_string(row.get("Data Source")),
    }


def _normalize_client_growth_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "commcell_name": clean_string(row.get("CommCell Name")),
        "commserv_unique_id": normalize_int(row.get("CommservUniqueId")),
        "data_source": clean_string(row.get("Data Source")),
        "monthly_growth": normalize_int(row.get("Monthly Growth")),
        "year_totals": _year_totals(row),
        "monthly_counts": _monthly_counts(row),
    }


def _year_totals(row: dict[str, Any]) -> dict[str, int | None]:
    return {
        key: normalize_int(value)
        for key, value in row.items()
        if isinstance(key, str) and key.isdigit() and len(key) == 4
    }


def _monthly_counts(row: dict[str, Any]) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    for key, value in row.items():
        month = normalize_month(key)
        if not month or month == key:
            continue
        values[month] = normalize_int(value)
    return dict(sorted(values.items()))
