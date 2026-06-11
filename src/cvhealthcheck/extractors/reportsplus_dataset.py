"""
cvhealthcheck.extractors.reportsplus_dataset
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The extractor for the directly-addressed Reports Plus dataset source
(``reportsplus_dataset``, ADR 0014).

Unlike the ``rest`` source (ADR 0003: ``report_id`` + ``dataset_name``
resolved through a live report-definition walk), this source declares the
dataset address itself in the binding's ``recognition_hints.dataset_address``
— a bare dataset GUID (standalone datasets) or ``{reportGuid}:{entryGuid}``
(report-bound datasets). Every section issues its own GET against that one
dataset with its own ``fields`` / ``orderby`` / ``limit`` / ``parameters``,
so sections are different projections/queries of the same dataset.

Declared ``parameters`` keys are the dataset's bare declared parameter names;
they are encoded to the ``parameter.<name>`` / repeated ``parameter.<name>[]``
query forms here. Because the dataset engine **silently ignores unknown
parameter names** (gate finding 3, ``docs/research/adr0014-gate-findings.md``),
the extractor first reads the dataset's declared parameters from the metadata
endpoint and fails the whole collection loudly on any undeclared name — a typo
must not collect wrong data successfully.

The result ends at ``ExtractionResult`` and feeds the unchanged
``result_to_artifact`` → ``save_artifact`` tail (ADR 0006 D1/D4.1). The
artifact source type maps to ``SourceType.rest`` — the extraction type carries
the addressing grammar; the artifact source type carries the transport
(ADR 0014 resolved question).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from cvhealthcheck.db.rule_overrides import load_section_overrides
from cvhealthcheck.db.rules import (
    load_rules_registry,
    load_subject_row_rules,
    load_subject_section_scope,
)
from cvhealthcheck.db.section_types import (
    UnsupportedSectionTypeError,
    validate_section_type,
)
from cvhealthcheck.extractors.conformance import check_conformance
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.rest import shape_dataset_rows
from cvhealthcheck.extractors.rp_dataset_address import (
    REPORTSPLUS_DATASET_SOURCE_TYPE,
    AddressPolicyError,
    ParameterPolicyError,
    encode_dataset_parameters,
    validate_rp_dataset_address,
)

__all__ = ["ReportsPlusDatasetExtractor", "REPORTSPLUS_DATASET_SOURCE_TYPE"]


class ReportsPlusDatasetExtractor:
    """Collects a subject's sections from one directly-addressed RP dataset.

    ``session`` is duck-typed (``fetch_dataset`` + ``get_dataset_metadata``) —
    the live path passes a ``CommvaultSession``; tests pass a fake.
    """

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        session: Any,
        customer_id: str = "default",
        project_id: str = "default",
    ) -> None:
        self._db = db_conn
        self._session = session
        self._customer_id = customer_id
        self._project_id = project_id

    def extract(self, subject_id: str, version: int = 1) -> ExtractionResult:
        result = ExtractionResult(
            subject_id=subject_id, source_type=REPORTSPLUS_DATASET_SOURCE_TYPE
        )
        result.rules_registry = load_rules_registry(self._db)
        result.section_row_rules = load_subject_row_rules(self._db, subject_id, version)
        result.section_scope = load_subject_section_scope(self._db, subject_id, version)
        result.section_overrides = load_section_overrides(
            self._db, self._customer_id, self._project_id, subject_id, version
        )

        instructions = self._load_section_instructions(subject_id, version)
        if not instructions:
            result.errors.append(
                f"No reportsplus_dataset extraction instructions found for "
                f"{subject_id} v{version}"
            )
            return result

        for instr in instructions:
            try:
                validate_section_type(
                    instr["section_type"],
                    subject_id=subject_id,
                    section_id=instr["section_id"],
                )
            except UnsupportedSectionTypeError as exc:
                result.errors.append(str(exc))
                return result

        # Re-validated at collect as defence-in-depth (already validated at
        # persist); a missing/invalid address is a seeding error, loud.
        try:
            address = self._resolve_address(subject_id, version)
        except AddressPolicyError as exc:
            result.errors.append(
                f"Invalid Reports Plus dataset address for {subject_id} "
                f"v{version}: {exc}"
            )
            return result

        # Gate finding 3: unknown parameter names are silently ignored by the
        # data endpoint, so any declared name is checked against the dataset's
        # declared parameters BEFORE collecting. Fail-whole: collecting with an
        # unvalidatable or undeclared parameter would write a wrong artifact.
        error = self._validate_parameter_names(address, instructions)
        if error:
            result.errors.append(error)
            return result

        for instr in instructions:
            section_id = instr["section_id"]
            section_title = instr.get("title", section_id)
            extraction = instr.get("extraction_instructions") or {}

            try:
                encoded = encode_dataset_parameters(extraction.get("parameters"))
            except ParameterPolicyError as exc:
                result.errors.append(f"Section '{section_id}': {exc}")
                return result

            fields: list[str] = extraction.get("fields") or []
            try:
                raw_rows = self._session.fetch_dataset(
                    address,
                    fields=fields or None,
                    orderby=extraction.get("orderby"),
                    limit=extraction.get("limit"),
                    parameters=encoded or None,
                )
            except Exception as exc:
                # Fail-whole: abort on first section error so we don't write a
                # half-collected artifact (same discipline as the rest path).
                result.errors.append(
                    f"Section '{section_id}': fetch_dataset({address}) failed: {exc}"
                )
                return result

            rows = shape_dataset_rows(raw_rows, extraction)

            failure = check_conformance(rows, extraction.get("conformance"))
            if failure is not None:
                result.section_failures[section_id] = failure
                result.section_titles[section_id] = section_title
                continue

            output_as = extraction.get("output_as", "table")
            if output_as == "metric":
                result.section_metric_specs[section_id] = extraction.get("metric", {})
            elif output_as == "chart":
                result.section_chart_specs[section_id] = extraction.get("chart", {})
            elif output_as == "card":
                result.section_card_specs[section_id] = extraction.get("card", {})
            elif output_as == "table":
                result.section_table_specs[section_id] = extraction.get("table", {})

            result.sections[section_id] = rows
            result.section_output_types[section_id] = output_as
            result.section_titles[section_id] = section_title

        return result

    def _resolve_address(self, subject_id: str, version: int) -> str:
        """The dataset address this subject's RP-dataset source collects from.

        Read from the ``reportsplus_dataset`` row's
        ``recognition_hints.dataset_address``. No default — raises
        :class:`AddressPolicyError` when missing or out of grammar."""
        row = self._db.execute(
            "SELECT recognition_hints FROM subject_sources"
            " WHERE subject_id = ? AND subject_version = ? AND source_type = ?",
            (subject_id, version, REPORTSPLUS_DATASET_SOURCE_TYPE),
        ).fetchone()
        address = None
        if row is not None and row["recognition_hints"]:
            try:
                hints = json.loads(row["recognition_hints"])
            except (json.JSONDecodeError, TypeError):
                hints = {}
            if isinstance(hints, dict):
                address = hints.get("dataset_address")
        return validate_rp_dataset_address(address)

    def _validate_parameter_names(
        self, address: str, instructions: list[dict[str, Any]]
    ) -> str | None:
        """Check every declared parameter name against the dataset's declared
        ``GetOperation.parameters``. Returns an error string (the caller fails
        the whole extract) or None. Skips the metadata GET entirely when no
        section declares parameters."""
        declared_by_section: dict[str, list[str]] = {}
        for instr in instructions:
            params = (instr.get("extraction_instructions") or {}).get("parameters")
            if isinstance(params, dict) and params:
                declared_by_section[instr["section_id"]] = list(params)
        if not declared_by_section:
            return None

        try:
            metadata = self._session.get_dataset_metadata(address)
        except Exception as exc:
            return (
                f"could not read dataset metadata for {address} to validate "
                f"parameter names (the engine silently ignores unknown names, "
                f"so collecting unvalidated would risk wrong data): {exc}"
            )

        known = {
            p.get("name")
            for p in ((metadata.get("GetOperation") or {}).get("parameters") or [])
            if isinstance(p, dict)
        }
        unknown = {
            section_id: sorted(set(names) - known)
            for section_id, names in declared_by_section.items()
            if set(names) - known
        }
        if unknown:
            detail = "; ".join(
                f"{sid}: {', '.join(names)}" for sid, names in sorted(unknown.items())
            )
            return (
                f"parameter name(s) not declared by dataset {address} "
                f"(declared: {', '.join(sorted(n for n in known if n))}) — {detail}"
            )
        return None

    def _load_section_instructions(
        self, subject_id: str, version: int
    ) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT sss.section_id,
                   sss.extraction_instructions,
                   ss.section_type,
                   ss.title
            FROM subject_section_sources sss
            JOIN subject_sources src ON src.id = sss.source_id
            JOIN subject_sections ss
                ON ss.subject_id      = src.subject_id
               AND ss.subject_version  = src.subject_version
               AND ss.section_id      = sss.section_id
            WHERE src.subject_id      = ?
              AND src.subject_version  = ?
              AND src.source_type     = ?
            ORDER BY ss.sort_order
            """,
            (subject_id, version, REPORTSPLUS_DATASET_SOURCE_TYPE),
        ).fetchall()

        result = []
        for row in rows:
            try:
                extraction = (
                    json.loads(row["extraction_instructions"])
                    if row["extraction_instructions"]
                    else {}
                )
            except (json.JSONDecodeError, TypeError):
                extraction = {}
            result.append({
                "section_id": row["section_id"],
                "title": row["title"],
                "section_type": row["section_type"],
                "extraction_instructions": extraction,
            })
        return result
