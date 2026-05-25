"""Smoke test for the Quick HC Settings placeholder page.

The Settings page is intentionally minimal — a route target so future
preferences have somewhere obvious to land, plus client-side
inspection and reset of the two localStorage keys (quickhc-theme-v1
and quickhc-state-v1). The page has no server-side state, so the
contract this test pins is small: the route returns 200 for anonymous
callers and the response body contains the page heading.
"""
from __future__ import annotations

from cvhealthcheck.web.app import create_app


def test_quick_hc_settings_route_renders_for_anonymous_user() -> None:
    app = create_app()
    response = app.test_client().get("/quick-hc/settings")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Settings" in body
    # The page exposes the two localStorage keys it manages — verifying
    # they are present in the response body would catch a refactor that
    # renames or removes one without updating the settings page.
    assert "quickhc-theme-v1" in body
    assert "quickhc-state-v1" in body
