from __future__ import annotations

import re
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, SourceType
from cvhealthcheck.artifacts.models import (
    CanonicalArtifact,
    CardSection,
    Finding,
    FindingsSection,
    MetricSection,
    TableSection,
    ChartSection,
)
from cvhealthcheck.quickhc.registry import (
    CSV_IMPORT_SOURCE_ID,
    HTML_IMPORT_SOURCE_ID,
    JSON_IMPORT_SOURCE_ID,
    LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
    LICENSE_SUMMARY_METADATA_SECTION_ID,
    LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
    LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
    QUICK_HC_TILE_BY_ID,
    REST_COMMAND_CENTER_API_SOURCE_ID,
    REST_REPORTS_PLUS_SOURCE_ID,
    SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
    SECURITY_ASSESSMENT_METADATA_SECTION_ID,
    SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
)

# ── mappings ──

_ARTIFACT_STATUS_TO_STATE: dict[str, str] = {
    ArtifactStatus.critical: "issues",
    ArtifactStatus.warning:  "issues",
    ArtifactStatus.good:     "ok",
    ArtifactStatus.unknown:  "nodata",
}

_FINDING_SEV: dict[str, str] = {
    FindingSeverity.critical: "crit",
    FindingSeverity.warning:  "warn",
    FindingSeverity.good:     "good",
    FindingSeverity.info:     "info",
}

_SOURCE_TYPE_TO_ID: dict[str, str] = {
    SourceType.reportsplus_rest: REST_REPORTS_PLUS_SOURCE_ID,
    SourceType.csv_import:       CSV_IMPORT_SOURCE_ID,
    SourceType.html_import:      HTML_IMPORT_SOURCE_ID,
    SourceType.json_import:      JSON_IMPORT_SOURCE_ID,
    SourceType.rest:             REST_REPORTS_PLUS_SOURCE_ID,
    SourceType.rest_commserve:   REST_COMMAND_CENTER_API_SOURCE_ID,
}

_SOURCE_TYPE_LABEL: dict[str, str] = {
    SourceType.reportsplus_rest: "REPORTSPLUS",
    SourceType.csv_import:       "CSV",
    SourceType.html_import:      "HTML",
    SourceType.json_import:      "JSON",
    SourceType.rest:             "REST",
    SourceType.rest_commserve:   "REST",
}

# TableSection IDs that are not workload sections in license_summary.
# Accept both short form (legacy) and fully-qualified form stored by the extractor.
_LS_NON_WORKLOAD_IDS = {
    "other_licenses",
    "agent_feature_licenses",
    "license_summary.other_licenses",
    "license_summary.agent_feature_licenses",
}


# ── public API ──

def artifact_to_view(artifact: CanonicalArtifact) -> dict[str, Any]:
    """Generic view builder for any canonical artifact."""
    state = _artifact_state(artifact)

    metrics = {m.id: m.value for m in artifact.summary.metrics}
    if metrics:
        parts = [f"{int(v)} {k.replace('_', ' ')}" for k, v in list(metrics.items())[:3] if v]
        subtitle = " · ".join(parts) if parts else "Data available"
    else:
        total_rows = sum(
            len(sec.items)
            for sec in artifact.sections
            if isinstance(sec, (TableSection, FindingsSection))
        )
        subtitle = f"{total_rows} rows" if total_rows else "Data available"

    src = artifact.source
    active_src = _SOURCE_TYPE_TO_ID.get(src.type, REST_REPORTS_PLUS_SOURCE_ID)
    subject_id = artifact.subject.id
    # ADR 0010 layout slice 2: per-section {scope, checks} baked at collection.
    evaluation = artifact.metadata.get("evaluation") or {}

    sections: list[dict] = []
    for sec in artifact.sections:
        sec_id = sec.id if sec.id.startswith(f"{subject_id}.") else f"{subject_id}.{sec.id}"
        if isinstance(sec, FindingsSection):
            count = len(sec.items)
            sections.append({
                "id": sec_id,
                "title": sec.title,
                "meta": f"{count} finding{'s' if count != 1 else ''}",
                "included": True,
                "type": "findings_list",
                "findings": [_finding_view(f) for f in sec.items],
                "rows": [],
                # ADR 0010 layout: section pill = worst finding severity (e.g. the
                # derived <subject>.compliance section → "Warning"). None → no pill.
                "sev": _worst_finding_sev(sec.items),
            })
        elif isinstance(sec, TableSection):
            count = len(sec.items)
            columns = [col.label for col in sec.columns]
            rows = [
                [str(item.get(col.id) if item.get(col.id) is not None else "") for col in sec.columns]
                for item in sec.items
            ]
            # ADR 0010 layout: carry the baked per-row _verdict to the view as row
            # METADATA (row-aligned), NOT as a visible data column — it drives the
            # STATUS dot. Absent (no rules on this section) → None per row → the dot
            # falls back to info; the explicit not_evaluated must NOT be that.
            row_verdicts = [item.get("_verdict") for item in sec.items]
            sections.append({
                "id": sec_id,
                "title": sec.title,
                "meta": f"{count} row{'s' if count != 1 else ''}",
                "included": True,
                "type": "table",
                "columns": columns,
                "rows": rows,
                "row_verdicts": row_verdicts,
                # section pill = worst row verdict EXCLUDING not_evaluated; None → no pill.
                "sev": _worst_verdict_code(row_verdicts),
                # Always-present scope caption on the legend bar (safety net — it
                # survives toggling the Evaluation cards out). None when the section
                # is not evaluated. ``sec.id`` here is the catalog section_id.
                "scope_caption": (
                    _scope_phrases((evaluation[sec.id].get("scope")) or [])[1]
                    if sec.id in evaluation else None
                ),
                "empty_message": sec.empty_message,
            })
        elif isinstance(sec, MetricSection):
            # ADR 0004 presentational face: render_mode is the *declared*
            # discriminator (not inferred from severity presence). "metric"
            # selects the rich renderer; anything else (License Summary's
            # commcell_info, which predates the concept) stays the plain
            # key/value "meta" block — byte-for-byte unchanged.
            if sec.render_mode == "metric":
                sections.append(_metric_section_view(sec, sec_id))
            else:
                meta_rows = [{"k": item.label.upper(), "v": str(item.value)} for item in sec.items]
                sections.append({
                    "id": sec_id,
                    "title": sec.title,
                    "meta": "",
                    "included": True,
                    "type": "meta",
                    "rows": meta_rows,
                })
        elif isinstance(sec, ChartSection):
            sections.append(_chart_section_view(sec, sec_id))
        elif isinstance(sec, CardSection):
            # ADR 0007 ph3 follow-on: honor the section's own view_mode (carried
            # on the artifact from the catalog binding) instead of the hardcoded
            # tiles default — so a card authored view_mode="table" renders as the
            # Field/Value table. Source-agnostic; unset → tiles (unchanged).
            sections.append(_card_section_view(sec, sec_id, view_mode=sec.view_mode or "tiles"))

    # ── ADR 0010 layout slice 2: the Evaluation band ──
    # Every section defaults to the "report" band; the derived <subject>.compliance
    # findings MOVE to the "evaluation" band, retitled "Findings". A read-only
    # "Evaluation criteria" card (no status pill) is built per evaluated section.
    # Order: report sections, then Evaluation (criteria first, then findings).
    for s in sections:
        s.setdefault("band", "report")
        if s["type"] == "findings_list" and s["id"].endswith(".compliance"):
            s["band"] = "evaluation"
            s["title"] = "Findings"
    criteria = [_evaluation_criteria_view(sid, block) for sid, block in evaluation.items()]
    report_sections = [s for s in sections if s.get("band") != "evaluation"]
    eval_findings = [s for s in sections if s.get("band") == "evaluation"]
    sections = report_sections + criteria + eval_findings

    return {
        "id": subject_id,
        "name": artifact.subject.title,
        "description": "",
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": None,
        "activeSource": active_src,
        "sources": [],
        "sections": sections,
    }


def security_assessment_to_view(artifact: CanonicalArtifact) -> dict[str, Any]:
    state = _artifact_state(artifact)

    metrics   = {m.id: int(m.value) for m in artifact.summary.metrics}
    critical  = metrics.get("critical", 0)
    warning   = metrics.get("warning",  0)
    info      = metrics.get("info",     0)
    good      = metrics.get("good",     0)
    total     = critical + warning + info + good

    parts: list[str] = []
    if critical: parts.append(f"{critical} critical")
    if warning:  parts.append(f"{warning} warning")
    if info:     parts.append(f"{info} info")
    if good:     parts.append(f"{good} good")
    subtitle = " · ".join(parts) if parts else f"{total} checks"

    src          = artifact.source
    active_src   = _SOURCE_TYPE_TO_ID.get(src.type, REST_REPORTS_PLUS_SOURCE_ID)
    collected_at = str(src.collected_at or "")
    report_id    = str(src.report_id or "")
    report_name  = str(src.report_name or "")
    source_label = _SOURCE_TYPE_LABEL.get(src.type, str(src.type or "").upper())

    # Carry the section TITLE with each finding so the highlight display shows
    # "Access Security", not finding.category (the namespaced section_id post-cut).
    all_findings = [
        (sec.title, f)
        for sec in artifact.sections
        if isinstance(sec, FindingsSection)
        for f in sec.items
    ]

    highlight_findings = [
        _finding_view(f, section_label=section_title)
        for section_title, f in all_findings
        if f.severity in (FindingSeverity.critical, FindingSeverity.warning)
    ][:12]
    highlight_rows = [
        [str(section_title or ""), str(f.title or ""), f.severity.value.capitalize(), str(f.description or "")]
        for section_title, f in all_findings
        if f.severity in (FindingSeverity.critical, FindingSeverity.warning)
    ][:12]

    detail_sections = [
        {
            "id": sec.id if sec.id.startswith("security_assessment.") else f"security_assessment.{sec.id}",
            "title": sec.title,
            "meta": f"{len(sec.items)} finding{'s' if len(sec.items) != 1 else ''}",
            "included": True,
            "type": "findings_list",
            "findings": [_finding_view(f, section_label=sec.title) for f in sec.items],
            "rows": [
                [
                    str(f.title or ""),
                    f.severity.value.capitalize(),
                    str(f.description or ""),
                    str(f.recommendation or ""),
                ]
                for f in sec.items
            ],
            "columns": ["Parameter", "Status", "Remarks", "Action"],
        }
        for sec in artifact.sections
        if isinstance(sec, FindingsSection)
    ]

    meta_rows: list[dict] = [{"k": "SOURCE", "v": source_label}]
    if collected_at:
        meta_rows.append({"k": "IMPORTED", "v": collected_at[:19]})
    if report_name and report_id:
        meta_rows.append({"k": "REPORT", "v": f"{report_name} ({report_id})"})
    elif report_name:
        meta_rows.append({"k": "REPORT", "v": report_name})

    summary_rows: list[dict] = [
        {"k": "TOTAL CHECKS", "v": str(total)},
        {"k": "CRITICAL",     "v": str(critical), "cls": "err"  if critical > 0 else ""},
        {"k": "WARNING",      "v": str(warning),  "cls": "warn" if warning  > 0 else ""},
        {"k": "INFO",         "v": str(info)},
        {"k": "GOOD",         "v": str(good),     "cls": "ok"   if good     > 0 else ""},
    ]
    if collected_at:
        summary_rows.append({"k": "COLLECTED", "v": collected_at[:19]})

    sections: list[dict] = [
        {
            "id": SECURITY_ASSESSMENT_METADATA_SECTION_ID,
            "title": "Source metadata",
            "meta": report_name or "Security Assessment",
            "included": True,
            "type": "meta",
            "rows": meta_rows,
        },
        {
            "id": SECURITY_ASSESSMENT_SUMMARY_SECTION_ID,
            "title": "Summary counters",
            "meta": f"{total} checks",
            "included": True,
            "type": "counters",
            "counters": {"Critical": critical, "Warning": warning, "Info": info, "Good": good},
            "rows": summary_rows,
        },
        {
            "id": SECURITY_ASSESSMENT_HIGHLIGHTS_SECTION_ID,
            "title": "Critical / Warning highlights",
            "meta": f"{len(highlight_findings)} finding{'s' if len(highlight_findings) != 1 else ''}",
            "included": True,
            "type": "findings_grid",
            "findings": highlight_findings,
            "columns": ["Section", "Parameter", "Status", "Remarks"],
            "rows": highlight_rows,
        },
        *detail_sections,
    ]

    return {
        "id": "security_assessment",
        "name": "Security Assessment",
        "description": _tile_description("security_assessment"),
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": None,
        "activeSource": active_src,
        "sources": [],
        "sections": sections,
    }


def license_summary_to_view(artifact: CanonicalArtifact) -> dict[str, Any]:
    state = _artifact_state(artifact)

    src         = artifact.source
    active_src  = _SOURCE_TYPE_TO_ID.get(src.type, REST_REPORTS_PLUS_SOURCE_ID)
    imported_at = str(src.imported_at or src.collected_at or "")
    source_label = _SOURCE_TYPE_LABEL.get(src.type, str(src.type or "").upper())

    info_sec  = next((s for s in artifact.sections if isinstance(s, MetricSection) and s.id in {"commcell_info", "license_summary.commcell_info"}), None)
    other_sec = next((s for s in artifact.sections if isinstance(s, TableSection)  and s.id in {"other_licenses", "license_summary.other_licenses"}), None)
    agent_sec = next((s for s in artifact.sections if isinstance(s, TableSection)  and s.id in {"agent_feature_licenses", "license_summary.agent_feature_licenses"}), None)
    workload_secs = [
        s for s in artifact.sections
        if isinstance(s, TableSection) and s.id not in _LS_NON_WORKLOAD_IDS
    ]

    wl_count    = len(workload_secs)
    other_count = len(other_sec.items) if other_sec else 0
    subtitle_parts: list[str] = []
    if wl_count:    subtitle_parts.append(f"{wl_count} workload section{'s' if wl_count != 1 else ''}")
    if other_count: subtitle_parts.append(f"{other_count} other licenses")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    result_sections: list[dict] = []

    # CommCell info / metadata → type "meta"
    if info_sec:
        meta_rows: list[dict] = [{"k": item.label.upper(), "v": str(item.value)} for item in info_sec.items]
    else:
        meta_rows = [{"k": "SOURCE", "v": source_label}]
        if imported_at:
            meta_rows.append({"k": "IMPORTED", "v": imported_at[:19]})
    result_sections.append({
        "id": LICENSE_SUMMARY_METADATA_SECTION_ID,
        "title": "Summary metadata",
        "meta": "Source and dates",
        "included": True,
        "type": "meta",
        "rows": meta_rows,
    })

    # All workload TableSections → one "workload" section
    result_sections.append({
        "id": LICENSE_SUMMARY_WORKLOAD_SECTION_ID,
        "title": "Workload Summary Sections",
        "meta": f"{wl_count} section{'s' if wl_count != 1 else ''}",
        "included": True,
        "type": "workload",
        "workload": [
            {
                "name": sec.title,
                "rows": [
                    {
                        "license": str(item.get("license") or ""),
                        "ent":     str(item.get("entitlement_value") or ""),
                        "used":    str(item.get("used") or ""),
                        "pct":     _parse_percent(item.get("usage_percent")),
                    }
                    for item in sec.items
                ],
            }
            for sec in workload_secs
        ],
    })

    # Other licenses table
    if other_sec is not None:
        result_sections.append({
            "id": LICENSE_SUMMARY_OTHER_LICENSES_SECTION_ID,
            "title": "Other Licenses table",
            "meta": f"{other_count} row{'s' if other_count != 1 else ''}",
            "included": True,
            "type": "table",
            "columns": [col.label for col in other_sec.columns],
            "rows": [
                [str(item.get(col.id) if item.get(col.id) is not None else "") for col in other_sec.columns]
                for item in other_sec.items
            ],
        })

    # Agent/feature licenses table
    if agent_sec is not None:
        agent_count = len(agent_sec.items)
        result_sections.append({
            "id": LICENSE_SUMMARY_AGENT_FEATURE_LICENSES_SECTION_ID,
            "title": "Agent / Feature Licenses table",
            "meta": f"{agent_count} row{'s' if agent_count != 1 else ''}",
            "included": True,
            "type": "table",
            "columns": [col.label for col in agent_sec.columns],
            "rows": [
                [str(item.get(col.id) if item.get(col.id) is not None else "") for col in agent_sec.columns]
                for item in agent_sec.items
            ],
        })

    return {
        "id": "license_summary",
        "name": "License Summary",
        "description": _tile_description("license_summary"),
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": None,
        "activeSource": active_src,
        "sources": [],
        "sections": result_sections,
    }


# ── private helpers ──

def _artifact_state(artifact: CanonicalArtifact) -> str:
    if not artifact.sections:
        return "nodata"
    return _ARTIFACT_STATUS_TO_STATE.get(artifact.summary.status, "nodata")


_METRIC_SEV_CODE: dict[str, str] = {
    FindingSeverity.critical: "crit",
    FindingSeverity.warning:  "warn",
    FindingSeverity.good:     "good",
    FindingSeverity.info:     "info",
    FindingSeverity.muted:    "muted",
}


def _metric_section_view(sec: MetricSection, sec_id: str) -> dict[str, Any]:
    """Render a rich (render_mode="metric") MetricSection for the workspace.

    Each item carries a display value ("n/a" for a None/sentinel value, kept
    distinct from a real 0), the derived flag, and a severity badge code +
    verdict reason (the auditable tooltip).
    """
    items = []
    for item in sec.items:
        sev = item.severity.value if item.severity is not None else None
        reason = item.verdict_chain[-1].reason if item.verdict_chain else ""
        items.append({
            "id": item.id,
            "label": item.label,
            "value": _fmt_metric_value(item.value),
            "unit": item.unit or "",
            "derived": bool(item.derived),
            "sev": _METRIC_SEV_CODE.get(sev) if sev else None,
            "reason": reason,
        })
    # Section-level summary verdict for the header badge (consistent with card):
    # the worst item severity (skipping None/muted). Per-item badges remain the
    # detail; this is the section's overall status next to the checkbox.
    section_sev, section_reason = _worst_item_verdict(sec)
    return {
        "id": sec_id,
        "title": sec.title,
        "meta": "",
        "included": True,
        "type": "metric",
        "items": items,
        "sev": _METRIC_SEV_CODE.get(section_sev) if section_sev else None,
        "reason": section_reason,
    }


def _worst_item_verdict(sec: MetricSection) -> tuple[str | None, str]:
    """Worst (highest-rank) item severity + its reason, skipping None/muted."""
    rank = {"good": 0, "info": 1, "warning": 2, "critical": 3}
    worst_item = None
    worst_rank = -1
    for item in sec.items:
        if item.severity is None or item.severity == FindingSeverity.muted:
            continue
        r = rank.get(item.severity.value, -1)
        if r > worst_rank:
            worst_rank, worst_item = r, item
    if worst_item is None:
        return None, ""
    reason = worst_item.verdict_chain[-1].reason if worst_item.verdict_chain else ""
    return worst_item.severity.value, reason


def _card_section_view(
    sec: CardSection, sec_id: str, view_mode: str = "tiles"
) -> dict[str, Any]:
    """Render a card section: a labeled-value grid plus a section-level status
    badge (when the card carries a verdict). Mirrors how a metric shows its
    badge; the badge code reuses the shared severity vocabulary.

    Phase-8 follow-on (per-field card judging): each item also carries its own
    `sev`/`reason` — identical shape to a metric item — so the renderer can paint
    a per-field indicator. A field with no rule has `sev=None` and renders bare
    (informational = no rule = no indicator). The section-level `sev`/`reason`
    (the rolled-up header badge) is unchanged.

    ``view_mode`` ("tiles" | "table") is a presentational hint the JS renderer
    reads to pick the layout — tiles (the labeled grid, default) or a Field/Value
    table. It rides as data on the section (e.g. the catalog binding); the
    renderer branches on it, never on the subject id. Default "tiles" keeps every
    other card unchanged."""
    sev = sec.severity.value if sec.severity is not None else None
    reason = sec.verdict_chain[-1].reason if sec.verdict_chain else ""
    items = []
    for item in sec.items:
        item_sev = item.severity.value if item.severity is not None else None
        item_reason = item.verdict_chain[-1].reason if item.verdict_chain else ""
        items.append({
            "label": item.label,
            "value": _fmt_card_value(item.value),
            "unit": item.unit or "",
            "sev": _METRIC_SEV_CODE.get(item_sev) if item_sev else None,
            "reason": item_reason,
        })
    return {
        "id": sec_id,
        "title": sec.title,
        "meta": "",
        "included": True,
        "type": "card",
        "view_mode": view_mode if view_mode in ("tiles", "table") else "tiles",
        "columns": sec.columns,
        "items": items,
        "sev": _METRIC_SEV_CODE.get(sev) if sev else None,
        "reason": reason,
    }


def _fmt_card_value(value: Any) -> str:
    """Display string for a card field. None -> '—' (em dash, identity 'absent')."""
    if value is None:
        return "—"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.1f}"
    return str(value)


def _chart_section_view(sec: ChartSection, sec_id: str) -> dict[str, Any]:
    """Render a chart section to the canonical chart-data structure the JS
    Chart.js renderer consumes. One structure for all chart_types; the JS
    `chart_type` discriminator decides how to draw it."""
    return {
        "id": sec_id,
        "title": sec.title,
        "meta": "",
        "included": True,
        "type": "chart",
        "chart": {
            "chart_type": sec.chart_type.value if hasattr(sec.chart_type, "value") else str(sec.chart_type),
            "labels": list(sec.labels),
            "series": [{"id": s.id, "label": s.label, "data": list(s.data)} for s in sec.series],
            "x_axis": sec.x_axis.label if sec.x_axis else None,
            "y_axis": sec.y_axis.label if sec.y_axis else None,
        },
    }


def _fmt_metric_value(value: Any) -> str:
    """Display string for a metric value. None (sentinel) -> 'n/a'."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        # Trim trailing .0 for whole numbers; keep one decimal otherwise.
        return str(int(value)) if value.is_integer() else f"{value:.1f}"
    return str(value)


def _finding_view(f: Finding, section_label: str | None = None) -> dict[str, str]:
    sev = _FINDING_SEV.get(f.severity, "info")
    # SA migration: prefer an explicit section_label (the FindingsSection title)
    # over f.category — post-cut, category is the namespaced section_id
    # (e.g. "security_assessment.access_security"), not a display name.
    section = section_label if section_label is not None else str(f.category or "")
    description = str(f.description or "")
    if section and description:
        rem = f"{section} · {description}"
    else:
        rem = description or section
    return {"sev": sev, "title": str(f.title or ""), "rem": rem}


# ADR 0010 layout: roll a section's pill up from its per-row/per-finding verdicts.
_VERDICT_SEV_RANK = {"good": 0, "warning": 1, "critical": 2}
_VERDICT_TO_SEV_CODE = {"good": "good", "warning": "warn", "critical": "crit"}
_SEV_CODE_RANK = {"good": 0, "info": 1, "warn": 2, "crit": 3}


def _worst_verdict_code(verdicts: list[Any]) -> str | None:
    """Section pill from per-row verdicts: worst EXCLUDING ``not_evaluated`` (and
    absent). Returned as a sev code (good/warn/crit); ``None`` ⇒ no pill."""
    worst: str | None = None
    for verdict in verdicts:
        if verdict in _VERDICT_SEV_RANK and (
            worst is None or _VERDICT_SEV_RANK[verdict] > _VERDICT_SEV_RANK[worst]
        ):
            worst = verdict
    return _VERDICT_TO_SEV_CODE.get(worst) if worst else None


def _worst_finding_sev(findings: list[Finding]) -> str | None:
    """Section pill from findings: the worst finding severity as a sev code, or
    ``None`` when there are no findings."""
    worst: str | None = None
    for finding in findings:
        code = _FINDING_SEV.get(finding.severity, "info")
        if worst is None or _SEV_CODE_RANK[code] > _SEV_CODE_RANK[worst]:
            worst = code
    return worst


# ── ADR 0010 criteria card phrasing ──────────────────────────────────────────
# Each check's PRIMARY line is the rule's AUTHORED `description` (slice 3),
# falling back to the rule's `title` with its `{row.*}` template placeholders
# stripped — NEVER the raw rule id. The condition line is the mechanically
# formatted `condition_text` baked in `result_to_artifact`. The SCOPE sentence is
# still derived here (interim) — an authored scope label is the scope-authoring
# slice; `_scope_phrases` stays until then.
_SEV_STR_TO_CODE = {"critical": "crit", "warning": "warn", "info": "info", "good": "good"}
_TEMPLATE_PLACEHOLDER = re.compile(r"\{[^}]*\}")


def _title_static(title: str | None) -> str:
    """A rule `title` is a per-row template (e.g. ``Empty group: {row.name}``);
    render only its static text for the criteria card."""
    if not title:
        return ""
    stripped = _TEMPLATE_PLACEHOLDER.sub("", title)
    return re.sub(r"\s+", " ", stripped).strip().rstrip(":·-–— ").strip()


def _scope_phrases(conditions: list[Any]) -> tuple[str, str]:
    """(full sentence, short caption) for a scope. INTERIM: handles eq-on-
    ``association``; an empty scope → "all rows"; anything else → a generic
    subset phrase."""
    for cond in conditions or []:
        if cond.get("target") == "association" and cond.get("operator") == "eq":
            value = str(cond.get("value", "")).strip().lower()
            sentence = f"{value.capitalize()} server groups."
            caption = f"{value} server groups"
            if value == "manual":
                sentence += " Automatic groups are excluded from assessment."
                caption += " · automatic excluded"
            return sentence, caption
    if not conditions:
        return "All rows are assessed.", "all rows"
    return "A subset of rows is assessed.", "a subset of rows"


def _evaluation_criteria_view(section_id: str, block: dict[str, Any]) -> dict[str, Any]:
    """The read-only "Evaluation criteria" card: a plain-language scope sentence +
    one severity-tagged check sentence per bound rule. No status pill — it
    describes the assessment, it is not a verdict."""
    scope_sentence, _ = _scope_phrases(block.get("scope") or [])
    checks = [
        {"sev": _SEV_STR_TO_CODE.get(str(c.get("severity")), "info"),
         "primary": c.get("description") or _title_static(c.get("title")) or "Check",
         "condition": c.get("condition_text") or ""}
        for c in (block.get("checks") or [])
    ]
    return {
        "id": f"{section_id}.criteria",
        "title": "Evaluation criteria",
        "meta": "",
        "included": True,
        "type": "criteria",
        "band": "evaluation",
        "scope_sentence": scope_sentence,
        "checks": checks,
    }


def _parse_percent(value: Any) -> int:
    text = str(value or "").strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _tile_description(tile_id: str) -> str:
    tile = QUICK_HC_TILE_BY_ID.get(tile_id)
    return tile.subtitle if tile else ""


