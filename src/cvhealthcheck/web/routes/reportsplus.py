from __future__ import annotations

from .shared import (
    _auth_failure_redirect,
    _bool_filter,
    _diagnostics,
    _inventory_message,
    _parameters_from_form,
    _reportsplus_client,
    bp,
    build_report_metric_inventory,
    catalog_status,
    clear_current_token,
    extract_records,
    extract_report,
    filter_reports,
    find_report_content_clues,
    login_required,
    parse_content_field,
    read_json,
    redirect,
    render_template,
    request,
    summarize_dataset_metadata,
    summarize_datasets,
    summarize_reports,
    to_pretty_json,
    url_for,
    write_catalog,
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
@login_required
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
@login_required
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
