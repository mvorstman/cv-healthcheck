from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CATALOG_DIR = Path("data/catalog")


def collected_at() -> str:
    return datetime.now(tz=UTC).isoformat()


def write_catalog(
    name: str,
    endpoint_path: str,
    records: Any,
    catalog_dir: Path = CATALOG_DIR,
) -> Path:
    catalog_dir.mkdir(parents=True, exist_ok=True)
    path = catalog_dir / f"{name}.json"
    payload = {
        "collected_at": collected_at(),
        "source_endpoint": endpoint_path,
        "record_count": len(records) if isinstance(records, list) else 0,
        "records": records,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def write_json(name: str, payload: Any, catalog_dir: Path = CATALOG_DIR) -> Path:
    catalog_dir.mkdir(parents=True, exist_ok=True)
    path = catalog_dir / name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def read_json(name: str, catalog_dir: Path = CATALOG_DIR) -> Any:
    path = catalog_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


def catalog_path(name: str, catalog_dir: Path = CATALOG_DIR) -> Path:
    return catalog_dir / name


def catalog_status(name: str, catalog_dir: Path = CATALOG_DIR) -> dict[str, Any]:
    path = catalog_path(name, catalog_dir)
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"exists": True, "path": str(path), "error": "invalid JSON"}
    return {
        "exists": True,
        "path": str(path),
        "collected_at": payload.get("collected_at"),
        "record_count": payload.get("record_count"),
    }
