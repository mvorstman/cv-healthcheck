from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from flask import Blueprint, redirect, render_template, request, url_for

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
from cvhealthcheck.metrics import (
    get_capacity_license_usage,
    get_client_count_history,
    get_client_growth_details,
    get_client_growth_summary,
)
from cvhealthcheck.output.json_report import to_pretty_json
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

bp = Blueprint("main", __name__)
F = TypeVar("F", bound=Callable)


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


@bp.route("/login", methods=["GET", "POST"])
def login():
    settings = load_settings()
    error = None
    next_url = _safe_next()
    if request.args.get("expired") == "1":
        error = "Commvault token expired. Please sign in again."

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = _safe_next(next_url)
        try:
            token = login_to_commvault(settings.base_url, username, password)
        except AuthError as exc:
            error = str(exc)
        else:
            set_current_token(token)
            return redirect(next_url or url_for("main.lab_readiness"))

    return render_template(
        "login.html",
        error=error,
        base_url=settings.base_url,
        next_url=next_url,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    clear_current_token()
    return redirect(url_for("main.login"))


@bp.route("/")
@login_required
def index():
    settings = load_settings()
    client = CommvaultApiClient(settings=settings, token=_current_token())
    ping = client.ping() if settings.base_url else None
    if ping:
        auth_redirect = _auth_failure_redirect(ping)
        if auth_redirect:
            return auth_redirect
    return render_template(
        "index.html",
        base_url=settings.base_url,
        verify_ssl=settings.verify_ssl,
        token_loaded=client.token_loaded,
        api_reachable=bool(ping and ping.ok),
        api_status_code=ping.status_code if ping else None,
        api_error=ping.error if ping else None,
    )


@bp.route("/lab-readiness")
@login_required
def lab_readiness():
    result = assess_lab_readiness(write=True, token=_current_token())
    indicators = result.get("indicators", {})
    for name in ("commserve_reachable", "reports_plus_reachable"):
        indicator = indicators.get(name, {})
        if indicator.get("notes") == "HTTP 401":
            clear_current_token()
            return redirect(url_for("main.login", next=request.path, expired="1"))
    states = [
        "NOT_READY",
        "READY_FOR_DISCOVERY",
        "READY_FOR_DATA_EXECUTION",
        "READY_FOR_HEALTH_RULE_TESTING",
    ]
    return render_template(
        "lab_readiness.html",
        result=result,
        states=states,
        indicators=result.get("indicators", {}),
    )


@bp.route("/api/test")
@login_required
def api_test():
    result = _api_client().ping()
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
    running = "WebService is Running!" in result.text
    return render_template(
        "api_test.html",
        result=result,
        running=running,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/reports")
@login_required
def reportsplus_reports():
    client = _reportsplus_client()
    result = client.list_reports()
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
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
@login_required
def reportsplus_report_detail(report_id_or_guid: str):
    result = _reportsplus_client().get_report(report_id_or_guid)
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
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


@bp.route("/reportsplus/report/<report_id>")
@login_required
def reportsplus_report_extract(report_id: str):
    extraction = extract_report(
        report_id,
        client=_reportsplus_client(),
        execute=request.args.get("execute", "1") != "0",
    )
    report_status = extraction.get("summary", {}).get("report_http_status")
    if report_status == 401:
        clear_current_token()
        return redirect(url_for("main.login", next=request.path, expired="1"))
    return render_template(
        "report_extract.html",
        extraction=extraction,
        report_id=report_id,
    )


@bp.route("/reportsplus/report/<report_id>/metrics")
def reportsplus_report_metrics(report_id: str):
    inventory = build_report_metric_inventory(report_id)
    return render_template(
        "report_metrics.html",
        inventory=inventory,
        report_id=report_id,
    )


@bp.route("/reportsplus/datasets")
@login_required
def reportsplus_datasets():
    client = _reportsplus_client()
    result = client.list_datasets()
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
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


@bp.route("/metrics/client-count")
def metrics_client_count():
    metric = get_client_count_history(live=False)
    return render_template(
        "metric_detail.html",
        title="Client Count",
        metrics=[metric],
    )


@bp.route("/metrics/client-growth")
def metrics_client_growth():
    return render_template(
        "metric_detail.html",
        title="Client Growth",
        metrics=[
            get_client_growth_summary(live=False),
            get_client_growth_details(live=False),
        ],
    )


@bp.route("/metrics/capacity-license")
def metrics_capacity_license():
    metric = get_capacity_license_usage(live=False)
    return render_template(
        "metric_detail.html",
        title="Capacity License Usage",
        metrics=[metric],
    )


@bp.route("/reportsplus/dataset/<path:dataset_guid>")
@login_required
def reportsplus_dataset(dataset_guid: str):
    result = _reportsplus_client().get_dataset_metadata(dataset_guid)
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
    summary = summarize_dataset_metadata(result.data)
    return render_template(
        "dataset.html",
        dataset_guid=dataset_guid,
        result=result,
        summary=summary,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )


@bp.route("/reportsplus/data/<path:dataset_guid>")
@login_required
def reportsplus_data(dataset_guid: str):
    fields = request.args.get("fields") or None
    orderby = request.args.get("orderby") or None
    limit_raw = request.args.get("limit") or None
    limit = int(limit_raw) if limit_raw else None
    parameters = _parameters_from_form()

    result = None
    rows = []
    if request.args:
        result = _reportsplus_client().get_dataset_data(
            dataset_guid=dataset_guid,
            fields=fields,
            orderby=orderby,
            limit=limit,
            parameters=parameters,
        )
        auth_redirect = _auth_failure_redirect(result)
        if auth_redirect:
            return auth_redirect
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
