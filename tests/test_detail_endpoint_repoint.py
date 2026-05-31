"""ADR 0004 #25 / phase 6.5 — detail_endpoint repoint guard.

Phase 6.5 retires the Development-page dev tools, including the per-metric dev
pages (main.metrics_client_growth / main.metrics_capacity_license). Two tiles
used to point their report "detail" link at those dev pages; phase 6.5 repoints
them at the canonical workspace (main.quick_hc), where client_growth (phase 6)
and capacity_license (phase 5) now render natively.

These tests are the repoint-FIRST guard: every tile's detail_endpoint must
resolve under a real app context (so deleting the dev routes can't strand a
url_for() into a BuildError -> 500 on the report page), and no tile may point at
a retired dev metrics route.
"""
from __future__ import annotations

from cvhealthcheck.quickhc.registry import list_tiles
from cvhealthcheck.quickhc.report_service import _detail_url_for_tile
from cvhealthcheck.web.app import create_app


_RETIRED_DEV_ENDPOINTS = {
    "main.metrics_client_growth",
    "main.metrics_capacity_license",
    "main.metrics_client_count",
}


def test_no_tile_points_at_a_retired_dev_metrics_route() -> None:
    offenders = {
        tile.id: tile.detail_endpoint
        for tile in list_tiles()
        if tile.detail_endpoint in _RETIRED_DEV_ENDPOINTS
    }
    assert not offenders, f"tiles still point at retired dev routes: {offenders}"


def test_every_tile_detail_endpoint_resolves_under_app_context() -> None:
    app = create_app()
    with app.test_request_context():
        for tile in list_tiles():
            if not tile.detail_endpoint:
                continue
            # url_for() raises BuildError if the endpoint no longer exists; a
            # truthy "/..." path proves the link is live post-deletion.
            url = _detail_url_for_tile(tile)
            assert url and url.startswith("/"), (tile.id, tile.detail_endpoint, url)


def test_migrated_metric_tiles_open_the_workspace() -> None:
    by_id = {tile.id: tile for tile in list_tiles()}
    for tile_id in ("client_growth", "capacity_license"):
        assert by_id[tile_id].detail_endpoint == "main.quick_hc"
