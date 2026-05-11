from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HealthFinding:
    check_id: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthReport:
    findings: list[HealthFinding] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings": [
                {
                    "check_id": finding.check_id,
                    "status": finding.status,
                    "message": finding.message,
                    "details": finding.details,
                }
                for finding in self.findings
            ]
        }

