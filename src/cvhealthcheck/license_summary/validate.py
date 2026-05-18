from __future__ import annotations

from .models import (
    AgentFeatureLicense,
    OtherLicense,
    WorkloadSummaryRow,
    WorkloadSummarySection,
)


def is_valid_other_license(payload: dict[str, object]) -> bool:
    license_name = str(payload.get("license") or "").strip()
    return bool(license_name)


def is_valid_agent_feature_license(payload: dict[str, object]) -> bool:
    license_name = str(payload.get("license") or "").strip()
    return bool(license_name)


def filter_valid_other_licenses(candidates: list[dict[str, object]]) -> list[OtherLicense]:
    return [
        OtherLicense.from_dict(candidate)
        for candidate in candidates
        if is_valid_other_license(candidate)
    ]


def filter_valid_agent_feature_licenses(
    candidates: list[dict[str, object]],
) -> list[AgentFeatureLicense]:
    return [
        AgentFeatureLicense.from_dict(candidate)
        for candidate in candidates
        if is_valid_agent_feature_license(candidate)
    ]


def is_valid_workload_summary_row(payload: dict[str, object]) -> bool:
    license_name = str(payload.get("license") or "").strip()
    return bool(license_name)


def filter_valid_workload_summary_sections(
    candidates: list[dict[str, object]],
) -> list[WorkloadSummarySection]:
    sections: list[WorkloadSummarySection] = []
    for candidate in candidates:
        section_name = str(candidate.get("section_name") or "").strip()
        if not section_name:
            continue
        rows = [
            WorkloadSummaryRow.from_dict(row)
            for row in candidate.get("rows") or []
            if isinstance(row, dict) and is_valid_workload_summary_row(row)
        ]
        if rows:
            sections.append(WorkloadSummarySection(section_name=section_name, rows=rows))
    return sections
