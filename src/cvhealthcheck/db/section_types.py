"""
cvhealthcheck.db.section_types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Catalog section_type validation.

The subject_sections table has a schema-level CHECK constraint allowing
section_type IN ('findings','table','metric','chart'). That's the
*structural* set of values the catalog can hold.

The *runtime-supported* set is narrower: the canonical extractor produces
FindingsSection / TableSection / MetricSection (the latter via the legacy
builders, not the catalog-driven path). ChartSection is defined in the
artifact schema but never instantiated by any code path — see the ADR 0004
survey for the silent-render-nothing pattern this creates.

This module pins the runtime-supported set and surfaces a clear error
when a catalog row declares a section_type the runtime cannot honour.
The validation fires at two layers:

- Insert-time, from `create_subject_from_proposal` — catches future AI
  proposals declaring unsupported types.
- Collection-time, from `RESTExtractor._load_section_instructions` —
  catches anyone bypassing insert-time (raw SQL, migrations).

The mismatch is loud and informational, not destructive. Existing chart
catalog rows (storage_utilization, cloud_storage_egress_ingress,
client_growth.chart) are preserved on disk; ADR 0004 will address chart
support. Only NEW writes and ATTEMPTS TO COLLECT against chart sections
fail loudly.
"""
from __future__ import annotations


SUPPORTED_SECTION_TYPES: frozenset[str] = frozenset({"findings", "table", "metric"})
"""Section types the runtime can honour today.

`findings` and `table` are produced by the catalog-driven extractor.
`metric` is produced by legacy builders (the canonical schema has
MetricSection but result_to_artifact does not emit it).

`chart` is structurally allowed by the schema CHECK but produces
nothing at runtime — see ADR 0004.
"""


class UnsupportedSectionTypeError(ValueError):
    """Raised when a catalog row declares a section_type the runtime cannot
    honour. The error message names the subject, section, declared type,
    and the supported set — and points at ADR 0004 for chart support."""


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
            f"This catalog row is preserved — ADR 0004 will address "
            f"support for additional section types (e.g. chart)."
        )
