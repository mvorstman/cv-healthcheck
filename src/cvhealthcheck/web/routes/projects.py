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
    return ("Not implemented yet (phase 4 step 3).", 501)


@bp.route("/customers/<customer_id>/projects/<project_id>/edit", methods=["GET", "POST"])
def projects_edit(customer_id: str, project_id: str):
    return ("Not implemented yet (phase 4 step 4).", 501)


@bp.route("/customers/<customer_id>/projects/<project_id>/delete", methods=["GET", "POST"])
def projects_delete(customer_id: str, project_id: str):
    return ("Not implemented yet (phase 4 step 5).", 501)


@bp.route("/api/active-project", methods=["GET", "POST"])
def api_active_project():
    return ("Not implemented yet (phase 4 step 6).", 501)
