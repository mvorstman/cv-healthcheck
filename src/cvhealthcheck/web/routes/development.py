from __future__ import annotations

from .shared import (
    bp,
    login_required,
    render_template,
)


# ── Development hub ──

@bp.route("/development")
@login_required
def development():
    return render_template("development.html")
