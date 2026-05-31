"""Phase-8 follow-on — per-field metric rules + first exercise of the
judge→recommend seam (recommend-seam-contract.md §3a/§3b).

Proves: (a) two fields of one metric section judged independently with their own
verdicts; (b) a fired, surviving rule's declared recommendation payload surfaces
as recommendation_intent on the emitted item (with inputs_resolved), absent on
the un-declared field; (c) SC4 — a muted/waived item carries no intent; (d) the
seam field is additive (absent-when-None) and reloads unchanged.
"""
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.enums import FindingSeverity as S
from cvhealthcheck.artifacts.models import CanonicalArtifact, MetricItem, MetricSection, RecommendationIntent, VerdictEntry
from cvhealthcheck.evaluative import engine
from cvhealthcheck.extractors.fixture import FixtureExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _collect(db_path: Path):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        res = FixtureExtractor(conn).extract("_metric_test", 1)
    finally:
        conn.close()
    return result_to_artifact(res, "_metric_test", "Metric Test")


def _items(artifact):
    metric = next(s for s in artifact.sections if isinstance(s, MetricSection))
    return {i.id: i for i in metric.items}


# ── (a) two independent per-field verdicts on one section ──

def test_two_fields_judged_independently(migrated_db_path: Path):
    items = _items(_collect(migrated_db_path))
    assert items["used"].severity == S.critical          # used=35 >= 30 -> critical
    assert items["utilisation_pct"].severity == S.warning  # 70% -> warning
    # independent: each carries its own verdict_chain keyed to its own rule
    assert items["used"].verdict_chain[0].rule_id == "used_capacity_threshold"
    assert items["utilisation_pct"].verdict_chain[0].rule_id == "utilisation_threshold"


# ── (b) recommendation_intent surfaced on the declaring field, absent on the un-declared ──

def test_recommendation_intent_on_declaring_field(migrated_db_path: Path):
    items = _items(_collect(migrated_db_path))
    ri = items["used"].recommendation_intent
    assert ri is not None
    assert ri.intent_kind == "trend_projection"
    assert ri.signal == "capacity.trend"
    assert ri.inputs_resolved == {"utilisation_pct": 70.0}   # resolved at judge time
    # the un-declared field carries no intent
    assert items["utilisation_pct"].recommendation_intent is None
    assert items["purchased"].recommendation_intent is None  # no rule at all


# ── (c) SC4: muted/waived item carries no intent ──

def test_sc4_muted_unit_carries_no_intent_unit():
    rule = {"rule_id": "r", "kind": "threshold", "comparison": ">=",
            "bands": [{"at": 1, "severity": "critical"}], "default_severity": "good",
            "recommendation": {"intent_kind": "trend_projection", "signal": "x", "inputs": ["v"]}}
    # muted headline -> no intent
    assert engine.surface_recommendation([rule], S.muted, [], {"v": 5}) is None
    # unjudged (None) -> no intent
    assert engine.surface_recommendation([rule], None, [], {"v": 5}) is None
    # fired + surviving -> intent, inputs resolved
    chain = [VerdictEntry(layer="template_default", severity=S.critical, rule_id="r", reason="x")]
    ri = engine.surface_recommendation([rule], S.critical, chain, {"v": 5})
    assert ri.signal == "x" and ri.inputs_resolved == {"v": 5}


def test_sc4_override_muted_declaring_rule_suppresses_intent(migrated_db_path: Path):
    # Waive the recommendation-bearing rule (override -> muted). Its declared
    # payload must NOT surface (SC4): a waived unit carries no recommendation.
    conn = sqlite3.connect(str(migrated_db_path))
    conn.execute(
        "INSERT INTO rule_overrides (customer_id, project_id, subject_id, subject_version, "
        "section_id, rule_id, severity, reason) VALUES "
        "('default','default','_metric_test',1,'_metric_test.capacity',"
        "'used_capacity_threshold','muted','waived')"
    )
    conn.commit(); conn.close()
    used = _items(_collect(migrated_db_path))["used"]
    assert used.severity == S.muted
    assert used.recommendation_intent is None                # SC4: suppressed despite the payload
    # the verdict chain still records both layers (audit), only the intent is suppressed
    assert [v.layer for v in used.verdict_chain] == ["template_default", "override"]


# ── (d) additive: absent-when-None serialization + reload unchanged ──

def test_recommendation_intent_omitted_when_absent():
    m = MetricItem(id="x", label="X", value=1.0, severity=S.good,
                   verdict_chain=[VerdictEntry(layer="template_default", severity=S.good, rule_id="r", reason="ok")])
    assert "recommendation_intent" not in m.model_dump(mode="json")   # absent, not null
    m2 = MetricItem(id="y", label="Y", value=1.0,
                    recommendation_intent=RecommendationIntent(intent_kind="attention", signal="s"))
    assert "recommendation_intent" in m2.model_dump(mode="json")


def test_artifact_with_intent_reloads_unchanged(migrated_db_path: Path):
    stored = _collect(migrated_db_path).model_dump(mode="json")
    reloaded = CanonicalArtifact.model_validate(stored)
    ri = _items(reloaded)["used"].recommendation_intent
    assert ri is not None and ri.signal == "capacity.trend"
    assert _items(reloaded)["utilisation_pct"].recommendation_intent is None
