from __future__ import annotations

from .shared import (
    _capacity_license_chart,
    _client_count_chart,
    _client_growth_chart,
    _client_growth_detail_chart,
    bp,
    get_capacity_license_usage,
    get_client_count_history,
    get_client_growth_details,
    get_client_growth_summary,
    render_template,
)


@bp.route("/metrics/client-count")
def metrics_client_count():
    metric = get_client_count_history(live=False)
    return render_template(
        "metric_detail.html",
        title="Client Count",
        metrics=[metric],
        chart=_client_count_chart(metric),
    )


@bp.route("/metrics/client-growth")
def metrics_client_growth():
    summary = get_client_growth_summary(live=False)
    details = get_client_growth_details(live=False)
    charts = [
        chart
        for chart in (
            _client_growth_chart(summary),
            _client_growth_detail_chart(details),
        )
        if chart
    ]
    return render_template(
        "metric_detail.html",
        title="Client Growth",
        metrics=[summary, details],
        charts=charts,
    )


@bp.route("/metrics/capacity-license")
def metrics_capacity_license():
    metric = get_capacity_license_usage(live=False)
    return render_template(
        "metric_detail.html",
        title="Capacity License Usage",
        metrics=[metric],
        chart=_capacity_license_chart(metric),
    )
