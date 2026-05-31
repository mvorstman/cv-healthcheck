"""ADR 0004 phase 7 — TableSection.empty_message threads catalog → view.

The presentational empty-state string (backup_job_summary's "No jobs in the
selected window") must travel: extraction_instructions["table"]["empty_message"]
-> ExtractionResult.section_table_specs -> TableSection.empty_message ->
artifact_to_view's table dict -> the JS renderer (which uses it instead of the
generic "No data.").
"""
from cvhealthcheck.artifacts.models import CanonicalArtifact, TableSection
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.quickhc.canonical_view import artifact_to_view


def _table_result(rows, empty_message=None):
    r = ExtractionResult(subject_id="backup_job_summary", source_type="rest")
    sid = "backup_job_summary.recent_jobs"
    r.sections[sid] = rows
    r.section_output_types[sid] = "table"
    r.section_titles[sid] = "Recent jobs"
    if empty_message is not None:
        r.section_table_specs[sid] = {"empty_message": empty_message}
    return r


def test_empty_message_carried_onto_table_section():
    art = result_to_artifact(
        _table_result([], empty_message="No jobs in the selected window"),
        "backup_job_summary", "Backup Job Summary",
    )
    table = next(s for s in art.sections if isinstance(s, TableSection))
    assert table.empty_message == "No jobs in the selected window"
    assert table.items == []
    # survives JSON round-trip
    CanonicalArtifact.model_validate(art.model_dump(mode="json"))


def test_empty_message_reaches_view_model():
    art = result_to_artifact(
        _table_result([], empty_message="No jobs in the selected window"),
        "backup_job_summary", "Backup Job Summary",
    )
    view = artifact_to_view(art)
    table = next(s for s in view["sections"] if s["type"] == "table")
    assert table["empty_message"] == "No jobs in the selected window"
    assert table["rows"] == []


def test_empty_message_defaults_none_when_unset():
    art = result_to_artifact(_table_result([{"a": 1}]), "x", "X")
    table = next(s for s in art.sections if isinstance(s, TableSection))
    assert table.empty_message is None
