from __future__ import annotations

from .shared import (
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    _security_assessment_registry_filters,
    bp,
    export_security_assessment_registry,
    flash,
    get_flashed_messages,
    import_security_assessment_upload,
    load_security_assessment_artifact,
    login_required,
    make_response,
    redirect,
    render_template,
    request,
    security_assessment_status,
    to_pretty_json,
    url_for,
)


# ── Development hub ──

@bp.route("/development")
@login_required
def development():
    return render_template("development.html")


# ── Security Assessment (standalone / dev access) ──
#
# ADR 0004 phase 6.5: the dev-page Environment tools (lab-readiness, api-test)
# and the entire Reports Plus exploration cluster (reports / datasets /
# report-extract / health-candidates / execution-validation / raw data) were
# retired as disposable scaffolding. This Security Assessment cluster is HELD
# for its own dedicated pass — its canonical-coverage parity (workspace SA
# subject + unified upload) needs separate verification before removal.

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
