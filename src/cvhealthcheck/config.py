from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    token_path: Path
    verify_ssl: bool = True
    timeout_seconds: float = 30.0
    # ADR-0008 C: shared secret guarding the loopback internal endpoint. Set
    # out-of-band via CV_INTERNAL_SECRET in ~/.cv-healthcheck-env (never in repo);
    # None when unset, so the endpoint fails closed (503).
    internal_secret: str | None = None


def project_root() -> Path:
    return Path.cwd()


def load_settings() -> Settings:
    base_url = os.getenv("CV_BASE_URL", "").rstrip("/")
    token_path = Path(os.getenv("CV_TOKEN_FILE") or os.getenv("CV_TOKEN_PATH", ".token"))
    verify_ssl = _as_bool(os.getenv("CV_VERIFY_SSL"), default=True)
    timeout_seconds = float(os.getenv("CV_TIMEOUT") or os.getenv("CV_TIMEOUT_SECONDS", "30"))
    internal_secret = os.getenv("CV_INTERNAL_SECRET") or None

    return Settings(
        base_url=base_url,
        token_path=token_path,
        verify_ssl=verify_ssl,
        timeout_seconds=timeout_seconds,
        internal_secret=internal_secret,
    )


def warn_if_ssl_verification_disabled(settings: Settings, *, component: str) -> None:
    if settings.verify_ssl:
        return
    logger.warning(
        "SSL certificate verification is disabled for %s. "
        "Set CV_VERIFY_SSL=true unless this is an isolated lab environment.",
        component,
    )
