from __future__ import annotations

from typing import Any


def _find_values_by_key(value: Any, key_names: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in key_names:
                found.append(child)
            found.extend(_find_values_by_key(child, key_names))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_values_by_key(child, key_names))
    return found


def summarize_dataset_metadata(metadata: Any) -> dict[str, Any]:
    return {
        "fields": _find_values_by_key(metadata, {"fields", "columns"}),
        "parameters": _find_values_by_key(metadata, {"parameters", "params"}),
        "backend": _find_values_by_key(metadata, {"backend", "backendtype", "type"}),
        "sql": _find_values_by_key(metadata, {"sql", "query", "storedprocedure", "sp"}),
    }

