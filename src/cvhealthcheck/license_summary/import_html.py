from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from .artifact import build_license_summary_artifact, write_license_summary_artifact
from .normalize import (
    classify_header,
    clean_text,
    extract_metadata_from_row,
    normalize_agent_feature_record,
    normalize_header,
    normalize_other_license_record,
)


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
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        table_kind = classify_header(headers)
        if table_kind is None:
            continue
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
            if table_kind == "other":
                other_licenses.append(normalize_other_license_record(record))
            else:
                agent_feature_licenses.append(normalize_agent_feature_record(record))

    return build_license_summary_artifact(
        source_type="html",
        source_file=source_file,
        generated_on=generated_on,
        source={"title": title},
        metadata=metadata,
        other_licenses=other_licenses,
        agent_feature_licenses=agent_feature_licenses,
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


def _cell_text(cell: Tag) -> str:
    text = cell.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
