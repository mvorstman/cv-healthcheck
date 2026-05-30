from __future__ import annotations

from flask import jsonify

from cvhealthcheck.web.active_project import (
    ActiveProjectMissingError,
    get_active_customer,
)

from .shared import (
    AuthError,
    LicenseSummaryService,
    SecurityAssessmentService,
    bp,
    get_current_username,
    is_authenticated,
    is_authenticated_for,
    login_to_commvault,
    request,
    set_current_token,
)
from cvhealthcheck.quickhc.description_service import save_description_override
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID


@bp.route("/api/login", methods=["POST"])
def api_login():
    """Inline login — accepts JSON credentials, returns JSON result.

    Customer-aware under ADR 0003 phase 3: authenticates against the
    active customer's CommCell and binds the resulting token to that
    customer's id.
    """
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    try:
        customer = get_active_customer()
    except ActiveProjectMissingError as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    base_url = customer.get("commcell_hostname")
    if not base_url:
        customer_name = customer.get("customer_name") or customer["customer_id"]
        return jsonify({
            "success": False,
            "error": (
                f"Customer '{customer_name}' has no CommCell URL configured. "
                "Edit the customer and set commcell_hostname before signing in."
            ),
        }), 400
    try:
        token = login_to_commvault(base_url, username, password)
    except AuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 401
    except Exception as exc:
        return jsonify({"success": False, "error": f"Login failed: {exc}"}), 500
    set_current_token(token, customer_id=customer["customer_id"], username=username)
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
    # Collection is customer-bound: a token issued for one customer does not
    # authorise collecting against the active customer's CommCell. The connect
    # badge cares only about `authenticated`, but the Collect control needs to
    # know whether the existing token is bound to the *active* customer so it
    # can open the connect modal in-place instead of letting /collect bounce to
    # the standalone /login page. Read-only; no token is issued or cleared here.
    authenticated_for_active = False
    if authenticated:
        try:
            customer = get_active_customer()
        except ActiveProjectMissingError:
            customer = None
        if customer is not None:
            authenticated_for_active = is_authenticated_for(customer["customer_id"])
    return jsonify({
        "authenticated": authenticated,
        "authenticated_for_active": authenticated_for_active,
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
