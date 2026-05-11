from __future__ import annotations

from flask import Blueprint, render_template, request

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.config import load_settings
from cvhealthcheck.output.json_report import to_pretty_json
from cvhealthcheck.reportsplus.client import ReportsPlusClient
from cvhealthcheck.reportsplus.metadata import summarize_dataset_metadata

bp = Blueprint("main", __name__)


def _parameters_from_form() -> dict[str, str]:
    raw = request.args.get("parameters", "").strip()
    parameters: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parameters[key.strip()] = value.strip()
    return parameters


@bp.route("/")
def index():
    settings = load_settings()
    client = CommvaultApiClient(settings=settings)
    ping = client.ping() if settings.base_url else None
    return render_template(
        "index.html",
        base_url=settings.base_url,
        verify_ssl=settings.verify_ssl,
        token_loaded=client.token_loaded,
        api_reachable=bool(ping and ping.ok),
        api_status_code=ping.status_code if ping else None,
        api_error=ping.error if ping else None,
    )


@bp.route("/api/test")
def api_test():
    result = CommvaultApiClient().ping()
    running = "WebService is Running!" in result.text
    return render_template(
        "api_test.html",
        result=result,
        running=running,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/dataset/<path:dataset_guid>")
def reportsplus_dataset(dataset_guid: str):
    result = ReportsPlusClient().get_dataset_metadata(dataset_guid)
    summary = summarize_dataset_metadata(result.data)
    return render_template(
        "dataset.html",
        dataset_guid=dataset_guid,
        result=result,
        summary=summary,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/data/<path:dataset_guid>")
def reportsplus_data(dataset_guid: str):
    fields = request.args.get("fields") or None
    orderby = request.args.get("orderby") or None
    limit_raw = request.args.get("limit") or None
    limit = int(limit_raw) if limit_raw else None
    parameters = _parameters_from_form()

    result = None
    rows = []
    if request.args:
        result = ReportsPlusClient().get_dataset_data(
            dataset_guid=dataset_guid,
            fields=fields,
            orderby=orderby,
            limit=limit,
            parameters=parameters,
        )
        if isinstance(result.data, list):
            rows = result.data
        elif isinstance(result.data, dict):
            for value in result.data.values():
                if isinstance(value, list):
                    rows = value
                    break

    columns = sorted({key for row in rows if isinstance(row, dict) for key in row})
    return render_template(
        "data.html",
        dataset_guid=dataset_guid,
        fields=fields or "",
        orderby=orderby or "",
        limit=limit_raw or "",
        parameters=request.args.get("parameters", ""),
        result=result,
        rows=rows,
        columns=columns,
        formatted=(
            to_pretty_json(result.data) if result and result.data is not None else ""
        ),
    )

