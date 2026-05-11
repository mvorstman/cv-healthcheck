from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    token_path: Path
    verify_ssl: bool = False
    timeout_seconds: float = 30.0


def project_root() -> Path:
    return Path.cwd()


def load_settings() -> Settings:
    base_url = os.getenv("CV_BASE_URL", "").rstrip("/")
    token_path = Path(os.getenv("CV_TOKEN_PATH", ".token"))
    verify_ssl = _as_bool(os.getenv("CV_VERIFY_SSL"), default=False)
    timeout_seconds = float(os.getenv("CV_TIMEOUT_SECONDS", "30"))

    return Settings(
        base_url=base_url,
        token_path=token_path,
        verify_ssl=verify_ssl,
        timeout_seconds=timeout_seconds,
    )

