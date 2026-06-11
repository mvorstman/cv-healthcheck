"""ADR 0014 — directly-addressed Reports Plus dataset source, end to end:

  persist — create_subject_from_proposal validates + stores dataset_address
            in recognition_hints (required; invalid/missing rolls back).
  collect — ReportsPlusDatasetExtractor reads the address back, validates
            declared parameter names against dataset metadata (the engine
            silently ignores unknown names — gate finding 3), encodes
            parameters to parameter.<name> / parameter.<name>[] forms, and
            ends at ExtractionResult feeding the unchanged result_to_artifact
            tail (SourceType.rest, live -> collected_at set).

The session is a fake (fetch_dataset + get_dataset_metadata); no network.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.db.subjects import create_subject_from_proposal
from cvhealthcheck.extractors.reportsplus_dataset import (
    REPORTSPLUS_DATASET_SOURCE_TYPE,
    ReportsPlusDatasetExtractor,
)
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.extractors.rp_dataset_address import AddressPolicyError

_BARE = "2b3e43c0-21fe-401d-ebf8-c485309262a7"
_COMPOSITE = "d7faef75-cf66-40a2-98ce-a2d0cc2a144b:02878d11-7f2c-499b-a1c4-b40372639c17"


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class FakeSession:
    """Duck-typed CommvaultSession: records calls, returns canned data."""

    def __init__(
        self,
        rows: list[dict] | None = None,
        declared_params: list[str] | None = None,
        metadata_error: Exception | None = None,
        fetch_error: Exception | None = None,
    ) -> None:
        self.rows = rows if rows is not None else [{"name": "alpha", "total": 3}]
        self.declared_params = declared_params or []
        self.metadata_error = metadata_error
        self.fetch_error = fetch_error
        self.fetch_calls: list[dict] = []
        self.metadata_calls: list[str] = []

    def get_dataset_metadata(self, dataset_guid: str) -> dict:
        self.metadata_calls.append(dataset_guid)
        if self.metadata_error is not None:
            raise self.metadata_error
        return {
            "GetOperation": {
                "parameters": [{"name": n} for n in self.declared_params],
            },
        }

    def fetch_dataset(self, dataset_guid, fields=None, orderby=None,
                      limit=None, parameters=None):
        self.fetch_calls.append({
            "address": dataset_guid, "fields": fields, "orderby": orderby,
            "limit": limit, "parameters": parameters,
        })
        if self.fetch_error is not None:
            raise self.fetch_error
        return list(self.rows)


def _proposal(subject_id: str, address: object, section_extraction: dict | None = None,
              include_address: bool = True) -> dict:
    extraction = section_extraction or {"output_as": "table"}
    source_info: dict = {
        "extractable": True,
        "sections": {"rows": extraction},
    }
    if include_address:
        source_info["dataset_address"] = address
    return {
        "subject_id": subject_id,
        "version": 1,
        "title": "RP Dataset Test",
        "description": "ADR 0014 mechanism test (throwaway).",
        "category": "operations",
        "sections": [
            {"section_id": "rows", "title": "Rows", "section_type": "table",
             "default_selected": True, "sort_order": 0},
        ],
        "extraction_instructions": {REPORTSPLUS_DATASET_SOURCE_TYPE: source_info},
    }


# ── persist (D2 analog of the CC endpoint write) ───────────────────────────────

def test_proposal_persists_validated_address_into_recognition_hints(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        create_subject_from_proposal(db, _proposal("_rp_persist", _COMPOSITE.upper()))
        row = db.execute(
            "SELECT recognition_hints FROM subject_sources"
            " WHERE subject_id = '_rp_persist' AND source_type = ?",
            (REPORTSPLUS_DATASET_SOURCE_TYPE,),
        ).fetchone()
        hints = json.loads(row["recognition_hints"])
        assert hints["dataset_address"] == _COMPOSITE  # lowercase-normalized
    finally:
        db.close()


@pytest.mark.parametrize("address,include", [
    ("not-a-guid", True),
    (f"/datasets/{_BARE}/data", True),
    (None, False),                       # address omitted entirely — required
])
def test_proposal_with_bad_or_missing_address_rolls_back(
    migrated_db_path: Path, address, include
):
    db = _conn(migrated_db_path)
    try:
        with pytest.raises(AddressPolicyError):
            create_subject_from_proposal(
                db, _proposal("_rp_bad", address, include_address=include)
            )
        gone = db.execute(
            "SELECT COUNT(*) AS n FROM subjects WHERE subject_id = '_rp_bad'"
        ).fetchone()["n"]
        assert gone == 0  # all-or-nothing
    finally:
        db.close()


# ── collect ────────────────────────────────────────────────────────────────────

def _approved(db, subject_id, address, extraction):
    create_subject_from_proposal(db, _proposal(subject_id, address, extraction))


def test_extract_table_rows_and_artifact_tail(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_collect", _COMPOSITE, {"output_as": "table"})
        session = FakeSession(rows=[{"name": "alpha", "total": 3},
                                    {"name": "beta", "total": 7}])
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_collect", 1)

        assert result.errors == []
        assert result.sections["rows"] == [{"name": "alpha", "total": 3},
                                           {"name": "beta", "total": 7}]
        assert session.fetch_calls[0]["address"] == _COMPOSITE
        # no parameters declared -> the metadata endpoint is never called
        assert session.metadata_calls == []

        artifact = result_to_artifact(result, subject_id="_rp_collect",
                                      subject_title="RP Dataset Test")
        assert artifact.source.type == SourceType.rest        # resolved mapping
        assert artifact.source.collected_at is not None       # live source
    finally:
        db.close()


def test_declared_parameters_are_validated_and_encoded(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_params", _BARE, {
            "output_as": "table",
            "parameters": {"userlist": [1, 2], "i_days": 7},
        })
        session = FakeSession(declared_params=["userlist", "i_days", "Company"])
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_params", 1)

        assert result.errors == []
        assert session.metadata_calls == [_BARE]
        assert session.fetch_calls[0]["parameters"] == {
            "parameter.userlist[]": [1, 2],
            "parameter.i_days": 7,
        }
    finally:
        db.close()


def test_undeclared_parameter_name_fails_loudly_before_any_fetch(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_typo", _BARE, {
            "output_as": "table",
            "parameters": {"userlst": [1]},          # typo'd name
        })
        session = FakeSession(declared_params=["userlist"])
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_typo", 1)

        assert len(result.errors) == 1
        assert "userlst" in result.errors[0]
        assert "userlist" in result.errors[0]        # names the declared set
        assert session.fetch_calls == []             # nothing collected
        assert result.sections == {}
    finally:
        db.close()


def test_metadata_failure_fails_whole_collection(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_metafail", _BARE, {
            "output_as": "table",
            "parameters": {"userlist": [1]},
        })
        session = FakeSession(metadata_error=RuntimeError("boom"))
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_metafail", 1)

        assert len(result.errors) == 1
        assert "metadata" in result.errors[0]
        assert session.fetch_calls == []
    finally:
        db.close()


def test_fetch_error_fails_whole_collection(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_fetchfail", _BARE, {"output_as": "table"})
        session = FakeSession(fetch_error=RuntimeError("dataset down"))
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_fetchfail", 1)

        assert len(result.errors) == 1
        assert "fetch_dataset" in result.errors[0]
        assert result.sections == {}
    finally:
        db.close()


def test_missing_source_row_or_address_is_loud(migrated_db_path: Path):
    db = _conn(migrated_db_path)
    try:
        result = ReportsPlusDatasetExtractor(db, FakeSession()).extract("_rp_nothing", 1)
        assert result.errors  # no instructions at all
    finally:
        db.close()


def test_row_shaping_vocabulary_applies(migrated_db_path: Path):
    """column_map / null_values run through the shared shape_dataset_rows."""
    db = _conn(migrated_db_path)
    try:
        _approved(db, "_rp_shape", _BARE, {
            "output_as": "table",
            "null_values": ["N/A"],
            "column_map": [
                {"source": "name", "canonical": "client", "type": "string"},
                {"source": "total", "canonical": "count", "type": "int"},
            ],
        })
        session = FakeSession(rows=[{"name": "alpha", "total": "N/A"}])
        result = ReportsPlusDatasetExtractor(db, session).extract("_rp_shape", 1)
        assert result.errors == []
        assert result.sections["rows"] == [{"client": "alpha", "count": None}]
    finally:
        db.close()
