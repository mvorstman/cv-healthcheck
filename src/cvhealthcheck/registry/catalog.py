from __future__ import annotations

from cvhealthcheck.adapters.commcell_details import adapt_rest as _adapt_commcell_rest
from cvhealthcheck.adapters.security_assessment import adapt_reportsplus_rest
from cvhealthcheck.artifacts.enums import SourceType

from .tile import SectionDefinition, SourceDefinition, TileDefinition

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
