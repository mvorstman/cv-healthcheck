"""Tests for the upload-dispatch module that replaces session 2's
branch dispatch in quick_hc_subject_import.

The dispatch module is data only — these tests verify the lookup
contract: known system subjects with upload behavior return a
non-None handler, everything else returns None.
"""
from __future__ import annotations

from cvhealthcheck.license_summary.service import (
    LicenseSummaryImportError,
    import_license_summary_upload,
)
from cvhealthcheck.security_assessment.service import (
    SecurityAssessmentImportError,
    import_security_assessment_upload,
)
from cvhealthcheck.web.routes.upload_dispatch import (
    UPLOAD_HANDLERS,
    UploadHandler,
    get_handler,
)


def test_security_assessment_handler_is_wired_correctly() -> None:
    handler = get_handler("security_assessment")
    assert handler is not None
    assert isinstance(handler, UploadHandler)
    assert handler.form_field == "assessment_file"
    assert handler.import_fn is import_security_assessment_upload
    assert handler.error_class is SecurityAssessmentImportError
    assert handler.redirect_endpoint == "main.quick_hc_security_assessment"
    # success_format is a callable that produces the flash text from
    # the persisted artifact dict; smoke-test the shape.
    msg = handler.success_format({
        "source_type": "html",
        "source_file": "/tmp/assessment.html",
        "finding_count": 7,
    })
    assert "HTML import completed" in msg
    assert "/tmp/assessment.html" in msg
    assert "7 findings" in msg


def test_license_summary_handler_is_wired_correctly() -> None:
    handler = get_handler("license_summary")
    assert handler is not None
    assert isinstance(handler, UploadHandler)
    assert handler.form_field == "license_summary_file"
    assert handler.import_fn is import_license_summary_upload
    assert handler.error_class is LicenseSummaryImportError
    assert handler.redirect_endpoint == "main.quick_hc_license_summary"
    msg = handler.success_format({
        "source_type": "csv",
        "source_file": "/tmp/ls.csv",
        "other_licenses": [{}, {}, {}],
        "agent_feature_licenses": [{}, {}],
    })
    assert "CSV import completed" in msg
    assert "/tmp/ls.csv" in msg
    assert "3 other licenses" in msg
    assert "2 agent/feature licenses" in msg


def test_ai_subject_returns_none() -> None:
    # AI subjects fall through to the generic dispatcher in the route
    # handler — they have no entry in UPLOAD_HANDLERS.
    assert get_handler("cloud_storage_egress_ingress") is None
    assert get_handler("storage_utilization") is None


def test_unknown_subject_returns_none() -> None:
    assert get_handler("does_not_exist_anywhere") is None


def test_upload_handlers_has_exactly_the_known_two_subjects() -> None:
    # Pins the module's surface: any addition to UPLOAD_HANDLERS is a
    # deliberate change that should also update tests/CHANGELOG/HANDOVER.
    assert set(UPLOAD_HANDLERS.keys()) == {"security_assessment", "license_summary"}
