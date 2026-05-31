from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cvhealthcheck.adapters.commcell_details import adapt_rest
from cvhealthcheck.artifacts.enums import ArtifactStatus, SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact, MetricSection

SAMPLE_RESULT = {
    "collected_at": "2026-05-22T17:37:54.263799+00:00",
    "http_status": 200,
    "ok": True,
    "identity": {
        "hostName": "cs01",
        "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D",
        "csVersionInfo": "11 SP40.47",
        "releaseId": 16,
        "osType": "Unix",
        "timeZone": "0:0:America/Danmarkshavn",
    },
    "raw": {
        "hostName": "cs01",
        "csVersionInfo": "11 SP40.47",
        "releaseId": 16,
        "osType": "Unix",
        "timeZone": "0:0:America/Danmarkshavn",
        "commcell": {"commCellId": 2, "commCellName": "CS01"},
    },
}


class TestAdaptRestValid:
    def setup_method(self):
        self.artifact = adapt_rest(SAMPLE_RESULT)

    def test_returns_canonical_artifact(self):
        assert isinstance(self.artifact, CanonicalArtifact)

    def test_artifact_type_is_environment(self):
        assert self.artifact.artifact_type == "environment"

    def test_subject_id_is_environment(self):
        assert self.artifact.subject.id == "environment"

    def test_subject_title(self):
        assert self.artifact.subject.title == "CommCell Details"

    def test_source_type_is_rest_commserve(self):
        assert self.artifact.source.type == SourceType.rest_commserve

    def test_source_endpoint(self):
        assert self.artifact.source.endpoint == "/commandcenter/api/CommServ"

    def test_source_has_no_report_id(self):
        assert self.artifact.source.report_id is None

    def test_generated_at_from_collected_at(self):
        expected = datetime(2026, 5, 22, 17, 37, 54, 263799, tzinfo=timezone.utc)
        assert self.artifact.generated_at == expected

    def test_summary_status_good(self):
        assert self.artifact.summary.status == ArtifactStatus.good

    def test_summary_metrics_empty(self):
        assert self.artifact.summary.metrics == []

    def test_one_metric_section(self):
        assert len(self.artifact.sections) == 1
        assert isinstance(self.artifact.sections[0], MetricSection)

    def test_metric_section_id(self):
        assert self.artifact.sections[0].id == "environment"

    def test_expected_metric_ids(self):
        section = self.artifact.sections[0]
        ids = [item.id for item in section.items]
        assert ids == [
            "hostname",
            "cs_guid",
            "cs_version_info",
            "release_id",
            "os_type",
            "timezone",
        ]

    def test_metric_values(self):
        section = self.artifact.sections[0]
        by_id = {item.id: item.value for item in section.items}
        assert by_id["hostname"] == "cs01"
        assert by_id["cs_guid"] == "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"
        assert by_id["cs_version_info"] == "11 SP40.47"
        assert by_id["release_id"] == 16
        assert by_id["os_type"] == "Unix"
        assert by_id["timezone"] == "0:0:America/Danmarkshavn"

    def test_does_not_use_raw_fields(self):
        # raw contains commcell.commCellId; it must not appear as a metric
        section = self.artifact.sections[0]
        ids = {item.id for item in section.items}
        assert "commcell_id" not in ids
        assert "comm_cell_id" not in ids

    def test_pydantic_round_trip(self):
        dumped = self.artifact.model_dump(mode="json")
        reloaded = CanonicalArtifact.model_validate(dumped)
        assert reloaded.artifact_type == "environment"
        assert reloaded.summary.status == ArtifactStatus.good


class TestAdaptRestMissingIdentity:
    def test_empty_result_produces_valid_artifact(self):
        artifact = adapt_rest({})
        assert isinstance(artifact, CanonicalArtifact)
        assert artifact.artifact_type == "environment"
        assert artifact.summary.status == ArtifactStatus.unknown
        assert artifact.sections == []

    def test_empty_identity_dict_is_unknown(self):
        artifact = adapt_rest({"identity": {}})
        assert artifact.summary.status == ArtifactStatus.unknown

    def test_partial_identity_omits_none_fields(self):
        result = {
            "collected_at": "2026-05-22T00:00:00Z",
            "identity": {
                "hostName": "cs02",
                "csGUID": None,
                "csVersionInfo": "11 SP40.47",
            },
        }
        artifact = adapt_rest(result)
        section = artifact.sections[0]
        ids = [item.id for item in section.items]
        assert "hostname" in ids
        assert "cs_version_info" in ids
        assert "cs_guid" not in ids

    def test_partial_identity_with_hostname_is_good(self):
        artifact = adapt_rest({"identity": {"hostName": "cs02"}})
        assert artifact.summary.status == ArtifactStatus.good

    def test_missing_collected_at_falls_back_to_now(self):
        before = datetime.now(timezone.utc)
        artifact = adapt_rest({"identity": {"hostName": "cs01"}})
        after = datetime.now(timezone.utc)
        assert before <= artifact.generated_at <= after
