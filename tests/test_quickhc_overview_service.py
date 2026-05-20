from __future__ import annotations

from cvhealthcheck.quickhc.models import SectionDefinition, TileDefinition
from cvhealthcheck.quickhc import overview_service


def test_build_quick_hc_overview_context_aggregates_all_subjects(monkeypatch) -> None:
    monkeypatch.setattr(
        overview_service,
        "catalog_status",
        lambda *args, **kwargs: {"exists": True},
    )
    monkeypatch.setattr(
        overview_service,
        "commcell_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "commcell"},
    )
    monkeypatch.setattr(
        overview_service,
        "security_assessment_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "security"},
    )
    monkeypatch.setattr(
        overview_service,
        "license_summary_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "license"},
    )
    monkeypatch.setattr(
        overview_service,
        "client_growth_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "growth"},
    )
    monkeypatch.setattr(
        overview_service,
        "capacity_license_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "capacity"},
    )
    monkeypatch.setattr(
        overview_service,
        "backup_job_summary_quick_hc_preview",
        lambda tile=None: {"exists": True, "summary": "backup"},
    )
    monkeypatch.setattr(
        overview_service,
        "OVERVIEW_PREVIEW_BUILDERS",
        {
            "commcell_preview": overview_service.commcell_quick_hc_preview,
            "security_assessment_preview": overview_service.security_assessment_quick_hc_preview,
            "license_summary_preview": overview_service.license_summary_quick_hc_preview,
            "client_growth_preview": overview_service.client_growth_quick_hc_preview,
            "capacity_license_preview": overview_service.capacity_license_quick_hc_preview,
            "backup_job_summary_preview": overview_service.backup_job_summary_quick_hc_preview,
        },
    )

    context = overview_service.build_quick_hc_overview_context()

    assert context["commcell_status"] == {"exists": True}
    assert context["commcell_preview"]["summary"] == "commcell"
    assert context["security_assessment"]["summary"] == "security"
    assert context["license_summary"]["summary"] == "license"
    assert context["client_growth"]["summary"] == "growth"
    assert context["capacity_license"]["summary"] == "capacity"
    assert context["backup_job_summary"]["summary"] == "backup"
    assert set(context["quick_hc_tile_previews"]) == {
        "environment",
        "security_assessment",
        "license_summary",
        "client_growth",
        "capacity_license",
        "backup_job_summary",
    }
    assert set(context["quick_hc_tiles"]) == {
        "environment",
        "security_assessment",
        "license_summary",
        "client_growth",
        "capacity_license",
        "backup_job_summary",
    }


def test_build_quick_hc_tile_previews_uses_tile_renderer_metadata() -> None:
    tile = TileDefinition(
        id="synthetic",
        title="Synthetic",
        subtitle="Preview metadata test",
        source_type="test",
        source_service="test_service",
        artifact_type="synthetic",
        preview_renderer="synthetic_preview",
        report_renderer="synthetic_report",
        sections=(
            SectionDefinition(
                id="synthetic.summary",
                label="Summary",
            ),
        ),
    )
    builders = {"synthetic_preview": lambda tile: {"id": tile.id, "title": tile.title}}

    original = overview_service.OVERVIEW_PREVIEW_BUILDERS
    try:
        overview_service.OVERVIEW_PREVIEW_BUILDERS = builders
        previews = overview_service.build_quick_hc_tile_previews((tile,))
    finally:
        overview_service.OVERVIEW_PREVIEW_BUILDERS = original

    assert previews == {"synthetic": {"id": "synthetic", "title": "Synthetic"}}
