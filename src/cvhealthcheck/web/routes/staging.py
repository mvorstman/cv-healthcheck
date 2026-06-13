from __future__ import annotations

from .shared import bp, flash, redirect, render_template, url_for
from cvhealthcheck.db import get_db
from cvhealthcheck.db import staging as staging_db
from cvhealthcheck.db.staging import execute_approval


@bp.route("/quick-hc/staging")
def quick_hc_staging():
    # Proposals-only review queue (ADR-0015 slice 1): artifact staging was
    # removed, so the page shows pending/rejected subject proposals. The
    # approved column is gone — an approved proposal becomes a catalog subject.
    db = get_db()
    try:
        artifacts = staging_db.list_staged_artifacts(db)
    finally:
        db.close()

    pending = [a for a in artifacts if a.get("status") == "pending"]
    rejected = [a for a in artifacts if a.get("status") == "rejected"]
    return render_template(
        "quick_hc_staging.html",
        pending=pending,
        rejected=rejected,
    )


@bp.route("/quick-hc/staging/<stage_id>/approve", methods=["POST"])
def quick_hc_staging_approve(stage_id: str):
    # Publishes a subject proposal into the catalog (catalog-global — no
    # context needed). A non-proposal row raises ValueError (artifact
    # approval removed, ADR-0015 slice 1).
    db = get_db()
    try:
        result = execute_approval(db, stage_id, reviewed_by="web")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc_staging"))
    finally:
        db.close()

    flash(
        f"Subject '{result['title']}' v{result['version']} added to catalog.",
        "success",
    )
    return redirect(url_for("main.quick_hc_staging"))


@bp.route("/quick-hc/staging/<stage_id>/reject", methods=["POST"])
def quick_hc_staging_reject(stage_id: str):
    db = get_db()
    try:
        updated = staging_db.reject_staged_artifact(db, stage_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc_staging"))
    finally:
        db.close()

    if updated is None:
        flash("Staged artifact not found.", "error")
    else:
        flash(f"Rejected staged artifact for {updated['subject_id']}.", "success")
    return redirect(url_for("main.quick_hc_staging"))
