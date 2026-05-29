"""Tests for the ADR 0004 family-derivation convention (subject_family)."""
import pytest

from cvhealthcheck.db.subjects import subject_family


@pytest.mark.parametrize(
    "subject_id, expected",
    [
        # No suffix — v1 is implicit, family is the id itself.
        ("capacity_license", "capacity_license"),
        # Explicit v2+ suffix is stripped.
        ("capacity_license_v2", "capacity_license"),
        # Multi-digit version.
        ("capacity_license_v10", "capacity_license"),
        ("client_growth_v123", "client_growth"),
        # Suffix must be terminal — a _vN in the middle is not stripped.
        ("something_v2_else", "something_v2_else"),
        # Suffix can't be the whole id — "v2" has no family prefix.
        ("v2", "v2"),
        # _v with no digits is not a version suffix.
        ("subject_vX", "subject_vX"),
        ("backup_v", "backup_v"),
    ],
)
def test_subject_family(subject_id: str, expected: str) -> None:
    assert subject_family(subject_id) == expected
