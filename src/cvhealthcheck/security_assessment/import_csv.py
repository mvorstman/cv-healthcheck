from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from .artifact import build_security_assessment_artifact, write_security_assessment_artifact

EXPECTED_HEADERS = ["Parameter", "Status", "Remarks", "Action"]


def import_security_assessment_csv(
    file_path: str | Path,
    *,
    write_artifact: bool = True,
) -> dict[str, Any]:
    path = Path(file_path)
    csv_text = path.read_text(encoding="utf-8-sig")
    artifact = parse_security_assessment_csv(csv_text, source_file=str(path))
    if write_artifact:
        artifact["artifact_paths"] = write_security_assessment_artifact(artifact)
    return artifact


def parse_security_assessment_csv(
    csv_text: str,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    section = "Other"
    title: str | None = None
    generated_on: str | None = None
    in_table = False

    reader = csv.reader(StringIO(csv_text))
    for row in reader:
        values = [value.replace("\r\n", "\n").replace("\r", "\n") for value in row]
        trimmed = [value.strip() for value in values]
        non_empty = [value for value in trimmed if value]
        joined_non_empty = ", ".join(non_empty)
        if not non_empty:
            continue

        if joined_non_empty == "Security Assessment":
            title = non_empty[0]
            in_table = False
            continue

        if joined_non_empty.startswith("Generated on:"):
            generated_on = joined_non_empty.split(":", 1)[1].strip() or None
            in_table = False
            continue

        if trimmed[:4] == EXPECTED_HEADERS:
            in_table = True
            continue

        if len(non_empty) == 1:
            section = non_empty[0]
            in_table = False
            continue

        if in_table or len(values) >= 4:
            findings.append(
                {
                    "section": section,
                    "parameter": values[0].strip(),
                    "status": values[1].strip() if len(values) > 1 else "",
                    "remarks": values[2].strip() if len(values) > 2 else "",
                    "action": values[3].strip() if len(values) > 3 else "",
                }
            )

    return build_security_assessment_artifact(
        findings,
        source_type="csv",
        source_file=source_file,
        generated_on=generated_on,
        source={"title": title or "Security Assessment"},
    )
