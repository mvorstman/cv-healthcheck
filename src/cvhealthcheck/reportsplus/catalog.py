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
        "source": endpoint_path,
        "records": records,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path
