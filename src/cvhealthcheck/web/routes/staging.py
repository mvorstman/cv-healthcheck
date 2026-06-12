from __future__ import annotations

from .shared import bp, flash, redirect, render_template, url_for
from cvhealthcheck.context import ContextMismatchError, NoExplicitContextError
from cvhealthcheck.db import get_db
from cvhealthcheck.db import staging as staging_db
from cvhealthcheck.db.staging import execute_approval
from cvhealthcheck.web.active_project import require_active_context


@bp.route("/quick-hc/staging")
def quick_hc_staging():
    db = get_db()
    try:
        artifacts = staging_db.list_staged_artifacts(db)
    finally:
        db.close()

    pending = [artifact for artifact in artifacts if artifact.get("status") == "pending"]
    approved = [artifact for artifact in artifacts if artifact.get("status") == "approved"]
    rejected = [artifact for artifact in artifacts if artifact.get("status") == "rejected"]
    return render_template(
        "quick_hc_staging.html",
        pending=pending,
        approved=approved,
        rejected=rejected,
    )


@bp.route("/quick-hc/staging/<stage_id>/approve", methods=["POST"])
def quick_hc_staging_approve(stage_id: str):
    # D5: artifact approvals require the explicitly selected context;
    # proposal approvals are catalog-global and pass None through.
    ctx = None
    try:
        ctx = require_active_context()
    except NoExplicitContextError:
        pass
    db = get_db()
    try:
        result = execute_approval(
            db, stage_id, reviewed_by="web",
            customer_id=ctx[0] if ctx else None,
            project_id=ctx[1] if ctx else None,
        )
    except NoExplicitContextError:
        flash(
            "Select a customer and project before approving a staged artifact.",
            "error",
        )
        return redirect(url_for("main.quick_hc_staging"))
    except (ContextMismatchError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.quick_hc_staging"))
    finally:
        db.close()

    if result["type"] == "subject_proposal":
        flash(
            f"Subject '{result['title']}' v{result['version']} added to catalog.",
            "success",
        )
    else:
        flash(f"Approved staged artifact for {result['subject_id']}.", "success")
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
