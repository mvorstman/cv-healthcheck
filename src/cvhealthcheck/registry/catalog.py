from __future__ import annotations

from cvhealthcheck.adapters.commcell_details import adapt_rest as _adapt_commcell_rest
from cvhealthcheck.adapters.license_summary import adapt as _adapt_license_summary
from cvhealthcheck.adapters.security_assessment import adapt_reportsplus_rest
from cvhealthcheck.artifacts.enums import SourceType

from .tile import ArtifactAdapter, SectionDefinition, SourceDefinition, TileDefinition

# ---------------------------------------------------------------------------
# security_assessment
# ---------------------------------------------------------------------------

_SA_SECTIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(id="access_security",             title="Access Security",             type="findings"),
    SectionDefinition(id="auditing",                    title="Auditing",                    type="findings"),
    SectionDefinition(id="platform_security",           title="Platform Security",           type="findings"),
    SectionDefinition(id="company_and_owners_security", title="Company and Owners Security", type="findings"),
    SectionDefinition(id="capabilities",                title="Capabilities",                type="findings"),
    SectionDefinition(id="hardening",                   title="Hardening",                   type="findings"),
)

_SA_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(SourceType.reportsplus_rest, "REST / Reports Plus", "Live collection via Reports Plus report and dataset endpoints.", implemented=True),
    SourceDefinition(SourceType.csv_import,       "CSV import",          "Offline CSV import.",                                           implemented=False),
    SourceDefinition(SourceType.html_import,      "HTML import",         "Offline HTML import.",                                          implemented=False),
    SourceDefinition(SourceType.json_import,      "JSON import",         "Offline JSON import.",                                          implemented=False),
)

# ---------------------------------------------------------------------------
# license_summary
# ---------------------------------------------------------------------------

_LS_SECTIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(id="commcell_info",         title="CommCell Info",           type="metric"),
    SectionDefinition(id="other_licenses",         title="Other Licenses",          type="table"),
    SectionDefinition(id="agent_feature_licenses", title="Agent / Feature Licenses", type="table"),
    SectionDefinition(id="workload_summary",       title="Workload Summary",         type="table"),
)

_LS_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(SourceType.rest,        "REST",        "Live collection via Commvault REST API.", implemented=True),
    SourceDefinition(SourceType.csv_import,  "CSV import",  "Offline CSV import.",                    implemented=True),
    SourceDefinition(SourceType.html_import, "HTML import", "Offline HTML import.",                   implemented=True),
)

# ---------------------------------------------------------------------------
# environment (CommCell Details)
# ---------------------------------------------------------------------------

_ENV_SECTIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(id="environment", title="CommCell Details", type="metric"),
)

_ENV_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(SourceType.rest_commserve, "REST / Command Center API", "Live collection of CommCell identity from Command Center.", implemented=True),
    SourceDefinition(SourceType.csv_import,     "CSV import",               "Offline CSV import.",                                      implemented=False),
    SourceDefinition(SourceType.html_import,    "HTML import",              "Offline HTML import.",                                     implemented=False),
    SourceDefinition(SourceType.json_import,    "JSON import",              "Offline JSON import.",                                     implemented=False),
)

# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, TileDefinition] = {
    "license_summary": TileDefinition(
        id="license_summary",
        title="License Summary",
        description="License usage summary across capacity, other, and agent/feature license categories.",
        artifact_type="license_summary",
        supported_sources=_LS_SOURCES,
        sections=_LS_SECTIONS,
        adapter_map={
            SourceType.rest:        _adapt_license_summary,
            SourceType.csv_import:  _adapt_license_summary,
            SourceType.html_import: _adapt_license_summary,
        },
    ),
    "security_assessment": TileDefinition(
        id="security_assessment",
        title="Security Assessment",
        description="Security posture summary with findings across all assessment categories.",
        artifact_type="security_assessment",
        supported_sources=_SA_SOURCES,
        sections=_SA_SECTIONS,
        adapter_map={SourceType.reportsplus_rest: adapt_reportsplus_rest},
    ),
    "environment": TileDefinition(
        id="environment",
        title="CommCell Details",
        description="Platform identity and environment context for the CommCell.",
        artifact_type="environment",
        supported_sources=_ENV_SOURCES,
        sections=_ENV_SECTIONS,
        adapter_map={SourceType.rest_commserve: _adapt_commcell_rest},
    ),
}


def get_tile(subject_id: str) -> TileDefinition | None:
    return REGISTRY.get(subject_id)


def list_tiles() -> tuple[TileDefinition, ...]:
    return tuple(REGISTRY.values())


def get_adapter(subject_id: str, source_type: SourceType) -> ArtifactAdapter | None:
    tile = REGISTRY.get(subject_id)
    if tile is None:
        return None
    return tile.adapter_map.get(source_type)
