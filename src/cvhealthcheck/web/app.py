from __future__ import annotations

from flask import Flask

from .routes.main import bp as main_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(main_bp)
    return app


app = create_app()

