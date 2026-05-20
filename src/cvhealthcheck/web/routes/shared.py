from __future__ import annotations

from functools import wraps
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import (
    Blueprint,
    flash,
    get_flashed_messages,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.auth import (
    AuthError,
    clear_current_token,
    get_current_token,
    is_authenticated,
    login_to_commvault,
    set_current_token,
)
from cvhealthcheck.config import load_settings
from cvhealthcheck.labreadiness.evaluator import assess_lab_readiness
from cvhealthcheck.license_summary import (
    LicenseSummaryImportError,
    LicenseSummaryService,
    import_license_summary_upload,
)
from cvhealthcheck.metrics import (
    get_client_count_history,
    get_client_growth_details,
)
from cvhealthcheck.output.json_report import to_pretty_json
from cvhealthcheck.quickhc import get_commcell_identity
from cvhealthcheck.reportsplus.catalog import catalog_status, read_json, write_catalog
from cvhealthcheck.reportsplus.client import ReportsPlusClient
from cvhealthcheck.reportsplus.extract_report import extract_report
from cvhealthcheck.reportsplus.inventory import (
    LOGIN_TOKEN_REQUIRED_MESSAGE,
    extract_records,
    filter_reports,
    find_report_content_clues,
    parse_content_field,
    summarize_datasets,
    summarize_reports,
)
from cvhealthcheck.reportsplus.metric_inventory import build_report_metric_inventory
from cvhealthcheck.reportsplus.metadata import summarize_dataset_metadata
from cvhealthcheck.reportsplus.security_assessment import (
    extract_security_assessment,
    load_security_assessment_artifact,
    security_assessment_status,
)
from cvhealthcheck.security_assessment.service import (
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    export_security_assessment_registry,
    import_security_assessment_upload,
)

bp = Blueprint("main", __name__)
F = TypeVar("F", bound=Callable)
logger = logging.getLogger(__name__)
LICENSE_SUMMARY_UPLOAD_EXTENSIONS = {".csv", ".htm", ".html"}


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def _current_token() -> str:
    return get_current_token() or ""


def _api_client() -> CommvaultApiClient:
    return CommvaultApiClient(token=_current_token())


def _reportsplus_client() -> ReportsPlusClient:
    return ReportsPlusClient(token=_current_token())


def _auth_failure_redirect(result):
    if getattr(result, "status_code", None) == 401:
        clear_current_token()
        return redirect(url_for("main.login", next=request.path, expired="1"))
    return None


def _safe_next(default: str | None = None) -> str:
    value = request.values.get("next", "")
    if value.startswith("/") and not value.startswith("//"):
        return value
    return default or url_for("main.lab_readiness")


def _parameters_from_form() -> dict[str, str]:
    raw = request.args.get("parameters", "").strip()
    parameters: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parameters[key.strip()] = value.strip()
    return parameters


def _bool_filter(name: str) -> bool | None:
    value = request.args.get(name, "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _diagnostics(result, records) -> dict[str, object]:
    return {
        "endpoint": result.url,
        "status": result.status_code or "request failed",
        "elapsed_ms": (
            round(result.elapsed_seconds * 1000, 1)
            if result.elapsed_seconds is not None
            else None
        ),
        "record_count": len(records),
    }


def _inventory_message(result) -> str | None:
    if result.status_code == 401:
        return LOGIN_TOKEN_REQUIRED_MESSAGE
    return None


def _security_assessment_registry_filters() -> dict[str, str | None]:
    return {
        "customer_id": request.args.get("customer_id", "").strip() or None,
        "commcell_id": request.args.get("commcell_id", "").strip() or None,
        "source_type": request.args.get("source_type", "").strip() or None,
        "engagement_id": request.args.get("engagement_id", "").strip() or None,
        "report_stream_id": request.args.get("report_stream_id", "").strip() or None,
    }


def _month_records(metric: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            record
            for record in metric.get("records", [])
            if isinstance(record, dict) and record.get("month")
        ],
        key=lambda record: str(record.get("month", "")),
    )


def _number_or_none(value: Any, *, allow_negative: bool = True) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        if not allow_negative and value < 0:
            return None
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not allow_negative and number < 0:
        return None
    return number


def _client_count_chart(metric: dict[str, Any]) -> dict[str, Any] | None:
    records = _month_records(metric)
    if not records:
        return None

    return {
        "canvas_id": "client-count-chart",
        "type": "line",
        "title": "Client Count History",
        "subtitle": "Total protected clients by month.",
        "labels": [record.get("month") for record in records],
        "datasets": [
            {
                "type": "line",
                "label": "Total clients",
                "data": [
                    _number_or_none(record.get("total_clients")) or 0
                    for record in records
                ],
                "borderColor": "rgb(15, 118, 110)",
                "backgroundColor": "rgba(15, 118, 110, 0.12)",
                "borderWidth": 2,
                "pointRadius": 3,
                "tension": 0.25,
                "fill": True,
                "yAxisID": "clients",
            }
        ],
        "x_label": "Month",
        "scales": {
            "clients": {
                "beginAtZero": True,
                "position": "left",
                "title": {"display": True, "text": "Total clients"},
            }
        },
    }


def _client_growth_chart(metric: dict[str, Any]) -> dict[str, Any] | None:
    records = _month_records(metric)
    if not records:
        return None

    removed_values = [_number_or_none(record.get("removed")) or 0 for record in records]
    datasets = [
        {
            "type": "bar",
            "label": "Added",
            "data": [_number_or_none(record.get("added")) or 0 for record in records],
            "backgroundColor": "rgba(37, 99, 235, 0.35)",
            "borderColor": "rgb(37, 99, 235)",
            "borderWidth": 1,
            "order": 2,
            "yAxisID": "yActivity",
        },
        {
            "type": "line",
            "label": "Total clients",
            "data": [
                _number_or_none(record.get("total_clients")) or 0
                for record in records
            ],
            "borderColor": "rgb(15, 118, 110)",
            "backgroundColor": "rgba(15, 118, 110, 0.12)",
            "borderWidth": 2,
            "pointRadius": 3,
            "tension": 0.25,
            "fill": False,
            "order": 1,
            "yAxisID": "yTotal",
        },
    ]
    if any(value for value in removed_values):
        datasets.insert(
            1,
            {
                "type": "bar",
                "label": "Removed",
                "data": removed_values,
                "backgroundColor": "rgba(220, 38, 38, 0.25)",
                "borderColor": "rgb(220, 38, 38)",
                "borderWidth": 1,
                "order": 2,
                "yAxisID": "yActivity",
            },
        )

    return {
        "canvas_id": "client-growth-chart",
        "type": "bar",
        "title": "Client Growth History",
        "subtitle": "Total clients over time with monthly additions and removals.",
        "labels": [record.get("month") for record in records],
        "datasets": datasets,
        "x_label": "Month",
        "scales": {
            "yTotal": {
                "beginAtZero": True,
                "position": "left",
                "title": {"display": True, "text": "Total clients"},
            },
            "yActivity": {
                "beginAtZero": True,
                "position": "right",
                "grid": {"drawOnChartArea": False},
                "title": {"display": True, "text": "Added / removed clients"},
            },
        },
    }


def _capacity_license_chart(metric: dict[str, Any]) -> dict[str, Any] | None:
    records = _month_records(metric)
    if not records:
        return None

    return {
        "canvas_id": "capacity-license-chart",
        "type": "line",
        "title": "Capacity License Usage History",
        "subtitle": "Used and purchased capacity by month.",
        "labels": [record.get("month") for record in records],
        "datasets": [
            {
                "type": "line",
                "label": "Used capacity",
                "data": [
                    _number_or_none(record.get("used_capacity"), allow_negative=False)
                    for record in records
                ],
                "borderColor": "rgb(37, 99, 235)",
                "backgroundColor": "rgba(37, 99, 235, 0.12)",
                "borderWidth": 2,
                "pointRadius": 3,
                "tension": 0.25,
                "spanGaps": True,
                "yAxisID": "capacity",
            },
            {
                "type": "line",
                "label": "Purchased capacity",
                "data": [
                    _number_or_none(
                        record.get("purchased_capacity"),
                        allow_negative=False,
                    )
                    for record in records
                ],
                "borderColor": "rgb(15, 118, 110)",
                "backgroundColor": "rgba(15, 118, 110, 0.12)",
                "borderWidth": 2,
                "borderDash": [6, 4],
                "pointRadius": 3,
                "tension": 0.25,
                "spanGaps": True,
                "yAxisID": "capacity",
            },
        ],
        "x_label": "Month",
        "scales": {
            "capacity": {
                "beginAtZero": True,
                "position": "left",
                "title": {"display": True, "text": "Capacity"},
            }
        },
    }


def _client_growth_detail_chart(metric: dict[str, Any]) -> dict[str, Any] | None:
    records = [
        record
        for record in metric.get("records", [])
        if isinstance(record, dict) and isinstance(record.get("monthly_counts"), dict)
    ]
    months = sorted(
        {
            month
            for record in records
            for month in record.get("monthly_counts", {})
            if month
        }
    )
    if not records or not months:
        return None

    colors = [
        "rgb(37, 99, 235)",
        "rgb(15, 118, 110)",
        "rgb(124, 58, 237)",
        "rgb(217, 119, 6)",
    ]
    datasets = []
    for index, record in enumerate(records):
        counts = record.get("monthly_counts", {})
        color = colors[index % len(colors)]
        label = record.get("commcell_name") or record.get("data_source") or "CommCell"
        datasets.append(
            {
                "type": "line",
                "label": label,
                "data": [_number_or_none(counts.get(month)) or 0 for month in months],
                "borderColor": color,
                "backgroundColor": "rgba(37, 99, 235, 0.08)",
                "borderWidth": 2,
                "pointRadius": 3,
                "tension": 0.25,
                "yAxisID": "clients",
            }
        )

    return {
        "canvas_id": "client-growth-detail-chart",
        "type": "line",
        "title": "Client Growth Detail",
        "subtitle": "Client count history by CommCell.",
        "labels": months,
        "datasets": datasets,
        "x_label": "Month",
        "scales": {
            "clients": {
                "beginAtZero": True,
                "position": "left",
                "title": {"display": True, "text": "Clients"},
            }
        },
    }
