"""ADR 0004 phase 8 step 3 — vendor → template → override layer resolution.

Covers the §2 worked example (template critical + project override mute on the
same rule_id → resolved muted, both verdicts in the chain), the contrast
(unrelated lower override does NOT lower the headline — most-severe-surviving),
the override loading path (rule_overrides → extractor → engine, end-to-end via
RESTExtractor), DP10 project-vs-customer-wide scope preference, and the
working/finalized read-as-stored rule (a stored artifact's verdict_chain is read
as-is, never re-resolved).
"""
import sqlite3
import tempfile
from pathlib import Path

from cvhealthcheck.artifacts.enums import FindingSeverity as S
from cvhealthcheck.artifacts.models import CanonicalArtifact, MetricSection, VerdictEntry
from cvhealthcheck.db.rule_overrides import load_section_overrides
from cvhealthcheck.evaluative import engine
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


_TEMPLATE = {
    "rule_id": "capacity_utilisation", "target": "utilisation_pct", "kind": "threshold",
    "comparison": ">=", "bands": [{"at": 90, "severity": "critical"}], "default_severity": "good",
}


# ── resolution algorithm (DP4 / DP6) ──

def test_worked_example_override_mutes_same_rule_id():
    sev, chain = engine.evaluate(
        95.0, [_TEMPLATE], label="Utilisation", unit="%",
        override_verdicts=[engine.build_override_verdict(
            {"rule_id": "capacity_utilisation", "severity": "muted", "reason": "waived"})],
    )
    assert sev == S.muted                                   # override mutes the headline
    assert [(v.layer, v.rule_id, v.severity) for v in chain] == [
        ("template_default", "capacity_utilisation", S.critical),  # both fired verdicts,
        ("override", "capacity_utilisation", S.muted),             # in layer order (DP6)
    ]


def test_contrast_unrelated_lower_override_does_not_lower_headline():
    sev, chain = engine.evaluate(
        95.0, [_TEMPLATE], label="Utilisation", unit="%",
        override_verdicts=[engine.build_override_verdict(
            {"rule_id": "unrelated", "severity": "warning", "reason": "x"})],
    )
    assert sev == S.critical                                # template critical survives (DP4)
    assert len(chain) == 2 and chain[1].severity == S.warning  # the override is still recorded


def test_all_surviving_muted_yields_muted():
    sev, chain = engine.evaluate(
        None, [{"rule_id": "r", "kind": "threshold", "comparison": ">=", "bands": [],
                "default_severity": "good", "mute_on_sentinel": True}],
        label="X")
    assert sev == S.muted and len(chain) == 1


def test_no_verdicts_is_unjudged():
    assert engine.evaluate(5.0, [], label="X") == (None, [])


def test_vendor_layer_composes():
    sev, chain = engine.evaluate(
        95.0, [_TEMPLATE], label="U", unit="%",
        vendor_verdicts=[VerdictEntry(layer="vendor", rule_id="v", severity=S.warning, reason="vendor")],
    )
    # vendor + template, both recorded, vendor first; headline = most-severe = critical
    assert [v.layer for v in chain] == ["vendor", "template_default"]
    assert sev == S.critical


# ── end-to-end: override loading path (rule_overrides -> extractor -> engine) ──
#
# Uses the _metric_test subject (FixtureExtractor, scoped to default/default):
# its utilisation_pct template rule `utilisation_threshold` fires WARNING on the
# fixture, with a clean CEL. (capacity_license is deliberately NOT used here —
# its sentinel_when CEL errors in celpy for genuine non-null/non-zero values, a
# pre-existing latent issue out of scope for step 3.)

_SECTION = "_metric_test.capacity"
_RULE = "utilisation_threshold"


def _collect_metric_test(db_path: Path):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        res = FixtureExtractor(conn).extract("_metric_test", 1)
    finally:
        conn.close()
    return result_to_artifact(res, "_metric_test", "Metric Test")


def _util_item(artifact):
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    return {i.id: i for i in metric.items}["utilisation_pct"]


def _seed_override(db_path: Path, severity: str, reason: str, *, project_id="default"):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO rule_overrides (customer_id, project_id, subject_id, subject_version, "
        "section_id, rule_id, severity, reason) VALUES (?,?,?,?,?,?,?,?)",
        ("default", project_id, "_metric_test", 1, _SECTION, _RULE, severity, reason),
    )
    conn.commit(); conn.close()


def test_e2e_no_override_fires_template_verdict(migrated_db_path: Path):
    item = _util_item(_collect_metric_test(migrated_db_path))
    assert item.severity == S.warning
    assert [v.layer for v in item.verdict_chain] == ["template_default"]


def test_e2e_project_override_mutes_template(migrated_db_path: Path):
    _seed_override(migrated_db_path, "muted", "Waived for Acme burst window (E-1207)")
    item = _util_item(_collect_metric_test(migrated_db_path))
    assert item.severity == S.muted                               # override muted the headline
    assert [(v.layer, v.severity) for v in item.verdict_chain] == [
        ("template_default", S.warning),
        ("override", S.muted),
    ]
    assert item.verdict_chain[1].reason == "Waived for Acme burst window (E-1207)"


def test_e2e_finalized_read_is_not_re_resolved(migrated_db_path: Path):
    # Build a working artifact WITH the override applied (muted), serialize it as
    # a finalized snapshot would, then re-load: the chain is read AS-STORED — no
    # DB override lookup on read, so removing the override later cannot
    # retroactively change a delivered artifact.
    _seed_override(migrated_db_path, "muted", "waived at finalization")
    stored_json = _collect_metric_test(migrated_db_path).model_dump(mode="json")
    reloaded = CanonicalArtifact.model_validate(stored_json)      # read-as-stored, no re-resolution
    assert _util_item(reloaded).severity == S.muted
    assert [v.layer for v in _util_item(reloaded).verdict_chain] == ["template_default", "override"]


# ── DP10 scope: project-specific preferred over customer-wide ──

def test_load_overrides_prefers_project_specific_over_customer_wide():
    p = Path(tempfile.mkdtemp()) / "t.db"
    from cvhealthcheck.db.migrations import run_migrations
    run_migrations(db_path=p)
    conn = sqlite3.connect(str(p))
    conn.executemany(
        "INSERT INTO rule_overrides (customer_id, project_id, subject_id, subject_version, "
        "section_id, rule_id, severity, reason) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("default", None, "capacity_license", 1, "capacity_license.summary", "capacity_utilisation", "warning", "customer-wide"),
            ("default", "default", "capacity_license", 1, "capacity_license.summary", "capacity_utilisation", "muted", "this assessment"),
        ],
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    overrides = load_section_overrides(conn, "default", "default", "capacity_license", 1)
    conn.close()
    rows = overrides["capacity_license.summary"]
    assert len(rows) == 1                                          # no double-fire
    assert rows[0]["severity"] == "muted" and rows[0]["reason"] == "this assessment"  # project wins
