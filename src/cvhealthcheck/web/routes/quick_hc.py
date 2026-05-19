from __future__ import annotations

from pathlib import Path

from .shared import (
    LICENSE_SUMMARY_UPLOAD_EXTENSIONS,
    LicenseSummaryImportError,
    LicenseSummaryService,
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    _capacity_license_quick_hc,
    _client_growth_quick_hc,
    _current_token,
    _license_summary_quick_hc,
    _reportsplus_client,
    bp,
    catalog_status,
    clear_current_token,
    flash,
    get_commcell_identity,
    get_flashed_messages,
    import_license_summary_upload,
    import_security_assessment_upload,
    is_authenticated,
    login_required,
    read_json,
    redirect,
    render_template,
    request,
    security_assessment_quick_hc,
    to_pretty_json,
    url_for,
)
from cvhealthcheck.quickhc import QuickHcReportService
from cvhealthcheck.quickhc.report_service import REPORT_SELECTION_IDS


@bp.route("/quick-hc")
def quick_hc():
    return render_template(
        "quick_hc.html",
        commcell_status=catalog_status("commserv.json", catalog_dir=Path("data/catalog/rest")),
        security_assessment=security_assessment_quick_hc(),
        license_summary=_license_summary_quick_hc(),
        client_growth=_client_growth_quick_hc(),
        capacity_license=_capacity_license_quick_hc(),
        selected_report_sections=REPORT_SELECTION_IDS,
    )


@bp.route("/quick-hc/report", methods=["GET", "POST"])
def quick_hc_report():
    if request.method == "POST":
        selection_ids = {
            item
            for item in request.form.getlist("selection_ids")
            if isinstance(item, str) and item.strip() in REPORT_SELECTION_IDS
        }
        report = QuickHcReportService().build_report(
            selection_ids,
            default_to_all=False,
        )
    else:
        report = QuickHcReportService().build_report()
    return render_template(
        "quick_hc_report.html",
        report=report,
    )


@bp.route("/quick-hc/commcell")
def quick_hc_commcell():
    if is_authenticated():
        result = get_commcell_identity(token=_current_token())
    else:
        try:
            result = read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))
        except FileNotFoundError:
            return redirect(url_for("main.login", next=request.path))
    if result.get("http_status") == 401:
        clear_current_token()
        return redirect(url_for("main.login", next=request.path, expired="1"))
    return render_template(
        "quick_hc_commcell.html",
        result=result,
        formatted=to_pretty_json(result),
    )


@bp.route("/quick-hc/security-assessment")
def quick_hc_security_assessment():
    flashes = [
        {"category": category, "message": text}
        for category, text in get_flashed_messages(with_categories=True)
    ]
    return render_template(
        "quick_hc_security_assessment.html",
        assessment=security_assessment_quick_hc(),
        flashes=flashes,
    )


@bp.route("/quick-hc/security-assessment/import", methods=["POST"])
def quick_hc_security_assessment_import():
    upload = request.files.get("assessment_file")
    filename = (upload.filename if upload else "") or ""
    if not filename:
        flash("No file selected.", "error")
        return redirect(url_for("main.quick_hc_security_assessment"))

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
    return redirect(url_for("main.quick_hc_security_assessment"))


@bp.route("/quick-hc/security-assessment/collect", methods=["POST"])
@login_required
def quick_hc_security_assessment_collect():
    service = SecurityAssessmentService()
    try:
        result = service.collect_from_rest(client=_reportsplus_client())
    except SecurityAssessmentImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc_security_assessment"))
    except Exception as exc:
        flash(f"Security Assessment REST collection failed: {exc}", "error")
        return redirect(url_for("main.quick_hc_security_assessment"))

    source = result["normalized"].get("source", {})
    if source.get("http_status") == 401:
        clear_current_token()
        return redirect(
            url_for(
                "main.login",
                next=url_for("main.quick_hc_security_assessment"),
                expired="1",
            )
        )

    finding_count = int(result["normalized"].get("finding_count") or 0)
    flash(
        f"REST collection completed with {finding_count} findings.",
        "success",
    )
    return redirect(url_for("main.quick_hc_security_assessment"))


@bp.route("/quick-hc/license-summary")
def quick_hc_license_summary():
    artifact = None
    try:
        artifact = LicenseSummaryService().get_current()
    except FileNotFoundError:
        pass
    flashes = [
        {"category": category, "message": text}
        for category, text in get_flashed_messages(with_categories=True)
    ]
    return render_template(
        "license_summary.html",
        artifact=artifact,
        flashes=flashes,
    )


@bp.route("/quick-hc/license-summary/import", methods=["POST"])
def quick_hc_license_summary_import():
    upload = request.files.get("license_summary_file")
    filename = (upload.filename if upload else "") or ""
    if not filename:
        flash("No file selected.", "error")
        return redirect(url_for("main.quick_hc_license_summary"))

    suffix = Path(filename).suffix.lower()
    if suffix not in LICENSE_SUMMARY_UPLOAD_EXTENSIONS:
        flash("Unsupported file type. Upload a License Summary CSV or HTML export.", "error")
        return redirect(url_for("main.quick_hc_license_summary"))

    try:
        artifact = import_license_summary_upload(
            upload.stream,
            original_filename=filename,
        )
    except LicenseSummaryImportError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"License Summary import failed: {exc}", "error")
    else:
        source_type = str(artifact.get("source_type") or "unknown").upper()
        other_count = len(artifact.get("other_licenses") or [])
        agent_count = len(artifact.get("agent_feature_licenses") or [])
        flash(
            f"{source_type} import completed for {artifact.get('source_file')} with {other_count} other licenses and {agent_count} agent/feature licenses.",
            "success",
        )
    return redirect(url_for("main.quick_hc_license_summary"))


@bp.route("/quick-hc/license-summary/collect", methods=["POST"])
@login_required
def quick_hc_license_summary_collect():
    service = LicenseSummaryService()
    try:
        result = service.collect_from_rest(client=_reportsplus_client())
    except LicenseSummaryImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc_license_summary"))
    except Exception as exc:
        flash(f"License Summary REST collection failed: {exc}", "error")
        return redirect(url_for("main.quick_hc_license_summary"))

    source = result["normalized"].get("source", {})
    if source.get("http_status") == 401:
        clear_current_token()
        return redirect(url_for("main.login", next=url_for("main.quick_hc_license_summary"), expired="1"))

    other_count = len(result["normalized"].get("other_licenses") or [])
    agent_count = len(result["normalized"].get("agent_feature_licenses") or [])
    flash(
        f"REST collection completed with {other_count} other licenses and {agent_count} agent/feature licenses.",
        "success",
    )
    return redirect(url_for("main.quick_hc_license_summary"))
