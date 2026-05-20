from __future__ import annotations

from cvhealthcheck.quickhc import overview_service


def test_build_quick_hc_overview_context_aggregates_all_subjects(monkeypatch) -> None:
    monkeypatch.setattr(
        overview_service,
        "catalog_status",
        lambda *args, **kwargs: {"exists": True},
    )
    monkeypatch.setattr(
        overview_service,
        "commcell_quick_hc_preview",
        lambda: {"exists": True, "summary": "commcell"},
    )
    monkeypatch.setattr(
        overview_service,
        "security_assessment_quick_hc_preview",
        lambda: {"exists": True, "summary": "security"},
    )
    monkeypatch.setattr(
        overview_service,
        "license_summary_quick_hc_preview",
        lambda: {"exists": True, "summary": "license"},
    )
    monkeypatch.setattr(
        overview_service,
        "client_growth_quick_hc_preview",
        lambda: {"exists": True, "summary": "growth"},
    )
    monkeypatch.setattr(
        overview_service,
        "capacity_license_quick_hc_preview",
        lambda: {"exists": True, "summary": "capacity"},
    )

    context = overview_service.build_quick_hc_overview_context()

    assert context["commcell_status"] == {"exists": True}
    assert context["commcell_preview"]["summary"] == "commcell"
    assert context["security_assessment"]["summary"] == "security"
    assert context["license_summary"]["summary"] == "license"
    assert context["client_growth"]["summary"] == "growth"
    assert context["capacity_license"]["summary"] == "capacity"
    assert set(context["quick_hc_tiles"]) == {
        "environment",
        "security_assessment",
        "license_summary",
        "client_growth",
        "capacity_license",
    }
