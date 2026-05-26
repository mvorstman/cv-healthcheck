"""Project management routes (ADR 0002 phase 4).

CRUD UI for the projects table. Each project belongs to a customer.
Project creation auto-sets the new project as active.

Routes:
    GET  /customers/<c>/projects/new                    — create form
    POST /customers/<c>/projects/new                    — create handler
    GET  /customers/<c>/projects/<p>                    — detail
    GET  /customers/<c>/projects/<p>/edit               — edit form
    POST /customers/<c>/projects/<p>/edit               — edit handler
    GET  /customers/<c>/projects/<p>/delete             — confirmation page
    POST /customers/<c>/projects/<p>/delete             — delete handler
    GET  /api/active-project                            — read active
    POST /api/active-project                            — write active
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.db import get_db
from cvhealthcheck.web.active_project import set_active_project

from .shared import bp, flash, redirect, render_template, request, url_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_project_id(project_number: str, existing_ids: set[str]) -> str:
    """Slug a project_number into a URL-stable project_id. Collisions
    disambiguated with _2, _3, ... — same pattern as customer ids.
    """
    base = re.sub(r"[^a-z0-9]+", "_", (project_number or "").lower()).strip("_")
    if not base:
        base = f"project_{uuid.uuid4().hex[:8]}"
    candidate = base
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _form_payload(form: Any) -> dict[str, Any]:
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    return {
        "project_number": (form.get("project_number") or "").strip(),
        "ticket_reference": _clean(form.get("ticket_reference")),
        "assigned_consultant": _clean(form.get("assigned_consultant")),
    }


def _fetch_customer(db: sqlite3.Connection, customer_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT customer_id, customer_name FROM customers WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _fetch_project(
    db: sqlite3.Connection, customer_id: str, project_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT project_id, customer_id, project_number, ticket_reference,"
        "       assigned_consultant, created_at, working_state_modified_at"
        " FROM projects WHERE customer_id = ? AND project_id = ?",
        (customer_id, project_id),
    ).fetchone()
    return dict(row) if row is not None else None


def _project_number_exists(
    db: sqlite3.Connection,
    customer_id: str,
    project_number: str,
    *,
    excluding_project_id: str | None = None,
) -> bool:
    if excluding_project_id is None:
        row = db.execute(
            "SELECT 1 FROM projects WHERE customer_id = ? AND project_number = ?",
            (customer_id, project_number),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT 1 FROM projects"
            " WHERE customer_id = ? AND project_number = ? AND project_id != ?",
            (customer_id, project_number, excluding_project_id),
        ).fetchone()
    return row is not None


@bp.route("/customers/<customer_id>/projects/new", methods=["GET", "POST"])
def projects_new(customer_id: str):
    db = get_db()
    try:
        customer = _fetch_customer(db, customer_id)
    finally:
        db.close()
    if customer is None:
        return ("Customer not found.", 404)

    if request.method == "POST":
        payload = _form_payload(request.form)
        error = None
        if not payload["project_number"]:
            error = "Project number is required."
        else:
            db = get_db()
            try:
                if _project_number_exists(db, customer_id, payload["project_number"]):
                    error = "A project with this number already exists for this customer."
            finally:
                db.close()
        if error is not None:
            return render_template(
                "project_form.html",
                customer=customer,
                project=payload,
                mode="new",
                error=error,
            )

        now = _now()
        db = get_db()
        try:
            existing = {
                row["project_id"]
                for row in db.execute(
                    "SELECT project_id FROM projects WHERE customer_id = ?",
                    (customer_id,),
                ).fetchall()
            }
            project_id = _slugify_project_id(payload["project_number"], existing)
            db.execute(
                "INSERT INTO projects (project_id, customer_id, project_number,"
                " ticket_reference, assigned_consultant, created_at,"
                " working_state_modified_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    customer_id,
                    payload["project_number"],
                    payload["ticket_reference"],
                    payload["assigned_consultant"],
                    now,
                    now,
                ),
            )
            db.commit()
        finally:
            db.close()

        # Auto-activate the new project.
        set_active_project(customer_id, project_id)
        flash(
            f"Project '{payload['project_number']}' created and set as active.",
            "success",
        )
        return redirect(
            url_for(
                "main.projects_detail",
                customer_id=customer_id,
                project_id=project_id,
            )
        )

    return render_template(
        "project_form.html",
        customer=customer,
        project={},
        mode="new",
        error=None,
    )


@bp.route("/customers/<customer_id>/projects/<project_id>")
def projects_detail(customer_id: str, project_id: str):
    from cvhealthcheck.web.active_project import get_active_project

    db = get_db()
    try:
        customer = _fetch_customer(db, customer_id)
        if customer is None:
            return ("Customer not found.", 404)
        project = _fetch_project(db, customer_id, project_id)
        if project is None:
            return ("Project not found.", 404)
        finalizations = db.execute(
            "SELECT finalization_id, finalization_number, finalized_at,"
            "       finalized_by, ticket_reference, notes"
            " FROM finalizations WHERE project_id = ?"
            " ORDER BY finalization_number DESC",
            (project_id,),
        ).fetchall()
        finalizations = [dict(row) for row in finalizations]
    finally:
        db.close()

    active_customer_id, active_project_id = get_active_project()
    is_active = (
        active_customer_id == customer_id and active_project_id == project_id
    )
    return render_template(
        "project_detail.html",
        customer=customer,
        project=project,
        finalizations=finalizations,
        is_active=is_active,
    )


@bp.route("/customers/<customer_id>/projects/<project_id>/edit", methods=["GET", "POST"])
def projects_edit(customer_id: str, project_id: str):
    db = get_db()
    try:
        customer = _fetch_customer(db, customer_id)
        if customer is None:
            return ("Customer not found.", 404)
        existing = _fetch_project(db, customer_id, project_id)
    finally:
        db.close()
    if existing is None:
        return ("Project not found.", 404)

    if request.method == "POST":
        payload = _form_payload(request.form)
        error = None
        if not payload["project_number"]:
            error = "Project number is required."
        else:
            db = get_db()
            try:
                if _project_number_exists(
                    db,
                    customer_id,
                    payload["project_number"],
                    excluding_project_id=project_id,
                ):
                    error = "A project with this number already exists for this customer."
            finally:
                db.close()
        if error is not None:
            return render_template(
                "project_form.html",
                customer=customer,
                project={"project_id": project_id, **payload},
                mode="edit",
                error=error,
            )

        now = _now()
        db = get_db()
        try:
            db.execute(
                "UPDATE projects SET project_number = ?, ticket_reference = ?,"
                " assigned_consultant = ?, working_state_modified_at = ?"
                " WHERE customer_id = ? AND project_id = ?",
                (
                    payload["project_number"],
                    payload["ticket_reference"],
                    payload["assigned_consultant"],
                    now,
                    customer_id,
                    project_id,
                ),
            )
            db.commit()
        finally:
            db.close()
        flash(f"Project '{payload['project_number']}' updated.", "success")
        return redirect(
            url_for(
                "main.projects_detail",
                customer_id=customer_id,
                project_id=project_id,
            )
        )

    return render_template(
        "project_form.html",
        customer=customer,
        project=existing,
        mode="edit",
        error=None,
    )


@bp.route("/customers/<customer_id>/projects/<project_id>/delete", methods=["GET", "POST"])
def projects_delete(customer_id: str, project_id: str):
    from cvhealthcheck.web.active_project import (
        get_active_project,
        resolve_default_project,
        set_active_project,
    )

    db = get_db()
    try:
        customer = _fetch_customer(db, customer_id)
        if customer is None:
            return ("Customer not found.", 404)
        existing = _fetch_project(db, customer_id, project_id)
        if existing is None:
            return ("Project not found.", 404)
        row = db.execute(
            "SELECT COUNT(*) FROM finalizations WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        finalization_count = int(row[0]) if row else 0
    finally:
        db.close()

    if request.method == "POST":
        if finalization_count > 0:
            # Defense in depth — the GET-side renders without a confirm
            # button, but a direct POST could still land. Finalized
            # projects cannot be deleted via the UI per ADR 0002.
            return render_template(
                "project_delete.html",
                customer=customer,
                project=existing,
                finalization_count=finalization_count,
                blocked=True,
            ), 400

        # If we're deleting the active project, fall back to the
        # migration-seeded Default project (which is guaranteed to
        # exist) so the workspace doesn't render against a dangling
        # project_id.
        active_customer_id, active_project_id = get_active_project()
        was_active = (
            active_customer_id == customer_id and active_project_id == project_id
        )

        db = get_db()
        try:
            db.execute(
                "DELETE FROM projects WHERE customer_id = ? AND project_id = ?",
                (customer_id, project_id),
            )
            db.commit()
            if was_active:
                fallback_customer, fallback_project = resolve_default_project(db)
        finally:
            db.close()

        if was_active:
            set_active_project(fallback_customer, fallback_project)

        flash(f"Project '{existing['project_number']}' deleted.", "success")
        return redirect(
            url_for("main.customers_detail", customer_id=customer_id)
        )

    return render_template(
        "project_delete.html",
        customer=customer,
        project=existing,
        finalization_count=finalization_count,
        blocked=finalization_count > 0,
    )


@bp.route("/api/active-project", methods=["GET", "POST"])
def api_active_project():
    """Active-project read/write.

    GET: returns the current active (customer_id, project_id) plus
    customer_name and project_number, as JSON. Used by the
    active-project selector on every workspace page.

    POST: takes customer_id and project_id (form-encoded), validates
    that the project belongs to the customer, and updates the session.
    For form callers, supply a redirect_to URL — the handler responds
    with 302 to that location after switching. For AJAX callers,
    omit redirect_to and the handler responds with JSON.
    """
    from cvhealthcheck.web.active_project import (
        get_active_project,
        set_active_project,
    )
    from flask import jsonify

    if request.method == "GET":
        active_customer_id, active_project_id = get_active_project()
        db = get_db()
        try:
            customer = _fetch_customer(db, active_customer_id)
            project = _fetch_project(db, active_customer_id, active_project_id)
            customers = db.execute(
                "SELECT customer_id, customer_name FROM customers"
                " ORDER BY customer_name ASC, customer_id ASC"
            ).fetchall()
            all_projects = db.execute(
                "SELECT project_id, customer_id, project_number"
                " FROM projects ORDER BY created_at DESC, project_id ASC"
            ).fetchall()
        finally:
            db.close()

        return jsonify({
            "active": {
                "customer_id": active_customer_id,
                "project_id": active_project_id,
                "customer_name": (customer or {}).get("customer_name"),
                "project_number": (project or {}).get("project_number"),
            },
            "customers": [
                {
                    "customer_id": c["customer_id"],
                    "customer_name": c["customer_name"],
                    "projects": [
                        {
                            "project_id": p["project_id"],
                            "project_number": p["project_number"],
                        }
                        for p in all_projects
                        if p["customer_id"] == c["customer_id"]
                    ],
                }
                for c in customers
            ],
        })

    # POST
    customer_id = (request.form.get("customer_id") or "").strip()
    project_id = (request.form.get("project_id") or "").strip()
    redirect_to = (request.form.get("redirect_to") or "").strip()

    if not customer_id or not project_id:
        msg = "customer_id and project_id are required."
        if redirect_to:
            flash(msg, "error")
            return redirect(redirect_to)
        return jsonify({"error": msg}), 400

    db = get_db()
    try:
        # Validate the pair: the project must exist under that customer.
        row = db.execute(
            "SELECT 1 FROM projects WHERE customer_id = ? AND project_id = ?",
            (customer_id, project_id),
        ).fetchone()
    finally:
        db.close()
    if row is None:
        msg = f"No project '{project_id}' under customer '{customer_id}'."
        if redirect_to:
            flash(msg, "error")
            return redirect(redirect_to)
        return jsonify({"error": msg}), 400

    set_active_project(customer_id, project_id)
    if redirect_to:
        return redirect(redirect_to)
    return jsonify({
        "active": {"customer_id": customer_id, "project_id": project_id},
    })
