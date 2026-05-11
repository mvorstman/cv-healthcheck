from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ReadinessState(StrEnum):
    NOT_READY = "NOT_READY"
    READY_FOR_DISCOVERY = "READY_FOR_DISCOVERY"
    READY_FOR_DATA_EXECUTION = "READY_FOR_DATA_EXECUTION"
    READY_FOR_HEALTH_RULE_TESTING = "READY_FOR_HEALTH_RULE_TESTING"


@dataclass(frozen=True)
class Indicator:
    name: str
    value: Any
    status: str
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status,
            "notes": self.notes,
        }
