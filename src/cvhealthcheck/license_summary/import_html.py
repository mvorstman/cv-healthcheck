from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from .artifact import build_license_summary_artifact, write_license_summary_artifact
from .normalize import (
    AGENT_FEATURE_SECTION,
    OTHER_LICENSE_SECTION,
    SUMMARY_SECTION_NAMES,
    classify_header,
    clean_text,
    extract_metadata_from_row,
    normalize_agent_feature_record,
    normalize_header,
    normalize_other_license_record,
    normalize_workload_summary_record,
)


_KNOWN_SECTION_TITLES = (
    SUMMARY_SECTION_NAMES | {OTHER_LICENSE_SECTION, AGENT_FEATURE_SECTION}
)
_TITLE_BEARING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span"}


def import_license_summary_html(
    file_path: str | Path,
    *,
    write_artifact: bool = True,
) -> dict[str, Any]:
    path = Path(file_path)
    artifact = parse_license_summary_html(
        path.read_text(encoding="utf-8"),
        source_file=str(path),
    )
    if write_artifact:
        artifact["artifact_paths"] = write_license_summary_artifact(artifact)
    return artifact


def parse_license_summary_html(
    html_text: str,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(["script", "style"]):
        node.decompose()

    metadata: dict[str, Any] = {}
    all_text = soup.get_text("\n", strip=True)
    generated_on = _extract_generated_on(all_text)
    title = _document_title(soup)
    for line in all_text.splitlines():
        metadata.update(extract_metadata_from_row([line]))

    other_licenses: list[dict[str, Any]] = []
    agent_feature_licenses: list[dict[str, Any]] = []
    workload_summary_sections: list[dict[str, Any]] = []
    summary_sections_by_name: dict[str, list[dict[str, Any]]] = {}
    claimed_section_names: set[str] = set()
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        table_kind = classify_header(headers)
        if table_kind is None:
            continue
        section_name = _table_section_name(table, claimed=claimed_section_names)
        if section_name is not None:
            claimed_section_names.add(section_name)
        tbody = table.find("tbody") or table
        for row in tbody.find_all("tr", recursive=False):
            cells = row.find_all(["td", "th"], recursive=False)
            values = [_cell_text(cell) for cell in cells]
            if not any(values):
                continue
            if tuple(normalize_header(value) for value in values) == tuple(
                normalize_header(value) for value in headers
            ):
                continue
            record = {
                header: values[index] if index < len(values) else ""
                for index, header in enumerate(headers)
            }
            # When the resolved section title identifies a workload-summary
            # section, route by section name rather than header shape. The
            # header-only classifier cannot tell "Virtualization Licenses"
            # apart from "Other Licenses" when both tables omit unit
            # qualifiers (bare "License"/"Available Total"/"Used"/"Summary").
            if section_name in SUMMARY_SECTION_NAMES:
                normalized = normalize_workload_summary_record(record)
                if normalized:
                    summary_sections_by_name.setdefault(section_name, []).append(normalized)
            elif table_kind == "other":
                other_licenses.append(normalize_other_license_record(record))
            elif table_kind == "agent":
                agent_feature_licenses.append(normalize_agent_feature_record(record))

    for section_name, section_rows in summary_sections_by_name.items():
        workload_summary_sections.append(
            {"section_name": section_name, "rows": section_rows}
        )

    return build_license_summary_artifact(
        source_type="html",
        source_file=source_file,
        generated_on=generated_on,
        source={"title": title},
        metadata=metadata,
        other_licenses=other_licenses,
        agent_feature_licenses=agent_feature_licenses,
        workload_summary_sections=workload_summary_sections,
    )


def _document_title(soup: BeautifulSoup) -> str:
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    return title or "License summary"


def _extract_generated_on(text: str) -> str | None:
    match = re.search(r"Generated on:\s*(.+)", text)
    if not match:
        return None
    return match.group(1).splitlines()[0].strip() or None


def _table_headers(table: Tag) -> list[str]:
    thead = table.find("thead")
    if thead is not None:
        header_row = thead.find("tr", recursive=False)
        if header_row is not None:
            return [_cell_text(cell) for cell in header_row.find_all(["th", "td"], recursive=False)]
    first_row = table.find("tr")
    if first_row is None:
        return []
    return [_cell_text(cell) for cell in first_row.find_all(["th", "td"], recursive=False)]


def _table_section_name(
    table: Tag,
    *,
    claimed: set[str] | None = None,
) -> str | None:
    # Walk DOM order backward from the table and return the first
    # element whose *direct* text (string children, not recursive
    # get_text()) matches a known section title. Commvault HTML exports
    # wrap section titles in <span class="component-title-text"> inside
    # nested <div> wrappers — there are no h2/h3 headings — so the
    # previous heuristic of taking the nearest preceding div and
    # dumping get_text() returned the table's own concatenated text.
    #
    # Using direct text means a wrapper div containing further markup
    # (e.g. the table itself) won't accidentally match — only an
    # element whose immediate text reads exactly "Capacity Licenses"
    # (etc.) is treated as the title.
    #
    # The `claimed` set guards against cross-wiring: once a title has
    # been attributed to one table, a later table walking back through
    # the DOM will skip past it rather than silently inheriting the
    # prior table's section.
    claimed = claimed or set()
    for prev in table.find_all_previous():
        if prev.name not in _TITLE_BEARING_TAGS:
            continue
        direct_text = clean_text(
            "".join(child for child in prev.children if isinstance(child, str))
        )
        if direct_text and direct_text in _KNOWN_SECTION_TITLES and direct_text not in claimed:
            return direct_text
    return None


def _cell_text(cell: Tag) -> str:
    text = cell.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
