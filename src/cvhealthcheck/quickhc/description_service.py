from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cvhealthcheck.quickhc.registry import QUICK_HC_TILE_BY_ID
from cvhealthcheck.reportsplus.catalog import read_json, write_json

DESCRIPTION_CATALOG_DIR = Path("data/catalog/quickhc/descriptions")


def description_override_path(
    tile_id: str,
    *,
    catalog_dir: Path | None = None,
) -> Path:
    return (catalog_dir or DESCRIPTION_CATALOG_DIR) / f"{tile_id}.json"


def load_description_override(
    tile_id: str,
    *,
    catalog_dir: Path | None = None,
) -> dict[str, Any] | None:
    try:
        return read_json(
            f"{tile_id}.json",
            catalog_dir=catalog_dir or DESCRIPTION_CATALOG_DIR,
        )
    except FileNotFoundError:
        return None


def resolve_tile_description(
    tile_id: str,
    *,
    catalog_dir: Path | None = None,
) -> str:
    tile = QUICK_HC_TILE_BY_ID[tile_id]
    payload = load_description_override(tile_id, catalog_dir=catalog_dir)
    description = str((payload or {}).get("description") or "").strip()
    return description or tile.description


def save_description_override(
    tile_id: str,
    description: str,
    *,
    catalog_dir: Path | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    if tile_id not in QUICK_HC_TILE_BY_ID:
        raise KeyError(tile_id)
    payload: dict[str, Any] = {
        "tile_id": tile_id,
        "description": description.strip(),
        "updated_at": datetime.now(UTC).isoformat(),
        "version": 1,
    }
    if updated_by:
        payload["updated_by"] = updated_by
    write_json(
        f"{tile_id}.json",
        payload,
        catalog_dir or DESCRIPTION_CATALOG_DIR,
    )
    return payload
