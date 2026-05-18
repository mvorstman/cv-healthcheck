from __future__ import annotations

from .shared import (
    SecurityAssessmentService,
    _security_assessment_registry_filters,
    bp,
    login_required,
    render_template,
    url_for,
)


@bp.route("/development")
@login_required
def development():
    return render_template("development.html")


@bp.route("/development/security-assessment-registry")
@login_required
def security_assessment_registry_view():
    service = SecurityAssessmentService()
    filters = _security_assessment_registry_filters()
    history = service.get_history(**filters)
    history_url = url_for(
        "main.security_assessment_history",
        **{key: value for key, value in filters.items() if value},
    )
    return render_template(
        "security_assessment_registry_history.html",
        filters=filters,
        artifacts=history["artifacts"],
        import_runs=history["import_runs"],
        report_runs=history["report_runs"],
        history_url=history_url,
    )
