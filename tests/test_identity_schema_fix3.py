"""Fix 3 — identity-schema split (ADR-0015 profile layer).

Covers the three kept-distinct identity values, the normalization seams, the
URL-shaped-only migration data move + flag mechanism, the conflation fix
(commserve_name or None, never customer_name), and the commcell_hostname
writer-freeze.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.identity import (
    effective_connection_url,
    normalize_commcell_id,
    normalize_connection_url,
)


# ── CCID normalization (hex ≡ decimal, canonical hex) ─────────────────────────

def test_ccid_hex_and_decimal_are_equal():
    assert normalize_commcell_id("F9EE5") == "f9ee5"
    assert normalize_commcell_id("1023717") == "f9ee5"      # decimal == F9EE5
    assert normalize_commcell_id("0xF9EE5") == "f9ee5"


def test_ccid_already_hex_is_stable():
    assert normalize_commcell_id("337f") == "337f"          # has a hex letter
    assert normalize_commcell_id("337F") == "337f"
    assert normalize_commcell_id("fe111") == "fe111"


def test_ccid_empty_is_none():
    assert normalize_commcell_id(None) is None
    assert normalize_commcell_id("") is None
    assert normalize_commcell_id("   ") is None


@pytest.mark.parametrize("bad", ["SMOKE-TEST-CS", "cs-001", "gw02", "12.3", "0x"])
def test_ccid_junk_raises(bad):
    with pytest.raises(ValueError):
        normalize_commcell_id(bad)


# ── connection URL normalization (scheme repair + validation) ─────────────────

def test_url_schemeless_gets_https():
    assert normalize_connection_url("gw02:4433") == "https://gw02:4433"
    assert normalize_connection_url("cs01.lab:4433") == "https://cs01.lab:4433"


def test_url_with_scheme_preserved_and_trimmed():
    assert normalize_connection_url("http://h:81/") == "http://h:81"
    assert normalize_connection_url("https://192.168.0.1:4433") == "https://192.168.0.1:4433"


def test_url_empty_is_none():
    assert normalize_connection_url(None) is None
    assert normalize_connection_url("  ") is None


def test_url_hostless_raises():
    with pytest.raises(ValueError):
        normalize_connection_url("https://")


def test_effective_connection_url_prefers_new_then_legacy_then_none():
    assert effective_connection_url(
        {"connection_url": "https://new:4433", "commcell_hostname": "https://old:4433"}
    ) == "https://new:4433"
    assert effective_connection_url(
        {"connection_url": None, "commcell_hostname": "gw02:4433"}
    ) == "https://gw02:4433"                                  # legacy fallback, repaired
    assert effective_connection_url({"connection_url": None, "commcell_hostname": None}) is None


# ── migration 0032 data move (URL-shaped only) + flag mechanism ───────────────

def _migration_update_sql() -> str:
    """The exact UPDATE from migration 0032 — loaded, not duplicated, so the
    test moves with the migration."""
    sql = (
        Path(__file__).resolve().parent.parent
        / "src/cvhealthcheck/db/migrations/0032_identity_schema_split.sql"
    ).read_text()
    idx = sql.index("UPDATE customers")
    return sql[idx:]


def test_migration_moves_url_shaped_only_and_flags_the_rest(migrated_db_path: Path):
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    try:
        db.execute("DELETE FROM customers")
        for cid, host in (
            ("https_row", "https://cs01:4433"),
            ("http_row", "http://cs02:81"),
            ("nonurl_row", "gw02:4433"),       # no scheme -> NOT moved, flagged
            ("name_row", "SMOKE-TEST-CS"),     # a name -> NOT moved, flagged
        ):
            db.execute(
                "INSERT INTO customers (customer_id, customer_name, commcell_hostname,"
                " connection_url, created_at, updated_at)"
                " VALUES (?, ?, ?, NULL, '2026-01-01', '2026-01-01')",
                (cid, cid, host),
            )
        db.commit()

        db.executescript(_migration_update_sql())   # re-run the real data move
        db.commit()

        moved = dict(db.execute(
            "SELECT connection_url FROM customers WHERE customer_id IN"
            " ('https_row','http_row')"
        ).fetchall()[0])
        assert db.execute(
            "SELECT connection_url FROM customers WHERE customer_id='https_row'"
        ).fetchone()[0] == "https://cs01:4433"
        assert db.execute(
            "SELECT connection_url FROM customers WHERE customer_id='http_row'"
        ).fetchone()[0] == "http://cs02:81"
        # non-URL values left for manual fix (connection_url still NULL)
        for cid in ("nonurl_row", "name_row"):
            assert db.execute(
                "SELECT connection_url FROM customers WHERE customer_id=?", (cid,)
            ).fetchone()[0] is None

        from cvhealthcheck.db.customers import legacy_hostname_review_flags
        flagged = {f["customer_id"] for f in legacy_hostname_review_flags(db)}
        assert flagged == {"nonurl_row", "name_row"}
    finally:
        db.close()


def test_flag_mechanism_empty_when_all_url_shaped(migrated_db_path: Path):
    db = sqlite3.connect(str(migrated_db_path))
    db.row_factory = sqlite3.Row
    try:
        db.execute("DELETE FROM customers")
        db.execute(
            "INSERT INTO customers (customer_id, customer_name, commcell_hostname,"
            " connection_url, created_at, updated_at)"
            " VALUES ('ok', 'OK', 'https://h:4433', 'https://h:4433',"
            " '2026-01-01', '2026-01-01')"
        )
        db.commit()
        from cvhealthcheck.db.customers import legacy_hostname_review_flags
        assert legacy_hostname_review_flags(db) == []
    finally:
        db.close()


# ── conflation fix: commserve_name or None, NEVER customer_name ───────────────

def _collect_and_capture(monkeypatch, customer: dict):
    """Drive the collect route with a faked extractor + customer, return the
    artifact handed to the store."""
    from cvhealthcheck.web.app import create_app
    from cvhealthcheck.extractors.html import ExtractionResult
    import cvhealthcheck.web.routes.quick_hc as route_module

    res = ExtractionResult(subject_id="capacity_license", source_type="rest")
    res.sections["rows"] = [{"col": "v"}]
    res.section_output_types["rows"] = "table"
    res.section_titles["rows"] = "Rows"

    captured = {}

    class FakeStore:
        def __init__(self, *a, **k): pass
        def save_artifact(self, artifact):
            captured["artifact"] = artifact

    class FakeExtractor:
        def __init__(self, *a, **k): pass
        def extract(self, *a, **k): return res

    monkeypatch.setattr(route_module, "get_active_customer", lambda *a, **k: customer)
    monkeypatch.setattr(route_module, "is_authenticated_for", lambda *a, **k: True)
    monkeypatch.setattr(route_module, "_current_token", lambda *a, **k: "t")
    monkeypatch.setattr(route_module, "RESTExtractor", FakeExtractor)
    monkeypatch.setattr(route_module, "ArtifactStore", FakeStore)
    monkeypatch.setattr(route_module, "CommvaultSession",
                        lambda *a, **k: __import__("contextlib").nullcontext())

    client = create_app().test_client()
    with client.session_transaction() as sess:
        sess["active_project"] = {"customer_id": "c", "project_id": "p"}
    client.post("/quick-hc/capacity_license/collect")
    return captured.get("artifact")


_BASE_CUSTOMER = {
    "customer_id": "c", "customer_name": "Acme Corp",
    "connection_url": "https://h:4433", "commcell_hostname": None,
}


def test_conflation_stamps_commserve_name(monkeypatch):
    cust = {**_BASE_CUSTOMER, "commserve_name": "CS01", "commcell_id": "337f"}
    artifact = _collect_and_capture(monkeypatch, cust)
    assert artifact is not None
    assert artifact.source.commcell_name == "CS01"
    assert artifact.source.commcell_id == "337f"


def test_conflation_none_not_customer_name_when_unset(monkeypatch):
    cust = {**_BASE_CUSTOMER, "commserve_name": None, "commcell_id": None}
    artifact = _collect_and_capture(monkeypatch, cust)
    assert artifact is not None
    assert artifact.source.commcell_name is None      # NOT 'Acme Corp'
    assert artifact.source.commcell_id is None


def test_conflation_bad_ccid_stamps_none_not_crash(monkeypatch):
    cust = {**_BASE_CUSTOMER, "commserve_name": None, "commcell_id": "SMOKE-TEST-CS"}
    artifact = _collect_and_capture(monkeypatch, cust)
    assert artifact is not None
    assert artifact.source.commcell_id is None        # un-normalizable -> None, no 500


# ── writer-freeze: no code path writes commcell_hostname ──────────────────────

def test_commcell_hostname_is_frozen_on_edit(migrated_db_path: Path, monkeypatch):
    """Editing a customer through the route writes connection_url but leaves
    the READ-ONLY-LEGACY commcell_hostname untouched."""
    import cvhealthcheck.web.routes.customers as customers_routes
    from cvhealthcheck.web.app import create_app

    def open_db():
        conn = sqlite3.connect(str(migrated_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    monkeypatch.setattr(customers_routes, "get_db", open_db)

    db = open_db()
    db.execute(
        "INSERT INTO customers (customer_id, customer_name, commcell_hostname,"
        " connection_url, created_at, updated_at)"
        " VALUES ('frz', 'Frozen', 'https://legacy:4433', NULL,"
        " '2026-01-01', '2026-01-01')"
    )
    db.commit()
    db.close()

    app = create_app()
    app.config["SECRET_KEY"] = "test"
    client = app.test_client()
    resp = client.post("/customers/frz/edit", data={
        "customer_name": "Frozen", "connection_url": "https://new:4433",
    })
    assert resp.status_code == 302

    db = open_db()
    row = db.execute(
        "SELECT commcell_hostname, connection_url FROM customers WHERE customer_id='frz'"
    ).fetchone()
    db.close()
    assert row["commcell_hostname"] == "https://legacy:4433"   # FROZEN
    assert row["connection_url"] == "https://new:4433"          # written


def test_no_writer_targets_commcell_hostname_in_sql():
    """Grep-level guard: no INSERT/UPDATE in the customer writer modules names
    commcell_hostname as a WRITE target. It is still SELECTed (read-only-legacy
    + the flag query), so this checks write patterns only, not any mention."""
    import re
    for rel in ("web/routes/customers.py", "db/customers.py"):
        src = (Path(__file__).resolve().parent.parent / "src/cvhealthcheck" / rel).read_text()
        # UPDATE ... commcell_hostname = ?   (assignment target)
        assert not re.search(r"commcell_hostname\s*=\s*\?", src), rel
        # INSERT INTO customers (... commcell_hostname ...)  (write column list)
        assert not re.search(
            r"INSERT\s+INTO\s+customers\s*\([^)]*commcell_hostname", src, re.I | re.S
        ), rel
