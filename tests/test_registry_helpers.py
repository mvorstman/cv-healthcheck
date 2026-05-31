from __future__ import annotations

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.registry import get_adapter, get_tile, list_tiles


class TestListTiles:
    def test_returns_tuple(self):
        assert isinstance(list_tiles(), tuple)

    def test_contains_environment(self):
        ids = {t.id for t in list_tiles()}
        assert "environment" in ids

    def test_security_assessment_removed_from_registry(self):
        # ADR 0003 phase 4 migrated SA to the catalog-driven extractor;
        # the hardcoded registry no longer carries it.
        ids = {t.id for t in list_tiles()}
        assert "security_assessment" not in ids

    def test_length_matches_registry(self):
        from cvhealthcheck.registry import REGISTRY
        assert len(list_tiles()) == len(REGISTRY)


class TestGetAdapter:
    def test_returns_callable_for_environment_implemented_source(self):
        adapter = get_adapter("environment", SourceType.rest_commserve)
        assert callable(adapter)

    def test_returns_none_for_unknown_subject(self):
        assert get_adapter("does_not_exist", SourceType.reportsplus_rest) is None

    def test_returns_none_for_security_assessment(self):
        # SA is no longer in the registry — get_adapter returns None for it.
        assert get_adapter("security_assessment", SourceType.reportsplus_rest) is None

    def test_returns_none_for_unimplemented_source_env_csv(self):
        assert get_adapter("environment", SourceType.csv_import) is None

    def test_returns_none_for_unimplemented_source_env_html(self):
        assert get_adapter("environment", SourceType.html_import) is None

    def test_returns_none_for_unimplemented_source_env_json(self):
        assert get_adapter("environment", SourceType.json_import) is None

    def test_adapter_produces_canonical_artifact_environment(self):
        adapter = get_adapter("environment", SourceType.rest_commserve)
        assert isinstance(adapter({}), CanonicalArtifact)


class TestSectionIdsMatchAdapterOutput:
    def test_environment_section_id_matches_adapter(self):
        adapter = get_adapter("environment", SourceType.rest_commserve)
        tile = get_tile("environment")
        registry_ids = {s.id for s in tile.sections}

        result = {
            "collected_at": "2026-05-22T00:00:00Z",
            "identity": {"hostName": "cs01", "csGUID": "abc-123"},
        }
        artifact = adapter(result)
        produced_ids = {s.id for s in artifact.sections}
        assert produced_ids == registry_ids
