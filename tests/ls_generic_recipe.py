"""ADR-0017 LS recipe (first parity signal) — the generic License Summary recipe.

Authored against the settled ADR-0017 target + adjusted comparator. The bespoke LS
pipeline STAYS; this recipe is published into a harness-local DB (through the
compile gate) and used to produce a GENERIC candidate CanonicalArtifact for the
parity harness — no catalog/migration change, no UI change, no bespoke change.

Canonicals match the BESPOKE ADAPTER's field/section ids (license / available_total
/ used / permanent_total… ; section ids other_licenses / agent_feature_licenses /
the _to_snake workload names) so the comparator aligns sections. Extracts ONLY
what files carry (ADR-0017): NO commcell_info identity (D2 — context-enrichment,
deferred), NO usage_percent (D5). Counts are COMPUTED SECTIONS, not summary
metrics (D3/F5). Workload is HTML-only (section_title_selector), not csv
multi_section (no CSV export carries workload blocks).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    MetricItem,
    MetricSection,
)
from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import HTMLExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

from ls_parity_harness import fixture_format

GENERIC_SUBJECT_ID = "license_summary_generic"
_NULLS = ["N/A", "-", ""]

# Workload sections (HTML-only): bespoke section_name → _to_snake id. "Other
# Licenses" workload is OMITTED — its _to_snake id collides with the
# other_licenses TABLE section (a known bespoke collision; flagged, not resolved).
_WORKLOAD = [
    ("Capacity Licenses", "capacity_licenses"),
    ("Operating Instance Licenses", "operating_instance_licenses"),
    ("Virtualization Licenses", "virtualization_licenses"),
    ("User Licenses", "user_licenses"),
    ("Data Insights Licenses", "data_insights_licenses"),
    ("Air Gap Protect Licenses", "air_gap_protect_licenses"),
]

# Coalesce candidate columns for the workload entitlement / used (the exact
# variants the bespoke _first_present_text walks — report-version / license-type).
_AVAIL = [
    "Available Total", "Available Total (TB)", "Available Total (instances)",
    "Available Total (users)", "Available Total (VMs)",
    "Permanent Purchased", "Permanent Purchased (TB)", "Permanent Purchased (instances)",
    "Permanent Purchased (users)",
    "Term Purchased", "Term Purchased (TB)", "Term Purchased (instances)",
    "Term Purchased (users)",
]
_USED = ["Used", "Used (TB)", "Used (instances)", "Used (users)", "Used (VMs)"]

_OTHER_CM = [
    {"source": "License", "canonical": "license", "type": "string"},
    {"source": "Available Total", "canonical": "available_total", "transforms": ["number_with_unit"]},
    {"source": "Used", "canonical": "used", "transforms": ["number_with_unit"]},
]
_AGENT_CM = [
    {"source": "License", "canonical": "license", "type": "string"},
    {"source": "Permanent Total", "canonical": "permanent_total", "transforms": ["to_integer"]},
    {"source": "Permanent Used", "canonical": "permanent_used", "transforms": ["to_integer"]},
    {"source": "Term Total", "canonical": "term_total", "transforms": ["to_integer"]},
    {"source": "Term Used", "canonical": "term_used", "transforms": ["to_integer"]},
]
_WORKLOAD_CM = [
    {"source": "License", "canonical": "license", "type": "string"},
    {"source": _AVAIL, "canonical": "entitlement_value", "transforms": ["number_with_unit"]},
    {"source": _USED, "canonical": "used", "transforms": ["number_with_unit"]},
    {"source": "Summary", "canonical": "status", "type": "string"},
]
# Exact label confirmed in the deciding-reads: "Registration code" (lowercase 'c').
_META_LM = [
    {"source": "Registration code", "canonical": "registration_code",
     "transforms": ["trim", "mask_registration_code"]},
]

# D2 OBSERVATIONAL metadata (report evidence) — exact labels confirmed across the
# corpus. Extracted into a staging section the enrichment CONSUMES into
# commcell_info. null_values=[] so "N/A" (a real bespoke value) is preserved.
# "CommCell Name" is report-evidence identity (used only as the precedence
# fallback when no declared context is present).
_OBSERVED_LM = [
    {"source": ["CommCell Name"], "canonical": "commcell_name"},
    {"source": ["Version", "CommCell Version"], "canonical": "commcell_version"},
    {"source": ["License expiration", "License Expiry", "License expiry"],
     "canonical": "license_expiry"},
    {"source": ["Usage collection time", "Last collection time",
                "Last Collection Time", "Usage Collection Time"],
     "canonical": "last_collection"},
]
_OBSERVED_SECTION = "_commcell_observed"  # staging section, consumed by enrichment


def _section_decls() -> list[dict]:
    decls = [
        ("other_licenses", "table"),
        ("agent_feature_licenses", "table"),
        ("other_license_count", "metric"),       # computed (sort after its source)
        ("agent_feature_count", "metric"),       # computed (sort after its source)
        ("commcell_meta", "metric"),             # metadata_pairs (registration_code)
        (_OBSERVED_SECTION, "metric"),           # metadata_pairs (observational; staged)
    ]
    decls += [(sid, "table") for _name, sid in _WORKLOAD]
    return [
        {"section_id": sid, "title": sid, "section_type": st,
         "default_selected": True, "sort_order": i}
        for i, (sid, st) in enumerate(decls)
    ]


def _computed(ctype, source_section, field=None):
    r = {"format": "computed", "computed_type": ctype,
         "source_section": source_section, "output_as": "table"}
    if field:
        r["field"] = field
    return r


def _csv_sections() -> dict:
    return {
        "other_licenses": {"format": "single_table", "column_map": _OTHER_CM,
                           "null_values": _NULLS, "output_as": "table"},
        "agent_feature_licenses": {"format": "single_table", "column_map": _AGENT_CM,
                                   "null_values": _NULLS, "output_as": "table"},
        "other_license_count": _computed("row_count", "other_licenses"),
        "agent_feature_count": _computed("distinct_count", "agent_feature_licenses", "license"),
        "commcell_meta": {"format": "metadata_pairs", "label_map": _META_LM,
                          "null_values": _NULLS, "output_as": "table"},
        _OBSERVED_SECTION: {"format": "metadata_pairs", "label_map": _OBSERVED_LM,
                            "null_values": [], "output_as": "table"},
    }


def _html_table(title, column_map):
    return {"section_title_selector": ".reportstabletitle", "section_title_match": title,
            "column_map": column_map, "null_values": _NULLS, "output_as": "table"}


def _html_sections() -> dict:
    secs = {
        # Match the TABLE by its EXACT full title so it no longer collides with the
        # bare "Other Licenses" workload-summary title (ADR-0017 "Other Licenses"
        # disambiguation). The workload "Other Licenses" can't be authored here too
        # — its bespoke _to_snake id is also "other_licenses" and the recipe can't
        # declare two sections with one id (DB unique); see the slice finding.
        "other_licenses": _html_table("Other Licenses - current usage details", _OTHER_CM),
        "agent_feature_licenses": _html_table("Agent and Feature Licenses", _AGENT_CM),
        "other_license_count": _computed("row_count", "other_licenses"),
        "agent_feature_count": _computed("distinct_count", "agent_feature_licenses", "license"),
        "commcell_meta": {"format": "metadata_pairs", "label_map": _META_LM,
                          "null_values": _NULLS, "output_as": "table"},
        _OBSERVED_SECTION: {"format": "metadata_pairs", "label_map": _OBSERVED_LM,
                            "null_values": [], "output_as": "table"},
    }
    for name, sid in _WORKLOAD:
        secs[sid] = _html_table(name, _WORKLOAD_CM)
    return secs


LS_RECIPE_PROPOSAL: dict[str, Any] = {
    "subject_id": GENERIC_SUBJECT_ID,
    "version": 1,
    "title": "License Summary (generic)",
    "description": "ADR-0017 generic LS recipe — first parity signal.",
    "category": "reporting",
    "sections": _section_decls(),
    "extraction_instructions": {
        "csv": {"extractable": True, "sections": _csv_sections()},
        "html": {"extractable": True, "sections": _html_sections()},
    },
}


def publish_ls_recipe(db) -> dict:
    """Publish the generic recipe THROUGH the compile gate. Raises
    ProposalCompileError if the gate rejects it (caller must STOP + report)."""
    return create_subject_from_proposal(db, LS_RECIPE_PROPOSAL)


def generic_candidate(path: Path, db, customer: dict | None = None) -> CanonicalArtifact:
    """The generic recipe output for a real export — the harness candidate seam.
    Includes the D2 enrichment: assemble commcell_info from {context identity +
    report-evidence observational}. ``customer`` is the active-customer context
    (None in the harness, where no customer is selected — matching bespoke's
    no-context "Unknown CommCell" default)."""
    fmt = fixture_format(path)
    extractor = CSVExtractor(db) if fmt == "csv" else HTMLExtractor(db)
    result = extractor.extract(path, GENERIC_SUBJECT_ID)
    artifact = result_to_artifact(result, subject_id=GENERIC_SUBJECT_ID,
                                  subject_title="License Summary")
    return _enrich_commcell_info(artifact, customer)


def _enrich_commcell_info(artifact: CanonicalArtifact, customer: dict | None) -> CanonicalArtifact:
    """ADR-0017 D2: assemble the commcell_info MetricSection from context identity
    (commcell_name) + report-evidence observational fields (consumed from the
    staged metadata_pairs section). Present only where each value exists, matching
    bespoke's per-file variation. The staging section is dropped (enrichment-
    assembled, not a recipe section)."""
    observed: dict = {}
    kept = []
    for section in artifact.sections:
        if section.id == _OBSERVED_SECTION:
            rows = getattr(section, "items", []) or []
            if rows:
                observed = rows[0]
            continue  # consume the staging section — never appears in the output
        kept.append(section)

    # identity precedence: real declared context > real report-evidence > placeholder
    ctx_name = (customer or {}).get("commserve_name")
    ctx_name = ctx_name if (ctx_name and str(ctx_name).strip()) else None
    evidence_name = observed.get("commcell_name") or None
    commcell_name = ctx_name or evidence_name or "Unknown CommCell"

    items: list[MetricItem] = []
    _add_metric_item(items, "commcell_name", "CommCell Name", commcell_name)
    _add_metric_item(items, "commcell_version", "CommCell Version", observed.get("commcell_version"))
    _add_metric_item(items, "license_expiry", "License Expiry", observed.get("license_expiry"))
    _add_metric_item(items, "last_collection", "Last Collection Time", observed.get("last_collection"))
    kept.append(MetricSection(type="metric", id="commcell_info", title="CommCell Info", items=items))
    return artifact.model_copy(update={"sections": kept})


def _add_metric_item(items: list[MetricItem], item_id: str, label: str, value) -> None:
    # Mirror the bespoke adapter's _add_metric: skip None / blank.
    if value is not None and str(value).strip():
        items.append(MetricItem(id=item_id, label=label, value=str(value)))


# ---------------------------------------------------------------------------
# Signal runner (report — also callable as a script)
# ---------------------------------------------------------------------------

def run_signal(db) -> dict[str, Any]:
    """Generic-vs-bespoke over the 38, against a db with the recipe published.
    Returns pass/fail/pending totals + failure classes (section|field|note)."""
    import collections

    from ls_parity_harness import (
        Outcome, bespoke_canonical, compare_artifacts, discover_ls_fixtures,
    )

    def _is_ls_content(art) -> bool:
        # Real LS corpus = 38: exclude the 3 misfiled non-LS exports (2 Security
        # Assessment + the cv_redesign mock), which yield no LS table rows.
        return any(
            getattr(s, "type", None) == "table" and (getattr(s, "items", []) or [])
            for s in art.sections
        )

    total = {"pass": 0, "fail": 0, "pending": 0}
    classes: dict[tuple, dict] = collections.OrderedDict()
    candidate_errors: list[tuple] = []
    for path in discover_ls_fixtures():
        try:
            base = bespoke_canonical(path)
        except Exception:
            continue
        if not _is_ls_content(base):
            continue  # misfiled non-LS (the 3) — exclude from the real LS corpus
        try:
            cand = generic_candidate(path, db)
        except Exception as exc:
            candidate_errors.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue
        report = compare_artifacts(path.name, base, cand)
        total["pass"] += len(report.passed)
        total["fail"] += len(report.failed)
        total["pending"] += len(report.pending)
        for r in report.failed:
            key = (r.section, r.field, r.note)
            cls = classes.setdefault(key, {"count": 0, "sample": None})
            cls["count"] += 1
            if cls["sample"] is None:
                cls["sample"] = (r.file, r.expected, r.actual)
    return {"totals": total, "failure_classes": classes, "candidate_errors": candidate_errors}


if __name__ == "__main__":  # pragma: no cover - manual report
    import tempfile

    from cvhealthcheck.db.migrations import run_migrations
    from cvhealthcheck.db.compile_gate import ProposalCompileError
    import sqlite3

    with tempfile.TemporaryDirectory() as d:
        dbp = Path(d) / "t.db"
        run_migrations(db_path=dbp)
        conn = sqlite3.connect(str(dbp)); conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            publish_ls_recipe(conn)
            print("COMPILE GATE: published OK")
        except ProposalCompileError as exc:
            print("COMPILE GATE REJECTED:\n" + str(exc))
            raise SystemExit(0)
        s = run_signal(conn)
        print("TOTALS:", s["totals"])
        if s["candidate_errors"]:
            print("CANDIDATE ERRORS:", s["candidate_errors"][:5])
        print(f"FAILURE CLASSES ({len(s['failure_classes'])}):")
        for (section, field, note), info in sorted(
            s["failure_classes"].items(), key=lambda kv: -kv[1]["count"]
        ):
            f, exp, act = info["sample"]
            print(f"  [{info['count']:4}] section={section!r} field={field!r} note={note!r}")
            print(f"         e.g. {f}: expected={exp!r} actual={act!r}")
        conn.close()
