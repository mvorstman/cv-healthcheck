from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from hashlib import md5

from flask import jsonify

from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.config import load_settings
from cvhealthcheck.db import get_db
from cvhealthcheck.context import ContextMismatchError, NoExplicitContextError
from cvhealthcheck.identity import effective_connection_url, normalize_commcell_id
from cvhealthcheck.web.active_project import (
    ActiveProjectMissingError,
    get_active_customer,
    make_active_project_store,
    require_active_context,
)
from cvhealthcheck.db import staging as _staging_db
from cvhealthcheck.db.subjects import (
    delete_subject,
    get_subject,
    get_subject_sources,
    list_family_versions,
    resolve_active_version,
    set_pinned_subject_id,
    subject_family,
)
from cvhealthcheck.extractors.command_center import (
    COMMAND_CENTER_SOURCE_TYPE,
    CommandCenterExtractor,
)
from cvhealthcheck.extractors.dispatcher import extract_file
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.reportsplus_dataset import (
    REPORTSPLUS_DATASET_SOURCE_TYPE,
    ReportsPlusDatasetExtractor,
)
from cvhealthcheck.extractors.rest import RESTExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.reportsplus.session import CommvaultSession

from .shared import (
    LicenseSummaryImportError,
    LicenseSummaryService,
    _current_token,
    _reportsplus_client,
    bp,
    clear_current_token,
    flash,
    get_commcell_identity,
    get_current_username,
    get_flashed_messages,
    is_authenticated,
    is_authenticated_for,
    login_required,
    redirect,
    render_template,
    request,
    to_pretty_json,
    url_for,
)
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.quickhc.source_provenance import (
    build_backup_job_summary_provenance,
    build_commcell_provenance,
)
from cvhealthcheck.reportsplus.backup_job_summary import (
    load_backup_job_summary_artifact,
)
from cvhealthcheck.web.routes.upload_dispatch import (
    UploadHandler,
    get_handler as _get_upload_handler,
)


def _workspace_redirect(subject_id: str | None = None):
    """Redirect to the Quick HC workspace.

    When subject_id is provided, append #subject=<subject_id> so the JS
    init can re-open that subject after the full-page reload. Pairs
    with _readSubjectFromHash in quick_hc.js. The subject_id is the
    underscored form used in the database and in the workspace's
    subject keys (not the hyphenated route form).
    """
    url = url_for("main.quick_hc")
    if subject_id:
        url = f"{url}#subject={subject_id}"
    return redirect(url)


_CONTEXT_REQUIRED_MSG = (
    "Select a customer and project before collecting/importing/deleting."
)


def _context_required_response(subject_id: str | None = None, *, inline: bool = False):
    """The web layer's single translation of NoExplicitContextError (D5).

    The data layer refuses unconditionally; this is the one place UI
    judgment is applied: a clean flash+redirect (or JSON 409 for X-Inline
    callers) telling the operator to select a customer/project first."""
    if inline:
        return jsonify({"success": False, "error": _CONTEXT_REQUIRED_MSG}), 409
    flash(_CONTEXT_REQUIRED_MSG, "error")
    return _workspace_redirect(subject_id)


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
        # Best-effort active customer for the source-tile version dropdown.
        try:
            customer_id = get_active_customer(db).get("customer_id")
        except Exception:
            customer_id = None
        initial_data = build_subject_initial_data(db, customer_id=customer_id)
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


@bp.route("/quick-hc/proposals/<stage_id>/approve", methods=["POST"])
def quick_hc_proposal_approve(stage_id: str):
    """Approve a pending subject proposal from the consolidated /quick-hc page.

    Routes through the shared execute_approval (MCP review loop + the
    /quick-hc/staging page) so the proposal is promoted into the subjects
    catalog, then full-page redirects to /quick-hc — both zones re-render
    from fresh server state (ADR 0009 Phase 1; no DOM surgery).

    D5: artifact-type approvals require the explicitly selected context;
    proposal approvals are catalog-global and pass context=None through."""
    ctx = None
    try:
        ctx = require_active_context()
    except NoExplicitContextError:
        pass  # fine for proposals; execute_approval refuses artifact rows
    db = get_db()
    try:
        result = _staging_db.execute_approval(
            db, stage_id, reviewed_by="web",
            customer_id=ctx[0] if ctx else None,
            project_id=ctx[1] if ctx else None,
        )
    except NoExplicitContextError:
        return _context_required_response()
    except ContextMismatchError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc"))
    except ValueError as exc:
        # incl. UnknownContextError (a ValueError): unknown customer/project.
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc"))
    finally:
        db.close()
    if result.get("type") == "subject_proposal":
        flash(f"Subject '{result['title']}' v{result['version']} added to catalog.", "success")
    else:
        flash(f"Approved staged artifact for {result.get('subject_id')}.", "success")
    return redirect(url_for("main.quick_hc"))


@bp.route("/quick-hc/proposals/<stage_id>/reject", methods=["POST"])
def quick_hc_proposal_reject(stage_id: str):
    """Reject a pending subject proposal from the consolidated /quick-hc page.

    Uses the UNCHANGED reject_staged_artifact, then redirects to /quick-hc."""
    db = get_db()
    try:
        updated = _staging_db.reject_staged_artifact(db, stage_id, reviewed_by="web")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc"))
    finally:
        db.close()
    if updated is None:
        flash("Proposal not found.", "error")
    else:
        flash(f"Rejected proposal for {updated['subject_id']}.", "success")
    return redirect(url_for("main.quick_hc"))


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
    # D5 gate: deletes the scoped artifact too — explicit context only.
    try:
        ctx_customer_id, ctx_project_id = require_active_context()
    except NoExplicitContextError:
        return _context_required_response(subject_id)
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
    ArtifactStore(ctx_customer_id, ctx_project_id).delete_artifact(subject_id)
    flash(f"'{title}' removed from catalog.", "success")
    return redirect(url_for("main.quick_hc"))


def _has_command_center_source(db, subject_id: str, version: int) -> bool:
    """True iff the subject declares a ``rest_command_center_api`` source — the
    discriminator that routes its /collect to the single-object extractor (ADR
    0007 ph2). Defensive: any error -> False (falls back to the Reports-Plus path)."""
    try:
        return any(
            s.get("source_type") == COMMAND_CENTER_SOURCE_TYPE
            for s in get_subject_sources(db, subject_id, version)
        )
    except Exception:
        return False


def _has_reportsplus_dataset_source(db, subject_id: str, version: int) -> bool:
    """True iff the subject declares a ``reportsplus_dataset`` source — routes
    its /collect to the directly-addressed dataset extractor (ADR 0014).
    Defensive: any error -> False (falls back to the report-walk REST path)."""
    try:
        return any(
            s.get("source_type") == REPORTSPLUS_DATASET_SOURCE_TYPE
            for s in get_subject_sources(db, subject_id, version)
        )
    except Exception:
        return False


@bp.route("/quick-hc/<subject_id>/collect", methods=["POST"])
def quick_hc_generic_collect(subject_id: str):
    """Collect a subject's REST data using the active customer's CommCell.

    Under ADR 0003 phase 3 the auth flow is customer-bound: the CommCell
    URL comes from the active customer's row, and the session token must
    be bound to that same customer. A token bound to a different customer
    is cleared before redirecting to /login. Artifact provenance comes
    from the customer row, not from the global commserv.json.
    """
    settings = load_settings()
    # D5 gate: a collect WRITES customer data — explicit context only, never
    # the silent Default fallback.
    try:
        ctx_customer_id, ctx_project_id = require_active_context()
    except NoExplicitContextError:
        return _context_required_response(subject_id)
    try:
        customer = get_active_customer()
    except ActiveProjectMissingError as exc:
        flash(str(exc), "error")
        return _workspace_redirect(subject_id)

    customer_id = customer["customer_id"]
    # Fix 3: connection_url with READ-ONLY-LEGACY commcell_hostname fallback.
    base_url = effective_connection_url(customer)
    if not base_url:
        customer_name = customer.get("customer_name") or customer_id
        flash(
            f"Customer '{customer_name}' has no connection URL configured. "
            "Edit the customer to set its Connection URL before collecting.",
            "error",
        )
        return _workspace_redirect(subject_id)

    # Customer-bound auth check. A bare is_authenticated() token bound to a
    # different customer (or unbound) is not good enough — clear it and
    # redirect to the customer-aware /login.
    if not is_authenticated_for(customer_id):
        if is_authenticated():
            clear_current_token()
        # ADR 0007 ph3 follow-on (BUG 3): the result.errors path flashes (below),
        # but this auth-gate redirect used to be silent — an auth-failed collect
        # then looked identical to a stale success (the stored artifact + its old
        # timestamp just stayed). Flash so the failure is visible, not silent.
        customer_label = customer.get("customer_name") or customer_id
        flash(
            f"Collection failed: sign in to Commvault for customer '{customer_label}' before collecting.",
            "error",
        )
        return redirect(url_for("main.login", next=request.path))

    token = _current_token()

    db = get_db()
    try:
        # ADR 0004: collection uses the template version pinned for this
        # customer+family (or the latest version if unpinned). Today every
        # family has one version, so this resolves to subject_id unchanged.
        active_subject_id = resolve_active_version(db, customer_id, subject_id)
        subject = get_subject(db, active_subject_id)
        if subject is None:
            flash(f"Subject '{active_subject_id}' not found.", "error")
            # Subject doesn't exist — don't preserve the fragment, the
            # JS would fall back to the default anyway.
            return _workspace_redirect()
        title = subject["title"]
        version = subject["version"]
        project_id = ctx_project_id
        # ADR 0007 ph2 / ADR 0014 — pluggable extractor selection by the subject's
        # collect source type. Command Center API -> CommandCenterExtractor;
        # directly-addressed RP dataset -> ReportsPlusDatasetExtractor; default
        # Reports-Plus report walk -> RESTExtractor. The auth checks above and the
        # result_to_artifact -> save_artifact tail below are identical for all.
        if _has_command_center_source(db, active_subject_id, version):
            extractor = CommandCenterExtractor(
                db, token=token, customer_id=customer_id, project_id=project_id
            )
            result = extractor.extract(active_subject_id, version)
        elif _has_reportsplus_dataset_source(db, active_subject_id, version):
            with CommvaultSession(base_url, token, verify_ssl=settings.verify_ssl) as cv_session:
                extractor = ReportsPlusDatasetExtractor(db, cv_session, customer_id, project_id)
                result = extractor.extract(active_subject_id, version)
        else:
            with CommvaultSession(base_url, token, verify_ssl=settings.verify_ssl) as cv_session:
                extractor = RESTExtractor(db, cv_session, customer_id, project_id)
                result = extractor.extract(active_subject_id, version)
    except Exception as exc:
        flash(f"Collection failed: {exc}", "error")
        return _workspace_redirect(subject_id)
    finally:
        db.close()

    if result.errors:
        flash(f"Collection errors: {'; '.join(result.errors)}", "error")
        return _workspace_redirect(subject_id)

    # Fix 3 conflation fix: stamp the CommCell IDENTITY, not the customer
    # label. commcell_name <- commserve_name (None when unset — NEVER
    # customer_name, which re-creates the conflation we are killing).
    # commcell_id <- the normalized CCID, or None if the stored value is
    # not yet a clean id (flagged-for-manual-fix data must not crash collect).
    try:
        stamped_ccid = normalize_commcell_id(customer.get("commcell_id"))
    except ValueError:
        stamped_ccid = None
    artifact = result_to_artifact(
        result,
        subject_id=active_subject_id,
        subject_title=title,
        commcell_id=stamped_ccid,
        commcell_name=customer.get("commserve_name"),
    )
    ArtifactStore(ctx_customer_id, ctx_project_id).save_artifact(artifact)

    if result.warnings:
        warn_str = "; ".join(result.warnings[:2])
        flash(f"REST collection completed for '{title}'. Warnings: {warn_str}", "success")
    else:
        flash(f"REST collection completed for '{title}'.", "success")
    return _workspace_redirect(subject_id)


@bp.route("/quick-hc/<subject_id>/pin-version", methods=["POST"])
def quick_hc_pin_version(subject_id: str):
    """ADR 0004: pin which template version this customer's family collects next.

    Writes the source-tile version dropdown's selection into
    customer_subject_pin for the active customer. The chosen version must be a
    real member of the subject's family.
    """
    chosen = (request.form.get("version") or "").strip()
    # D5 gate: the pin is a customer-scoped write (customer_subject_pin).
    try:
        ctx_customer_id, _ = require_active_context()
    except NoExplicitContextError:
        return _context_required_response(subject_id)

    db = get_db()
    try:
        family = subject_family(subject_id)
        versions = list_family_versions(db, family)
        if chosen not in versions:
            flash(
                f"'{chosen}' is not a known version of {family!r}.",
                "error",
            )
            return _workspace_redirect(subject_id)
        set_pinned_subject_id(db, ctx_customer_id, family, chosen)
    finally:
        db.close()

    flash(f"Template version for '{family}' set to '{chosen}'.", "success")
    return _workspace_redirect(subject_id)


@bp.route("/quick-hc/<subject_id>/collect-fixture", methods=["POST"])
def quick_hc_collect_fixture(subject_id: str):
    """ADR 0004 phase 2: collect an internal/test subject from its shipped JSON
    fixture. No lab/auth/CommCell needed — the FixtureExtractor reads a file
    sandboxed to data/test_fixtures/ and produces a canonical artifact."""
    # D5 gate: the artifact write is store-scoped — explicit context only.
    try:
        ctx_customer_id, ctx_project_id = require_active_context()
    except NoExplicitContextError:
        return _context_required_response(subject_id)
    db = get_db()
    try:
        active_subject_id = resolve_active_version(db, None, subject_id)
        subject = get_subject(db, active_subject_id)
        if subject is None:
            flash(f"Subject '{active_subject_id}' not found.", "error")
            return _workspace_redirect(subject_id)
        title = subject["title"]
        version = subject["version"]
        result = FixtureExtractor(db).extract(active_subject_id, version)
    finally:
        db.close()

    if result.errors:
        flash(f"Fixture collection errors: {'; '.join(result.errors)}", "error")
        return _workspace_redirect(subject_id)

    artifact = result_to_artifact(
        result, subject_id=active_subject_id, subject_title=title
    )
    try:
        ArtifactStore(ctx_customer_id, ctx_project_id).save_artifact(artifact)
    except Exception as exc:
        flash(f"Could not save artifact: {exc}", "error")
        return _workspace_redirect(subject_id)

    flash(f"Collected '{title}' from fixture.", "success")
    return _workspace_redirect(subject_id)


@bp.route("/quick-hc/commcell")
def quick_hc_commcell():
    if is_authenticated():
        result = get_commcell_identity(token=_current_token())
    else:
        # Fix 2 (c): the unauthenticated view used to serve the GLOBAL
        # commserv.json cache — cross-customer identity. Honest-empty now;
        # the live view requires authentication.
        result = {
            "collected_at": None,
            "source": None,
            "http_status": None,
            "ok": False,
            "identity": None,
            "error": "Not connected — sign in to view live CommCell identity.",
        }
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
    return _workspace_redirect("security_assessment")


# Security Assessment REST collection now routes through the generic
# /quick-hc/<subject_id>/collect handler (ADR 0003 phase 4). The previous
# bespoke route at /quick-hc/security-assessment/collect was retired
# along with SecurityAssessmentService.collect_from_rest.


@bp.route("/quick-hc/license-summary")
def quick_hc_license_summary():
    return _workspace_redirect("license_summary")


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


@bp.route("/quick-hc/license-summary/collect", methods=["POST"])
@login_required
def quick_hc_license_summary_collect():
    # D5 gate, route-level: refuse BEFORE the REST round-trip. The service's
    # _require_project_store refuses unconditionally as well (data layer);
    # this early check just avoids collecting work that can't be persisted.
    try:
        require_active_context()
    except NoExplicitContextError:
        return _context_required_response("license_summary")
    service = LicenseSummaryService()
    try:
        result = service.collect_from_rest(client=_reportsplus_client())
    except NoExplicitContextError:
        # D5: the service's scoped save refused (data layer); translate here.
        return _context_required_response("license_summary")
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


# ──────────────────────────────────────────────────────────────────────
# Unified upload route — sole upload path since session 4.
# Sessions 1-3 built and landed this route; session 4 deleted the old
# per-subject (/quick-hc/<x>/import with hyphens) and generic
# (/quick-hc/import) routes it replaced. See
# docs/refactor_unified_upload_2026-05-31.md for the full plan, and
# docs/adr/0001-source-building-fork.md for why source-building is
# intentionally NOT unified (the route is; the view shapes aren't).
# ──────────────────────────────────────────────────────────────────────


@bp.route("/quick-hc/<subject_id>/import", methods=["POST"])
def quick_hc_subject_import(subject_id: str):
    """Unified upload route — dispatches via the upload_dispatch module.

    Behavior contract (verified by tests/test_unified_upload_route.py
    and tests/test_upload_dispatch.py):
      - Unknown subject_id (not in the db) → 404.
      - subject_id in upload_dispatch.UPLOAD_HANDLERS → run that
        handler. Today: security_assessment, license_summary.
      - subject_id is a system subject with no handler entry and no
        extractable file (html/csv) bindings → 404. Today: environment,
        client_growth, capacity_license, backup_job_summary (REST/metrics-only).
      - System subject with no handler but WITH file bindings → generic
        dispatcher. Today: security_assessment (SA migration PR2 — uploads
        now route through the generic extractor like any catalog subject).
      - Anything else (AI, user, future created_by values) → generic
        dispatcher branch with X-Inline JSON-response mode, ?stage=1
        staging, and the three-way error reporting
        (recognition / extractable / extraction).
    """
    # D5 gate: every upload branch writes customer data (canonical store or
    # a staged row) — one gate here covers the handler path (LS) and the
    # generic dispatcher path alike.
    try:
        require_active_context()
    except NoExplicitContextError:
        return _context_required_response(
            subject_id, inline=request.headers.get("X-Inline") == "1"
        )
    db = get_db()
    try:
        subject = get_subject(db, subject_id)
        has_file_bindings = subject is not None and any(
            src.get("source_type") in ("html", "csv") and src.get("extractable")
            for src in get_subject_sources(db, subject_id, subject.get("version", 1))
        )
    finally:
        db.close()

    if subject is None:
        return ("Unknown subject.", 404)

    handler = _get_upload_handler(subject_id)
    if handler is not None:
        return _handle_system_upload(handler)

    if (subject.get("created_by") or "ai") == "system" and not has_file_bindings:
        # System subject with no upload path — REST/metrics only (environment,
        # client_growth, capacity_license, backup_job_summary).
        return ("Subject does not support uploads.", 404)

    # AI/user subjects, and system subjects with file bindings
    # (security_assessment), go through the generic dispatcher.
    return _unified_dispatcher_upload(subject_id)


def _handle_system_upload(handler: UploadHandler):
    """Run an upload through the handler's import function and report
    the result. Behavior parameters (form field name, import function,
    error class, success-message format, redirect endpoint) all come
    from the handler — no subject-specific code in this function.

    Supports X-Inline: 1 (JSON response in place of flash+redirect),
    mirroring the generic dispatcher branch. Without X-Inline,
    flash+redirect is preserved.
    """
    inline = request.headers.get("X-Inline") == "1"

    upload = request.files.get(handler.form_field)
    filename = (upload.filename if upload else "") or ""
    if not filename:
        if inline:
            return jsonify({"success": False, "error": "No file selected."}), 400
        flash("No file selected.", "error")
        return redirect(url_for(handler.redirect_endpoint))

    try:
        artifact = handler.import_fn(upload.stream, original_filename=filename)
    except handler.error_class as exc:
        if inline:
            return jsonify({"success": False, "error": str(exc)}), 422
        flash(str(exc), "error")
    except Exception as exc:
        if inline:
            return jsonify({"success": False, "error": f"Import failed: {exc}"}), 500
        flash(f"Import failed: {exc}", "error")
    else:
        msg = handler.success_format(artifact)
        if inline:
            return jsonify({"success": True, "message": msg})
        flash(msg, "success")
    return redirect(url_for(handler.redirect_endpoint))


def _unified_dispatcher_upload(subject_id: str):
    """Dispatcher branch of the unified route — sole AI/user upload
    path since session 4 deleted the per-subject /quick-hc/import
    generic route.

    Reads subject_id from the URL path. Supports X-Inline: 1 (JSON
    response in place of flash+redirect), ?stage=1 (route through
    staged_artifacts instead of canonical store), and three-way error
    reporting (recognition / extractable / extraction).

    Session-4 redirect-target change: previously redirected to
    main.quick_hc_generic_import (the now-deleted GET upload page).
    Redirects to main.quick_hc instead — the natural landing after a
    Quick HC upload.
    """
    inline = request.headers.get("X-Inline") == "1"

    upload = request.files.get("file")
    filename = (upload.filename if upload else "") or ""
    if not filename:
        if inline:
            return jsonify({"success": False, "error": "No file selected."}), 400
        flash("No file selected.", "error")
        return _workspace_redirect(subject_id)

    suffix = Path(filename).suffix or ".tmp"
    tmp_path: Path | None = None
    db = get_db()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            upload.save(tmp)
            tmp_path = Path(tmp.name)

        dispatch = extract_file(tmp_path, db, subject_id=subject_id)

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
                # D5 (c) + migration 0033: staged customer evidence is stamped
                # with the explicitly selected (customer, project) — the full
                # creation context (the route gate guarantees the selection
                # exists).
                _ctx_customer, _ctx_project = require_active_context()
                _staging_db.create_staged_artifact(
                    db,
                    stage_id,
                    artifact.artifact_type,
                    artifact.model_dump_json(),
                    source_file=filename,
                    source_type=dispatch.source_type,
                    customer_id=_ctx_customer,
                    project_id=_ctx_project,
                )
                msg = f"Imported {title} — review in staging before approving."
                if inline:
                    return jsonify({"success": True, "message": msg, "title": title})
                flash(msg, "success")
            else:
                ArtifactStore(*require_active_context()).save_artifact(artifact)
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

    return _workspace_redirect(subject_id)
