"""Subject-specific source-provenance dispatch — sibling to upload_dispatch.

Subjects whose REST collection is hardcoded in Python services (rather
than described by rows in subject_section_sources) cannot have their
source status derived from catalog data the way the generic source-
building path does. Their provenance lives in a dedicated builder
function — build_security_assessment_provenance and
build_license_summary_provenance in source_provenance.py — that knows
which collection methods (REST, CSV, HTML) are implemented for the
subject and what metadata to attach.

This module wires those builders into the generic source-building path
via a dict[str, ProvenanceBuilder] keyed by subject_id. _build_generic_
sources consults the dict before falling through to the catalog-table
logic. Two entries today: security_assessment and license_summary.

This is the same architectural shape as upload_dispatch.py — a small
in-Python dict mapping subject_id to a callable. Code is the honest
place for code-like data (the builders ARE code). The δ → β migration
path stays clean: if/when the set of subjects with hardcoded REST
collection grows enough that this dict becomes painful, the builders
themselves become the migration unit, not the dispatch shape.

See also:
  - src/cvhealthcheck/web/routes/upload_dispatch.py — sibling dispatch
    for the unified-upload route's subject-specific behavior.
  - docs/refactor_unified_upload_session_5a_design.md Section 6 — the
    δ → β migration rationale that applies here too.
"""
from __future__ import annotations

from typing import Any, Callable

from cvhealthcheck.quickhc.source_provenance import (
    build_license_summary_provenance,
    build_security_assessment_provenance,
)

ProvenanceBuilder = Callable[[dict[str, Any] | None], list[dict[str, Any]]]

PROVENANCE_DISPATCH: dict[str, ProvenanceBuilder] = {
    "security_assessment": build_security_assessment_provenance,
    "license_summary": build_license_summary_provenance,
}


def get_provenance_builder(subject_id: str) -> ProvenanceBuilder | None:
    """Return the provenance builder for subject_id, or None if the
    subject's source status should be derived from catalog data (the
    default generic path).
    """
    return PROVENANCE_DISPATCH.get(subject_id)
