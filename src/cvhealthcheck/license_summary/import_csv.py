from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from .artifact import build_license_summary_artifact, write_license_summary_artifact
from .normalize import (
    AGENT_FEATURE_SECTION,
    OTHER_LICENSE_SECTION,
    classify_header,
    clean_text,
    extract_metadata_from_row,
    normalize_agent_feature_record,
    normalize_other_license_record,
)


def import_license_summary_csv(
    file_path: str | Path,
    *,
    write_artifact: bool = True,
) -> dict[str, Any]:
    path = Path(file_path)
    artifact = parse_license_summary_csv(
        path.read_text(encoding="utf-8-sig"),
        source_file=str(path),
    )
    if write_artifact:
        artifact["artifact_paths"] = write_license_summary_artifact(artifact)
    return artifact


def parse_license_summary_csv(
    csv_text: str,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    reader = csv.reader(StringIO(csv_text))
    return _artifact_from_rows(
        [[value.replace("\r\n", "\n").replace("\r", "\n") for value in row] for row in reader],
        source_type="csv",
        source_file=source_file,
    )


def _artifact_from_rows(
    rows: list[list[str]],
    *,
    source_type: str,
    source_file: str | None,
) -> dict[str, Any]:
    title: str | None = None
    generated_on: str | None = None
    metadata: dict[str, Any] = {}
    other_licenses: list[dict[str, Any]] = []
    agent_feature_licenses: list[dict[str, Any]] = []
    active_table: str | None = None
    active_headers: list[str] = []

    for row in rows:
        trimmed = [clean_text(value) for value in row]
        non_empty = [value for value in trimmed if value]
        if not non_empty:
            active_table = None
            active_headers = []
            continue

        joined = ", ".join(non_empty)
        lowered_joined = joined.lower()
        if title is None and lowered_joined == "license summary":
            title = joined
            active_table = None
            active_headers = []
            continue
        if lowered_joined.startswith("generated on:"):
            generated_on = joined.split(":", 1)[1].strip() or None
            active_table = None
            active_headers = []
            continue
        if len(non_empty) == 1 and non_empty[0] in {OTHER_LICENSE_SECTION, AGENT_FEATURE_SECTION}:
            active_table = None
            active_headers = []
            continue

        metadata.update(extract_metadata_from_row(non_empty))
        table_kind = classify_header(non_empty)
        if table_kind is not None:
            active_table = table_kind
            active_headers = non_empty
            continue

        if active_table is None or not active_headers:
            continue

        record = {
            header: trimmed[index] if index < len(trimmed) else ""
            for index, header in enumerate(active_headers)
        }
        if active_table == "other":
            other_licenses.append(normalize_other_license_record(record))
        elif active_table == "agent":
            agent_feature_licenses.append(normalize_agent_feature_record(record))

    return build_license_summary_artifact(
        source_type=source_type,
        source_file=source_file,
        generated_on=generated_on,
        source={"title": title or "License summary"},
        metadata=metadata,
        other_licenses=other_licenses,
        agent_feature_licenses=agent_feature_licenses,
    )
