from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.quickhc.registry import (
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
    JSON_IMPORT_SOURCE_ID,
    QUICK_HC_SECTION_IDS,
    QUICK_HC_SELECTION_IDS,
    QUICK_HC_SUBJECT_IDS,
    QUICK_HC_TILE_BY_ID,
    REST_COMMAND_CENTER_API_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    STANDARD_SOURCES,
    get_tiles,
    report_overview_default_selection_ids,
    report_subsection_options,
)


@pytest.fixture()
def tiles_db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def test_tile_ids_are_unique(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    tile_ids = [t["id"] for t in tiles]
    assert len(tile_ids) == len(set(tile_ids))


def test_section_ids_are_unique(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    section_ids = [sec["id"] for t in tiles for sec in t["sections"]]
    assert len(section_ids) == len(set(section_ids))


# License Summary canonical section ids are intentionally BARE per ADR-0017 and
# the existing rendering contract (registry/catalog.py + bespoke adapter + parity
# target). The prefix invariant predates the DB recipe being live for LS and was
# never exercised against it; prefixing LS would be a regression dressed as
# consistency (adapter/catalog/comparator/artifact-shape blast radius). This is
# ONE named, justified exemption — the invariant still holds for every other
# subject (do NOT generalize it).
_BARE_SECTION_ID_SUBJECTS = frozenset({"license_summary"})


def test_every_section_id_starts_with_tile_id_prefix(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    for tile in tiles:
        if tile["id"] in _BARE_SECTION_ID_SUBJECTS:
            continue  # see _BARE_SECTION_ID_SUBJECTS — ADR-0017 bare-id exemption
        for sec in tile["sections"]:
            assert sec["id"].startswith(f"{tile['id']}.")


def test_every_tile_has_required_metadata(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    assert tiles, "get_tiles returned empty list"
    for tile in tiles:
        assert tile["id"]
        assert tile["title"]
        assert tile["category"]
        assert tile["category_label"]


def test_every_tile_has_at_least_one_section(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    for tile in tiles:
        assert tile["sections"], f"tile {tile['id']} has no sections"


def test_every_default_selected_section_belongs_to_its_tile(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    for tile in tiles:
        all_ids = {sec["id"] for sec in tile["sections"]}
        default_ids = {sec["id"] for sec in tile["sections"] if sec["default_selected"]}
        assert default_ids.issubset(all_ids)


def test_tile_section_ids_are_unique_per_tile(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    for tile in tiles:
        ids = [sec["id"] for sec in tile["sections"]]
        assert len(ids) == len(set(ids)), f"duplicate section ids in tile {tile['id']}"


def test_every_tile_has_at_least_one_source_with_valid_canonical_id(tiles_db: sqlite3.Connection) -> None:
    valid_ids = set(STANDARD_SOURCES)
    tiles = get_tiles(tiles_db)
    for tile in tiles:
        assert tile["sources"], f"tile {tile['id']} has no sources"
        for src in tile["sources"]:
            assert src["id"] in valid_ids, (
                f"tile {tile['id']} has source with unknown id {src['id']!r}"
            )


def test_environment_surfaces_command_center_tab_with_collect_url(tiles_db: sqlite3.Connection) -> None:
    """ADR 0007 ph3 follow-on (BUG 1 + row-7 display): environment's generic source
    tabs map the rest_command_center_api row (row 22) to a "REST / Command Center
    API" tab WITH a collect_url, and the stale plain-'rest' row (row 7) is
    suppressed so the user sees ONE correct source tab."""
    env = next(t for t in get_tiles(tiles_db) if t["id"] == "environment")
    by_id = {s["id"]: s for s in env["sources"]}
    # The command-center tab is present with the shared /collect url.
    cc = by_id.get(REST_COMMAND_CENTER_API_SOURCE_ID)
    assert cc is not None, "command-center source tab missing"
    assert cc["source_type"] == "rest_command_center_api"
    assert cc["label"] == "REST / Command Center API"
    assert cc["collect_url"] == "/quick-hc/environment/collect"
    # The stale plain-'rest' tab is suppressed when a command-center source exists.
    assert REST_REPORTS_PLUS_SOURCE_ID not in by_id
    assert [s["id"] for s in env["sources"]] == [REST_COMMAND_CENTER_API_SOURCE_ID]


def test_command_center_suppression_does_not_affect_non_cc_subjects(tiles_db: sqlite3.Connection) -> None:
    """The plain-'rest' suppression is keyed on the presence of a command-center
    source, so subjects without one keep their REST / Reports Plus tab."""
    cg = next(t for t in get_tiles(tiles_db) if t["id"] == "client_growth")
    ids = {s["id"] for s in cg["sources"]}
    assert REST_COMMAND_CENTER_API_SOURCE_ID not in ids   # no CC source -> no suppression
    assert REST_REPORTS_PLUS_SOURCE_ID in ids             # reports-plus tab intact


def test_get_tiles_includes_all_system_subjects(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    tile_ids = {t["id"] for t in tiles}
    for subject_id in QUICK_HC_SUBJECT_IDS:
        assert subject_id in tile_ids, f"system subject {subject_id!r} not in get_tiles()"


def test_backup_job_summary_tile_is_registered(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    bjs = next((t for t in tiles if t["id"] == "backup_job_summary"), None)
    assert bjs is not None, "backup_job_summary not found in get_tiles()"
    assert bjs["title"] == "Backup Job Summary"
    section_ids = {sec["id"] for sec in bjs["sections"]}
    assert "backup_job_summary.summary" in section_ids
    assert "backup_job_summary.status_breakdown" in section_ids
    assert "backup_job_summary.recent_failures" in section_ids
    assert "backup_job_summary.recent_jobs" in section_ids


def test_security_assessment_tile_registers_detail_sections(tiles_db: sqlite3.Connection) -> None:
    tiles = get_tiles(tiles_db)
    sa = next((t for t in tiles if t["id"] == "security_assessment"), None)
    assert sa is not None, "security_assessment not found in get_tiles()"
    section_ids = {sec["id"] for sec in sa["sections"]}
    for expected in (
        "security_assessment.metadata",
        "security_assessment.summary",
        "security_assessment.highlights",
        "security_assessment.access_security",
        "security_assessment.auditing",
        "security_assessment.platform_security",
        "security_assessment.company_and_owners_security",
        "security_assessment.capabilities",
        "security_assessment.hardening",
    ):
        assert expected in section_ids, f"missing section {expected}"


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




