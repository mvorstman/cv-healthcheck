from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

from .enums import ArtifactStatus, ChartType, FindingSeverity, FindingStatus, SourceType


class ArtifactSource(BaseModel):
    type:          SourceType
    report_id:     int | None      = None
    report_name:   str | None      = None
    endpoint:      str | None      = None
    collected_at:  datetime | None = None
    imported_at:   datetime | None = None
    commcell_id:   str | None      = None
    commcell_name: str | None      = None
    # ADR 0004: the subject_id (and therefore the template version) under
    # which this artifact was collected — e.g. "capacity_license" or
    # "capacity_license_v2". Optional on read so artifacts predating ADR 0004
    # phase 1 load cleanly; set on every write through result_to_artifact.
    template_version: str | None   = None


class ArtifactSubject(BaseModel):
    id:    str
    title: str


class SummaryMetric(BaseModel):
    id:    str
    label: str
    value: int | float
    unit:  str | None = None


class ArtifactSummary(BaseModel):
    status:  ArtifactStatus
    metrics: list[SummaryMetric] = Field(default_factory=list)


class FindingReference(BaseModel):
    label: str
    href:  str


class Finding(BaseModel):
    id:             str
    severity:       FindingSeverity
    status:         FindingStatus
    category:       str
    title:          str
    description:    str | None                 = None
    recommendation: str | None                 = None
    references:     list[FindingReference]     = Field(default_factory=list)
    raw_ref:        Any | None                 = None
    # Vendor-stable identifiers preserved across collections so rule
    # overrides have something stable to target. vendor_key is the
    # vendor's text identifier (e.g. Commvault's attrName = "2FAEnabled");
    # vendor_id is the vendor's numeric identifier as a string (e.g.
    # PARAMID = "25018"). Both optional — older artifacts predating
    # 2026-05-28 carry neither.
    vendor_key:     str | None                 = None
    vendor_id:      str | None                 = None


class TableColumn(BaseModel):
    id:    str
    label: str
    unit:  str | None = None


class ChartAxis(BaseModel):
    label: str
    unit:  str | None = None


class ChartSeries(BaseModel):
    id:    str
    label: str
    data:  list[float]


class MetricItem(BaseModel):
    id:    str
    label: str
    value: str | int | float
    unit:  str | None = None


class FindingsSection(BaseModel):
    type:  Literal["findings"]
    id:    str
    title: str
    items: list[Finding] = Field(default_factory=list)


class TableSection(BaseModel):
    type:    Literal["table"]
    id:      str
    title:   str
    columns: list[TableColumn]         = Field(default_factory=list)
    items:   list[dict[str, Any]]      = Field(default_factory=list)


class ChartSection(BaseModel):
    type:       Literal["chart"]
    id:         str
    title:      str
    chart_type: ChartType
    x_axis:     ChartAxis | None = None
    y_axis:     ChartAxis | None = None
    labels:     list[str]        = Field(default_factory=list)
    series:     list[ChartSeries] = Field(default_factory=list)

    @model_validator(mode="after")
    def _labels_match_series(self) -> "ChartSection":
        for s in self.series:
            if len(s.data) != len(self.labels):
                raise ValueError(
                    f"series '{s.id}' has {len(s.data)} points but labels has {len(self.labels)}"
                )
        return self


class MetricSection(BaseModel):
    type:  Literal["metric"]
    id:    str
    title: str
    items: list[MetricItem] = Field(default_factory=list)


Section = Annotated[
    Union[FindingsSection, TableSection, ChartSection, MetricSection],
    Field(discriminator="type"),
]


class CanonicalArtifact(BaseModel):
    schema_version: int = 1
    artifact_type:  str
    generated_at:   datetime
    source:         ArtifactSource
    subject:        ArtifactSubject
    summary:        ArtifactSummary
    sections:       list[Section]        = Field(default_factory=list)
    metadata:       dict[str, Any]       = Field(default_factory=dict)
