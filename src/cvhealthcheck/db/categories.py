"""
cvhealthcheck.db.categories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The subject ``category`` vocabulary — the single, primary classification axis.

``category`` is stored free-text on the ``subjects`` row (no DB enum), so this
dict is the authoritative term set: its keys are the known category slugs and
its values their display labels. An unknown category is still accepted — the
caller falls back to a title-cased form (preserving prior behavior).

This is the single source of truth for the category vocabulary: both
``create_subject_from_proposal`` (display-label derivation) and the Domain
Labels disjointness test import it from here, rather than mirroring the terms.
Distinct from the additive domain-label vocabulary (ADR-0012), held in the
``domain_label`` table, which must stay disjoint from these slugs.
"""
from __future__ import annotations

CATEGORY_LABELS: dict[str, str] = {
    "identity": "Identity",
    "security": "Security",
    "licensing": "Licensing",
    "performance": "Performance",
    "operations": "Operations",
    "storage": "Storage",
}

# The set of known category slugs — e.g. for the Domain Labels disjointness
# invariant (category vocabulary ∩ domain-label vocabulary == ∅).
CATEGORY_VOCABULARY: frozenset[str] = frozenset(CATEGORY_LABELS)
