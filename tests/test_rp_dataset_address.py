"""Unit tests for the ADR-0014 Reports Plus dataset address/parameter policy
(``extractors.rp_dataset_address``) — the leaf validation both the persist path
(``create_subject_from_proposal``) and the collect path (extractor) apply to
AI-asserted input. Pure functions — no DB, no network.
"""
from __future__ import annotations

import pytest

from cvhealthcheck.extractors.rp_dataset_address import (
    AddressPolicyError,
    ParameterPolicyError,
    encode_dataset_parameters,
    validate_rp_dataset_address,
)

_BARE = "2b3e43c0-21fe-401d-ebf8-c485309262a7"
_COMPOSITE = "d7faef75-cf66-40a2-98ce-a2d0cc2a144b:02878d11-7f2c-499b-a1c4-b40372639c17"


# ── address grammar ────────────────────────────────────────────────────────────

def test_accepts_bare_guid_and_composite():
    assert validate_rp_dataset_address(_BARE) == _BARE
    assert validate_rp_dataset_address(_COMPOSITE) == _COMPOSITE


def test_normalizes_case_and_whitespace():
    assert validate_rp_dataset_address(f"  {_BARE.upper()}  ") == _BARE


@pytest.mark.parametrize("bad", [
    None,                                     # no default — required (unlike CC endpoint)
    "",
    "not-a-guid",
    _BARE + ":",                              # dangling separator
    ":" + _BARE,
    f"{_BARE}:{_BARE}:{_BARE}",               # three parts
    f"/datasets/{_BARE}",                     # a path, not an address
    f"{_BARE}/data",
    f"{_BARE}?limit=1",
    "https://host/commandcenter/api/cr/reportsplusengine/datasets/" + _BARE,
    12345,
])
def test_rejects_out_of_grammar(bad):
    with pytest.raises(AddressPolicyError):
        validate_rp_dataset_address(bad)


# ── parameter encoding ─────────────────────────────────────────────────────────

def test_scalar_and_list_parameters_encode_to_query_forms():
    assert encode_dataset_parameters({"i_days": 7, "Company": "ALL"}) == {
        "parameter.i_days": 7,
        "parameter.Company": "ALL",
    }
    # list value -> repeated name[] form (gate finding 3)
    assert encode_dataset_parameters({"userlist": [1, 2]}) == {
        "parameter.userlist[]": [1, 2],
    }


def test_empty_or_none_parameters_encode_to_empty():
    assert encode_dataset_parameters(None) == {}
    assert encode_dataset_parameters({}) == {}


@pytest.mark.parametrize("bad", [
    {"parameter.i_days": 7},                  # pre-prefixed — authors pass bare names
    {"i days": 7},                            # not identifier-shaped
    {"1abc": 7},
    {"a[]": 7},
    {"ok": {"nested": 1}},                    # non-scalar value
    {"ok": [1, [2]]},                         # non-scalar inside list
])
def test_rejects_out_of_shape_parameters(bad):
    with pytest.raises(ParameterPolicyError):
        encode_dataset_parameters(bad)
