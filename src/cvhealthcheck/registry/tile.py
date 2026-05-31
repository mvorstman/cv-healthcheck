from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact


class ArtifactAdapter(Protocol):
    def __call__(self, data: dict[str, Any]) -> CanonicalArtifact: ...


@dataclass
class SectionDefinition:
    id:         str
    title:      str
    type:       str   # "findings" | "table" | "chart" | "metric"
    reportable: bool = True


@dataclass(frozen=True)
class SourceDefinition:
    source_type:  SourceType
    label:        str
    description:  str
    implemented:  bool = True


@dataclass
class TileDefinition:
    id:                str
    title:             str
    description:       str
    artifact_type:     str
    supported_sources: tuple[SourceDefinition, ...]
    sections:          tuple[SectionDefinition, ...]
    adapter_map:       dict[SourceType, ArtifactAdapter]
