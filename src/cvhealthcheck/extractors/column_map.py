"""Shared column-map resolution for the CSV and HTML extractors.

ADR-0016 transform layer, slice 1 — `source` coalesce. A recipe column's
``source`` may be:

  - a **string** → current 1:1 behavior, unchanged; or
  - a **list[string]** → coalesce / first-present: among the candidate columns,
    in order, use the first that is present in the header AND non-empty in the
    row. No merge, no concatenate, no arithmetic across candidates (ADR-0016 D4).
    A missing candidate is skipped; none present-and-usable → null.

CSV and HTML import the SAME resolver here so coalesce behaves identically across
both formats (License Summary is imported as either) — the parity the harness
depends on. The two extractors differ only in how they read a row into a list of
cell-text strings; everything below is shared.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


class UnknownTransformError(ValueError):
    """Raised when a recipe names a transform absent from the closed registry.

    Interim enforcement: unknown transform raises at application time now; the
    ADR-0015 compile gate will reject at publish later (ADR-0016 Compile-Validated
    invariant — held even before the gate exists)."""


class SensitiveFieldError(ValueError):
    """Raised when a sensitive-tagged canonical field omits its mandatory
    transform (ADR-0016 Security-by-Construction).

    Interim enforcement: raised eagerly at recipe-application time (resolve_
    columns) now; the ADR-0015 compile gate will reject at publish later — same
    pattern as the unknown-transform check. A masking transform cannot be omitted
    by author oversight."""


@dataclass
class ResolvedColumn:
    canonical: str
    col_type: str
    candidates: list[tuple[str, int]]   # (source-name, header index), in priority order
    coalesce: bool
    transforms: list[str] = field(default_factory=list)


def entry_sources(col: dict) -> list[str]:
    """The candidate source column names for a column_map entry — a 1-element
    list for a string source, the list itself for a coalesce source."""
    src = col.get("source", "")
    return [str(x) for x in (src if isinstance(src, list) else [src])]


def header_has_all(column_map: list[dict], cells_lower: set[str]) -> bool:
    """A header row matches when EVERY column has at least one candidate source
    present in the row. For string sources this is the old all-sources-present
    rule; for coalesce sources, any one present candidate satisfies the column."""
    return bool(column_map) and all(
        any(s.lower() in cells_lower for s in entry_sources(col)) for col in column_map
    )


def resolve_columns(
    column_map: list[dict],
    header_map: dict[str, int],
    *,
    section_id: str,
    warnings: list[str],
    fuzzy: bool = False,
) -> list[ResolvedColumn]:
    """Resolve each column_map entry's source(s) to header indices, in order.

    String source → a single-candidate ResolvedColumn (coalesce=False), exactly
    as before. List source → a ResolvedColumn (coalesce=True) holding the present
    candidates in priority order (a coalesce entry with zero present candidates is
    kept so the row emits the canonical field as null)."""
    resolved: list[ResolvedColumn] = []
    for col in column_map:
        is_coalesce = isinstance(col.get("source", ""), list)
        sources = entry_sources(col)
        col_type = col.get("type", "string")
        canonical = col.get("canonical") or (sources[0] if sources else "")
        col_fuzzy = fuzzy or bool(col.get("fuzzy_match"))

        # ADR-0016 slice 2: validate the transform chain eagerly (once per
        # column, before row extraction) — unknown name raises here, regardless
        # of whether the column's source is present.
        transforms = list(col.get("transforms", []) or [])
        for name in transforms:
            if name not in TRANSFORMS:
                raise UnknownTransformError(
                    f"Unknown transform '{name}' for field '{canonical}' in section "
                    f"'{section_id}'. Known transforms: {sorted(TRANSFORMS)}."
                )

        # ADR-0016 Security-by-Construction: a sensitive field must carry its
        # mandatory transform(s). A recipe that does not declare the sensitive
        # field at all is fine (nothing to protect); one that DOES must include
        # the specific required transform — not merely "some transform".
        required = SENSITIVE_FIELD_REQUIREMENTS.get(canonical)
        if required:
            missing = [t for t in required if t not in transforms]
            if missing:
                raise SensitiveFieldError(
                    f"Sensitive field '{canonical}' in section '{section_id}' must "
                    f"apply {required} but is missing {missing}. A masking transform "
                    f"cannot be omitted (interim apply-time enforcement; the ADR-0015 "
                    f"compile gate will reject at publish later)."
                )

        candidates: list[tuple[str, int]] = []
        for src in sources:
            idx = header_map.get(src.lower())
            if idx is None and col_fuzzy and src.startswith("None_"):
                stripped = src[5:]
                idx = header_map.get(stripped.lower())
                if idx is not None:
                    warnings.append(
                        f"Fuzzy-matched '{src}' → '{stripped}' for section '{section_id}'"
                    )
            if idx is not None:
                candidates.append((src, idx))

        if not candidates:
            if is_coalesce:
                warnings.append(
                    f"No coalesce candidate for '{canonical}' found among "
                    f"{sources} for section '{section_id}'"
                )
                resolved.append(ResolvedColumn(canonical, col_type, [], True, transforms))
            else:
                warnings.append(
                    f"Column '{sources[0]}' not found in headers for section '{section_id}'"
                )
            continue
        resolved.append(
            ResolvedColumn(canonical, col_type, candidates, is_coalesce, transforms)
        )
    return resolved


def coerce(
    raw: Any, col_type: str, null_values: list[str], col_name: str, section_name: str
) -> tuple[Any, str | None]:
    stripped = str(raw).strip()
    if stripped in null_values:
        return None, None
    if col_type == "string":
        return stripped, None
    if col_type == "integer":
        try:
            return int(stripped), None
        except (ValueError, TypeError):
            return None, (
                f"Could not coerce '{stripped}' to integer"
                f" (col='{col_name}', section='{section_name}')"
            )
    if col_type == "float":
        try:
            return float(stripped), None
        except (ValueError, TypeError):
            return None, (
                f"Could not coerce '{stripped}' to float"
                f" (col='{col_name}', section='{section_name}')"
            )
    return stripped, None


# ---------------------------------------------------------------------------
# Transform registry (ADR-0016 slice 2) — closed, platform-owned.
#
# A recipe field may carry ``transforms: [name, ...]``, applied in order to the
# (coalesced) source value. Names resolve ONLY against this registry; an unknown
# name is an error. Interim enforcement: unknown transform raises at application
# time now (resolve_columns / apply_transforms); the ADR-0015 compile gate will
# reject at publish later (ADR-0016 Compile-Validated invariant — held even
# before the gate exists). Slice 2 ships the four pure coercions only — mask
# (slice 3), number_with_unit (slice 4), to_float_percent, metadata_pairs and
# computed sections are NOT here.
# ---------------------------------------------------------------------------

def _t_trim(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _t_null_if_empty(value: Any) -> Any:
    if value is None:
        return None
    return None if str(value).strip() == "" else value


def _t_to_integer(value: Any) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _t_to_float(value: Any) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


# A registration code is a dash-separated run of alphanumeric (or already-masked
# ``*``) segments — "XXXX-XXXX-XXXX-1234" / "****-****-****-1234". The ``*`` is
# allowed so masking is idempotent (re-masking a masked value matches).
_REG_CODE_SHAPE = re.compile(r"^[A-Za-z0-9*]+(?:-[A-Za-z0-9*]+)+$")


def _t_mask_registration_code(value: Any) -> Any:
    """Mask a registration code, revealing only the trailing identifier segment:
    ``XXXX-XXXX-XXXX-1234`` → ``****-****-****-1234`` (ADR-0016 slice 3).

    FAIL CLOSED — the security property: any input this cannot confidently mask
    (null, empty, or a shape that is not the dash-segmented form above) returns
    None. A raw registration code must NOT survive this transform under ANY input,
    anticipated or not — so the only outcomes are a correctly-masked value or
    None, never the raw. Idempotent: re-masking a masked value yields the same
    masked value (``*`` segments stay ``*``)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or not _REG_CODE_SHAPE.match(s):
        return None
    segments = s.split("-")
    masked = ["*" * len(seg) for seg in segments[:-1]] + [segments[-1]]
    return "-".join(masked)


TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    "trim": _t_trim,
    "null_if_empty": _t_null_if_empty,
    "to_integer": _t_to_integer,
    "to_float": _t_to_float,
    "mask_registration_code": _t_mask_registration_code,
}

# ADR-0016 Security-by-Construction: a sensitive-tagged canonical field MUST carry
# the specific required transform(s) in its chain. Closed, platform-owned —
# extended only by ADR amendment. The compile gate will enforce at publish later;
# resolve_columns enforces eagerly at apply-time now.
SENSITIVE_FIELD_REQUIREMENTS: dict[str, list[str]] = {
    "registration_code": ["mask_registration_code"],
}


def apply_transforms(names: list[str], value: Any) -> Any:
    """Apply a transform chain (by name, in order) to a value. Unknown name →
    UnknownTransformError (interim enforcement; the compile gate catches it at
    publish later)."""
    result = value
    for name in names:
        fn = TRANSFORMS.get(name)
        if fn is None:
            raise UnknownTransformError(
                f"Unknown transform '{name}'. Known transforms: {sorted(TRANSFORMS)}."
            )
        result = fn(result)
    return result


def _shape_value(
    raw: Any,
    rc: ResolvedColumn,
    null_values: list[str],
    source_name: str,
    section_id: str,
    warnings: list[str],
) -> Any:
    """Shape a selected raw cell into the canonical value: the transform chain
    when the column declares one, else the legacy ``type`` coercion (unchanged)."""
    if rc.transforms:
        return apply_transforms(rc.transforms, raw)
    value, warn = coerce(raw, rc.col_type, null_values, source_name, section_id)
    if warn:
        warnings.append(warn)
    return value


def extract_row(
    cell_texts: list[str],
    resolved: list[ResolvedColumn],
    null_values: list[str],
    section_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build one canonical row from a list of cell-text strings. For a coalesce
    column, walk its candidates in order and take the first present-and-non-empty
    (and non-null) cell; if none qualifies the canonical field is null. For a
    string column, behavior is identical to the pre-coalesce extractor."""
    row: dict[str, Any] = {}
    for rc in resolved:
        if rc.coalesce:
            chosen: tuple[str, str] | None = None
            for src, idx in rc.candidates:
                raw = cell_texts[idx] if idx < len(cell_texts) else ""
                stripped = raw.strip()
                if stripped and stripped not in null_values:
                    chosen = (raw, src)
                    break
            if chosen is None:
                row[rc.canonical] = None
            else:
                row[rc.canonical] = _shape_value(
                    chosen[0], rc, null_values, chosen[1], section_id, warnings
                )
        else:
            src, idx = rc.candidates[0]
            raw = cell_texts[idx] if idx < len(cell_texts) else ""
            row[rc.canonical] = _shape_value(raw, rc, null_values, src, section_id, warnings)
    return row
