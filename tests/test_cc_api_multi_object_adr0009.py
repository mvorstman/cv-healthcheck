"""ADR 0009 D1 + D2 — the generalized Command Center API source.

Covers the *mechanism*, shape-agnostic: a synthetic multi-record collection
(NOT a `/v4/servergroup` payload — that shape is unverified until the Step-5 live
capture). Proves:

  D1 axis 1 — the extractor collects from a binding-declared relative endpoint
              (default CommServ), validated relative + read-only.
  D1 axis 2 — `output_as: "table"` projects a multi-record collection into rows
              that flow through the unchanged result_to_artifact -> TableSection.
  D2        — an MCP proposal can declare `rest_command_center_api` + an explicit
              relative endpoint; create_subject_from_proposal persists it into
              recognition_hints and rejects a non-relative / non-read-only one.

All offline: the network fetch is replaced by an injected identity_provider.
"""
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.models import CanonicalArtifact, TableSection
from cvhealthcheck.db.subjects import create_subject_from_proposal, get_subject_sources
from cvhealthcheck.extractors.cc_endpoint import (
    DEFAULT_CC_ENDPOINT,
    EndpointPolicyError,
    validate_cc_endpoint,
)
from cvhealthcheck.extractors.command_center import (
    COMMAND_CENTER_SOURCE_TYPE,
    CommandCenterExtractor,
    _project_table_rows,
)
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# A synthetic collection response — generic on purpose (the real servergroup
# shape is unverified until Step 5).
_COLLECTION = {
    "http_status": 200,
    "ok": True,
    "error": None,
    "raw": {
        "items": [
            {"name": "alpha", "stats": {"total": 3}, "extra": "dropped"},
            {"name": "beta", "stats": {"total": 7}},
        ]
    },
}


def _table_proposal(subject_id: str, endpoint: str) -> dict:
    section_id = f"{subject_id}.rows"
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": "CC Table Mechanism Test",
        "description": "ADR 0009 mechanism test (throwaway).",
        "category": "operations",
        "sections": [
            {"section_id": section_id, "title": "Rows", "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {
            COMMAND_CENTER_SOURCE_TYPE: {
                "extractable": True,
                "endpoint": endpoint,
                "sections": {
                    section_id: {
                        "output_as": "table",
                        "table": {
                            "root_key": "items",
                            "columns": [
                                {"id": "Name", "field": "name"},
                                {"id": "Count", "field": "stats.total"},
                            ],
                        },
                    },
                },
            },
        },
    }


# ── cc_endpoint policy (D2 / D4) ──────────────────────────────────────────────

def test_validate_cc_endpoint_defaults_and_accepts_relative():
    assert validate_cc_endpoint(None) == DEFAULT_CC_ENDPOINT
    assert validate_cc_endpoint("   ") == DEFAULT_CC_ENDPOINT
    assert validate_cc_endpoint("/commandcenter/api/v4/servergroup") == \
        "/commandcenter/api/v4/servergroup"


@pytest.mark.parametrize("bad", [
    "https://192.168.182.129:4433/commandcenter/api/v4/servergroup",  # absolute
    "//evil.example/commandcenter/api/x",                              # protocol-relative
    "/api/v4/servergroup",                                             # outside CC namespace
    "/commandcenter/api/../../etc/passwd",                             # traversal
    "/commandcenter/api/v4/server group",                             # whitespace
    "/commandcenter/api/v4\\servergroup",                            # backslash
    1234,                                                              # non-string
])
def test_validate_cc_endpoint_rejects_out_of_policy(bad):
    with pytest.raises(EndpointPolicyError):
        validate_cc_endpoint(bad)


# ── _project_table_rows (D1 axis 2, pure) ─────────────────────────────────────

def test_project_table_rows_with_column_map_selects_and_renames():
    spec = {"root_key": "items",
            "columns": [{"id": "Name", "field": "name"},
                        {"id": "Count", "field": "stats.total"}]}
    rows = _project_table_rows(_COLLECTION["raw"], spec)
    assert rows == [{"Name": "alpha", "Count": 3}, {"Name": "beta", "Count": 7}]


def test_project_table_rows_passthrough_without_columns():
    spec = {"root_key": "items"}
    rows = _project_table_rows({"items": [{"a": 1}, {"a": 2}]}, spec)
    assert rows == [{"a": 1}, {"a": 2}]


def test_project_table_rows_top_level_list_and_degenerate_cases():
    assert _project_table_rows([{"a": 1}], {}) == [{"a": 1}]          # raw is the list
    assert _project_table_rows({"items": "nope"}, {"root_key": "items"}) == []
    assert _project_table_rows({"other": []}, {"root_key": "items"}) == []
    assert _project_table_rows(["x", 2], {}) == [{"value": "x"}, {"value": 2}]


def test_project_table_rows_wraps_single_object_under_root_key():
    """A root_key resolving to a DICT (a single-object response, e.g.
    ``auditTrailInfo: {...}``) is a one-row table — auto-wrapped as [obj], not an
    empty table. The existing LIST case is unaffected."""
    raw = {"auditTrailInfo": {"retention_critical": 90, "retention_high": 365}}
    spec = {"root_key": "auditTrailInfo",
            "columns": [{"id": "retention_critical", "field": "retention_critical"},
                        {"id": "retention_high", "field": "retention_high"}]}
    # dict-wrap: exactly one row, fields projected
    assert _project_table_rows(raw, spec) == [{"retention_critical": 90, "retention_high": 365}]
    # passthrough (no columns) of a single object → one row, unchanged
    assert _project_table_rows({"obj": {"a": 1}}, {"root_key": "obj"}) == [{"a": 1}]
    # the existing multi-record LIST path is unchanged
    list_spec = {"root_key": "items", "columns": [{"id": "Name", "field": "name"}]}
    assert _project_table_rows(_COLLECTION["raw"], list_spec) == [{"Name": "alpha"}, {"Name": "beta"}]


# ── D1 axis 1: endpoint resolution from the binding ───────────────────────────

def test_environment_resolves_to_default_commserv_endpoint(migrated_db_path: Path):
    """environment has recognition_hints = NULL on its CC source -> default
    CommServ endpoint (byte-for-byte unchanged from ADR 0007)."""
    conn = _conn(migrated_db_path)
    try:
        ext = CommandCenterExtractor(conn)
        assert ext._resolve_endpoint("environment", 1) == DEFAULT_CC_ENDPOINT
    finally:
        conn.close()


# ── D2 persist + D1 axis 2: full propose -> persist -> extract -> artifact ─────

def test_proposed_cc_table_subject_persists_endpoint_and_collects_table(migrated_db_path: Path):
    conn = _conn(migrated_db_path)
    try:
        proposal = _table_proposal("_cc_table_test", "/commandcenter/api/v4/anything")
        create_subject_from_proposal(conn, proposal)

        # D2: the declared endpoint landed in recognition_hints (no schema column).
        sources = get_subject_sources(conn, "_cc_table_test", 1)
        cc = next(s for s in sources if s["source_type"] == COMMAND_CENTER_SOURCE_TYPE)
        assert cc["recognition_hints"]["endpoint"] == "/commandcenter/api/v4/anything"

        # the extractor reads that endpoint back from the binding ...
        ext = CommandCenterExtractor(conn, identity_provider=lambda: _COLLECTION)
        assert ext._resolve_endpoint("_cc_table_test", 1) == "/commandcenter/api/v4/anything"

        # D1 axis 2: ... and projects the collection into table rows.
        result = ext.extract("_cc_table_test", 1)
    finally:
        conn.close()

    assert not result.errors
    section_id = "_cc_table_test.rows"
    assert result.section_output_types[section_id] == "table"
    assert result.sections[section_id] == [
        {"Name": "alpha", "Count": 3}, {"Name": "beta", "Count": 7},
    ]

    artifact = result_to_artifact(result, "_cc_table_test", "CC Table Mechanism Test")
    CanonicalArtifact.model_validate(artifact.model_dump())  # reload validates
    # classified as the Command Center source type, live-collected (collected_at).
    assert artifact.source.type == SourceType.rest_commserve
    assert artifact.source.collected_at is not None
    table = next(s for s in artifact.sections if isinstance(s, TableSection))
    assert table.items == [{"Name": "alpha", "Count": 3}, {"Name": "beta", "Count": 7}]
    assert [c.id for c in table.columns] == ["Name", "Count"]


def test_proposed_cc_subject_with_absolute_endpoint_is_rejected(migrated_db_path: Path):
    """A non-relative endpoint is rejected at persist time -> the whole proposal
    write rolls back (no partial subject left behind)."""
    conn = _conn(migrated_db_path)
    try:
        proposal = _table_proposal(
            "_cc_bad_endpoint", "https://attacker.example/commandcenter/api/x"
        )
        with pytest.raises(EndpointPolicyError):
            create_subject_from_proposal(conn, proposal)
        # rolled back: the subject row is not present.
        row = conn.execute(
            "SELECT 1 FROM subjects WHERE subject_id = ?", ("_cc_bad_endpoint",)
        ).fetchone()
        assert row is None
    finally:
        conn.close()
