from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from hashlib import md5

from flask import jsonify

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.config import load_settings
from cvhealthcheck.db import get_db
from cvhealthcheck.db import staging as _staging_db
from cvhealthcheck.db.subjects import delete_subject, get_subject
from cvhealthcheck.extractors.dispatcher import extract_file
from cvhealthcheck.extractors.rest import RESTExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.reportsplus.report_definitions import REPORT_DEFINITIONS
from cvhealthcheck.reportsplus.session import CommvaultSession

from .shared import (
    LICENSE_SUMMARY_UPLOAD_EXTENSIONS,
    LicenseSummaryImportError,
    LicenseSummaryService,
    SecurityAssessmentImportError,
    SecurityAssessmentService,
    _current_token,
    _reportsplus_client,
    bp,
    clear_current_token,
    flash,
    get_commcell_identity,
    get_current_username,
    get_flashed_messages,
    import_license_summary_upload,
    import_security_assessment_upload,
    is_authenticated,
    login_required,
    read_json,
    redirect,
    render_template,
    request,
    to_pretty_json,
    url_for,
)
from cvhealthcheck.quickhc import QuickHcReportService
from cvhealthcheck.quickhc.report_service import (
    REPORT_SELECTION_IDS,
)
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.quickhc.source_provenance import (
    build_backup_job_summary_provenance,
    build_commcell_provenance,
)
from cvhealthcheck.reportsplus.backup_job_summary import (
    load_backup_job_summary_artifact,
)


def _read_commcell_provenance() -> tuple[str | None, str | None]:
    """Read CommCell identity from commserv.json for artifact provenance."""
    try:
        payload = read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))
        identity = payload.get("identity") if isinstance(payload, dict) else {}
        if not isinstance(identity, dict):
            identity = {}
        return identity.get("csGUID") or None, identity.get("hostName") or None
    except Exception:
        return None, None


def _quick_hc_asset_version() -> str:
    base = Path(__file__).resolve().parents[1] / "static"
    parts = []
    for name in ("quick_hc.css", "quick_hc.js"):
        path = base / name
        try:
            stat = path.stat()
            parts.append(f"{name}:{int(stat.st_mtime)}:{stat.st_size}")
        except FileNotFoundError:
            parts.append(f"{name}:missing")
    return md5("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


@bp.route("/quick-hc")
def quick_hc():
    db = get_db()
    try:
        initial_data = build_subject_initial_data(db)
    finally:
        db.close()
    flashes = [
        {"category": cat, "message": msg}
        for cat, msg in get_flashed_messages(with_categories=True)
    ]
    return render_template(
        "quick_hc.html",
        initial_data=initial_data,
        flashes=flashes,
        asset_version=_quick_hc_asset_version(),
        is_authenticated=is_authenticated(),
        current_username=get_current_username() if is_authenticated() else None,
    )


@bp.route("/quick-hc/settings")
def quick_hc_settings():
    """Placeholder Settings page.

    Reachable for anonymous users so that signed-out users can still reset
    their local preferences. The actual preference inspection and reset
    happens client-side via inline JS in the template — these preferences
    live in localStorage only (no server-side state yet).
    """
    return render_template(
        "quick_hc_settings.html",
        asset_version=_quick_hc_asset_version(),
        is_authenticated=is_authenticated(),
        current_username=get_current_username() if is_authenticated() else None,
    )


@bp.route("/quick-hc/<subject_id>/delete", methods=["POST"])
def quick_hc_delete_subject(subject_id: str):
    db = get_db()
    try:
        row = get_subject(db, subject_id)
        title = row["title"] if row else subject_id
        delete_subject(db, subject_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc"))
    finally:
        db.close()
    ArtifactStore().delete_artifact(subject_id)
    flash(f"'{title}' removed from catalog.", "success")
    return redirect(url_for("main.quick_hc"))


@bp.route("/quick-hc/<subject_id>/collect", methods=["POST"])
@login_required
def quick_hc_generic_collect(subject_id: str):
    settings = load_settings()
    base_url = settings.base_url
    if not base_url:
        flash("Commvault base URL is not configured.", "error")
        return redirect(url_for("main.quick_hc"))

    token = _current_token()
    report_definition = REPORT_DEFINITIONS.get(subject_id)

    db = get_db()
    try:
        subject = get_subject(db, subject_id)
        if subject is None:
            flash(f"Subject '{subject_id}' not found.", "error")
            return redirect(url_for("main.quick_hc"))
        title = subject["title"]
        version = subject["version"]
        with CommvaultSession(base_url, token, verify_ssl=settings.verify_ssl) as cv_session:
            extractor = RESTExtractor(db, cv_session)
            result = extractor.extract(subject_id, version, report_definition=report_definition)
    except Exception as exc:
        flash(f"Collection failed: {exc}", "error")
        return redirect(url_for("main.quick_hc"))
    finally:
        db.close()

    if result.errors:
        flash(f"Collection errors: {'; '.join(result.errors)}", "error")
        return redirect(url_for("main.quick_hc"))

    commcell_id, commcell_name = _read_commcell_provenance()
    artifact = result_to_artifact(
        result,
        subject_id=subject_id,
        subject_title=title,
        commcell_id=commcell_id,
        commcell_name=commcell_name,
    )
    ArtifactStore().save_artifact(artifact)

    if result.warnings:
        warn_str = "; ".join(result.warnings[:2])
        flash(f"REST collection completed for '{title}'. Warnings: {warn_str}", "success")
    else:
        flash(f"REST collection completed for '{title}'.", "success")
    return redirect(url_for("main.quick_hc"))


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
        source_provenance=build_commcell_provenance(result),
        formatted=to_pretty_json(result),
    )


@bp.route("/quick-hc/security-assessment")
def quick_hc_security_assessment():
    return redirect(url_for("main.quick_hc"))


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
    return redirect(url_for("main.quick_hc"))


@bp.route("/quick-hc/backup-job-summary")
def quick_hc_backup_job_summary():
    artifact = None
    try:
        artifact = load_backup_job_summary_artifact()
    except FileNotFoundError:
        pass
    flashes = [
        {"category": category, "message": text}
        for category, text in get_flashed_messages(with_categories=True)
    ]
    return render_template(
        "quick_hc_backup_job_summary.html",
        artifact=artifact,
        source_provenance=build_backup_job_summary_provenance(artifact),
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


@bp.route("/quick-hc/import", methods=["GET", "POST"])
def quick_hc_generic_import():
    inline = request.headers.get("X-Inline") == "1"

    if request.method == "GET":
        return render_template("quick_hc_import.html")

    upload = request.files.get("file")
    filename = (upload.filename if upload else "") or ""
    if not filename:
        if inline:
            return jsonify({"success": False, "error": "No file selected."}), 400
        flash("No file selected.", "error")
        return redirect(url_for("main.quick_hc_generic_import"))

    suffix = Path(filename).suffix or ".tmp"
    tmp_path: Path | None = None
    db = get_db()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            upload.save(tmp)
            tmp_path = Path(tmp.name)

        explicit_subject_id = request.args.get("subject_id") or None
        dispatch = extract_file(tmp_path, db, subject_id=explicit_subject_id)

        if not dispatch.recognized:
            msg = "File not recognised — no matching report type found."
            if inline:
                return jsonify({"success": False, "error": msg}), 422
            flash(msg, "warning")
        elif not dispatch.extractable:
            reason = dispatch.non_extractable_reason or "not extractable"
            msg = f"File recognised but not extractable: {reason}."
            if inline:
                return jsonify({"success": False, "error": msg}), 422
            flash(msg, "warning")
        elif dispatch.extraction_errors:
            msg = f"Extraction errors: {'; '.join(dispatch.extraction_errors)}"
            if inline:
                return jsonify({"success": False, "error": msg}), 422
            flash(msg, "error")
        else:
            artifact = dispatch.artifact
            title = dispatch.recognition_result.title  # type: ignore[union-attr]
            stage_flag = request.args.get("stage") == "1"
            if stage_flag:
                stage_id = f"stage_{uuid.uuid4().hex[:12]}"
                _staging_db.create_staged_artifact(
                    db,
                    stage_id,
                    artifact.artifact_type,
                    artifact.model_dump_json(),
                    source_file=filename,
                    source_type=dispatch.source_type,
                )
                msg = f"Imported {title} — review in staging before approving."
                if inline:
                    return jsonify({"success": True, "message": msg, "title": title})
                flash(msg, "success")
            else:
                ArtifactStore().save_artifact(artifact)
                msg = f"Imported {title} successfully."
                if inline:
                    return jsonify({"success": True, "message": msg, "title": title})
                flash(msg, "success")
    except Exception as exc:
        if inline:
            return jsonify({"success": False, "error": str(exc)}), 500
        flash(f"Import failed: {exc}", "error")
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        db.close()

    return redirect(url_for("main.quick_hc_generic_import"))
