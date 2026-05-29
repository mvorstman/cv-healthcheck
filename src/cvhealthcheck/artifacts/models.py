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
    # None entries are gaps (no data for that label) — e.g. capacity_license's
    # inactive months (-1 / null in the source). The chart renderer draws them
    # as breaks in the line (spanGaps:false), distinct from a real 0.
    data:  list[float | None]


class VerdictEntry(BaseModel):
    """One layer of an evaluative verdict chain (ADR 0004 §"Rules layering").

    Phase 2 emits a single ``template_default`` entry per evaluated metric.
    Phase 8 prepends a ``vendor`` layer and appends ``override`` layers to the
    same structure, and resolves rules by ``rule_id`` against a rules registry.
    """
    layer:    str                       # vendor | template_default | override
    severity: FindingSeverity
    rule_id:  str | None = None
    reason:   str                       # human-readable, populated — makes the verdict auditable


class MetricItem(BaseModel):
    id:    str
    label: str
    # None means "not applicable / no data" — a sentinel-resolved value
    # (e.g. capacity_license's -1 = "license not active that month"), kept
    # distinct from a real zero. The renderer shows it as "n/a".
    value: str | int | float | None = None
    unit:  str | None = None
    # True when this value was computed at collection time via a CEL
    # expression (ADR 0004 derived value) rather than read from a raw field.
    derived: bool = False
    # ADR 0004 evaluative face: the resolved severity for this metric and the
    # verdict chain that produced it. Empty/None for metrics with no rule.
    severity:      FindingSeverity | None = None
    verdict_chain: list[VerdictEntry]     = Field(default_factory=list)


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


class CardItem(BaseModel):
    label: str
    value: str | int | float | None = None   # None renders as "—"
    unit:  str | None = None


class CardSection(BaseModel):
    """ADR 0004 card section — a flat, labeled key-value identity block
    ("typically one row"). Distinct from a metric (emphasized/derived values):
    a card is a labeled grid of fields.

    Per the phase-4 steering decision, a card DOES carry a section-level verdict
    (the compliance engine judges every card), reusing the EXACT severity +
    verdict_chain shape MetricItem carries — so card and metric verdicts are
    structurally identical. This duplication of the evaluative shape across
    MetricItem and CardSection is intentional and temporary; phase 8 unifies the
    evaluative face into one shared section-level concern.
    """
    type:          Literal["card"]
    id:            str
    title:         str
    items:         list[CardItem] = Field(default_factory=list)
    # Presentational grid hint; None = auto (renderer picks columns by count).
    columns:       int | None = None
    # Evaluative face (reused from the metric machinery — same enum / VerdictEntry).
    severity:      FindingSeverity | None = None
    verdict_chain: list[VerdictEntry]     = Field(default_factory=list)


class MetricSection(BaseModel):
    type:  Literal["metric"]
    id:    str
    title: str
    items: list[MetricItem] = Field(default_factory=list)
    # ADR 0004 presentational face — declared render intent, NOT inferred from
    # whether items carry a severity. "metric" = the rich phase-2 renderer
    # (values, derived values, severity badges); "meta" = the plain key/value
    # block (License Summary's commcell_info predates the metric renderer and
    # defaults here, so its rendering is unchanged). Set to "metric" by
    # build_metric_section when the catalog declares output_as == "metric".
    render_mode: Literal["meta", "metric"] = "meta"


Section = Annotated[
    Union[FindingsSection, TableSection, ChartSection, MetricSection, CardSection],
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
