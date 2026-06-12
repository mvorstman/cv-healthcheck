from __future__ import annotations

from cvhealthcheck.identity import effective_connection_url
from cvhealthcheck.web.active_project import get_active_customer

from .shared import (
    AuthError,
    _safe_next,
    bp,
    clear_current_token,
    login_to_commvault,
    redirect,
    render_template,
    request,
    set_current_token,
    url_for,
)


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Connect to the active customer's CommCell.

    Under ADR 0003 phase 3, /login is customer-aware: the CommCell URL
    it authenticates against comes from the active customer's
    ``commcell_hostname`` column, and the resulting token is bound to
    that customer's id. If the active customer has no ``commcell_hostname``
    configured, the form renders in a disabled state with guidance to
    edit the customer first.
    """
    customer = get_active_customer()
    customer_name = customer.get("customer_name") or customer["customer_id"]
    # Fix 3: read the new connection_url, falling back to READ-ONLY-LEGACY
    # commcell_hostname during the transition; validated (schemeless repaired).
    connection_url = effective_connection_url(customer)

    error = None
    next_url = _safe_next()
    if request.args.get("expired") == "1":
        error = "Commvault token expired. Please sign in again."

    if request.method == "POST":
        if not connection_url:
            error = (
                f"Customer '{customer_name}' has no connection URL configured. "
                "Edit the customer and set its Connection URL before signing in."
            )
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            next_url = _safe_next(next_url)
            try:
                token = login_to_commvault(connection_url, username, password)
            except AuthError as exc:
                error = str(exc)
            else:
                set_current_token(
                    token,
                    customer_id=customer["customer_id"],
                    username=username,
                )
                return redirect(next_url or url_for("main.quick_hc"))

    return render_template(
        "login.html",
        error=error,
        base_url=connection_url,
        customer_name=customer_name,
        customer_id=customer["customer_id"],
        next_url=next_url,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    clear_current_token()
    return redirect(url_for("main.login"))


@bp.route("/")
def index():
    return redirect(url_for("main.quick_hc"))
