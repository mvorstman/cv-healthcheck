from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.subjects import (
    create_subject_from_proposal,
    get_subject,
    get_subject_sections,
    get_subject_sources,
    list_subjects_from_db,
)


@pytest.fixture()
def db(migrated_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(migrated_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _sample_proposal(**overrides) -> dict:
    base = {
        "subject_id": "storage_utilization",
        "version": 1,
        "title": "Storage Utilization",
        "description": "Storage capacity and usage across entities.",
        "category": "storage",
        "sections": [
            {
                "section_id": "storage_utilization.summary",
                "title": "Summary",
                "section_type": "metric",
                "default_selected": True,
                "sort_order": 1,
            }
        ],
        "extraction_instructions": {
            "html": {
                "extractable": True,
                "non_extractable_reason": None,
                "recognition_hints": {"title_contains": "Storage Utilization"},
                "sections": {
                    "storage_utilization.summary": {"selector": ".summary"},
                },
            }
        },
        "supersedes": None,
        "change_notes": None,
        "related_subjects": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# create_subject_from_proposal
# ---------------------------------------------------------------------------

def test_create_subject_from_proposal_writes_subjects_row(db) -> None:
    created = create_subject_from_proposal(db, _sample_proposal())
    assert created["subject_id"] == "storage_utilization"
    assert created["version"] == 1
    assert created["title"] == "Storage Utilization"
    assert created["status"] == "active"
    assert created["created_by"] == "ai"


def test_create_subject_from_proposal_writes_sections(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    sections = get_subject_sections(db, "storage_utilization", version=1)
    assert len(sections) == 1
    assert sections[0]["section_id"] == "storage_utilization.summary"
    assert sections[0]["section_type"] == "metric"


def test_create_subject_from_proposal_writes_sources(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    sources = get_subject_sources(db, "storage_utilization", version=1)
    assert len(sources) == 1
    source = sources[0]
    assert source["source_type"] == "html"
    assert source["extractable"] is True
    assert source["recognition_hints"] == {"title_contains": "Storage Utilization"}


def test_create_subject_from_proposal_writes_section_extraction_instructions(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    sources = get_subject_sources(db, "storage_utilization", version=1)
    html_source = next(s for s in sources if s["source_type"] == "html")
    assert "storage_utilization.summary" in html_source["sections"]
    assert html_source["sections"]["storage_utilization.summary"] == {"selector": ".summary"}


def test_create_subject_from_proposal_non_extractable_source(db) -> None:
    proposal = _sample_proposal()
    proposal["extraction_instructions"]["html"]["extractable"] = False
    proposal["extraction_instructions"]["html"]["non_extractable_reason"] = "charts_only"
    create_subject_from_proposal(db, proposal)
    sources = get_subject_sources(db, "storage_utilization", version=1)
    html = next(s for s in sources if s["source_type"] == "html")
    assert html["extractable"] is False
    assert html["non_extractable_reason"] == "charts_only"


def test_create_subject_from_proposal_returns_subjects_row_dict(db) -> None:
    created = create_subject_from_proposal(db, _sample_proposal())
    assert isinstance(created, dict)
    assert "id" in created
    assert "subject_id" in created


# ---------------------------------------------------------------------------
# get_subject
# ---------------------------------------------------------------------------

def test_get_subject_returns_active_version(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    row = get_subject(db, "storage_utilization")
    assert row is not None
    assert row["subject_id"] == "storage_utilization"
    assert row["status"] == "active"


def test_get_subject_by_explicit_version(db) -> None:
    create_subject_from_proposal(db, _sample_proposal(version=1))
    row = get_subject(db, "storage_utilization", version=1)
    assert row is not None
    assert row["version"] == 1


def test_get_subject_returns_none_for_missing(db) -> None:
    assert get_subject(db, "nonexistent_subject") is None


def test_get_subject_returns_none_for_missing_version(db) -> None:
    create_subject_from_proposal(db, _sample_proposal(version=1))
    assert get_subject(db, "storage_utilization", version=99) is None


# ---------------------------------------------------------------------------
# list_subjects_from_db
# ---------------------------------------------------------------------------

def test_list_subjects_from_db_returns_seeded_subjects(db) -> None:
    subjects = list_subjects_from_db(db)
    ids = {s["subject_id"] for s in subjects}
    assert "security_assessment" in ids
    assert "license_summary" in ids


def test_list_subjects_from_db_filters_by_status(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    active = list_subjects_from_db(db, status="active")
    assert all(s["status"] == "active" for s in active)

    superseded = list_subjects_from_db(db, status="superseded")
    assert superseded == []


def test_list_subjects_from_db_filters_by_category(db) -> None:
    create_subject_from_proposal(db, _sample_proposal(category="storage"))
    storage = list_subjects_from_db(db, category="storage")
    assert all(s["category"] == "storage" for s in storage)
    assert any(s["subject_id"] == "storage_utilization" for s in storage)


def test_list_subjects_from_db_filters_by_status_and_category(db) -> None:
    create_subject_from_proposal(db, _sample_proposal(category="storage"))
    results = list_subjects_from_db(db, status="active", category="storage")
    assert len(results) == 1
    assert results[0]["subject_id"] == "storage_utilization"


def test_list_subjects_from_db_ordered_by_category_title(db) -> None:
    subjects = list_subjects_from_db(db, status="active")
    pairs = [(s["category"], s["title"]) for s in subjects]
    assert pairs == sorted(pairs)


# ---------------------------------------------------------------------------
# get_subject_sources
# ---------------------------------------------------------------------------

def test_get_subject_sources_returns_joined_section_instructions(db) -> None:
    create_subject_from_proposal(db, _sample_proposal())
    sources = get_subject_sources(db, "storage_utilization")
    assert len(sources) == 1
    html = sources[0]
    assert html["source_type"] == "html"
    assert "storage_utilization.summary" in html["sections"]


def test_get_subject_sources_empty_for_unknown_subject(db) -> None:
    assert get_subject_sources(db, "nonexistent") == []


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def test_supersession_marks_old_version_superseded(db) -> None:
    v1 = create_subject_from_proposal(db, _sample_proposal(version=1))
    create_subject_from_proposal(
        db,
        _sample_proposal(version=2, supersedes=v1["id"], change_notes="Added REST source"),
    )

    v1_fresh = get_subject(db, "storage_utilization", version=1)
    assert v1_fresh is not None
    assert v1_fresh["status"] == "superseded"


def test_supersession_new_version_is_active(db) -> None:
    v1 = create_subject_from_proposal(db, _sample_proposal(version=1))
    create_subject_from_proposal(
        db, _sample_proposal(version=2, supersedes=v1["id"])
    )
    v2 = get_subject(db, "storage_utilization", version=2)
    assert v2 is not None
    assert v2["status"] == "active"


def test_get_subject_without_version_returns_latest_active(db) -> None:
    v1 = create_subject_from_proposal(db, _sample_proposal(version=1))
    create_subject_from_proposal(
        db, _sample_proposal(version=2, supersedes=v1["id"])
    )
    latest = get_subject(db, "storage_utilization")
    assert latest is not None
    assert latest["version"] == 2


# ---------------------------------------------------------------------------
# Transaction rollback
# ---------------------------------------------------------------------------

def test_transaction_rollback_on_missing_section_key(db) -> None:
    proposal = _sample_proposal()
    proposal["sections"] = [{"title": "No section_id here", "section_type": "metric"}]

    with pytest.raises(KeyError):
        create_subject_from_proposal(db, proposal)

    assert get_subject(db, "storage_utilization") is None
