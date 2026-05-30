"""SA migration PR1 — the production report's Security Assessment section now
reads the canonical store (get_canonical) via _canonical_to_sa_report_dict,
instead of the bespoke per-domain dict (get_current).

These tests prove the re-authored input renders EQUIVALENTLY to the bespoke-dict
output at the report-output level (counters, normalized section rows,
highlight_rows), pin the explicit field mapping, and lock the category ->
section.title display fix that matters once SA routes through the generic
extractor (where finding.category becomes the namespaced section_id).

Both stores are still live in PR1; the cut (repointing the writers) is PR2.
"""
from datetime import datetime, timezone

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    Finding,
    FindingsSection,
    SummaryMetric,
)
import re
from collections import OrderedDict

from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.reportsplus.security_assessment import (
    SECTION_ORDER,
    summarize_security_assessment_artifact,
)
from cvhealthcheck.security_assessment.artifact import build_security_assessment_artifact
from cvhealthcheck.quickhc.report_service import _canonical_to_sa_report_dict


def _sa_canonical_from_findings(findings, *, source_type="html"):
    """Build a generic-scheme SA CanonicalArtifact from a findings list via the
    real generic path (result_to_artifact) — the post-cut canonical shape
    (namespaced section ids, category == section_id, severity mapped). Replaces
    the deleted bespoke _build_canonical_from_import as a test converter."""
    r = ExtractionResult(subject_id="security_assessment", source_type=source_type)
    grouped = OrderedDict()
    for f in findings:
        grouped.setdefault(f["section"], []).append(f)
    for name, items in grouped.items():
        sid = "security_assessment." + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        r.sections[sid] = [
            {
                "parameter": it["parameter"], "status": it["status"],
                "severity": str(it["status"]).lower(),
                "remarks": it.get("remarks", ""), "action": it.get("action", ""),
            }
            for it in items
        ]
        r.section_output_types[sid] = "findings"
        r.section_titles[sid] = name
    return result_to_artifact(r, "security_assessment", "Security Assessment")


_FINDINGS = [
    {"section": "Access Security", "parameter": "MFA enabled", "status": "Critical",
     "remarks": "Missing for admin users", "action": "Enable MFA"},
    {"section": "Access Security", "parameter": "Password complexity", "status": "Good",
     "remarks": "Level 3", "action": ""},
    {"section": "Auditing", "parameter": "Audit retention", "status": "Info",
     "remarks": "30 days", "action": "Review retention"},
]


def _report_view(artifact_dict):
    """Replicate _build_security_assessment_section's normalized output — the
    fields the report actually renders (5-key rows + highlight_rows)."""
    summary = summarize_security_assessment_artifact(artifact_dict, SECTION_ORDER)
    sections, highlight_rows = [], []
    for section in summary.get("sections", []):
        rows = []
        for row in section.get("checks") or []:
            nr = {
                "section": row.get("section"), "parameter": row.get("parameter"),
                "status": row.get("status"), "remarks": row.get("remarks"),
                "action": row.get("action"),
            }
            rows.append(nr)
            if nr["status"] in {"Critical", "Warning"}:
                highlight_rows.append(nr)
        sections.append({"name": section.get("name"), "rows": rows})
    return {"counters": summary["counters"], "sections": sections, "highlight_rows": highlight_rows}


def test_report_output_parity_canonical_vs_bespoke():
    # Bespoke dict (what get_current() returns) -> canonical (what the store holds)
    # -> adapter (what the re-authored report reads). All from one source.
    bespoke = build_security_assessment_artifact(
        _FINDINGS, source_type="html", generated_on="May 1, 2026 10:00 AM",
        source={"title": "Security Assessment"},
    )
    # Post-cut canonical comes from the generic path (result_to_artifact).
    adapted = _canonical_to_sa_report_dict(_sa_canonical_from_findings(_FINDINGS))

    rb, ra = _report_view(bespoke), _report_view(adapted)
    assert rb["counters"] == ra["counters"]
    assert rb["sections"] == ra["sections"]
    assert rb["highlight_rows"] == ra["highlight_rows"]
    assert rb == ra  # full report-output equivalence


def test_adapter_field_mapping():
    canonical = _sa_canonical_from_findings(_FINDINGS)
    adapted = _canonical_to_sa_report_dict(canonical)

    assert adapted["source_type"] == "html"                       # SourceType -> "html"
    # imported_at maps from source.imported_at or .collected_at
    assert adapted["imported_at"] == (canonical.source.imported_at or canonical.source.collected_at).isoformat()
    # generated_on maps from canonical generated_at
    assert adapted["generated_on"] == canonical.generated_at.isoformat()
    assert adapted["status_counts"] == {"Critical": 1, "Warning": 0, "Good": 1, "Info": 1}


def test_category_to_section_title_fix_on_generic_scheme():
    # Post-cut shape: section.id namespaced, finding.category == namespaced id.
    # The adapter must show the section TITLE in rows, not the namespaced category.
    artifact = CanonicalArtifact(
        artifact_type="security_assessment",
        generated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
        source=ArtifactSource(type=SourceType.html_import, imported_at=datetime(2026, 5, 23, tzinfo=timezone.utc)),
        subject=ArtifactSubject(id="security_assessment", title="Security Assessment"),
        summary=ArtifactSummary(status=ArtifactStatus.critical, metrics=[
            SummaryMetric(id="critical", label="Critical", value=1),
        ]),
        sections=[FindingsSection(
            type="findings", id="security_assessment.access_security", title="Access Security",
            items=[Finding(
                id="abc123", severity=FindingSeverity.critical, status=FindingStatus.open,
                category="security_assessment.access_security",  # namespaced (post-cut)
                title="MFA enabled", description="Missing",
            )],
        )],
    )
    adapted = _canonical_to_sa_report_dict(artifact)
    assert adapted["sections"] == ["Access Security"]            # display title, not the id
    assert adapted["findings"][0]["section"] == "Access Security"  # NOT "security_assessment.access_security"
    assert adapted["findings"][0]["status"] == "Critical"
