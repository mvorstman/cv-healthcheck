from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cvhealthcheck.artifacts import AdapterNotFoundError
from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.registry import build_and_save_artifact
from cvhealthcheck.registry.execution import AdapterNotFoundError as AdapterNotFoundError2


# ---------------------------------------------------------------------------
# AdapterNotFoundError is the right type from both import paths
# ---------------------------------------------------------------------------

class TestAdapterNotFoundErrorExport:
    def test_exported_from_artifacts(self):
        from cvhealthcheck.artifacts import AdapterNotFoundError as E
        assert issubclass(E, Exception)

    def test_same_class_from_both_packages(self):
        assert AdapterNotFoundError is AdapterNotFoundError2

    def test_is_not_generic_exception(self):
        assert AdapterNotFoundError is not Exception
        assert AdapterNotFoundError is not ValueError


# ---------------------------------------------------------------------------
# Unknown subject raises AdapterNotFoundError
# ---------------------------------------------------------------------------

class TestUnknownSubject:
    def test_raises_adapter_not_found_error(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("does_not_exist", SourceType.reportsplus_rest, {})

    def test_not_bare_exception(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("no_such_tile", SourceType.csv_import, {})

    def test_error_message_contains_subject_id(self):
        with pytest.raises(AdapterNotFoundError, match="subject_id='ghost_tile'"):
            build_and_save_artifact("ghost_tile", SourceType.rest_commserve, {})

    def test_error_message_format(self):
        with pytest.raises(AdapterNotFoundError, match=r"No tile registered for subject_id='unknown'"):
            build_and_save_artifact("unknown", SourceType.reportsplus_rest, {})


# ---------------------------------------------------------------------------
# Unimplemented source raises AdapterNotFoundError
# ---------------------------------------------------------------------------

class TestUnimplementedSource:
    def test_sa_csv_raises_adapter_not_found_error(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("security_assessment", SourceType.csv_import, {})

    def test_sa_html_raises_adapter_not_found_error(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("security_assessment", SourceType.html_import, {})

    def test_sa_json_raises_adapter_not_found_error(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("security_assessment", SourceType.json_import, {})

    def test_env_csv_raises_adapter_not_found_error(self):
        with pytest.raises(AdapterNotFoundError):
            build_and_save_artifact("environment", SourceType.csv_import, {})

    def test_error_message_contains_subject_and_source(self):
        with pytest.raises(
            AdapterNotFoundError,
            match=r"No adapter for subject_id='security_assessment', source_type=SourceType\.csv_import",
        ):
            build_and_save_artifact("security_assessment", SourceType.csv_import, {})

    def test_error_message_env_unimplemented(self):
        with pytest.raises(
            AdapterNotFoundError,
            match=r"No adapter for subject_id='environment', source_type=SourceType\.html_import",
        ):
            build_and_save_artifact("environment", SourceType.html_import, {})


# ---------------------------------------------------------------------------
# Successful build + save
# ---------------------------------------------------------------------------

class TestBuildAndSave:
    def _tmp_store(self) -> ArtifactStore:
        self._tmpdir = tempfile.TemporaryDirectory()
        return ArtifactStore("default", "default", base_dir=Path(self._tmpdir.name))

    def teardown_method(self):
        if hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()

    def test_returns_canonical_artifact_sa(self):
        store = self._tmp_store()
        artifact = build_and_save_artifact(
            "security_assessment", SourceType.reportsplus_rest, {}, store=store
        )
        assert isinstance(artifact, CanonicalArtifact)
        assert artifact.artifact_type == "security_assessment"

    def test_returns_canonical_artifact_environment(self):
        store = self._tmp_store()
        artifact = build_and_save_artifact(
            "environment", SourceType.rest_commserve, {}, store=store
        )
        assert isinstance(artifact, CanonicalArtifact)
        assert artifact.artifact_type == "environment"

    def test_artifact_is_persisted(self):
        store = self._tmp_store()
        build_and_save_artifact(
            "security_assessment", SourceType.reportsplus_rest, {}, store=store
        )
        loaded = store.load_latest_artifact("security_assessment")
        assert isinstance(loaded, CanonicalArtifact)

    def test_loaded_artifact_matches_returned(self):
        store = self._tmp_store()
        artifact = build_and_save_artifact(
            "environment", SourceType.rest_commserve,
            {"collected_at": "2026-05-22T00:00:00Z", "identity": {"hostName": "cs01"}},
            store=store,
        )
        loaded = store.load_latest_artifact("environment")
        assert loaded.generated_at == artifact.generated_at
        assert loaded.artifact_type == artifact.artifact_type
