from __future__ import annotations

from typing import Any

from cvhealthcheck.adapters.license_summary import SUBJECT_ID, adapt
from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType


def _artifact(
    *,
    source_type: str = "csv",
    other_licenses: list[dict[str, Any]] | None = None,
    agent_feature_licenses: list[dict[str, Any]] | None = None,
    workload_summary_sections: list[dict[str, Any]] | None = None,
    commcell_name: str | None = None,
    commcell_version: str | None = None,
    license_expiry: str | None = None,
    last_collection_time: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "license_summary",
        "source_type": source_type,
        "imported_at": "2026-05-23T10:00:00+00:00",
        "other_licenses": other_licenses or [],
        "agent_feature_licenses": agent_feature_licenses or [],
        "workload_summary_sections": workload_summary_sections or [],
        "commcell_name": commcell_name,
        "commcell_version": commcell_version,
        "license_expiry": license_expiry,
        "last_collection_time": last_collection_time,
        "source": {},
    }


# ---------------------------------------------------------------------------
# source type mapping
# ---------------------------------------------------------------------------


def test_adapt_csv_maps_to_csv_import() -> None:
    canonical = adapt(_artifact(source_type="csv"))
    assert canonical.source.type == SourceType.csv_import


def test_adapt_html_maps_to_html_import() -> None:
    canonical = adapt(_artifact(source_type="html"))
    assert canonical.source.type == SourceType.html_import


def test_adapt_rest_maps_to_rest() -> None:
    canonical = adapt(_artifact(source_type="rest"))
    assert canonical.source.type == SourceType.rest


def test_adapt_unknown_source_type_defaults_to_rest() -> None:
    canonical = adapt(_artifact(source_type="xlsx"))
    assert canonical.source.type == SourceType.rest


# ---------------------------------------------------------------------------
# artifact identity
# ---------------------------------------------------------------------------


def test_adapt_artifact_type_is_license_summary() -> None:
    assert adapt(_artifact()).artifact_type == SUBJECT_ID


def test_adapt_subject_id_and_title() -> None:
    canonical = adapt(_artifact())
    assert canonical.subject.id == "license_summary"
    assert canonical.subject.title == "License Summary"


def test_adapt_provenance_reflects_source_type() -> None:
    for src, expected in (
        ("csv",  SourceType.csv_import),
        ("html", SourceType.html_import),
        ("rest", SourceType.rest),
    ):
        assert adapt(_artifact(source_type=src)).source.type == expected


# ---------------------------------------------------------------------------
# other licenses section
# ---------------------------------------------------------------------------


def test_other_licenses_become_table_section() -> None:
    canonical = adapt(_artifact(other_licenses=[
        {"license": "Cloud Storage", "available_total": 100, "used": 40, "unit": None},
    ]))
    section = next((s for s in canonical.sections if s.id == "other_licenses"), None)
    assert section is not None
    assert len(section.items) == 1
    assert section.items[0]["license"] == "Cloud Storage"


def test_other_licenses_empty_omits_section() -> None:
    canonical = adapt(_artifact(other_licenses=[]))
    assert all(s.id != "other_licenses" for s in canonical.sections)


def test_other_licenses_row_without_license_name_skipped() -> None:
    canonical = adapt(_artifact(other_licenses=[
        {"license": "",  "available_total": 100, "used": 40},
        {"license": "A", "available_total": 50,  "used": 10},
    ]))
    section = next((s for s in canonical.sections if s.id == "other_licenses"), None)
    assert section is not None
    assert len(section.items) == 1


# ---------------------------------------------------------------------------
# agent / feature licenses section
# ---------------------------------------------------------------------------


def test_agent_feature_licenses_become_table_section() -> None:
    canonical = adapt(_artifact(agent_feature_licenses=[
        {"license": "Virtual Server", "permanent_total": 50, "permanent_used": 12,
         "term_total": 10, "term_used": 3},
    ]))
    section = next((s for s in canonical.sections if s.id == "agent_feature_licenses"), None)
    assert section is not None
    assert len(section.items) == 1
    assert section.items[0]["license"] == "Virtual Server"


def test_agent_feature_licenses_deduplicated_by_name() -> None:
    canonical = adapt(_artifact(agent_feature_licenses=[
        {"license": "Virtual Server", "permanent_total": 50, "permanent_used": 12,
         "term_total": 10, "term_used": 3, "client": "A"},
        {"license": "Virtual Server", "permanent_total": 50, "permanent_used": 12,
         "term_total": 10, "term_used": 3, "client": "B"},
    ]))
    section = next((s for s in canonical.sections if s.id == "agent_feature_licenses"), None)
    assert section is not None
    assert len(section.items) == 1


def test_agent_feature_licenses_empty_omits_section() -> None:
    canonical = adapt(_artifact(agent_feature_licenses=[]))
    assert all(s.id != "agent_feature_licenses" for s in canonical.sections)


# ---------------------------------------------------------------------------
# workload summary sections
# ---------------------------------------------------------------------------


def test_workload_sections_become_table_sections() -> None:
    canonical = adapt(_artifact(workload_summary_sections=[
        {
            "section_name": "Capacity Licenses",
            "rows": [{"license": "Backup and Recovery", "entitlement_value": "100",
                      "used": "50", "usage_percent": "50%", "status": "OK"}],
        },
    ]))
    section = next((s for s in canonical.sections if s.id == "capacity_licenses"), None)
    assert section is not None
    assert section.title == "Capacity Licenses"
    assert len(section.items) == 1


def test_workload_section_id_is_snake_cased() -> None:
    canonical = adapt(_artifact(workload_summary_sections=[
        {"section_name": "Operating Instance Licenses",
         "rows": [{"license": "Virtualization", "entitlement_value": "20", "used": "5",
                   "usage_percent": "25%", "status": "OK"}]},
    ]))
    assert any(s.id == "operating_instance_licenses" for s in canonical.sections)


def test_workload_section_with_no_rows_omitted() -> None:
    canonical = adapt(_artifact(workload_summary_sections=[
        {"section_name": "Empty Section", "rows": []},
    ]))
    assert all(s.id != "empty_section" for s in canonical.sections)


# ---------------------------------------------------------------------------
# CommCell info section
# ---------------------------------------------------------------------------


def test_commcell_info_section_present_when_metadata_exists() -> None:
    canonical = adapt(_artifact(commcell_name="CommServe A", license_expiry="2026-12-31"))
    section = next((s for s in canonical.sections if s.id == "commcell_info"), None)
    assert section is not None
    metric_values = {m.id: m.value for m in section.items}
    assert metric_values["commcell_name"] == "CommServe A"
    assert metric_values["license_expiry"] == "2026-12-31"


def test_commcell_info_section_absent_when_no_metadata() -> None:
    canonical = adapt(_artifact())
    assert all(s.id != "commcell_info" for s in canonical.sections)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary_good_when_licenses_present() -> None:
    canonical = adapt(_artifact(other_licenses=[
        {"license": "Cloud Storage", "available_total": 100, "used": 40},
    ]))
    assert canonical.summary.status == ArtifactStatus.good


def test_summary_unknown_when_no_licenses() -> None:
    canonical = adapt(_artifact(other_licenses=[], agent_feature_licenses=[]))
    assert canonical.summary.status == ArtifactStatus.unknown


def test_summary_metrics_contain_counts() -> None:
    canonical = adapt(_artifact(
        other_licenses=[
            {"license": "A", "available_total": 100, "used": 40},
            {"license": "B", "available_total": 50,  "used": 10},
        ],
        agent_feature_licenses=[
            {"license": "Virtual Server", "permanent_total": 50, "permanent_used": 12,
             "term_total": 10, "term_used": 3},
        ],
    ))
    by_id = {m.id: m.value for m in canonical.summary.metrics}
    assert by_id["other_license_count"] == 2
    assert by_id["agent_feature_count"] == 1


# ---------------------------------------------------------------------------
# registry integration
# ---------------------------------------------------------------------------


def test_registry_includes_license_summary_tile() -> None:
    from cvhealthcheck.registry.catalog import get_tile
    tile = get_tile("license_summary")
    assert tile is not None
    assert tile.artifact_type == "license_summary"


def test_registry_adapter_map_covers_all_source_types() -> None:
    from cvhealthcheck.registry.catalog import get_adapter
    assert get_adapter("license_summary", SourceType.rest) is not None
    assert get_adapter("license_summary", SourceType.csv_import) is not None
    assert get_adapter("license_summary", SourceType.html_import) is not None


def test_registry_adapter_produces_canonical_artifact() -> None:
    from cvhealthcheck.registry.catalog import get_adapter
    adapter = get_adapter("license_summary", SourceType.csv_import)
    assert adapter is not None
    canonical = adapter(_artifact(
        source_type="csv",
        other_licenses=[{"license": "Cloud Storage", "available_total": 100, "used": 40}],
    ))
    assert canonical.artifact_type == "license_summary"
    assert canonical.source.type == SourceType.csv_import
