from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class QuickHcSource:
    mode: str
    subject: str
    endpoint: str
    method: str
    auth: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CommCellIdentity:
    hostName: str | None
    csGUID: str | None
    csVersionInfo: Any
    releaseId: Any
    osType: str | None
    timeZone: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
