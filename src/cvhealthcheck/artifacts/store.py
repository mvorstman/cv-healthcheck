from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import CanonicalArtifact

_DEFAULT_BASE_DIR = Path("data/catalog/artifacts")


class ArtifactStore:
    def __init__(self, base_dir: Path = _DEFAULT_BASE_DIR) -> None:
        self.base_dir = base_dir

    def save_artifact(self, artifact: CanonicalArtifact) -> Path:
        subject_dir = self.base_dir / artifact.artifact_type
        subject_dir.mkdir(parents=True, exist_ok=True)

        payload = artifact.model_dump(mode="json")
        encoded = json.dumps(payload, indent=2, sort_keys=True)

        timestamped_name = _ts_filename(artifact.generated_at.isoformat())
        (subject_dir / timestamped_name).write_text(encoded, encoding="utf-8")

        latest = subject_dir / "latest.json"
        latest.write_text(encoded, encoding="utf-8")
        return latest

    def load_latest_artifact(self, artifact_type: str) -> CanonicalArtifact:
        path = self.base_dir / artifact_type / "latest.json"
        if not path.exists():
            raise FileNotFoundError(path)
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return CanonicalArtifact.model_validate(data)


def _ts_filename(iso: str) -> str:
    safe = re.sub(r"[^\w]", "_", iso).strip("_")
    return f"{safe}.json"
