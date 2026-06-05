"""Unit tests for the shared ADR-0007 D2 field-path resolver
(`extractors.metric_section._resolve_field_path`), focused on the list-index
extension: a numeric path segment indexes into a list (e.g. the
commserve_software_cache table root_key
`commserveSoftwareCache.UaInfo.cacheContents.0.softwareCacheServicePackDetails`).
Dict semantics win; out-of-range / non-numeric / wrong-type -> default. Pure
function — no DB, no canonical store.
"""
from __future__ import annotations

from cvhealthcheck.extractors.metric_section import _resolve_field_path as R


def test_numeric_segment_indexes_into_a_list():
    assert R({"xs": ["a", "b", "c"]}, "xs.0") == "a"
    assert R({"xs": ["a", "b", "c"]}, "xs.2") == "c"


def test_nested_dict_list_dict_value_real_shape():
    # mirrors the live commserve_software_cache path shape (dict -> list -> dict -> value)
    raw = {"commserveSoftwareCache": {"UaInfo": {"cacheContents": [
        {"softwareCacheServicePackDetails": [{"osName": "WinX64"}]},
        {"softwareCacheServicePackDetails": [{"osName": "linux"}]},
    ]}}}
    got = R(raw, "commserveSoftwareCache.UaInfo.cacheContents.0.softwareCacheServicePackDetails")
    assert got == [{"osName": "WinX64"}]
    assert R(raw, "commserveSoftwareCache.UaInfo.cacheContents.1.softwareCacheServicePackDetails.0.osName") == "linux"


def test_out_of_range_index_returns_default():
    assert R({"xs": ["a"]}, "xs.5") is None
    assert R({"xs": []}, "xs.0") is None
    # honors a custom default (the contract _aggregate relies on)
    sentinel = object()
    assert R({"xs": ["a"]}, "xs.5", sentinel) is sentinel


def test_non_numeric_segment_on_a_list_returns_default():
    assert R({"xs": ["a", "b"]}, "xs.name") is None
    assert R({"xs": ["a", "b"]}, "xs.-1") is None      # negative is not isdigit -> default


def test_numeric_segment_on_dict_with_literal_zero_key_resolves_via_dict():
    # dict semantics win: a literal "0" key resolves by key, not list-index logic
    assert R({"m": {"0": "zero-key", "1": "one-key"}}, "m.0") == "zero-key"


def test_existing_dict_only_paths_still_resolve_regression():
    assert R({"a": {"b": {"c": 7}}}, "a.b.c") == 7
    assert R({"a": 1}, "a") == 1
    assert R({"a": {"b": 2}}, "a.x") is None           # missing key -> default
    assert R({"a": 1}, "a.b") is None                  # can't descend into a scalar -> default
    assert R({}, "anything") is None
