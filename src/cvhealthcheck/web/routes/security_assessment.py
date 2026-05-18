from __future__ import annotations

from typing import Any

from .shared import (
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    _reportsplus_client,
    _security_assessment_registry_filters,
    bp,
    clear_current_token,
    export_security_assessment_registry,
    extract_security_assessment,
    flash,
    get_flashed_messages,
    import_security_assessment_upload,
    is_authenticated,
    load_security_assessment_artifact,
    logger,
    login_required,
    make_response,
    redirect,
    render_template,
    request,
    security_assessment_status,
    to_pretty_json,
    url_for,
)


@bp.route("/security-assessment")
def reportsplus_security_assessment():
    message = None
    from . import main as main_routes

    if main_routes.is_authenticated() and request.args.get("refresh") == "1":
        result = main_routes.extract_security_assessment(
            client=_reportsplus_client(),
            execute=request.args.get("execute", "1") != "0",
        )
        report_status = result["normalized"].get("source", {}).get("http_status")
        if report_status == 401:
            clear_current_token()
            return redirect(url_for("main.login", next=request.path, expired="1"))
        flash(
            f"REST refresh completed with {result['normalized'].get('finding_count', 0)} findings.",
            "success",
        )
        logger.info(
            "Selected Security Assessment source=rest-refresh artifact_path=%s source_type=%s finding_count=%s",
            result.get("artifact"),
            result["normalized"].get("source_type"),
            result["normalized"].get("finding_count"),
        )
        return redirect(url_for("main.reportsplus_security_assessment"))

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
    selected_source = normalized.get("source_type") if normalized else None
    logger.info(
        "Rendering Security Assessment page selected_source=%s artifact_path=%s imported_at=%s source_type=%s finding_count=%s first_finding=%s",
        selected_source,
        status["path"],
        normalized.get("imported_at") if normalized else None,
        normalized.get("source_type") if normalized else None,
        normalized.get("finding_count") if normalized else None,
        _finding_preview(normalized.get("findings", [])) if normalized else "none",
    )
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


def _finding_preview(findings: Any) -> str:
    if not isinstance(findings, list) or not findings:
        return "none"
    first = findings[0]
    if not isinstance(first, dict):
        return str(first)[:160]
    section = str(first.get("section") or "").strip()
    parameter = str(first.get("parameter") or "").strip()
    status = str(first.get("status") or "").strip()
    return f"{section} | {parameter} | {status}"[:160]
