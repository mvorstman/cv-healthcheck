"""
cvhealthcheck.db.section_types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Catalog section_type validation.

The subject_sections table has a schema-level CHECK constraint allowing
section_type IN ('findings','table','metric','chart'). That's the
*structural* set of values the catalog can hold.

The *runtime-supported* set is the subset of those that some code path
actually produces and renders. ADR 0004 grows it phase by phase:
`findings` and `table` (ADR 0003), `metric` (phase 2), and `chart`
(phase 3) are all produced by the catalog-driven extractor + result_to_artifact
and rendered in the workspace. Types modelled but not yet produced/rendered
(e.g. `card`, `multi_section`) stay OUT of the supported set and fail loudly,
so a catalog row can never silently render nothing.

This module pins the runtime-supported set and surfaces a clear error
when a catalog row declares a section_type the runtime cannot honour.
The validation fires at two layers:

- Insert-time, from `create_subject_from_proposal` — catches future AI
  proposals declaring unsupported types.
- Collection-time, from `RESTExtractor._load_section_instructions` —
  catches anyone bypassing insert-time (raw SQL, migrations).

The mismatch is loud and informational, not destructive.
"""
from __future__ import annotations


SUPPORTED_SECTION_TYPES: frozenset[str] = frozenset({"findings", "table", "metric", "chart", "card"})
"""Section types the runtime can honour today.

All five are produced by the catalog-driven extractor + result_to_artifact and
rendered in the workspace: `findings`/`table` (ADR 0003), `metric` (ADR 0004
phase 2), `chart` (phase 3), `card` (phase 4). Section types that are modelled
but not yet produced/rendered (`multi_section`, deferred to a future LS ADR)
are intentionally absent and fail loudly until their phase lands.
"""


class UnsupportedSectionTypeError(ValueError):
    """Raised when a catalog row declares a section_type the runtime cannot
    honour. The error message names the subject, section, declared type,
    and the supported set."""


def validate_section_type(
    section_type: str,
    *,
    subject_id: str,
    section_id: str,
) -> None:
    """Raise UnsupportedSectionTypeError if section_type isn't runtime-supported.

    The runtime-supported set is SUPPORTED_SECTION_TYPES. A section_type
    outside the set (today: only 'chart') means the catalog declares a
    shape the runtime cannot produce — historically this rendered nothing
    silently.

    Called from two layers so the loud-failure path catches both new AI
    proposals (insert-time) and any other catalog write that bypasses
    the proposal flow (collection-time).
    """
    if section_type not in SUPPORTED_SECTION_TYPES:
        raise UnsupportedSectionTypeError(
            f"Subject {subject_id!r} section {section_id!r} declares "
            f"section_type={section_type!r}, which is not yet supported "
            f"by the runtime. Supported types: "
            f"{sorted(SUPPORTED_SECTION_TYPES)}. "
            f"This catalog row is preserved — a later ADR 0004 phase will "
            f"address support for additional section types (e.g. card, "
            f"multi_section)."
        )
