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

from dataclasses import dataclass
from typing import Any


@dataclass
class ResolvedColumn:
    canonical: str
    col_type: str
    candidates: list[tuple[str, int]]   # (source-name, header index), in priority order
    coalesce: bool


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
                resolved.append(ResolvedColumn(canonical, col_type, [], True))
            else:
                warnings.append(
                    f"Column '{sources[0]}' not found in headers for section '{section_id}'"
                )
            continue
        resolved.append(ResolvedColumn(canonical, col_type, candidates, is_coalesce))
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
                value, warn = coerce(chosen[0], rc.col_type, null_values, chosen[1], section_id)
                if warn:
                    warnings.append(warn)
                row[rc.canonical] = value
        else:
            src, idx = rc.candidates[0]
            raw = cell_texts[idx] if idx < len(cell_texts) else ""
            value, warn = coerce(raw, rc.col_type, null_values, src, section_id)
            if warn:
                warnings.append(warn)
            row[rc.canonical] = value
    return row
