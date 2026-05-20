from __future__ import annotations

from cvhealthcheck.quickhc.registry import (
    QUICK_HC_SECTION_IDS,
    QUICK_HC_SELECTION_IDS,
    QUICK_HC_SUBJECT_IDS,
    QUICK_HC_TILE_BY_ID,
    QUICK_HC_TILES,
    report_overview_default_selection_ids,
    report_subsection_options,
)
from cvhealthcheck.quickhc.overview_service import OVERVIEW_PREVIEW_BUILDERS
from cvhealthcheck.quickhc.report_service import QuickHcReportService
from cvhealthcheck.quickhc.report_service import (
    REPORT_OVERVIEW_DEFAULT_SELECTION_IDS,
    REPORT_SELECTION_IDS,
    REPORT_SUBSECTION_OPTIONS,
)


def test_tile_ids_are_unique() -> None:
    tile_ids = [tile.id for tile in QUICK_HC_TILES]
    assert len(tile_ids) == len(set(tile_ids))


def test_section_ids_are_unique() -> None:
    section_ids = [
        section.id
        for tile in QUICK_HC_TILES
        for section in tile.sections
    ]
    assert len(section_ids) == len(set(section_ids))


def test_every_section_id_starts_with_tile_id_prefix() -> None:
    for tile in QUICK_HC_TILES:
        for section in tile.sections:
            assert section.id.startswith(f"{tile.id}.")


def test_every_tile_has_required_metadata() -> None:
    for tile in QUICK_HC_TILES:
        assert tile.id
        assert tile.title
        assert tile.subtitle
        assert tile.description == tile.subtitle
        assert tile.source_type
        assert tile.source_service
        assert tile.artifact_type
        assert tile.preview_renderer
        assert tile.report_renderer


def test_every_tile_has_at_least_one_section() -> None:
    for tile in QUICK_HC_TILES:
        assert tile.sections


def test_every_default_selected_section_belongs_to_its_tile() -> None:
    for tile in QUICK_HC_TILES:
        default_section_ids = {
            section.id
            for section in tile.sections
            if section.default_selected
        }
        assert set(tile.default_section_ids) == default_section_ids
        assert default_section_ids.issubset({section.id for section in tile.sections})


def test_tile_section_ids_property_matches_registry_order() -> None:
    for tile in QUICK_HC_TILES:
        assert tile.section_ids == tuple(section.id for section in tile.sections)


def test_tile_by_id_contains_all_quick_hc_tiles() -> None:
    assert set(QUICK_HC_TILE_BY_ID) == {tile.id for tile in QUICK_HC_TILES}
    for tile in QUICK_HC_TILES:
        assert QUICK_HC_TILE_BY_ID[tile.id] == tile


def test_backup_job_summary_tile_is_registered() -> None:
    tile = QUICK_HC_TILE_BY_ID["backup_job_summary"]
    assert tile.title == "Backup Job Summary"
    assert tile.section_ids == (
        "backup_job_summary.summary",
        "backup_job_summary.status_breakdown",
        "backup_job_summary.recent_failures",
        "backup_job_summary.recent_jobs",
    )


def test_registry_report_subsection_options_include_all_tile_section_ids() -> None:
    subsection_options = report_subsection_options()
    assert set(subsection_options) == QUICK_HC_SUBJECT_IDS
    option_ids = {
        option["id"]
        for options in subsection_options.values()
        for option in options
    }
    assert option_ids == QUICK_HC_SECTION_IDS


def test_registry_selection_ids_include_all_tile_and_section_ids() -> None:
    expected_ids = QUICK_HC_SUBJECT_IDS | QUICK_HC_SECTION_IDS
    assert QUICK_HC_SELECTION_IDS == expected_ids


def test_registry_default_overview_selection_ids_are_subset_of_selection_ids() -> None:
    default_ids = report_overview_default_selection_ids()
    assert default_ids.issubset(QUICK_HC_SELECTION_IDS)


def test_report_service_selection_contract_matches_registry() -> None:
    assert REPORT_SUBSECTION_OPTIONS == report_subsection_options()
    assert REPORT_SELECTION_IDS == QUICK_HC_SELECTION_IDS
    assert REPORT_OVERVIEW_DEFAULT_SELECTION_IDS == report_overview_default_selection_ids()
    assert REPORT_OVERVIEW_DEFAULT_SELECTION_IDS.issubset(REPORT_SELECTION_IDS)


def test_every_tile_preview_renderer_has_registered_builder() -> None:
    for tile in QUICK_HC_TILES:
        assert tile.preview_renderer in OVERVIEW_PREVIEW_BUILDERS


def test_every_tile_report_renderer_has_registered_builder() -> None:
    builder_names = set(QuickHcReportService()._report_builders())
    for tile in QUICK_HC_TILES:
        assert tile.report_renderer in builder_names
