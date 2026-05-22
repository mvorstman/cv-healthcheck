from __future__ import annotations

from typing import Any

from cvhealthcheck.artifacts.enums import SourceType
from cvhealthcheck.artifacts.exceptions import AdapterNotFoundError
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.artifacts.store import ArtifactStore
from cvhealthcheck.registry.catalog import get_tile

_store = ArtifactStore()


def build_and_save_artifact(
    subject_id: str,
    source_type: SourceType,
    data: dict[str, Any],
    *,
    store: ArtifactStore | None = None,
) -> CanonicalArtifact:
    tile = get_tile(subject_id)
    if tile is None:
        raise AdapterNotFoundError(
            f"No tile registered for subject_id={subject_id!r}"
        )
    adapter = tile.adapter_map.get(source_type)
    if adapter is None:
        raise AdapterNotFoundError(
            f"No adapter for subject_id={subject_id!r}, source_type=SourceType.{source_type.name}"
        )
    artifact = adapter(data)
    (store or _store).save_artifact(artifact)
    return artifact
