"""Tests for the source-provenance dispatch module.

The dispatch wires the existing source_provenance builders into the
generic source-building path for subjects whose REST collection is
hardcoded in Python services (not described in subject_section_sources
rows).
"""
from __future__ import annotations

from cvhealthcheck.quickhc.source_provenance import (
    build_license_summary_provenance,
    build_security_assessment_provenance,
)
from cvhealthcheck.quickhc.source_provenance_dispatch import (
    PROVENANCE_DISPATCH,
    get_provenance_builder,
)


def test_security_assessment_builder_is_wired() -> None:
    builder = get_provenance_builder("security_assessment")
    assert builder is build_security_assessment_provenance


def test_license_summary_builder_is_wired() -> None:
    builder = get_provenance_builder("license_summary")
    assert builder is build_license_summary_provenance


def test_unknown_subject_returns_none() -> None:
    assert get_provenance_builder("environment") is None
    assert get_provenance_builder("backup_job_summary") is None
    assert get_provenance_builder("does_not_exist") is None


def test_provenance_dispatch_has_exactly_the_known_two_subjects() -> None:
    # Pins the surface: any addition is a deliberate change that
    # should also update tests/CHANGELOG/HANDOVER.
    assert set(PROVENANCE_DISPATCH.keys()) == {"security_assessment", "license_summary"}
