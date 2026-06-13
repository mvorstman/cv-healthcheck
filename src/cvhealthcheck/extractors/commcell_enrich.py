"""ADR-0017 D2 — commcell_info mixed-source enrichment (production seam).

``commcell_info`` is a MIXED-SOURCE enrichment section assembled at the
``result_to_artifact`` seam (not a recipe section):

  - **Identity** (``commcell_name``): authority = the CUSTOMER CONTEXT (the
    declared active customer), fed to ``result_to_artifact`` by its caller. This
    module NEVER discovers context — it receives it (the caller-fed boundary).
  - **Observational** (``commcell_version`` / ``license_expiry`` /
    ``last_collection``): authority = the REPORT EVIDENCE, reached via the recipe's
    ``metadata_pairs`` staging section (:data:`COMMCELL_OBSERVED_SECTION`). No new
    file read happens here — the evidence is already in the extracted artifact.

Identity precedence: declared context > report evidence > placeholder.
``"Unknown CommCell"`` is the placeholder — NOT an authoritative declared value
(ADR-0017 D2) — so a real report-evidence name beats it.

The enrichment is ADDITIVE and DATA-DRIVEN: it fires only when the staging section
is present (LS), and is a no-op (returns the SAME artifact object) otherwise — so
non-LS artifacts pass through byte-unchanged.
"""
from __future__ import annotations

from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    MetricItem,
    MetricSection,
)

# Reserved staging-section id the recipe emits (metadata_pairs over report
# evidence) and this seam CONSUMES into commcell_info. A subject opts into the
# enrichment simply by producing this section.
COMMCELL_OBSERVED_SECTION = "_commcell_observed"

# The bare default — treated as ABSENCE of declared identity (ADR-0017 D2).
COMMCELL_PLACEHOLDER = "Unknown CommCell"


def _add_metric_item(items: list[MetricItem], item_id: str, label: str, value) -> None:
    # Mirror the bespoke adapter's _add_metric: skip None / blank.
    if value is not None and str(value).strip():
        items.append(MetricItem(id=item_id, label=label, value=str(value)))


def enrich_commcell_info(
    artifact: CanonicalArtifact, commcell_name: str | None = None
) -> CanonicalArtifact:
    """Assemble the ``commcell_info`` MetricSection from caller-fed identity +
    report-evidence observational fields, consuming the staging section.

    No-op (returns the SAME object) when the staging section is absent, so any
    non-LS artifact is byte-unchanged. ``commcell_name`` is the declared-context
    identity supplied by the caller; this function performs NO discovery.
    """
    if not any(s.id == COMMCELL_OBSERVED_SECTION for s in artifact.sections):
        return artifact

    observed: dict = {}
    kept = []
    for section in artifact.sections:
        if section.id == COMMCELL_OBSERVED_SECTION:
            rows = getattr(section, "items", []) or []
            if rows:
                observed = rows[0]
            continue  # consume the staging section — never appears in the output
        kept.append(section)

    # identity precedence: real declared context > real report-evidence > placeholder.
    # the placeholder is absence-of-identity, so evidence beats it.
    ctx_name = (
        commcell_name
        if (commcell_name and str(commcell_name).strip()
            and str(commcell_name) != COMMCELL_PLACEHOLDER)
        else None
    )
    evidence_name = observed.get("commcell_name") or None
    name = ctx_name or evidence_name or COMMCELL_PLACEHOLDER

    items: list[MetricItem] = []
    _add_metric_item(items, "commcell_name", "CommCell Name", name)
    _add_metric_item(items, "commcell_version", "CommCell Version", observed.get("commcell_version"))
    _add_metric_item(items, "license_expiry", "License Expiry", observed.get("license_expiry"))
    _add_metric_item(items, "last_collection", "Last Collection Time", observed.get("last_collection"))
    kept.append(MetricSection(type="metric", id="commcell_info", title="CommCell Info", items=items))
    return artifact.model_copy(update={"sections": kept})
