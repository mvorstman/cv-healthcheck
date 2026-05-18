from __future__ import annotations

from .shared import (
    AuthError,
    CommvaultApiClient,
    _api_client,
    _auth_failure_redirect,
    _current_token,
    _safe_next,
    assess_lab_readiness,
    bp,
    clear_current_token,
    load_settings,
    login_required,
    login_to_commvault,
    redirect,
    render_template,
    request,
    set_current_token,
    to_pretty_json,
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
            set_current_token(token)
            return redirect(next_url or url_for("main.lab_readiness"))

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
@login_required
def index():
    settings = load_settings()
    client = CommvaultApiClient(settings=settings, token=_current_token())
    ping = client.ping() if settings.base_url else None
    if ping:
        auth_redirect = _auth_failure_redirect(ping)
        if auth_redirect:
            return auth_redirect
    return render_template(
        "index.html",
        base_url=settings.base_url,
        verify_ssl=settings.verify_ssl,
        token_loaded=client.token_loaded,
        api_reachable=bool(ping and ping.ok),
        api_status_code=ping.status_code if ping else None,
        api_error=ping.error if ping else None,
    )


@bp.route("/lab-readiness")
@login_required
def lab_readiness():
    result = assess_lab_readiness(write=True, token=_current_token())
    indicators = result.get("indicators", {})
    for name in ("commserve_reachable", "reports_plus_reachable"):
        indicator = indicators.get(name, {})
        if indicator.get("notes") == "HTTP 401":
            clear_current_token()
            return redirect(url_for("main.login", next=request.path, expired="1"))
    states = [
        "NOT_READY",
        "READY_FOR_DISCOVERY",
        "READY_FOR_DATA_EXECUTION",
        "READY_FOR_HEALTH_RULE_TESTING",
    ]
    return render_template(
        "lab_readiness.html",
        result=result,
        states=states,
        indicators=result.get("indicators", {}),
    )


@bp.route("/api/test")
@login_required
def api_test():
    result = _api_client().ping()
    auth_redirect = _auth_failure_redirect(result)
    if auth_redirect:
        return auth_redirect
    running = "WebService is Running!" in result.text
    return render_template(
        "api_test.html",
        result=result,
        running=running,
        formatted=to_pretty_json(result.data) if result.data is not None else result.text,
    )
