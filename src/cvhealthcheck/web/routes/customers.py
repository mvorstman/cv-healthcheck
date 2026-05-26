"""Customer management routes (ADR 0002 phase 3).

CRUD UI for the customers table. Manual entry only — CommCell-discovery
is deferred to a future phase (see HANDOVER's priority-ordered backlog).
No authentication required; consistent with the existing settings/staging
pages.

Routes:
    GET  /customers                       — list
    GET  /customers/new                   — create form
    POST /customers/new                   — create handler
    GET  /customers/<customer_id>/edit    — edit form
    POST /customers/<customer_id>/edit    — edit handler
    GET  /customers/<customer_id>/delete  — confirmation page
    POST /customers/<customer_id>/delete  — delete handler (strict guard)
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.db import get_db

from .shared import bp, flash, redirect, render_template, request, url_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_customer_id(name: str, existing_ids: set[str]) -> str:
    """Turn a customer name into a stable id slug, matching the
    migration-seeded 'default' style. On collision, append _2, _3, ..."""
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if not base:
        base = f"customer_{uuid.uuid4().hex[:8]}"
    candidate = base
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _form_payload(form: Any) -> dict[str, Any]:
    """Pull customer fields from a request form, trimming whitespace.
    Optional fields with empty values resolve to None (= NULL in storage).
    """
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    return {
        "customer_name": (form.get("customer_name") or "").strip(),
        "commcell_id": _clean(form.get("commcell_id")),
        "commcell_hostname": _clean(form.get("commcell_hostname")),
        "company_guid": _clean(form.get("company_guid")),
        "contact_info": _clean(form.get("contact_info")),
        "notes": _clean(form.get("notes")),
    }


_SELECT_COLUMNS = (
    "customer_id, customer_name, commcell_id, commcell_hostname, "
    "company_guid, contact_info, notes, created_at, updated_at"
)


def _fetch_customers_with_counts(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        f"SELECT {_SELECT_COLUMNS},"
        "       (SELECT COUNT(*) FROM projects p"
        "        WHERE p.customer_id = customers.customer_id) AS project_count"
        " FROM customers"
        " ORDER BY customer_name ASC, customer_id ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_customer(db: sqlite3.Connection, customer_id: str) -> dict[str, Any] | None:
    row = db.execute(
        f"SELECT {_SELECT_COLUMNS} FROM customers WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _count_projects(db: sqlite3.Connection, customer_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM projects WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return int(row[0]) if row else 0


@bp.route("/customers")
def customers_list():
    db = get_db()
    try:
        customers = _fetch_customers_with_counts(db)
    finally:
        db.close()
    return render_template("customers_list.html", customers=customers)


@bp.route("/customers/new", methods=["GET", "POST"])
def customers_new():
    if request.method == "POST":
        payload = _form_payload(request.form)
        if not payload["customer_name"]:
            return render_template(
                "customer_form.html",
                customer=payload,
                mode="new",
                error="Customer name is required.",
            )
        now = _now()
        db = get_db()
        try:
            existing = {
                row["customer_id"]
                for row in db.execute("SELECT customer_id FROM customers").fetchall()
            }
            customer_id = _slugify_customer_id(payload["customer_name"], existing)
            db.execute(
                "INSERT INTO customers (customer_id, customer_name, commcell_id,"
                " commcell_hostname, company_guid, contact_info, notes,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    customer_id,
                    payload["customer_name"],
                    payload["commcell_id"],
                    payload["commcell_hostname"],
                    payload["company_guid"],
                    payload["contact_info"],
                    payload["notes"],
                    now,
                    now,
                ),
            )
            db.commit()
        finally:
            db.close()
        flash(f"Customer '{payload['customer_name']}' created.", "success")
        return redirect(url_for("main.customers_list"))

    return render_template(
        "customer_form.html",
        customer={},
        mode="new",
        error=None,
    )


@bp.route("/customers/<customer_id>/edit", methods=["GET", "POST"])
def customers_edit(customer_id: str):
    db = get_db()
    try:
        existing = _fetch_customer(db, customer_id)
    finally:
        db.close()
    if existing is None:
        return ("Customer not found.", 404)

    if request.method == "POST":
        payload = _form_payload(request.form)
        if not payload["customer_name"]:
            return render_template(
                "customer_form.html",
                customer={"customer_id": customer_id, **payload},
                mode="edit",
                error="Customer name is required.",
            )
        now = _now()
        db = get_db()
        try:
            db.execute(
                "UPDATE customers SET customer_name = ?, commcell_id = ?,"
                " commcell_hostname = ?, company_guid = ?, contact_info = ?,"
                " notes = ?, updated_at = ?"
                " WHERE customer_id = ?",
                (
                    payload["customer_name"],
                    payload["commcell_id"],
                    payload["commcell_hostname"],
                    payload["company_guid"],
                    payload["contact_info"],
                    payload["notes"],
                    now,
                    customer_id,
                ),
            )
            db.commit()
        finally:
            db.close()
        flash(f"Customer '{payload['customer_name']}' updated.", "success")
        return redirect(url_for("main.customers_list"))

    return render_template(
        "customer_form.html",
        customer=existing,
        mode="edit",
        error=None,
    )


@bp.route("/customers/<customer_id>/delete", methods=["GET", "POST"])
def customers_delete(customer_id: str):
    db = get_db()
    try:
        existing = _fetch_customer(db, customer_id)
        project_count = _count_projects(db, customer_id)
    finally:
        db.close()

    if existing is None:
        return ("Customer not found.", 404)

    if request.method == "POST":
        if project_count > 0:
            # Defense in depth: the GET-side render disables the confirm
            # button, but a direct POST or a stale form could still arrive.
            return render_template(
                "customer_delete.html",
                customer=existing,
                project_count=project_count,
                blocked=True,
            ), 400
        db = get_db()
        try:
            db.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
            db.commit()
        finally:
            db.close()
        flash(f"Customer '{existing['customer_name']}' deleted.", "success")
        return redirect(url_for("main.customers_list"))

    return render_template(
        "customer_delete.html",
        customer=existing,
        project_count=project_count,
        blocked=project_count > 0,
    )
