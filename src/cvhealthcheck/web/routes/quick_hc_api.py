from __future__ import annotations

from flask import jsonify

from .shared import bp
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
