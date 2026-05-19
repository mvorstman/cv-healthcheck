from __future__ import annotations

from dataclasses import asdict, dataclass


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
    hostName: str | None = None
    csGUID: str | None = None
    csVersionInfo: str | None = None
    releaseId: str | int | None = None
    osType: str | None = None
    timeZone: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


@dataclass(frozen=True)
class SectionDefinition:
    id: str
    label: str
    default_selected: bool = True
    preview_renderer: str | None = None
    report_renderer: str | None = None


@dataclass(frozen=True)
class TileDefinition:
    id: str
    title: str
    subtitle: str
    source_type: str
    source_service: str
    artifact_type: str
    preview_renderer: str
    report_renderer: str
    sections: tuple[SectionDefinition, ...]
    report_label: str | None = None
    detail_endpoint: str | None = None
    status_behavior: str = "available_or_missing"
    collect_capable: bool = False
    import_capable: bool = False

    @property
    def display_label(self) -> str:
        return self.title

    @property
    def effective_report_label(self) -> str:
        return self.report_label or self.title
