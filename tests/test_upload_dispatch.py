"""Tests for the upload-dispatch module that replaces session 2's
branch dispatch in quick_hc_subject_import.

The dispatch module is data only — these tests verify the lookup
contract: known system subjects with upload behavior return a
non-None handler, everything else returns None.
"""
from __future__ import annotations

from cvhealthcheck.web.routes.upload_dispatch import (
    UPLOAD_HANDLERS,
    get_handler,
)


def test_security_assessment_routes_generically() -> None:
    # SA migration (PR2): security_assessment no longer has a bespoke upload
    # handler — it falls through to the generic dispatcher path like the other
    # catalog subjects. (The bespoke importer remains for the held #36 dev
    # Security-Assessment cluster's own import route, not the workspace upload.)
    assert get_handler("security_assessment") is None


def test_license_summary_routes_generically() -> None:
    # ADR-0017 routing cleanup: license_summary upload is SWITCHED to the generic
    # dispatcher and the bespoke upload orchestrator + handler were RETIRED.
    # get_handler returns None — LS uploads run through the generic dispatcher.
    assert get_handler("license_summary") is None


def test_ai_subject_returns_none() -> None:
    # AI subjects fall through to the generic dispatcher in the route
    # handler — they have no entry in UPLOAD_HANDLERS.
    assert get_handler("cloud_storage_egress_ingress") is None
    assert get_handler("storage_utilization") is None


def test_unknown_subject_returns_none() -> None:
    assert get_handler("does_not_exist_anywhere") is None


def test_upload_handlers_has_exactly_the_known_subjects() -> None:
    # Pins the module's surface: any change to UPLOAD_HANDLERS is a deliberate
    # change that should also update tests/CHANGELOG/HANDOVER. SA migration removed
    # security_assessment; ADR-0017 removed license_summary — every subject now
    # routes through the generic dispatcher. The dict is empty (the UploadHandler /
    # get_handler machinery remains for any future custom-upload subject).
    assert UPLOAD_HANDLERS == {}
