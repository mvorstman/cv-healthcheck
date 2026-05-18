from __future__ import annotations

import re
from typing import Any


OTHER_LICENSE_SECTION = "Other Licenses - current usage details"
AGENT_FEATURE_SECTION = "Agent and Feature Licenses - current usage details"
SUMMARY_SECTION_NAMES = {
    "Capacity Licenses",
    "Operating Instance Licenses",
    "Virtualization Licenses",
    "User Licenses",
    "Data Insights Licenses",
    "Air Gap Protect Licenses",
    "Other Licenses",
}

OTHER_LICENSE_HEADERS = ("license", "available total", "used")
AGENT_FEATURE_HEADERS = (
    "license",
    "permanent total",
    "permanent used",
    "term total",
    "term used",
    "client",
    "agent",
    "install date",
)
SUMMARY_HEADER_REQUIRED_PREFIXES = (
    "license",
    "available total",
    "used",
)

METADATA_LABELS = {
    "commcell name": "commcell_name",
    "commcell version": "commcell_version",
    "timezone": "timezone",
    "time zone": "timezone",
    "last collection time": "last_collection_time",
    "usage collection time": "last_collection_time",
    "license expiry": "license_expiry",
    "license expiration": "license_expiry",
    "last generation time": "last_generation_time",
    "license generation time": "last_generation_time",
    "last application time": "last_application_time",
    "license application time": "last_application_time",
    "customer id": "customer_id",
    "commcell id": "commcell_id",
    "registration code": "masked_registration_code",
    "version": "commcell_version",
}


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ").strip()).lower()


def clean_text(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def parse_number(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace(",", "")
    try:
        return int(float(normalized))
    except ValueError:
        return None


def maybe_unit_from_value(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"[A-Za-z%]+$", text)
    return match.group(0) if match else None


def split_metadata_label_value(text: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*([^:]+):\s*(.+?)\s*$", text)
    if not match:
        return None
    label = normalize_header(match.group(1))
    value = clean_text(match.group(2))
    if not label or not value:
        return None
    return label, value


def extract_metadata_from_row(values: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    non_empty = [clean_text(value) for value in values if clean_text(value)]
    if not non_empty:
        return metadata
    if len(non_empty) >= 2:
        first = normalize_header(non_empty[0])
        if first in METADATA_LABELS:
            metadata[METADATA_LABELS[first]] = _metadata_value(first, non_empty[1])
            return metadata
    for value in non_empty:
        pair = split_metadata_label_value(value)
        if pair is None:
            continue
        label, parsed_value = pair
        if label in METADATA_LABELS:
            metadata[METADATA_LABELS[label]] = _metadata_value(label, parsed_value)
    return metadata


def _metadata_value(label: str, value: str) -> str:
    if label == "registration code":
        return mask_registration_code(value) or ""
    return value


def classify_header(values: list[str]) -> str | None:
    normalized = tuple(normalize_header(value) for value in values if clean_text(value))
    if normalized[: len(OTHER_LICENSE_HEADERS)] == OTHER_LICENSE_HEADERS:
        return "other"
    if normalized[: len(AGENT_FEATURE_HEADERS)] == AGENT_FEATURE_HEADERS:
        return "agent"
    if _looks_like_summary_header(normalized):
        return "summary"
    return None


def _looks_like_summary_header(values: tuple[str, ...]) -> bool:
    if len(values) < 4:
        return False
    if not values[0].startswith(SUMMARY_HEADER_REQUIRED_PREFIXES[0]):
        return False
    if not values[1].startswith(SUMMARY_HEADER_REQUIRED_PREFIXES[1]):
        return False
    if not any(value.startswith(SUMMARY_HEADER_REQUIRED_PREFIXES[2]) for value in values[2:]):
        return False
    return "used %" in values or "summary" in values


def normalize_other_license_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_available = clean_text(record.get("Available Total"))
    raw_used = clean_text(record.get("Used"))
    return {
        "license": clean_text(record.get("License")),
        "available_total": parse_number(raw_available),
        "used": parse_number(raw_used),
        "unit": maybe_unit_from_value(raw_available) or maybe_unit_from_value(raw_used),
        "raw_available_total": raw_available or None,
        "raw_used": raw_used or None,
        "raw_fields": dict(record),
    }


def normalize_agent_feature_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "license": clean_text(record.get("License")),
        "permanent_total": parse_number(record.get("Permanent Total")),
        "permanent_used": parse_number(record.get("Permanent Used")),
        "term_total": parse_number(record.get("Term Total")),
        "term_used": parse_number(record.get("Term Used")),
        "client": clean_text(record.get("Client")) or None,
        "agent": clean_text(record.get("Agent")) or None,
        "install_date": clean_text(record.get("Install Date")) or None,
        "raw_fields": dict(record),
    }


def normalize_workload_summary_record(record: dict[str, Any]) -> dict[str, Any]:
    license_name = clean_text(record.get("License"))
    if not license_name:
        return {}
    return {
        "license": license_name,
        "entitlement_value": _first_present_text(
            record,
            (
                "Available Total",
                "Available Total (TB)",
                "Available Total (instances)",
                "Available Total (users)",
                "Available Total (VMs)",
                "Permanent Purchased",
                "Permanent Purchased (TB)",
                "Permanent Purchased (instances)",
                "Permanent Purchased (users)",
                "Term Purchased",
                "Term Purchased (TB)",
                "Term Purchased (instances)",
                "Term Purchased (users)",
            ),
        ),
        "used": _first_present_text(
            record,
            (
                "Used",
                "Used (TB)",
                "Used (instances)",
                "Used (users)",
                "Used (VMs)",
            ),
        ),
        "usage_percent": _first_present_text(record, ("Used %",)),
        "status": _first_present_text(record, ("Summary",)),
        "raw_fields": dict(record),
    }


def _first_present_text(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = clean_text(record.get(key))
        if value:
            return value
    return None


def mask_registration_code(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"
