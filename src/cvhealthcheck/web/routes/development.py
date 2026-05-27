from __future__ import annotations

from typing import Any

from cvhealthcheck.metrics import (
    get_capacity_license_usage,
    get_client_count_history,
    get_client_growth_details,
    get_client_growth_summary,
)
from cvhealthcheck.quickhc.source_provenance import build_metric_provenance

from .shared import (
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    _auth_failure_redirect,
    _bool_filter,
    _capacity_license_chart,
    _client_count_chart,
    _client_growth_chart,
    _client_growth_detail_chart,
    _diagnostics,
    _inventory_message,
    _parameters_from_form,
    _reportsplus_client,
    _security_assessment_registry_filters,
    assess_lab_readiness,
    bp,
    build_report_metric_inventory,
    catalog_status,
    clear_current_token,
    export_security_assessment_registry,
    extract_records,
    extract_report,
    filter_reports,
    find_report_content_clues,
    flash,
    get_flashed_messages,
    import_security_assessment_upload,
    is_authenticated,
    load_security_assessment_artifact,
    login_required,
    make_response,
    parse_content_field,
    read_json,
    redirect,
    render_template,
    request,
    security_assessment_status,
    summarize_dataset_metadata,
    summarize_datasets,
    summarize_reports,
    to_pretty_json,
    url_for,
    write_catalog,
    _api_client,
    _current_token,
)


# ── Development hub ──

@bp.route("/development")
@login_required
def development():
    return render_template("development.html")


@bp.route("/development/security-assessment-registry")
@login_required
def security_assessment_registry_view():
    service = SecurityAssessmentService()
    filters = _security_assessment_registry_filters()
    history = service.get_history(**filters)
    history_url = url_for(
        "main.security_assessment_history",
        **{key: value for key, value in filters.items() if value},
    )
    return render_template(
        "security_assessment_registry_history.html",
        filters=filters,
        artifacts=history["artifacts"],
        import_runs=history["import_runs"],
        report_runs=history["report_runs"],
        history_url=history_url,
    )


# ── Environment tools ──

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


# ── Metrics ──

@bp.route("/metrics/client-count")
@login_required
def metrics_client_count():
    metric = get_client_count_history(live=False)
    return render_template(
        "metric_detail.html",
        title="Client Count",
        metrics=[metric],
        chart=_client_count_chart(metric),
        source_provenance=build_metric_provenance(
            metric,
            artifact_name="client_count_history",
            report_name="Client Count",
        ),
    )


@bp.route("/metrics/client-growth")
@login_required
def metrics_client_growth():
    summary = get_client_growth_summary(live=False)
    details = get_client_growth_details(live=False)
    charts = [
        chart
        for chart in (
            _client_growth_chart(summary),
            _client_growth_detail_chart(details),
        )
        if chart
    ]
    return render_template(
        "metric_detail.html",
        title="Client Growth",
        metrics=[summary, details],
        charts=charts,
        source_provenance=build_metric_provenance(
            summary,
            artifact_name="client_growth_summary",
            report_name="Client Growth",
        ),
    )


@bp.route("/metrics/capacity-license")
@login_required
def metrics_capacity_license():
    metric = get_capacity_license_usage(live=False)
    return render_template(
        "metric_detail.html",
        title="Capacity License Usage",
        metrics=[metric],
        chart=_capacity_license_chart(metric),
        source_provenance=build_metric_provenance(
            metric,
            artifact_name="capacity_license_usage",
            report_name="Capacity License Usage",
        ),
    )


# ── Security Assessment (standalone / dev access) ──

@bp.route("/security-assessment")
def reportsplus_security_assessment():
    message = None
    # The ?refresh=1 REST collection path was retired in ADR 0003 phase 4
    # along with the bespoke extract_security_assessment helper. This dev
    # page now only renders the most-recently imported artifact (HTML or
    # CSV upload via /security-assessment/import). For live REST collection,
    # use the Quick HC workspace's Collect button on the Security Assessment
    # tile, which routes through the generic catalog-driven extractor.

    try:
        normalized = load_security_assessment_artifact()
    except FileNotFoundError:
        normalized = None
        message = (
            "No Security Assessment artifact exists yet. Log in and use "
            "`?refresh=1` to discover report 336."
        )
    flashes = [
        {"category": category, "message": text}
        for category, text in get_flashed_messages(with_categories=True)
    ]
    status = security_assessment_status()
    response = make_response(
        render_template(
            "security_assessment.html",
            normalized=normalized,
            status=status,
            flashes=flashes,
            message=message,
        )
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.route("/reportsplus/security-assessment")
def reportsplus_security_assessment_legacy():
    return redirect(url_for("main.reportsplus_security_assessment", **request.args))


@bp.route("/security-assessment/import", methods=["POST"])
def security_assessment_import():
    upload = request.files.get("assessment_file")
    filename = (upload.filename if upload else "") or ""
    if not filename:
        flash("No file selected.", "error")
        return redirect(url_for("main.reportsplus_security_assessment"))

    try:
        artifact = import_security_assessment_upload(
            upload.stream,
            original_filename=filename,
        )
    except SecurityAssessmentImportError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"Security Assessment import failed: {exc}", "error")
    else:
        source_type = str(artifact.get("source_type") or "unknown").upper()
        finding_count = int(artifact.get("finding_count") or 0)
        flash(
            f"{source_type} import completed for {artifact.get('source_file')} with {finding_count} findings.",
            "success",
        )
    return redirect(url_for("main.reportsplus_security_assessment"))


@bp.route("/security-assessment/history")
@login_required
def security_assessment_history():
    service = SecurityAssessmentService()
    artifact_id = request.args.get("artifact_id", "").strip() or None
    import_run_id = request.args.get("import_run_id", "").strip() or None
    report_run_id = request.args.get("report_run_id", "").strip() or None
    if artifact_id or import_run_id or report_run_id:
        payload = service.get_artifact(
            artifact_id=artifact_id,
            import_run_id=import_run_id,
            report_run_id=report_run_id,
        )
        response_payload = {
            "artifact": payload,
        }
    else:
        response_payload = service.get_history(**_security_assessment_registry_filters())
    response_payload["internal_only"] = True
    response = make_response(to_pretty_json(response_payload))
    response.mimetype = "application/json"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.route("/security-assessment/registry-export")
@login_required
def security_assessment_registry_export():
    response = make_response(
        to_pretty_json(
            {
                "internal_only": True,
                **export_security_assessment_registry(),
            }
        )
    )
    response.mimetype = "application/json"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


# ── Reports Plus ──

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
