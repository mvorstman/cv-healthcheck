from __future__ import annotations

from .models import AgentFeatureLicense, OtherLicense


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
