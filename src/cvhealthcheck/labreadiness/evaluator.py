from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cvhealthcheck.reportsplus.catalog import collected_at

from .collector import collect_indicators
from .models import Indicator, ReadinessState

LABREADINESS_DIR = Path("data/labreadiness")


def assess_lab_readiness(write: bool = True, token: str | None = None) -> dict[str, Any]:
    indicators = collect_indicators(token=token)
    state, reasoning, recommendations = evaluate(indicators)
    payload = {
        "timestamp": collected_at(),
        "readiness_state": state.value,
        "summary": _summary(state, indicators),
        "indicators": {
            key: indicator.as_dict() for key, indicator in indicators.items()
        },
        "reasoning": reasoning,
        "recommendations": recommendations,
    }
    if write:
        LABREADINESS_DIR.mkdir(parents=True, exist_ok=True)
        (LABREADINESS_DIR / "latest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    return payload


def evaluate(
    indicators: dict[str, Indicator],
) -> tuple[ReadinessState, list[str], list[str]]:
    api_ready = _truthy(indicators, "commserve_reachable")
    reports_ready = _truthy(indicators, "reports_plus_reachable")
    executable_count = _int_value(indicators, "executable_datasets_count")
    executable_records = _int_value(indicators, "executable_datasets_returning_records")
    audit_present = _truthy(indicators, "audit_records_present")
    backup_jobs_present = _truthy(indicators, "backup_jobs_present")
    successful_jobs_present = _truthy(indicators, "successful_backup_jobs_present")
    alerts_or_events = _truthy(indicators, "alerts_or_events_present")

    reasoning: list[str] = []
    recommendations: list[str] = []

    if not api_ready:
        reasoning.append("Base Command Center API is not reachable.")
        recommendations.append("Restore Command Center/API connectivity before testing discovery.")
        return ReadinessState.NOT_READY, reasoning, recommendations

    if not reports_ready:
        reasoning.append("Base API is reachable, but Reports Plus inventory is not reachable.")
        recommendations.append("Create or refresh .login_token before running Reports Plus discovery.")
        return ReadinessState.NOT_READY, reasoning, recommendations

    reasoning.append("Base API and Reports Plus inventory are reachable.")

    if executable_count <= 0:
        recommendations.append("Run candidate execution validation after catalog discovery.")
        return ReadinessState.READY_FOR_DISCOVERY, reasoning, recommendations

    reasoning.append(f"{executable_count} Reports Plus datasets validated as executable.")

    health_data_ready = (
        successful_jobs_present
        and backup_jobs_present
        and (audit_present or alerts_or_events)
        and executable_records >= 2
    )
    if health_data_ready:
        reasoning.append("Operational job and audit/event data are present.")
        return ReadinessState.READY_FOR_HEALTH_RULE_TESTING, reasoning, recommendations

    if not successful_jobs_present:
        recommendations.append("Run successful backup jobs to populate SLA and job-health datasets.")
    if not backup_jobs_present:
        recommendations.append("Run backup jobs so job summary datasets contain records.")
    if not alerts_or_events:
        recommendations.append("Generate or collect alert/event data before testing alert health logic.")
    if not audit_present:
        recommendations.append("Generate audited administrative activity for security/audit validation.")
    recommendations.append(
        "Treat empty Reports Plus results in this minimal lab as lack of operational activity, not product failure."
    )
    return ReadinessState.READY_FOR_DATA_EXECUTION, reasoning, recommendations


def _summary(state: ReadinessState, indicators: dict[str, Indicator]) -> str:
    if state is ReadinessState.READY_FOR_HEALTH_RULE_TESTING:
        return "Lab has enough operational evidence to begin health-rule testing."
    if state is ReadinessState.READY_FOR_DATA_EXECUTION:
        return (
            "Discovery and dataset execution work, but the lab lacks enough operational "
            "backup activity for meaningful health-rule testing."
        )
    if state is ReadinessState.READY_FOR_DISCOVERY:
        return "Lab is ready for inventory discovery, but dataset execution is not validated yet."
    return "Lab is not ready for cv-healthcheck discovery."


def _truthy(indicators: dict[str, Indicator], key: str) -> bool:
    return bool(indicators.get(key) and indicators[key].value)


def _int_value(indicators: dict[str, Indicator], key: str) -> int:
    value = indicators.get(key).value if indicators.get(key) else 0
    return value if isinstance(value, int) else 0
