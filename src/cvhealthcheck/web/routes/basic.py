from __future__ import annotations

from cvhealthcheck.web.active_project import get_active_customer

from .shared import (
    AuthError,
    _safe_next,
    bp,
    clear_current_token,
    get_current_username,
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
    commcell_hostname = customer.get("commcell_hostname")

    error = None
    next_url = _safe_next()
    if request.args.get("expired") == "1":
        error = "Commvault token expired. Please sign in again."

    if request.method == "POST":
        if not commcell_hostname:
            error = (
                f"Customer '{customer_name}' has no CommCell URL configured. "
                "Edit the customer and set commcell_hostname before signing in."
            )
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            next_url = _safe_next(next_url)
            try:
                token = login_to_commvault(commcell_hostname, username, password)
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
        base_url=commcell_hostname,
        customer_name=customer_name,
        customer_id=customer["customer_id"],
        next_url=next_url,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    clear_current_token()
    return redirect(url_for("main.login"))


@bp.route("/connections")
def connections():
    """Live connection status + connect/disconnect (ADR-0008 B). Thin: reads the held
    token's status from the store and the read-only env target; the Connect action reuses
    /login, Disconnect clears the store. No secrets (token/password) are rendered."""
    from cvhealthcheck import token_store
    from cvhealthcheck.config import load_settings
    settings = load_settings()
    try:
        customer = get_active_customer()
    except Exception:  # no active project / customer — page must still render
        customer = {}
    return render_template(
        "connections.html",
        status=token_store.status(),
        username=get_current_username(),
        customer_name=customer.get("customer_name") or customer.get("customer_id"),
        base_url=settings.base_url,
        verify_ssl=settings.verify_ssl,
    )


@bp.route("/connections/disconnect", methods=["POST"])
def connections_disconnect():
    clear_current_token()   # clears the in-process store + session markers
    return redirect(url_for("main.connections"))


@bp.route("/")
def index():
    return redirect(url_for("main.quick_hc"))
