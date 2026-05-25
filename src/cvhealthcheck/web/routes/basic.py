from __future__ import annotations

from .shared import (
    AuthError,
    _safe_next,
    bp,
    clear_current_token,
    load_settings,
    login_to_commvault,
    redirect,
    render_template,
    request,
    set_current_token,
    url_for,
)


@bp.route("/login", methods=["GET", "POST"])
def login():
    settings = load_settings()
    error = None
    next_url = _safe_next()
    if request.args.get("expired") == "1":
        error = "Commvault token expired. Please sign in again."

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = _safe_next(next_url)
        try:
            token = login_to_commvault(settings.base_url, username, password)
        except AuthError as exc:
            error = str(exc)
        else:
            set_current_token(token, username=username)
            return redirect(next_url or url_for("main.quick_hc"))

    return render_template(
        "login.html",
        error=error,
        base_url=settings.base_url,
        next_url=next_url,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    clear_current_token()
    return redirect(url_for("main.login"))


@bp.route("/")
def index():
    return redirect(url_for("main.quick_hc"))
