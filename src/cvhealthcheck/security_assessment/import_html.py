from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from .normalize import build_security_assessment_artifact, write_security_assessment_artifact

EXPECTED_HEADERS = ["parameter", "status", "remarks", "action"]
IGNORED_SECTION_HEADINGS = {"security assessment", "detailed checks"}


def import_security_assessment_html(
    file_path: str | Path,
    *,
    write_artifact: bool = True,
) -> dict[str, Any]:
    path = Path(file_path)
    html_text = path.read_text(encoding="utf-8")
    artifact = parse_security_assessment_html(html_text, source_file=str(path))
    if write_artifact:
        artifact["artifact_paths"] = write_security_assessment_artifact(artifact)
    return artifact


def parse_security_assessment_html(
    html_text: str,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    for node in soup.find_all(["script", "style"]):
        node.decompose()

    generated_on = _extract_generated_on(soup.get_text("\n", strip=True))
    findings: list[dict[str, Any]] = []
    seen_findings: set[tuple[str, str, str, str, str]] = set()
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        if headers != EXPECTED_HEADERS:
            continue
        section = _infer_section_name(table)
        tbody = table.find("tbody")
        if tbody is None:
            continue
        for row in tbody.find_all("tr", recursive=False):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 4:
                continue
            values = [_cell_text(cell) for cell in cells]
            if not _is_finding_row(values):
                continue
            finding_key = (section, values[0], values[1], values[2], values[3])
            if finding_key in seen_findings:
                continue
            seen_findings.add(finding_key)
            findings.append(
                {
                    "section": section,
                    "parameter": values[0],
                    "status": values[1],
                    "remarks": values[2],
                    "action": values[3],
                }
            )

    return build_security_assessment_artifact(
        findings,
        source_type="html",
        source_file=source_file,
        generated_on=generated_on,
        source={"title": _document_title(soup)},
    )


def _document_title(soup: BeautifulSoup) -> str:
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    return title or "Security Assessment"


def _extract_generated_on(text: str) -> str | None:
    match = re.search(r"Generated on:\s*(.+)", text)
    if not match:
        return None
    return match.group(1).splitlines()[0].strip() or None


def _table_headers(table: Tag) -> list[str]:
    thead = table.find("thead")
    if thead is None:
        return []
    header_row = thead.find("tr", recursive=False)
    if header_row is None:
        return []
    cells = header_row.find_all(["th", "td"], recursive=False)
    if len(cells) != 4:
        return []
    return [_cell_text(cell).lower() for cell in cells]


def _infer_section_name(table: Tag) -> str:
    for node in table.find_all_previous(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = _cell_text(node)
        if not text:
            continue
        lowered = text.lower()
        if lowered in IGNORED_SECTION_HEADINGS or text.startswith("Generated on:"):
            continue
        return text
    return "Other"


def _cell_text(cell: Tag) -> str:
    text = cell.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _is_finding_row(values: list[str]) -> bool:
    if len(values) != 4:
        return False
    lowered = [value.lower() for value in values]
    if lowered == EXPECTED_HEADERS:
        return False
    parameter, status, remarks, action = values
    if not parameter or not status:
        return False
    if "entries" in parameter.lower() and not remarks and not action:
        return False
    return True
