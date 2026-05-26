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

from .shared import bp


# -- step 2 lands the create form
# -- step 3 lands the detail view
# -- step 4 lands the edit form
# -- step 5 lands the delete flow
# -- step 6 lands the active-project JSON API
#
# Step 1 needs these endpoint names registered so customer_detail.html's
# url_for() calls resolve. Each stub returns a 501 placeholder; the real
# handler lands in the named step.


@bp.route("/customers/<customer_id>/projects/new", methods=["GET", "POST"])
def projects_new(customer_id: str):
    return ("Not implemented yet (phase 4 step 2).", 501)


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
