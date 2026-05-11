from __future__ import annotations

import json
from pathlib import Path


def load_token(token_path: Path | str = ".token") -> str | None:
    path = Path(token_path)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if isinstance(parsed, dict):
        token = parsed.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()

    return raw

