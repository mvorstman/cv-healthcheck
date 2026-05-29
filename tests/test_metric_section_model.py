"""ADR 0004 phase 2 — MetricSection / MetricItem / VerdictEntry model tests.

Pins the additive extensions: optional (sentinel) value, derived flag,
severity, the verdict-chain shape, and the explicit render_mode discriminator
that defaults to "meta" (so License Summary's commcell_info stays unchanged).
"""
import pytest
from pydantic import ValidationError

from cvhealthcheck.artifacts.enums import FindingSeverity
from cvhealthcheck.artifacts.models import (
    MetricItem,
    MetricSection,
    VerdictEntry,
)


def test_metric_item_defaults_backward_compatible():
    # The pre-phase-2 shape (id/label/value/unit) still validates.
    item = MetricItem(id="used", label="Used", value=35, unit="TB")
    assert item.value == 35
    assert item.derived is False
    assert item.severity is None
    assert item.verdict_chain == []


def test_metric_item_value_allows_none_sentinel():
    item = MetricItem(id="prev", label="Previous", value=None, unit="TB")
    assert item.value is None


def test_metric_item_with_severity_and_verdict_chain():
    item = MetricItem(
        id="utilisation_pct",
        label="Utilisation",
        value=70.0,
        unit="%",
        derived=True,
        severity=FindingSeverity.warning,
        verdict_chain=[
            VerdictEntry(
                layer="template_default",
                rule_id="utilisation_threshold",
                severity=FindingSeverity.warning,
                reason="Utilisation 70% >= 70% threshold",
            )
        ],
    )
    assert item.derived is True
    assert item.severity == FindingSeverity.warning
    assert item.verdict_chain[0].layer == "template_default"
    assert item.verdict_chain[0].reason  # non-empty, auditable


def test_verdict_entry_reason_required():
    # reason has no default — it must be supplied (auditability pin).
    with pytest.raises(ValidationError):
        VerdictEntry(layer="template_default", severity=FindingSeverity.good)


def test_metric_section_render_mode_defaults_to_meta():
    sec = MetricSection(type="metric", id="commcell_info", title="CommCell")
    assert sec.render_mode == "meta"


def test_metric_section_render_mode_metric():
    sec = MetricSection(type="metric", id="x", title="X", render_mode="metric")
    assert sec.render_mode == "metric"


def test_metric_section_render_mode_rejects_unknown():
    with pytest.raises(ValidationError):
        MetricSection(type="metric", id="x", title="X", render_mode="bogus")
