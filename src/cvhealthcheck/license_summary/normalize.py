from __future__ import annotations

import re
from typing import Any


OTHER_LICENSE_SECTION = "Other Licenses - current usage details"
AGENT_FEATURE_SECTION = "Agent and Feature Licenses - current usage details"

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

METADATA_LABELS = {
    "commcell name": "commcell_name",
    "commcell version": "commcell_version",
    "timezone": "timezone",
    "last collection time": "last_collection_time",
    "license expiry": "license_expiry",
    "last generation time": "last_generation_time",
    "last application time": "last_application_time",
    "customer id": "customer_id",
    "commcell id": "commcell_id",
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
            metadata[METADATA_LABELS[first]] = non_empty[1]
            return metadata
    for value in non_empty:
        pair = split_metadata_label_value(value)
        if pair is None:
            continue
        label, parsed_value = pair
        if label in METADATA_LABELS:
            metadata[METADATA_LABELS[label]] = parsed_value
    return metadata


def classify_header(values: list[str]) -> str | None:
    normalized = tuple(normalize_header(value) for value in values if clean_text(value))
    if normalized[: len(OTHER_LICENSE_HEADERS)] == OTHER_LICENSE_HEADERS:
        return "other"
    if normalized[: len(AGENT_FEATURE_HEADERS)] == AGENT_FEATURE_HEADERS:
        return "agent"
    return None


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
