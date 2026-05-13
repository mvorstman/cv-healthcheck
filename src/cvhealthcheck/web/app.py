from __future__ import annotations

import os
import secrets

from flask import Flask

from .routes.main import bp as main_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("CV_SECRET_KEY") or secrets.token_hex(32)
    app.register_blueprint(main_bp)
    return app


app = create_app()
