"""Shared redaction module (ADR-0008 D). Direct unit coverage — previously this lived
in the MCP probe tests; the probe is now app-mediated and no longer redacts, so the
shared `redact_user_descriptions` gets its own tests here (the app/endpoint uses it)."""
from __future__ import annotations

from cvhealthcheck.redaction import redact_user_descriptions


def test_redacts_description_keeps_siblings():
    out = redact_user_descriptions({"id": 5, "name": "alice", "description": "topsecretpw"})
    assert out["id"] == 5 and out["name"] == "alice"          # siblings raw/intact
    assert out["description"] == "[redacted: 11 chars]"       # len('topsecretpw') == 11


def test_nested_and_shape_agnostic():
    out = redact_user_descriptions({"outer": {"description": "abc", "keep": 1},
                                    "list": [{"description": "de"}]})
    assert out["outer"]["description"] == "[redacted: 3 chars]"
    assert out["outer"]["keep"] == 1
    assert out["list"][0]["description"] == "[redacted: 2 chars]"


def test_non_string_description_passes_through():
    # Only string descriptions are redacted; a non-str value is left as-is.
    out = redact_user_descriptions({"description": 42, "other": "x"})
    assert out["description"] == 42 and out["other"] == "x"


def test_scalars_and_none_pass_through():
    assert redact_user_descriptions(None) is None
    assert redact_user_descriptions("plain") == "plain"
    assert redact_user_descriptions([1, "two", {"description": "z"}])[2]["description"] == "[redacted: 1 chars]"
