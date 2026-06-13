"""ADR-0017 generic License Summary recipe — the production source of truth.

This is the catalog recipe that the generic extractor pipeline (extract_file ->
result_to_artifact) uses for the ``license_summary`` subject. It was authored and
proven against the bespoke pipeline by the LS parity harness (ADR-0016/0017); this
module is its promotion to ``src/`` so that:

  - the live catalog (migration ``0034``) and the parity harness share ONE recipe
    definition (no drift), and
  - the migration SQL is GENERATED from the proposal here
    (:func:`render_migration_sql`), so the recipe — not hand-written SQL — stays
    the source of truth. A drift-guard test asserts the committed migration is
    byte-identical to the render.

Closed transforms, coalesce, computed sections, and metadata_pairs are all the
ADR-0016 recipe layer; the proposal publishes THROUGH the compile gate
(:func:`publish_ls_recipe`).

Scope note: this module owns ONLY the recipe (sections + extraction
instructions). It does NOT own recognition (commit 3) or the commcell_info
enrichment (commit 2, the result_to_artifact seam), and it does not touch the
REST path.
"""
from __future__ import annotations

import json
from typing import Any

from cvhealthcheck.db.subjects import create_subject_from_proposal

# The LIVE subject id — the generic recipe REPLACES the 0003-era bespoke-shaped
# license_summary recipe under the same id (so the tile/route/API/store keep
# working). NOT a separate "license_summary_generic" subject.
GENERIC_SUBJECT_ID = "license_summary"
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
    # Title-anchored: a section title may live in the Commvault export wrapper
    # (.reportstabletitle) OR in a plain <h2> heading (the sample-style export).
    # Still EXACT section_title_match, still title-anchored — NOT header-shape
    # matching. The extractor associates the title with the table that FOLLOWS it.
    return {"section_title_selector": ".reportstabletitle, h2", "section_title_match": title,
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
    "title": "License Summary",
    "description": "ADR-0017 generic LS recipe — closed transforms, coalesce, computed counts.",
    "category": "licensing",
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


# ---------------------------------------------------------------------------
# Migration SQL generator (deterministic — the recipe is the source of truth)
# ---------------------------------------------------------------------------

_MIGRATION_BASENAME = "0034_license_summary_generic_recipe.sql"


def _sql_str(value: str) -> str:
    """A single-quoted SQL string literal with embedded quotes escaped."""
    return "'" + str(value).replace("'", "''") + "'"


def render_migration_sql(proposal: dict = LS_RECIPE_PROPOSAL) -> str:
    """Render the proposal into the migration SQL, deterministically.

    The output is BYTE-STABLE for a given proposal: sources/sections/section
    instructions follow the proposal's (insertion) order, and every JSON blob is
    serialized with ``sort_keys=True`` and fixed separators. Re-rendering the same
    proposal yields the same bytes; any recipe change yields different bytes (the
    drift-guard test enforces both directions).

    The migration replaces ONLY the recipe content: it deletes every
    license_summary section_source + every license_summary section, then recreates
    the sections and the csv/html extraction instructions. It deliberately does
    NOT touch the subjects row (so created_by='system' is preserved), does NOT
    rewrite source recognition_hints (INSERT OR IGNORE keeps the existing 0003
    values; recognition is commit 3), and does NOT touch the 'rest' source row.
    """
    sid = proposal["subject_id"]
    ver = int(proposal["version"])
    ei: dict = proposal.get("extraction_instructions", {})
    out: list[str] = []

    out.append(f"-- {_MIGRATION_BASENAME}")
    out.append("--")
    out.append("-- GENERATED FILE — do NOT edit by hand. Regenerate with:")
    out.append("--   python -m cvhealthcheck.license_summary.generic_recipe \\")
    out.append(f"--     > src/cvhealthcheck/db/migrations/{_MIGRATION_BASENAME}")
    out.append("-- Source of truth: cvhealthcheck.license_summary.generic_recipe.LS_RECIPE_PROPOSAL")
    out.append("-- (the drift-guard test asserts this file is byte-identical to the render).")
    out.append("--")
    out.append("-- ADR-0017 promotion, commit 1: replace the 0003-era bespoke-shaped")
    out.append(f"-- {sid} recipe (sections + extraction instructions) with the generic recipe")
    out.append("-- under the SAME subject_id. The subjects row is NOT touched (created_by=")
    out.append("-- 'system' preserved); csv/html recognition_hints are NOT touched (commit 3);")
    out.append("-- the 'rest' source row is NOT touched (REST collect is out of scope).")
    out.append("")
    out.append("-- Teardown the prior recipe content: every license_summary source's")
    out.append("-- section_sources, then all of its sections. Source ROWS are preserved.")
    out.append("DELETE FROM subject_section_sources WHERE source_id IN (")
    out.append(f"    SELECT id FROM subject_sources WHERE subject_id = {_sql_str(sid)}")
    out.append(");")
    out.append(f"DELETE FROM subject_sections WHERE subject_id = {_sql_str(sid)};")
    out.append("")
    out.append("-- Ensure the csv/html sources exist and are extractable. INSERT OR IGNORE")
    out.append("-- leaves an existing row (with its recognition_hints) untouched.")
    out.append("INSERT OR IGNORE INTO subject_sources")
    out.append("    (subject_id, subject_version, source_type, extractable,")
    out.append("     non_extractable_reason, recognition_hints)")
    out.append("VALUES")
    src_rows = [
        f"    ({_sql_str(sid)}, {ver}, {_sql_str(st)}, "
        f"{1 if ei[st].get('extractable', True) else 0}, NULL, NULL)"
        for st in ei
    ]
    out.append(",\n".join(src_rows) + ";")
    out.append("")
    out.append("-- Sections (generic recipe).")
    out.append("INSERT INTO subject_sections")
    out.append("    (subject_id, subject_version, section_id, title, section_type,")
    out.append("     default_selected, sort_order)")
    out.append("VALUES")
    sec_rows = [
        f"    ({_sql_str(sid)}, {ver}, {_sql_str(s['section_id'])}, {_sql_str(s['title'])}, "
        f"{_sql_str(s['section_type'])}, {1 if s.get('default_selected', True) else 0}, "
        f"{int(s['sort_order'])})"
        for s in proposal.get("sections", [])
    ]
    out.append(",\n".join(sec_rows) + ";")
    out.append("")
    out.append("-- Extraction instructions, per (source_type, section).")
    for st in ei:
        for section_id, instr in ei[st].get("sections", {}).items():
            blob = json.dumps(instr, sort_keys=True, separators=(", ", ": "))
            out.append(
                "INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)"
            )
            out.append(f"SELECT id, {_sql_str(section_id)}, json({_sql_str(blob)})")
            out.append(
                f"  FROM subject_sources WHERE subject_id = {_sql_str(sid)}"
                f" AND subject_version = {ver} AND source_type = {_sql_str(st)};"
            )
    out.append("")  # trailing newline
    return "\n".join(out)


if __name__ == "__main__":  # pragma: no cover - regeneration entry point
    print(render_migration_sql(), end="")
