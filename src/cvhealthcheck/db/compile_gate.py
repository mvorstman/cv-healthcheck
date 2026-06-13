"""ADR-0015 compile/publish gate — transform-aware per ADR-0016 D2.

Runs at the publish chokepoint (create_subject_from_proposal) BEFORE any catalog
write: it validates a proposal's recipe and rejects publish (raising
ProposalCompileError with every violation listed) if any check fails. The
rejection happens before the write transaction starts, so a bad proposal never
becomes catalog-live.

This is the PRIMARY enforcement; the interim apply-time raises in
extractors.column_map (UnknownTransformError, SensitiveFieldError,
UnknownComputedTypeError) STAY as defense-in-depth — a recipe that somehow reaches
extraction unvalidated still fails there.

The gate VALIDATES the existing closed model; it does not extend it.

Scope (confirmed from the extractors, not assumed):
  - Checks 1-3 (transform names, sensitive-field transforms, computed types) apply
    to recipes that feed extractors.column_map.resolve_columns / compute_section —
    i.e. the csv and html extractors. REST has its own transform-free
    _apply_column_map; CC / RP / json use neither column_map nor a format dispatch.
  - Check 4 (format ∈ allowed-set) applies per source type; only csv and html have
    a format dispatch, so only they are checked.
"""
from __future__ import annotations

from typing import Any

from cvhealthcheck.extractors.column_map import (
    COMPUTED_TYPES,
    SENSITIVE_FIELD_REQUIREMENTS,
    TRANSFORMS,
)


class ProposalCompileError(ValueError):
    """Publish rejected by the compile gate. Lists every violation; raised before
    any catalog write so the transaction never starts."""


# Allowed section formats per source type (confirmed from csv.py / html.py):
#   csv.py  dispatches single_table (default when absent), multi_section,
#           metadata_pairs, computed.
#   html.py dispatches metadata_pairs and computed; any other value (incl. absent)
#           is the table-via-selector default — named "table" here.
# Only csv and html have a format dispatch; other source types carry no `format`.
_ALLOWED_FORMATS: dict[str, set[str]] = {
    "csv": {"single_table", "multi_section", "metadata_pairs", "computed"},
    "html": {"table", "metadata_pairs", "computed"},
}
_DEFAULT_FORMAT: dict[str, str] = {"csv": "single_table", "html": "table"}
_TRANSFORM_SOURCE_TYPES = ("csv", "html")


def _canonical_of(entry: dict) -> str:
    """The canonical field name for a column_map / label_map entry, resolved the
    same way resolve_columns does (explicit canonical, else the first source)."""
    src = entry.get("source", "")
    sources = src if isinstance(src, list) else [src]
    return entry.get("canonical") or (str(sources[0]) if sources else "")


def _validate_recipe(
    source_type: str, section_id: str, recipe: dict, violations: list[str]
) -> None:
    ctx = f"source '{source_type}', section '{section_id}'"
    fmt = recipe.get("format")

    # Check 4 — format ∈ the allowed set FOR ITS SOURCE TYPE (csv / html only).
    if source_type in _ALLOWED_FORMATS:
        effective = fmt if fmt is not None else _DEFAULT_FORMAT[source_type]
        if effective not in _ALLOWED_FORMATS[source_type]:
            violations.append(
                f"{ctx}: format {effective!r} is not valid for source type "
                f"'{source_type}' (allowed: {sorted(_ALLOWED_FORMATS[source_type])})"
            )

    # Checks 1-3 apply only to the resolve_columns / compute path (csv / html).
    if source_type not in _TRANSFORM_SOURCE_TYPES:
        return

    # Check 3 — computed_type ∈ the closed COMPUTED_TYPES set.
    if fmt == "computed":
        ctype = recipe.get("computed_type")
        if ctype not in COMPUTED_TYPES:
            violations.append(
                f"{ctx}: computed_type {ctype!r} is not valid "
                f"(allowed: {sorted(COMPUTED_TYPES)})"
            )

    # Checks 1 & 2 — transform names + sensitive-field requirements, over BOTH
    # column_map (table formats) and label_map (metadata_pairs) entries.
    entries: list[dict] = []
    for key in ("column_map", "label_map"):
        block = recipe.get(key)
        if isinstance(block, list):
            entries.extend(e for e in block if isinstance(e, dict))

    for entry in entries:
        canonical = _canonical_of(entry)
        transforms = entry.get("transforms") or []
        if not isinstance(transforms, list):
            transforms = []

        # Check 1 — every transform name is in the closed registry.
        for name in transforms:
            if name not in TRANSFORMS:
                violations.append(
                    f"{ctx}, field '{canonical}': unknown transform {name!r} "
                    f"(known: {sorted(TRANSFORMS)})"
                )

        # Check 2 — a sensitive field carries its required transform(s).
        required = SENSITIVE_FIELD_REQUIREMENTS.get(canonical)
        if required:
            missing = [t for t in required if t not in transforms]
            if missing:
                violations.append(
                    f"{ctx}, sensitive field '{canonical}': missing required "
                    f"transform(s) {missing} (must apply {required})"
                )


def compile_validate_proposal(proposal: dict) -> None:
    """Validate every (source_type, section_id) recipe in the proposal. Collects
    ALL violations and raises ONE ProposalCompileError if any are found. A clean
    proposal returns None. Defensive against malformed shapes (non-dict source
    info or recipes are skipped — they are handled elsewhere / are not recipes
    this gate owns)."""
    violations: list[str] = []
    extraction_instructions = proposal.get("extraction_instructions") or {}
    if isinstance(extraction_instructions, dict):
        for source_type, source_info in extraction_instructions.items():
            if not isinstance(source_info, dict):
                continue
            sections = source_info.get("sections") or {}
            if not isinstance(sections, dict):
                continue
            for section_id, recipe in sections.items():
                if isinstance(recipe, dict):
                    _validate_recipe(source_type, section_id, recipe, violations)

    if violations:
        raise ProposalCompileError(
            f"Proposal rejected by the compile gate ({len(violations)} "
            f"violation(s)):\n  - " + "\n  - ".join(violations)
        )
