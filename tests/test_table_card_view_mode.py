"""TableSection.view_mode — a presentational layout discriminator (option b),
mirroring CardSection.view_mode / MetricSection.render_mode. A single-row table
can render as a Field/Value card while its row rules + per-row verdict still fire.
Presentational only: model default + serialization, the collection plumb, the
view pass-through, and the render marker. Fixture-based; never reads app.db.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource, ArtifactSubject, ArtifactSummary, CanonicalArtifact,
    TableColumn, TableSection,
)
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc.canonical_view import artifact_to_view

NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


# ── model: default + omit-when-default serialization ──────────────────────────

def test_view_mode_defaults_to_columns_and_is_omitted_from_json():
    sec = TableSection(type="table", id="t", title="T",
                       columns=[TableColumn(id="a", label="A")], items=[{"a": 1}])
    assert sec.view_mode == "columns"
    assert "view_mode" not in sec.model_dump()            # byte-identical to pre-change artifacts

def test_view_mode_card_is_serialized():
    sec = TableSection(type="table", id="t", title="T", view_mode="card",
                       columns=[TableColumn(id="a", label="A")], items=[{"a": 1}])
    assert sec.model_dump()["view_mode"] == "card"
    # round-trips through validation
    assert TableSection.model_validate(sec.model_dump()).view_mode == "card"


# ── collection: result_to_artifact reads the mode from the table spec ─────────

def _result(view_mode=None):
    r = ExtractionResult(subject_id="sg", source_type="rest")
    r.sections["sg.rows"] = [{"id": 1, "x": 9}]
    r.section_output_types["sg.rows"] = "table"
    r.section_titles["sg.rows"] = "Rows"
    if view_mode is not None:
        r.section_table_specs["sg.rows"] = {"view_mode": view_mode}
    return r

def test_collection_sets_card_view_mode_from_spec():
    art = result_to_artifact(_result(view_mode="card"), "sg", "SG")
    assert next(s for s in art.sections if s.type == "table").view_mode == "card"

def test_collection_defaults_to_columns_when_unset_or_unknown():
    assert next(s for s in result_to_artifact(_result(), "sg", "SG").sections
                if s.type == "table").view_mode == "columns"
    # a bad/unknown value never crashes collection — it degrades to the default
    assert next(s for s in result_to_artifact(_result(view_mode="bogus"), "sg", "SG").sections
                if s.type == "table").view_mode == "columns"


# ── view: artifact_to_view carries view_mode on the table section ─────────────

def _view(view_mode):
    art = CanonicalArtifact(
        artifact_type="sg", generated_at=NOW,
        source=ArtifactSource(type=SourceType.rest_commserve),
        subject=ArtifactSubject(id="sg", title="SG"),
        summary=ArtifactSummary(status=ArtifactStatus.good),
        sections=[TableSection(type="table", id="sg.rows", title="Rows", view_mode=view_mode,
            columns=[TableColumn(id="a", label="A")], items=[{"a": 1, "_verdict": "good"}])])
    return next(s for s in artifact_to_view(art)["sections"] if s["type"] == "table")

def test_view_carries_view_mode():
    assert _view("card")["view_mode"] == "card"
    assert _view("columns")["view_mode"] == "columns"
    # render-only: the per-row verdict still rides along regardless of layout
    assert _view("card")["row_verdicts"] == ["good"]


# ── render marker: the JS card-mode branch exists + reuses meta-grid ──────────

_JS = (Path(__file__).resolve().parents[1] / "src/cvhealthcheck/web/static/quick_hc.js").read_text()

def test_js_has_table_card_branch_reusing_meta_grid():
    assert "sec.view_mode === 'card'" in _JS          # the table-as-card branch
    assert "meta-grid" in _JS and "meta-card" in _JS  # reuses the card markup, not a new table
