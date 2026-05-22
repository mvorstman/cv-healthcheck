from __future__ import annotations

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.registry import get_adapter, get_tile, list_tiles


class TestListTiles:
    def test_returns_tuple(self):
        assert isinstance(list_tiles(), tuple)

    def test_contains_security_assessment(self):
        ids = {t.id for t in list_tiles()}
        assert "security_assessment" in ids

    def test_contains_environment(self):
        ids = {t.id for t in list_tiles()}
        assert "environment" in ids

    def test_length_matches_registry(self):
        from cvhealthcheck.registry import REGISTRY
        assert len(list_tiles()) == len(REGISTRY)


class TestGetAdapter:
    def test_returns_callable_for_implemented_source(self):
        adapter = get_adapter("security_assessment", SourceType.reportsplus_rest)
        assert callable(adapter)

    def test_returns_callable_for_environment_implemented_source(self):
        adapter = get_adapter("environment", SourceType.rest_commserve)
        assert callable(adapter)

    def test_returns_none_for_unknown_subject(self):
        assert get_adapter("does_not_exist", SourceType.reportsplus_rest) is None

    def test_returns_none_for_unimplemented_source_sa_csv(self):
        assert get_adapter("security_assessment", SourceType.csv_import) is None

    def test_returns_none_for_unimplemented_source_sa_html(self):
        assert get_adapter("security_assessment", SourceType.html_import) is None

    def test_returns_none_for_unimplemented_source_sa_json(self):
        assert get_adapter("security_assessment", SourceType.json_import) is None

    def test_returns_none_for_unimplemented_source_env_csv(self):
        assert get_adapter("environment", SourceType.csv_import) is None

    def test_returns_none_for_unimplemented_source_env_html(self):
        assert get_adapter("environment", SourceType.html_import) is None

    def test_returns_none_for_unimplemented_source_env_json(self):
        assert get_adapter("environment", SourceType.json_import) is None

    def test_adapter_produces_canonical_artifact(self):
        adapter = get_adapter("security_assessment", SourceType.reportsplus_rest)
        assert isinstance(adapter({}), CanonicalArtifact)

    def test_adapter_produces_canonical_artifact_environment(self):
        adapter = get_adapter("environment", SourceType.rest_commserve)
        assert isinstance(adapter({}), CanonicalArtifact)


class TestSectionIdsMatchAdapterOutput:
    def test_security_assessment_section_ids_match_adapter(self):
        adapter = get_adapter("security_assessment", SourceType.reportsplus_rest)
        tile = get_tile("security_assessment")
        registry_ids = {s.id for s in tile.sections}

        # Run adapter against real raw data to get actual produced section IDs
        import json, glob
        raw_files = sorted(glob.glob("data/catalog/reportsplus/report_336_raw_*.json"))
        executions = []
        datasets = []
        for path in raw_files:
            with open(path) as f:
                d = json.load(f)
            guid = d.get("dataset_guid", path)
            dataset_name = d.get("dataset_name") or "Unknown"
            data_field = d.get("data", {})
            rows = []
            if isinstance(data_field, list):
                rows = data_field
            elif isinstance(data_field, dict):
                for k in ("records", "rows", "data"):
                    if isinstance(data_field.get(k), list):
                        rows = data_field[k]
                        break
            datasets.append({"dataset_guid": guid, "dataset_name": dataset_name})
            executions.append({"dataset_guid": guid, "dataset_name": dataset_name,
                                "status": "EXECUTABLE", "http_status": 200, "sample_rows": rows})

        extraction = {
            "summary": {"collected_at": "2026-05-22T01:00:00Z", "report_name": "Security Assessment"},
            "datasets": datasets,
            "executions": executions,
        }
        artifact = adapter(extraction)
        produced_ids = {s.id for s in artifact.sections}
        assert produced_ids == registry_ids

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
