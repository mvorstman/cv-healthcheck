from __future__ import annotations

import html
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse


STATUS_ORDER = ("Critical", "Warning", "Info", "Good")
STATUS_LABELS = {
    "1_Good": "Good",
    "2_Info": "Info",
    "3_Warning": "Warning",
    "4_Critical": "Critical",
}


def checklist_summary(
    datasets: list[dict[str, Any]],
    section_order: list[str],
) -> dict[str, Any]:
    sections = {name: [] for name in section_order}
    for dataset in datasets:
        section = str(dataset.get("dataset_name") or "").strip()
        if section not in sections:
            sections[section or "Other"] = []
        for row in dataset.get("sample_rows") or []:
            check = normalize_check(row, fallback_section=section)
            if check:
                sections[check["section"]].append(check)

    grouped = [
        {"name": section, "checks": checks}
        for section, checks in sections.items()
        if checks
    ]
    checks = [check for group in grouped for check in group["checks"]]
    counters = {status: 0 for status in STATUS_ORDER}
    for check in checks:
        counters[check["status"]] = counters.get(check["status"], 0) + 1

    return {
        "counters": {
            "Critical": counters.get("Critical", 0),
            "Warning": counters.get("Warning", 0),
            "Info": counters.get("Info", 0),
            "Good": counters.get("Good", 0),
            "Total checks": len(checks),
        },
        "highlights": [
            check
            for check in checks
            if check["status"] in ("Critical", "Warning")
        ],
        "sections": grouped,
    }


def normalize_check(row: Any, fallback_section: str = "") -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    parameter = _text(row.get("parameter"))
    if not parameter:
        return None
    status = normalize_status(row.get("status"))
    return {
        "section": _text(row.get("group")) or fallback_section or "Other",
        "parameter": parameter,
        "status": status,
        "remarks": _text(row.get("remarks")),
        "action": _action(row.get("action")),
    }


def normalize_status(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return STATUS_LABELS.get(text, text or "Info")


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    parser = _TextExtractor()
    parser.feed(str(value))
    parser.close()
    return " ".join(html.unescape(parser.text).split())


def _action(value: Any) -> dict[str, str] | None:
    if value in (None, ""):
        return None
    parser = _LinkExtractor()
    parser.feed(str(value))
    parser.close()
    href = html.unescape(parser.href or "").strip()
    label = " ".join(html.unescape(parser.text or "").split())
    if not href or not _safe_href(href):
        return None
    return {"href": href, "label": label or "Open action"}


def _safe_href(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme:
        return parsed.scheme in {"http", "https"}
    return value.startswith(("/", "./", "../"))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(part for part in self.parts if part)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "li"}:
            self.parts.append(" ")


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href: str | None = None
        self.parts: list[str] = []
        self._inside_link = False

    @property
    def text(self) -> str:
        return " ".join(part for part in self.parts if part)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._inside_link = True
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.href = value

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._inside_link = False

    def handle_data(self, data: str) -> None:
        if self._inside_link:
            self.parts.append(data)
