from __future__ import annotations

from flask import Blueprint, render_template, request

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.config import load_settings
from cvhealthcheck.output.json_report import to_pretty_json
from cvhealthcheck.reportsplus.catalog import catalog_status, read_json, write_catalog
from cvhealthcheck.reportsplus.client import ReportsPlusClient
from cvhealthcheck.reportsplus.inventory import (
    LOGIN_TOKEN_REQUIRED_MESSAGE,
    extract_records,
    filter_reports,
    find_report_content_clues,
    parse_content_field,
    summarize_datasets,
    summarize_reports,
)
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


@bp.route("/reportsplus/reports")
def reportsplus_reports():
    client = ReportsPlusClient()
    result = client.list_reports()
    records = extract_records(result.data, preferred_keys=("reports", "data"))
    if result.ok:
        write_catalog("reports", client.reports_path, records)

    filtered_records = filter_reports(
        records,
        name=request.args.get("name") or None,
        metrics_only=request.args.get("metrics_only") == "on",
        deployed=_bool_filter("deployed"),
        viewable=_bool_filter("viewable"),
    )
    summaries = summarize_reports(filtered_records)
    return render_template(
        "reports.html",
        result=result,
        diagnostics=_diagnostics(result, records),
        catalog_status=catalog_status("reports.json"),
        message=_inventory_message(result),
        reports=summaries,
        filters={
            "name": request.args.get("name", ""),
            "metrics_only": request.args.get("metrics_only") == "on",
            "deployed": request.args.get("deployed", ""),
            "viewable": request.args.get("viewable", ""),
        },
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/reports/<path:report_id_or_guid>")
def reportsplus_report_detail(report_id_or_guid: str):
    result = ReportsPlusClient().get_report(report_id_or_guid)
    content = parse_content_field(result.data)
    clues = find_report_content_clues(content)
    return render_template(
        "report_detail.html",
        report_id_or_guid=report_id_or_guid,
        result=result,
        diagnostics=_diagnostics(result, extract_records(result.data)),
        content=content,
        clues=clues,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
        formatted_content=to_pretty_json(content) if content is not None else "",
    )


@bp.route("/reportsplus/datasets")
def reportsplus_datasets():
    client = ReportsPlusClient()
    result = client.list_datasets()
    records = extract_records(result.data, preferred_keys=("dataSet", "datasets", "data"))
    if result.ok:
        write_catalog("datasets", client.datasets_path, records)
    summaries = summarize_datasets(records)
    return render_template(
        "datasets.html",
        result=result,
        diagnostics=_diagnostics(result, records),
        catalog_status=catalog_status("datasets.json"),
        message=_inventory_message(result),
        datasets=summaries,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/health-candidates")
def reportsplus_health_candidates():
    status = catalog_status("health_candidate_priority.json")
    candidates = []
    message = None
    if status.get("exists"):
        payload = read_json("health_candidate_priority.json")
        records = payload.get("records", [])
        candidates = records if isinstance(records, list) else []
    else:
        message = (
            "Run `cv-healthcheck reportsplus catalog prioritize` "
            "to generate health_candidate_priority.json."
        )
    grouped = {
        priority: [
            candidate
            for candidate in candidates
            if candidate.get("priority") == priority
        ]
        for priority in ("HIGH", "MEDIUM", "LOW")
    }
    return render_template(
        "health_candidates.html",
        catalog_status=status,
        grouped=grouped,
        message=message,
    )


@bp.route("/reportsplus/execution-validation")
def reportsplus_execution_validation():
    status = catalog_status("execution_validation.json")
    records = []
    message = None
    if status.get("exists"):
        payload = read_json("execution_validation.json")
        value = payload.get("records", [])
        records = value if isinstance(value, list) else []
    else:
        message = (
            "Run `cv-healthcheck reportsplus catalog validate-candidates` "
            "to generate execution_validation.json."
        )
    grouped = {
        validation_status: [
            record for record in records if record.get("status") == validation_status
        ]
        for validation_status in ("EXECUTABLE", "NEEDS_PARAMS", "FAILS", "SKIPPED")
    }
    summary = {
        validation_status: len(items)
        for validation_status, items in grouped.items()
    }
    return render_template(
        "execution_validation.html",
        catalog_status=status,
        grouped=grouped,
        summary=summary,
        message=message,
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
