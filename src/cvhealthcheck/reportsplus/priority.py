from __future__ import annotations

from collections import Counter
from typing import Any

PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def prioritize_candidates(
    reports: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [
        _candidate("report", report) for report in reports
    ] + [
        _candidate("dataset", dataset) for dataset in datasets
    ]
    return sorted(
        candidates,
        key=lambda item: (
            PRIORITY_ORDER.get(str(item["priority"]), 99),
            str(item["name"]).lower(),
        ),
    )


def priority_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(candidate.get("priority", "LOW")) for candidate in candidates)
    return {
        "HIGH": counts.get("HIGH", 0),
        "MEDIUM": counts.get("MEDIUM", 0),
        "LOW": counts.get("LOW", 0),
    }


def _candidate(source_type: str, record: dict[str, Any]) -> dict[str, Any]:
    name = _name(source_type, record)
    text = _search_text(record)
    priority, reason = _priority_reason(text)
    return {
        "source_type": source_type,
        "name": name,
        "id": _id(source_type, record),
        "guid": _guid(source_type, record),
        "relevance_tags": _relevance_tags(record, text),
        "priority": priority,
        "reason": reason,
        "mapped_health_area": _mapped_health_area(text),
    }


def _priority_reason(text: str) -> tuple[str, str]:
    high_rules = [
        ("SLA", ("sla", "service level")),
        ("failed jobs", ("failed", "corrupted")),
        ("backup jobs", ("backup job", "job summary", "database job")),
        ("storage capacity", ("storage usage", "storage utilization", "capacity")),
        ("infrastructure utilization", ("infrastructure", "resource utilization")),
        ("readiness", ("readiness",)),
        ("MediaAgent/library/DDB health", ("mediaagent", "library", "dedup", "ddb")),
        ("audit/security", ("audit", "permission", "security")),
    ]
    for reason, needles in high_rules:
        if any(needle in text for needle in needles):
            return "HIGH", f"Matched high-priority health area: {reason}."

    medium_rules = [
        ("growth/trends", ("growth", "trend")),
        ("tenant usage", ("tenant", "company")),
        ("client growth", ("client growth", "client")),
        ("license", ("license",)),
        ("chargeback", ("chargeback",)),
        ("cloud ingress/egress", ("cloud", "ingress", "egress")),
    ]
    for reason, needles in medium_rules:
        if any(needle in text for needle in needles):
            return "MEDIUM", f"Matched medium-priority analysis area: {reason}."

    low_rules = [
        ("package details", ("package",)),
        ("file search", ("file search",)),
        ("report-management item", ("report", "custom")),
    ]
    for reason, needles in low_rules:
        if any(needle in text for needle in needles):
            return "LOW", f"Matched low-priority catalog area: {reason}."

    return "LOW", "No strong healthcheck signal found in catalog metadata."


def _mapped_health_area(text: str) -> str:
    mappings = [
        ("Metrics reporting", ("sla", "infrastructure", "resource utilization")),
        ("Command Center health", ("readiness",)),
        ("Failed jobs", ("failed", "corrupted")),
        ("Companies / tenants", ("tenant", "company", "commcell group")),
        ("Custom report data", ("package",)),
        ("Jobs", ("job", "backup", "restore")),
        ("Capacity/free space", ("capacity", "storage usage", "storage utilization")),
        ("Storage pools", ("storage", "policy copy")),
        ("Deduplication DB", ("dedup", "ddb")),
        ("MediaAgents", ("mediaagent",)),
        ("Libraries", ("library",)),
        ("Index health", ("index",)),
        ("CommServe DR backup", ("disaster recovery", "dr backup")),
        ("Schedules", ("schedule",)),
        ("Plans", ("plan",)),
        ("Users / security", ("user", "permission", "security", "audit")),
        ("Metrics reporting", ("metric", "metrics")),
        ("Custom report data", ("custom", "report")),
        ("Alerts", ("alert",)),
        ("Running jobs", ("running job",)),
    ]
    for area, needles in mappings:
        if any(needle in text for needle in needles):
            return area
    return "Unknown"


def _relevance_tags(record: dict[str, Any], text: str) -> list[str]:
    tags: list[str] = []
    relevance = record.get("relevance")
    if relevance and relevance != "Unknown":
        tags.append(str(relevance))
    explicit_tags = record.get("tags")
    if isinstance(explicit_tags, str) and explicit_tags.strip():
        tags.extend(tag.strip() for tag in explicit_tags.split(",") if tag.strip())
    for label in ("Storage", "Jobs", "SLA", "Audit", "Security", "Infrastructure", "Tenant", "Metrics"):
        if label.lower() in text and label not in tags:
            tags.append(label)
    return tags or ["Unknown"]


def _search_text(record: dict[str, Any]) -> str:
    values = [
        record.get("reportName"),
        record.get("dataSetName"),
        record.get("description"),
        record.get("tags"),
        record.get("relevance"),
    ]
    return " ".join(str(value) for value in values if value is not None).lower()


def _name(source_type: str, record: dict[str, Any]) -> str:
    if source_type == "report":
        return str(record.get("reportName") or "")
    return str(record.get("dataSetName") or "")


def _id(source_type: str, record: dict[str, Any]) -> Any:
    if source_type == "report":
        return record.get("reportId")
    return record.get("dataSetId")


def _guid(source_type: str, record: dict[str, Any]) -> Any:
    if source_type == "report":
        return record.get("guid")
    return record.get("dataSetGuid") or record.get("guid")
