"""ADR-0017 LS recipe — harness wrapper around the PRODUCTION recipe.

The recipe itself now lives in production
(:mod:`cvhealthcheck.license_summary.generic_recipe`) — a single source of truth
shared by the live catalog (migration ``0034``) and this parity harness. This
module re-exports it and adds the harness-only pieces:

  - the D2 ``commcell_info`` enrichment (still test-side here; its promotion to the
    live ``result_to_artifact`` seam is commit 2),
  - the candidate producer (extract → result_to_artifact → enrich), and
  - the signal runner (generic-vs-bespoke over the corpus).

No bespoke change. The enrichment + candidate path mirror what the live generic
path will do once commit 2 lands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    MetricItem,
    MetricSection,
)
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.html import HTMLExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

# Production recipe (source of truth) — re-exported for the harness + tests.
from cvhealthcheck.license_summary.generic_recipe import (  # noqa: F401
    GENERIC_SUBJECT_ID,
    LS_RECIPE_PROPOSAL,
    _OBSERVED_SECTION,
    publish_ls_recipe,
    render_migration_sql,
)

from ls_parity_harness import fixture_format


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
    """Generic-vs-bespoke over the distinct real-export corpus, against a db with
    the recipe published. Returns pass/fail/pending totals + failure classes."""
    import collections

    from ls_parity_harness import (
        Outcome, bespoke_canonical, compare_artifacts, discover_ls_fixtures,
    )

    def _is_ls_content(art) -> bool:
        # Exclude the misfiled non-LS exports (a stray Security Assessment + the
        # cv_redesign mock), which yield no LS table rows.
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
            continue  # misfiled non-LS — exclude from the real LS corpus
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
