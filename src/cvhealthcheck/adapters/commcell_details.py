from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    MetricItem,
    MetricSection,
)

SUBJECT_ID = "environment"
SUBJECT_TITLE = "CommCell Details"
COMMSERV_ENDPOINT = "/commandcenter/api/CommServ"

_METRIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("hostName",      "hostname",        "Host Name"),
    ("csGUID",        "cs_guid",         "CommCell ID"),
    ("csVersionInfo", "cs_version_info", "Version"),
    ("releaseId",     "release_id",      "Release"),
    ("osType",        "os_type",         "OS Type"),
    ("timeZone",      "timezone",        "Time Zone"),
)


def adapt_rest(result: dict[str, Any]) -> CanonicalArtifact:
    identity: dict[str, Any] = {}
    if isinstance(result.get("identity"), dict):
        identity = result["identity"]

    generated_at = _parse_dt(result.get("collected_at")) or datetime.now(timezone.utc)

    source = ArtifactSource(
        type=SourceType.rest_commserve,
        endpoint=COMMSERV_ENDPOINT,
        collected_at=generated_at,
    )

    items = [
        MetricItem(id=metric_id, label=label, value=raw_value)
        for source_key, metric_id, label in _METRIC_FIELDS
        if (raw_value := identity.get(source_key)) is not None
    ]

    sections = (
        [MetricSection(type="metric", id=SUBJECT_ID, title=SUBJECT_TITLE, items=items)]
        if items
        else []
    )

    status = ArtifactStatus.good if _has_meaningful_identity(identity) else ArtifactStatus.unknown

    return CanonicalArtifact(
        artifact_type=SUBJECT_ID,
        generated_at=generated_at,
        source=source,
        subject=ArtifactSubject(id=SUBJECT_ID, title=SUBJECT_TITLE),
        summary=ArtifactSummary(status=status, metrics=[]),
        sections=sections,
    )


def _has_meaningful_identity(identity: dict[str, Any]) -> bool:
    return bool(identity.get("hostName") or identity.get("csGUID"))


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
