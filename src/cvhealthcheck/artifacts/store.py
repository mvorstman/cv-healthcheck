from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import CanonicalArtifact

# store.py: src/cvhealthcheck/artifacts/store.py
# parents[0]=artifacts, parents[1]=cvhealthcheck, parents[2]=src, parents[3]=project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_BASE_DIR = _PROJECT_ROOT / "data" / "catalog" / "artifacts"

_WORKING_DIR_NAME = "working"


class ArtifactStore:
    """Customer/project-scoped artifact store (ADR 0002 phase 2).

    Each instance is bound to a single (customer_id, project_id) pair.
    All read/write operations operate against:

        <base_dir>/<customer_id>/<project_id>/working/<artifact_type>/

    Containing:
        - latest.json                 — current working state for the subject
        - <timestamp>.json            — append-only snapshots of each save

    Finalized snapshots are written by the finalize flow (phase 5) into a
    sibling 'finalized/<N>/' directory; ArtifactStore deliberately does NOT
    expose a write path for those — application-layer immutability (ADR 0002).
    """

    def __init__(
        self,
        customer_id: str,
        project_id: str,
        *,
        base_dir: Path | None = None,
    ) -> None:
        if not customer_id or not project_id:
            raise ValueError(
                "ArtifactStore requires non-empty customer_id and project_id"
            )
        self.customer_id = customer_id
        self.project_id = project_id
        self.base_dir = base_dir if base_dir is not None else _DEFAULT_BASE_DIR

    def _subject_dir(self, artifact_type: str) -> Path:
        return (
            self.base_dir
            / self.customer_id
            / self.project_id
            / _WORKING_DIR_NAME
            / artifact_type
        )

    def save_artifact(self, artifact: CanonicalArtifact) -> Path:
        subject_dir = self._subject_dir(artifact.artifact_type)
        subject_dir.mkdir(parents=True, exist_ok=True)

        payload = artifact.model_dump(mode="json")
        encoded = json.dumps(payload, indent=2, sort_keys=True)

        timestamped_name = _ts_filename(artifact.generated_at.isoformat())
        (subject_dir / timestamped_name).write_text(encoded, encoding="utf-8")

        latest = subject_dir / "latest.json"
        latest.write_text(encoded, encoding="utf-8")
        return latest

    def load_latest_artifact(self, artifact_type: str) -> CanonicalArtifact:
        path = self._subject_dir(artifact_type) / "latest.json"
        if not path.exists():
            raise FileNotFoundError(path)
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return CanonicalArtifact.model_validate(data)

    def delete_artifact(self, artifact_type: str) -> bool:
        """
        Delete all artifact files for the given artifact_type within this
        project's working directory. Removes latest.json and all timestamped
        snapshots. Returns True if anything was deleted, False if nothing
        existed. Finalized snapshots are not touched.
        """
        subject_dir = self._subject_dir(artifact_type)
        if not subject_dir.exists():
            return False
        deleted = False
        for f in subject_dir.glob("*.json"):
            f.unlink()
            deleted = True
        try:
            subject_dir.rmdir()
        except OSError:
            pass
        return deleted


def _ts_filename(iso: str) -> str:
    safe = re.sub(r"[^\w]", "_", iso).strip("_")
    return f"{safe}.json"
