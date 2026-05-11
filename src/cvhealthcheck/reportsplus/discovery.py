from __future__ import annotations

from typing import Any

from .metadata import summarize_dataset_metadata


def discover_dataset_shape(metadata: Any) -> dict[str, Any]:
    return summarize_dataset_metadata(metadata)

