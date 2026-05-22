from __future__ import annotations

from flask import jsonify

from .shared import bp
from .shared import request
from cvhealthcheck.quickhc.description_service import save_description_override
from cvhealthcheck.quickhc.subject_data_service import build_subject_initial_data
from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID


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
