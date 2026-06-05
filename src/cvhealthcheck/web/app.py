from __future__ import annotations

import os
import secrets

from flask import Flask
from markupsafe import Markup, escape

from .routes.main import bp as main_bp
from cvhealthcheck.db.migrations import run_migrations


def _localtime_span(value, fallback: str = "") -> Markup:
    """Render a stored UTC timestamp for DISPLAY in the browser's local timezone.

    Storage stays UTC — this only emits the markup that ``localtime.js`` rewrites
    client-side. ``value`` is a machine-readable UTC ISO-8601 string (…Z / +00:00);
    it rides in ``data-localtime`` AND as the element's text, so the raw UTC shows
    as the no-JS / bad-value fallback. An empty value renders the ``fallback``
    placeholder (e.g. "N/A", "Not collected yet"), never a span. This is the ONE
    server-side seam for timestamp display — route every template timestamp through
    it (the JS workspace uses window.fmtLocalTime, the same formatter)."""
    if not value:
        return Markup(escape(fallback))
    v = escape(str(value))
    return Markup(f'<span data-localtime="{v}">{v}</span>')


def create_app() -> Flask:
    run_migrations()
    app = Flask(__name__)
    app.secret_key = os.getenv("CV_SECRET_KEY") or secrets.token_hex(32)
    app.jinja_env.globals["localtime_span"] = _localtime_span
    app.register_blueprint(main_bp)
    return app


app = create_app()
