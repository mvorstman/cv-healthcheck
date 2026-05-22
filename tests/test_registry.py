from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.registry import REGISTRY, ArtifactAdapter, get_tile
from cvhealthcheck.registry.tile import SectionDefinition, SourceDefinition, TileDefinition


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_security_assessment_registered(self):
        assert "security_assessment" in REGISTRY

    def test_environment_registered(self):
        assert "environment" in REGISTRY

    def test_get_tile_security_assessment(self):
        tile = get_tile("security_assessment")
        assert tile is not None
        assert isinstance(tile, TileDefinition)

    def test_get_tile_environment(self):
        tile = get_tile("environment")
        assert tile is not None
        assert isinstance(tile, TileDefinition)

    def test_get_tile_unknown_returns_none(self):
        assert get_tile("does_not_exist") is None

    def test_get_tile_empty_string_returns_none(self):
        assert get_tile("") is None


# ---------------------------------------------------------------------------
# TileDefinition structure
# ---------------------------------------------------------------------------

class TestSecurityAssessmentTile:
    def setup_method(self):
        self.tile = get_tile("security_assessment")

    def test_id(self):
        assert self.tile.id == "security_assessment"

    def test_title(self):
        assert self.tile.title == "Security Assessment"

    def test_artifact_type(self):
        assert self.tile.artifact_type == "security_assessment"

    def test_section_ids_stable(self):
        ids = [s.id for s in self.tile.sections]
        assert ids == [
            "access_security",
            "auditing",
            "platform_security",
            "company_and_owners_security",
            "capabilities",
            "hardening",
        ]

    def test_all_sections_are_findings_type(self):
        for sec in self.tile.sections:
            assert sec.type == "findings", f"{sec.id} has type {sec.type!r}"

    def test_all_sections_reportable_by_default(self):
        for sec in self.tile.sections:
            assert sec.reportable is True

    def test_reportsplus_rest_is_implemented(self):
        source = _source_by_type(self.tile, SourceType.reportsplus_rest)
        assert source is not None
        assert source.implemented is True

    def test_csv_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.csv_import)
        assert source is not None
        assert source.implemented is False

    def test_html_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.html_import)
        assert source is not None
        assert source.implemented is False

    def test_json_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.json_import)
        assert source is not None
        assert source.implemented is False

    def test_adapter_map_has_reportsplus_rest(self):
        assert SourceType.reportsplus_rest in self.tile.adapter_map

    def test_adapter_is_callable(self):
        adapter = self.tile.adapter_map[SourceType.reportsplus_rest]
        assert callable(adapter)

    def test_adapter_produces_canonical_artifact(self):
        adapter = self.tile.adapter_map[SourceType.reportsplus_rest]
        artifact = adapter({})
        assert isinstance(artifact, CanonicalArtifact)
        assert artifact.artifact_type == "security_assessment"


class TestEnvironmentTile:
    def setup_method(self):
        self.tile = get_tile("environment")

    def test_id(self):
        assert self.tile.id == "environment"

    def test_title(self):
        assert self.tile.title == "CommCell Details"

    def test_artifact_type(self):
        assert self.tile.artifact_type == "environment"

    def test_section_ids_stable(self):
        ids = [s.id for s in self.tile.sections]
        assert ids == ["environment"]

    def test_section_type_is_metric(self):
        assert self.tile.sections[0].type == "metric"

    def test_section_reportable(self):
        assert self.tile.sections[0].reportable is True

    def test_rest_commserve_is_implemented(self):
        source = _source_by_type(self.tile, SourceType.rest_commserve)
        assert source is not None
        assert source.implemented is True

    def test_csv_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.csv_import)
        assert source is not None
        assert source.implemented is False

    def test_html_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.html_import)
        assert source is not None
        assert source.implemented is False

    def test_json_import_not_implemented(self):
        source = _source_by_type(self.tile, SourceType.json_import)
        assert source is not None
        assert source.implemented is False

    def test_adapter_map_has_rest_commserve(self):
        assert SourceType.rest_commserve in self.tile.adapter_map

    def test_adapter_is_callable(self):
        adapter = self.tile.adapter_map[SourceType.rest_commserve]
        assert callable(adapter)

    def test_adapter_produces_canonical_artifact(self):
        adapter = self.tile.adapter_map[SourceType.rest_commserve]
        artifact = adapter({})
        assert isinstance(artifact, CanonicalArtifact)
        assert artifact.artifact_type == "environment"


# ---------------------------------------------------------------------------
# ArtifactAdapter Protocol export
# ---------------------------------------------------------------------------

class TestArtifactAdapter:
    def test_exported_from_registry(self):
        from cvhealthcheck.registry import ArtifactAdapter
        assert ArtifactAdapter is not None

    def test_adapters_satisfy_protocol(self):
        from cvhealthcheck.adapters.commcell_details import adapt_rest
        from cvhealthcheck.adapters.security_assessment import adapt_reportsplus_rest
        # Both callables should satisfy ArtifactAdapter at runtime
        # (Protocol structural check via isinstance requires runtime_checkable)
        for fn in (adapt_reportsplus_rest, adapt_rest):
            assert callable(fn)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _source_by_type(tile: TileDefinition, source_type: SourceType) -> SourceDefinition | None:
    for s in tile.supported_sources:
        if s.source_type == source_type:
            return s
    return None
