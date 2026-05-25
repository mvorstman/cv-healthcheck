from __future__ import annotations

from flask import jsonify

from .shared import (
    AuthError,
    LicenseSummaryService,
    SecurityAssessmentService,
    bp,
    get_current_username,
    is_authenticated,
    load_settings,
    login_to_commvault,
    request,
    set_current_token,
)
from cvhealthcheck.quickhc.description_service import save_description_override
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID


@bp.route("/api/login", methods=["POST"])
def api_login():
    """Inline login — accepts JSON credentials, returns JSON result."""
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    settings = load_settings()
    if not settings.base_url:
        return jsonify({"success": False, "error": "Commvault base URL is not configured on this server."}), 400
    try:
        token = login_to_commvault(settings.base_url, username, password)
    except AuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 401
    except Exception as exc:
        return jsonify({"success": False, "error": f"Login failed: {exc}"}), 500
    set_current_token(token, username=username)
    return jsonify({"success": True})


@bp.route("/api/auth/status")
def api_auth_status():
    """Return whether the current session has a valid Commvault token,
    and the username when known.

    Session read only — does not round-trip to Commvault. Used by the
    Quick HC connection badge to refresh its state without reloading
    the page (window.IS_AUTHENTICATED goes stale on long-lived sessions
    after token expiry) and by the connect modal's sign-out branch to
    show "Signed in as <user>". ``username`` is None when the session
    is anonymous, and may also be None for legacy authenticated sessions
    created before SESSION_USERNAME_KEY was added.
    """
    authenticated = bool(is_authenticated())
    return jsonify({
        "authenticated": authenticated,
        "username": get_current_username() if authenticated else None,
    })


@bp.route("/api/quick-hc/status")
def api_quick_hc_status():
    """Return badge states for all subjects."""
    data = build_subject_initial_data()
    status = {}
    for cat in data.get("cats") or []:
        for subj in cat.get("subjects") or []:
            status[subj["id"]] = {
                "state": subj.get("state"),
                "subtitle": subj.get("subtitle"),
                "exists": subj.get("state") != "nodata",
            }
    return jsonify(status)


@bp.route("/api/quick-hc/subject/<subject_id>")
def api_quick_hc_subject(subject_id: str):
    """Return full subject data as JSON."""
    if subject_id not in QUICK_HC_TILE_BY_ID:
        return jsonify({"error": "Unknown subject"}), 404
    data = build_subject_initial_data()
    for cat in data.get("cats") or []:
        for subj in cat.get("subjects") or []:
            if subj["id"] == subject_id:
                return jsonify(subj)
    return jsonify({"error": "Subject not found"}), 404


@bp.route("/api/quick-hc/subject/<subject_id>/description", methods=["POST"])
def api_quick_hc_subject_description(subject_id: str):
    if subject_id not in QUICK_HC_TILE_BY_ID:
        return jsonify({"error": "Unknown subject"}), 404

    payload = request.get_json(silent=True) or {}
    description = payload.get("description")
    if not isinstance(description, str):
        return jsonify({"error": "Description must be a string"}), 400

    saved = save_description_override(subject_id, description)
    return jsonify(saved)


@bp.route("/api/security-assessment/canonical")
def api_security_assessment_canonical():
    try:
        canonical = SecurityAssessmentService().get_canonical()
    except FileNotFoundError:
        return jsonify({"error": "No canonical artifact exists yet."}), 404
    return jsonify(canonical.model_dump(mode="json"))


@bp.route("/api/license-summary/canonical")
def api_license_summary_canonical():
    try:
        canonical = LicenseSummaryService().get_canonical()
    except FileNotFoundError:
        return jsonify({"error": "No canonical artifact exists yet."}), 404
    return jsonify(canonical.model_dump(mode="json"))
