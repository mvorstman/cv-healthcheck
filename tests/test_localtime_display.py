"""Display-only UTC->local timestamp rendering (ADR 0007 follow-on).

Two guarantees:
  1. The single server-side seam `localtime_span` emits a machine-readable
     data-localtime span (which localtime.js rewrites to browser-local on load),
     with the raw UTC as fallback text, and a plain placeholder for empty values.
  2. THE HARD CONSTRAINT: a collect still STORES timestamps in UTC (…Z). The
     display change must never re-stamp or localize what is persisted.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from markupsafe import Markup

from cvhealthcheck.web.app import _localtime_span


# ── 1. the server-side display seam ──

def test_localtime_span_wraps_iso_in_data_localtime_with_raw_fallback_text():
    out = _localtime_span("2026-06-01T19:30:00Z")
    assert isinstance(out, Markup)
    html = str(out)
    # machine-readable UTC value rides in the attribute (for localtime.js)…
    assert 'data-localtime="2026-06-01T19:30:00Z"' in html
    # …AND as the element text, so no-JS / bad-value still shows the raw UTC.
    assert ">2026-06-01T19:30:00Z<" in html


def test_localtime_span_empty_value_renders_plain_fallback_not_a_span():
    assert str(_localtime_span(None, "N/A")) == "N/A"
    assert str(_localtime_span("", "Not collected yet")) == "Not collected yet"
    # default fallback is empty.
    assert str(_localtime_span(None)) == ""


def test_localtime_span_escapes_to_avoid_injection():
    out = str(_localtime_span('"><script>x</script>'))
    assert "<script>" not in out          # escaped, not raw markup
    assert "&lt;script&gt;" in out


# ── 2. THE HARD CONSTRAINT: storage stays UTC after a collect ──

_PAYLOAD = {
    "http_status": 200, "ok": True, "error": None,
    "raw": {
        "commcell": {"commCellName": "cs01", "commCellId": 2,
                     "csGUID": "C721DF1F-DB93-41A0-BD28-1EDEB944E34D"},
        "csTimeZone": {"TimeZoneName": "America/Danmarkshavn"},
        "csVersionInfo": "11 SP40.47", "osType": "Unix",
        "currentSPVersion": 40, "installedSPVersion": 40, "hostName": "cs01",
    },
}


def test_collect_still_stores_timestamps_in_utc(migrated_db_path: Path):
    """Guard: after a command-center collect, the SERIALIZED artifact timestamps
    are UTC (…Z) and tz-aware UTC — the display slice changed rendering only."""
    from cvhealthcheck.extractors.command_center import CommandCenterExtractor
    from cvhealthcheck.extractors.result_to_artifact import result_to_artifact

    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        result = CommandCenterExtractor(conn, identity_provider=lambda: _PAYLOAD).extract("environment", 1)
    finally:
        conn.close()
    artifact = result_to_artifact(result, "environment", "CommCell Details")

    # tz-aware UTC on the model.
    assert artifact.source.collected_at is not None
    assert artifact.source.collected_at.utcoffset().total_seconds() == 0
    assert artifact.generated_at.utcoffset().total_seconds() == 0

    # serialized form is UTC ISO-8601 (…Z) — the storage source of truth.
    dumped = artifact.model_dump(mode="json")
    assert dumped["source"]["collected_at"].endswith("Z")
    assert dumped["generated_at"].endswith("Z")
