from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_serializer, model_validator

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


class RecommendationIntent(BaseModel):
    """The judge→recommend seam payload surfaced onto an evaluated unit
    (recommend-seam-contract.md §3b). Present iff a fired, surviving rule
    declared a ``recommendation`` payload and the unit is not muted/waived (SC4).

    Carries the rule's DECLARED intent — generic, subject-agnostic (SC1/SC2) —
    plus the inputs resolved to their measured values at judge time (SC3, so a
    recommender needs no catalog round-trip). The seam does NOT generate any
    recommendation text — that's the future recommend stage."""
    intent_kind:     str                  # trend_projection | remediation | attention | informational (SC1)
    signal:          str                  # namespaced handle, e.g. "capacity.trend" (SC2)
    inputs_resolved: dict[str, Any] = Field(default_factory=dict)  # {field: measured value}
    note:            str | None = None


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
    # Recommend-seam contract §3b: the declared recommendation intent of the
    # surviving rule, surfaced onto the artifact. Optional and ABSENT from the
    # serialized JSON unless declared (the serializer below omits it when None,
    # so subjects with no recommendation rule stay byte-identical).
    recommendation_intent: RecommendationIntent | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_recommendation_intent(self, handler):
        data = handler(self)
        if self.recommendation_intent is None:
            data.pop("recommendation_intent", None)
        return data


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
    # ADR 0004 phase 7 (presentational): a subject-specific empty-state message
    # shown when there are no rows (e.g. backup_job_summary's "No jobs in the
    # selected window") instead of the generic "No data.". None -> generic.
    empty_message: str | None          = None
    # Presentational layout discriminator, mirroring CardSection.view_mode /
    # MetricSection.render_mode — carried on the artifact from the catalog binding,
    # honored by artifact_to_view + secBody, never keyed on subject id. "columns"
    # is the column-header table (default, unchanged); "card" renders a single-row
    # table as a Field/Value card (e.g. audit_trail retention). Render-only: the
    # row rules + per-row verdict still fire either way. Omitted from JSON when
    # default so existing table artifacts stay byte-identical.
    view_mode: Literal["columns", "card"] = "columns"

    @model_serializer(mode="wrap")
    def _omit_default_view_mode(self, handler):
        data = handler(self)
        if self.view_mode == "columns":
            data.pop("view_mode", None)
        return data


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
    # ADR 0004 phase-8 follow-on (per-field card judging): a card FIELD can now
    # carry its own verdict, mirroring MetricItem — resolved through the same
    # engine locus, the same rule kinds (threshold/presence), the same layering/
    # override + recommend-seam machinery. Optional: a field with no rule carries
    # nothing. Unlike MetricItem (which always emits severity/verdict_chain), the
    # serializer below OMITS all three when absent, so existing card artifacts —
    # whose items never had these fields — stay byte-identical (additive-absent).
    severity:      FindingSeverity | None = None
    verdict_chain: list[VerdictEntry]     = Field(default_factory=list)
    recommendation_intent: RecommendationIntent | None = None
    # ADR 0007 D3 (hex coercion): when a `type` coercion reshapes the displayed
    # value (e.g. integer → lowercase hex), the raw pre-coercion value is kept
    # here so it isn't discarded. Optional; omitted from JSON when absent, so
    # uncoerced items stay byte-identical.
    raw_value: int | float | str | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_evaluative(self, handler):
        data = handler(self)
        if self.severity is None:
            data.pop("severity", None)
        if not self.verdict_chain:
            data.pop("verdict_chain", None)
        if self.recommendation_intent is None:
            data.pop("recommendation_intent", None)
        if self.raw_value is None:
            data.pop("raw_value", None)
        return data


class CardSection(BaseModel):
    """ADR 0004 card section — a flat, labeled key-value identity block
    ("typically one row"). Distinct from a metric (emphasized/derived values):
    a card is a labeled grid of fields.

    Per the phase-4 steering decision, a card carries a section-level verdict,
    reusing the EXACT severity + verdict_chain shape MetricItem carries. Two ways
    it is populated (build_card_section):
      - Legacy `evaluative.rule` (singular): the engine judges one target_field
        and writes the result here (section severity + verdict_chain).
      - Phase-8 `evaluative.rules` (plural): each field is judged on its own
        CardItem (see CardItem.severity); `severity` here becomes the most-severe-
        surviving ROLL-UP across fields and `verdict_chain` stays empty (the
        per-field chains hold the provenance).
    """
    type:          Literal["card"]
    id:            str
    title:         str
    items:         list[CardItem] = Field(default_factory=list)
    # Presentational grid hint; None = auto (renderer picks columns by count).
    columns:       int | None = None
    # ADR 0007 ph3 follow-on: presentational layout hint that rides ON the artifact
    # so the source-agnostic render path (artifact_to_view → _card_section_view) can
    # pick the Field/Value TABLE the live card used instead of the tiles default.
    # Sourced from the catalog binding's card.view_mode at build_card_section time.
    # Optional; the serializer below OMITS it when absent so existing card artifacts
    # (which never carried it) stay byte-identical (additive-absent).
    view_mode:     Literal["tiles", "table"] | None = None
    # Evaluative face (reused from the metric machinery — same enum / VerdictEntry).
    severity:      FindingSeverity | None = None
    verdict_chain: list[VerdictEntry]     = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_absent_view_mode(self, handler):
        data = handler(self)
        if self.view_mode is None:
            data.pop("view_mode", None)
        return data


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
