from __future__ import annotations

import json
from typing import Any


def to_pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)

