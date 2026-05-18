from __future__ import annotations

from typing import Any, Iterable

from .models import CanonicalFinding

BLOCKED_TEXT_MARKERS = (
    "parameter status remarks action",
    "detailed checks",
    "1 to 3 of 3 entries",
)
MAX_PARAMETER_LENGTH = 300
MAX_STATUS_LENGTH = 40
MAX_FIELD_LENGTH = 4000
MAX_COMBINED_LENGTH = 6000


def is_valid_canonical_finding(candidate: dict[str, Any]) -> bool:
    parameter = str(candidate.get("parameter") or "")
    status = str(candidate.get("status") or "")
    remarks = str(candidate.get("remarks") or "")
    action = str(candidate.get("action") or "")

    if not parameter or not status:
        return False
    if len(parameter) > MAX_PARAMETER_LENGTH or len(status) > MAX_STATUS_LENGTH:
        return False
    if len(remarks) > MAX_FIELD_LENGTH or len(action) > MAX_FIELD_LENGTH:
        return False

    combined = "\n".join(
        [
            str(candidate.get("section") or ""),
            parameter,
            status,
            remarks,
            action,
        ]
    ).strip()
    lowered = combined.lower()
    if len(combined) > MAX_COMBINED_LENGTH:
        return False
    if lowered == "parameter\nstatus\nremarks\naction":
        return False
    if any(marker in lowered for marker in BLOCKED_TEXT_MARKERS):
        return False
    try:
        CanonicalFinding(
            section=str(candidate.get("section") or ""),
            parameter=parameter,
            status=status,
            remarks=remarks,
            action=action,
            source_type=str(candidate.get("source_type") or ""),
            source_file=candidate.get("source_file"),
            imported_at=str(candidate.get("imported_at") or ""),
        )
    except ValueError:
        return False
    return True


def filter_valid_findings(candidates: Iterable[dict[str, Any]]) -> list[CanonicalFinding]:
    findings: list[CanonicalFinding] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for candidate in candidates:
        if not is_valid_canonical_finding(candidate):
            continue
        finding = CanonicalFinding(
            section=str(candidate.get("section") or ""),
            parameter=str(candidate.get("parameter") or ""),
            status=str(candidate.get("status") or ""),
            remarks=str(candidate.get("remarks") or ""),
            action=str(candidate.get("action") or ""),
            source_type=str(candidate.get("source_type") or ""),
            source_file=candidate.get("source_file"),
            imported_at=str(candidate.get("imported_at") or ""),
        )
        finding_key = (
            finding.section,
            finding.parameter,
            finding.status,
            finding.remarks,
            finding.action,
        )
        if finding_key in seen:
            continue
        seen.add(finding_key)
        findings.append(finding)
    return findings
