from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity, FindingStatus, SourceType
from cvhealthcheck.artifacts.models import (
    ArtifactSource,
    ArtifactSubject,
    ArtifactSummary,
    CanonicalArtifact,
    CardSection,
    ChartSection,
    Finding,
    FindingsSection,
    MetricSection,
    SummaryMetric,
    TableColumn,
    TableSection,
)
from cvhealthcheck.evaluative.row_match import evaluate_section_rows, format_conditions
from cvhealthcheck.extractors.card_section import build_card_section
from cvhealthcheck.extractors.chart_section import build_chart_section
from cvhealthcheck.extractors.html import ExtractionResult
from cvhealthcheck.extractors.metric_section import build_metric_section, worst_metric_severity
from cvhealthcheck.identity import verify_commcell_id


_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "critical": FindingSeverity.critical,
    "warning":  FindingSeverity.warning,
    "good":     FindingSeverity.good,
    "info":     FindingSeverity.info,
}

_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "html":  SourceType.html_import,
    "csv":   SourceType.csv_import,
    "json":  SourceType.json_import,
    "rest":  SourceType.rest,
    # ADR 0007 (single-object Command Center API source). Reuses the existing
    # canonical CommServe source type rather than adding a redundant enum value.
    "rest_command_center_api": SourceType.rest_commserve,
    # ADR 0014 (directly-addressed Reports Plus dataset). SourceType.rest by
    # resolved decision: the extraction type carries the addressing grammar,
    # the artifact source type carries the transport.
    "reportsplus_dataset": SourceType.rest,
}

# Source types that represent a LIVE collection (stamp collected_at), as opposed
# to a file import (imported_at only).
_LIVE_SOURCE_TYPES = {SourceType.rest, SourceType.rest_commserve}


def _wire_commcell_id(result: ExtractionResult) -> Any:
    """The wire CommCell ID from a CC-API result's single-object record
    (commcell.commCellId, raw int) — Fix 4. None if not present in any section
    record (CC-API but no id -> unverifiable, comparison impossible)."""
    for rows in result.sections.values():
        if rows and isinstance(rows[0], dict):
            commcell = rows[0].get("commcell")
            if isinstance(commcell, dict) and commcell.get("commCellId") is not None:
                return commcell["commCellId"]
    return None


def result_to_artifact(
    result: ExtractionResult,
    subject_id: str,
    subject_title: str,
    file_path: Path | None = None,
    commcell_id: str | None = None,
    commcell_name: str | None = None,
) -> CanonicalArtifact:
    now = datetime.now(timezone.utc)
    artifact_source_type = _SOURCE_TYPE_MAP.get(
        result.source_type, SourceType.html_import
    )
    # ADR 0004: live REST collection records collected_at; file imports record
    # only imported_at (the file may have been generated earlier elsewhere).
    collected_at = now if artifact_source_type in _LIVE_SOURCE_TYPES else None
    # Fix 4 + import-verification slice: stamp the declared-vs-wire CommCell ID
    # verdict (PROVENANCE, never blocks). The per-source resolver decides what
    # wire CCID THIS source can provide:
    #   1. an extractor-surfaced wire CCID (result.wire_commcell_id) — e.g. an
    #      HTML metricsCommcellInfo panel. The seam is live; HTML extraction of
    #      it is deferred, so this is None today.
    #   2. else the CC-API (rest_commserve) identity payload (commcell.commCellId,
    #      raw int) read from the single-object record.
    #   3. else no wire identity -> attested (plain CSV; non-identity CC-API
    #      endpoints like server_groups/storage_policies that carry no CCID).
    # commcell_id here is the DECLARED value (customer row). No wire -> attested;
    # no declared -> unverifiable (the two are kept distinct). The verdict is
    # stamped on ArtifactSource only.
    wire_ccid = getattr(result, "wire_commcell_id", None)
    wire_source = getattr(result, "wire_commcell_source", None)
    if wire_ccid is None and artifact_source_type == SourceType.rest_commserve:
        wire_ccid = _wire_commcell_id(result)
        if wire_ccid is not None:
            wire_source = "commserv:commcell.commCellId"
    verdict = verify_commcell_id(
        commcell_id, wire_ccid, wire_source=wire_source, now=now,
    )
    source = ArtifactSource(
        type=artifact_source_type,
        collected_at=collected_at,
        imported_at=now,
        commcell_id=commcell_id,
        commcell_name=commcell_name,
        # The version-bearing subject_id this collection ran under.
        template_version=subject_id,
        **verdict,
    )
    subject = ArtifactSubject(id=subject_id, title=subject_title)

    sections = []
    severity_counts: dict[str, int] = {"critical": 0, "warning": 0, "good": 0, "info": 0}
    has_findings_section = False
    metric_sections: list[MetricSection] = []
    card_sections: list[CardSection] = []

    for section_id, rows in result.sections.items():
        output_as = result.section_output_types.get(section_id, "table")
        title = result.section_titles.get(section_id, section_id)

        if output_as == "findings":
            has_findings_section = True
            findings = []
            for row in rows:
                finding = _build_finding(section_id, row)
                findings.append(finding)
                sev = finding.severity.value
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            sections.append(FindingsSection(
                type="findings",
                id=section_id,
                title=title,
                items=findings,
            ))
        elif output_as == "metric":
            # ADR 0004 phase 2: compute derived values + verdicts at collection
            # time from the catalog metric declaration.
            spec = result.section_metric_specs.get(section_id, {})
            metric_section = build_metric_section(
                section_id, title, spec, rows, result.rules_registry,
                result.section_overrides.get(section_id),
            )
            sections.append(metric_section)
            metric_sections.append(metric_section)
        elif output_as == "chart":
            # ADR 0004 phase 3: map table columns to a chart view (line/pie/…).
            spec = result.section_chart_specs.get(section_id, {})
            sections.append(build_chart_section(section_id, title, spec, rows))
        elif output_as == "card":
            # ADR 0004 phase 4: a labeled identity block; carries a section-level
            # verdict via the reused metric threshold evaluator.
            spec = result.section_card_specs.get(section_id, {})
            card_section = build_card_section(
                section_id, title, spec, rows, result.rules_registry,
                result.section_overrides.get(section_id),
            )
            sections.append(card_section)
            card_sections.append(card_section)
        else:
            spec = result.section_table_specs.get(section_id, {})
            is_transpose = bool(spec.get("transpose"))
            # A transpose section carries id/key on each row for ref-stability +
            # rule targeting; honor its declared display columns so those internal
            # keys don't leak as columns. Other sections keep deriving from row keys.
            declared = spec.get("columns") if is_transpose else None
            if declared:
                columns = [TableColumn(id=c["id"], label=c.get("label", c["id"]))
                           for c in declared if isinstance(c, dict) and c.get("id")]
            else:
                columns = _derive_columns(rows)
            sections.append(TableSection(
                type="table",
                id=section_id,
                title=title,
                columns=columns,
                items=rows,
                empty_message=spec.get("empty_message"),
                # presentational layout hint. A transpose section is a "property"
                # table (columns layout + property verdict legend); otherwise the
                # binding's "card" opts in; anything else stays the default columns.
                view_mode=("property" if is_transpose
                           else "card" if spec.get("view_mode") == "card" else "columns"),
            ))

    # ADR 0010: row-scope compliance rules → a derived FindingsSection. Runs after
    # the extracted sections are built (one canonicalization path, ADR 0006 D1):
    # for each table section with bound row_match rules, evaluate each rule over
    # that section's rows. Findings fold into severity_counts + has_findings_section
    # so the summary status reflects them, exactly like a transcribed findings
    # section. Read-only over the rows — the rules never mutate the artifact data.
    table_by_id = {s.id: s for s in sections if isinstance(s, TableSection)}
    compliance_items: list[Finding] = []
    # ADR 0010 layout slice 2/3: the Evaluation band's criteria card is built from
    # the scope + the bound rules. Bake each rule's authored `description`, its
    # `title` (a row template), and the mechanically-formatted `condition_text` per
    # section so the view builder (artifact-only) renders strings, not derivation.
    evaluation_meta: dict[str, dict[str, Any]] = {}
    for section_id, row_rules in (result.section_row_rules or {}).items():
        section_rows = result.sections.get(section_id) or []
        scope = (result.section_scope or {}).get(section_id)
        evaluation_meta[section_id] = {
            "scope": list(scope or []),
            "checks": [{"rule_id": r.get("rule_id"), "severity": r.get("severity"),
                        "description": r.get("description"), "title": r.get("title"),
                        "condition_text": format_conditions(r.get("conditions"))}
                       for r in row_rules],
        }
        findings, per_row = evaluate_section_rows(row_rules, section_rows, scope=scope, now=now)
        for derived in findings:
            finding = _build_compliance_finding(section_id, derived)
            compliance_items.append(finding)
            sev = finding.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        # Bake the explicit per-row verdict onto the BUILT TableSection's items
        # (pydantic copied them at construction, so mutate the section, not the raw
        # rows). Same canonicalization mechanism as a card field's severity (ADR
        # 0010 D5 — no separate store). per_row is row-aligned; "not_evaluated"
        # stays distinct from "good".
        target = table_by_id.get(section_id)
        if target is not None:
            for item, verdict in zip(target.items, per_row):
                if isinstance(item, dict):
                    item["_verdict"] = verdict["verdict"]
    if compliance_items:
        has_findings_section = True
        sections.append(FindingsSection(
            type="findings",
            id=f"{subject_id}.compliance",
            title="Compliance",
            items=compliance_items,
        ))

    if not has_findings_section:
        # A metric or card section's verdict drives overall status when there
        # are no findings (e.g. the phase-2/4 test subjects).
        verdict_status = _verdict_overall_status(metric_sections, card_sections)
        if verdict_status is not None:
            summary = ArtifactSummary(status=verdict_status)
        else:
            has_data = any(
                (isinstance(s, TableSection) and len(s.items) > 0)
                or (isinstance(s, ChartSection) and len(s.series) > 0)
                for s in sections
            )
            summary = ArtifactSummary(
                status=ArtifactStatus.good if has_data else ArtifactStatus.unknown
            )
    else:
        metrics = [
            SummaryMetric(id="critical_count", label="Critical", value=severity_counts["critical"]),
            SummaryMetric(id="warning_count",  label="Warning",  value=severity_counts["warning"]),
            SummaryMetric(id="good_count",     label="Good",     value=severity_counts["good"]),
            SummaryMetric(id="info_count",     label="Info",     value=severity_counts["info"]),
        ]
        summary = ArtifactSummary(
            status=_overall_status(severity_counts),
            metrics=metrics,
        )

    # ADR 0004 conformance: carry any section failure records onto the
    # artifact. The renderer side (showing a failed section) is phase 2;
    # phase 1 emits the structured record under metadata.conformance_failures,
    # keyed by section_id, in the verbatim ADR shape.
    metadata: dict[str, Any] = {}
    section_failures = getattr(result, "section_failures", None)
    if section_failures:
        metadata["conformance_failures"] = dict(section_failures)
    if evaluation_meta:
        metadata["evaluation"] = evaluation_meta   # ADR 0010 layout slice 2

    return CanonicalArtifact(
        artifact_type=subject_id,
        generated_at=now,
        source=source,
        subject=subject,
        summary=summary,
        sections=sections,
        metadata=metadata,
    )


def _build_finding(section_id: str, row: dict[str, Any]) -> Finding:
    parameter = str(row.get("parameter") or "")
    finding_id = hashlib.sha256(
        f"{section_id}:{parameter}".encode()
    ).hexdigest()[:12]
    severity_str = str(row.get("severity") or "info")
    severity = _SEVERITY_MAP.get(severity_str, FindingSeverity.info)
    recommendation = row.get("action") or None
    if isinstance(recommendation, str) and not recommendation.strip():
        recommendation = None
    vendor_key_raw = row.get("vendor_key")
    vendor_key = (
        str(vendor_key_raw).strip() or None
        if vendor_key_raw is not None
        else None
    )
    vendor_id_raw = row.get("vendor_id")
    vendor_id = (
        str(vendor_id_raw).strip() or None
        if vendor_id_raw is not None
        else None
    )
    return Finding(
        id=finding_id,
        severity=severity,
        status=FindingStatus.open,
        category=section_id,
        title=parameter,
        description=row.get("remarks") or None,
        recommendation=recommendation,
        vendor_key=vendor_key,
        vendor_id=vendor_id,
    )


def _build_compliance_finding(section_id: str, derived: dict[str, Any]) -> Finding:
    """ADR 0010: a row_match rule's rendered finding → a canonical Finding.

    The id is stable per (rule_id, row_ref) so re-collection reproduces the same
    finding ids (and the duplicate-name case is disambiguated by row_ref = id,
    not name). ``category`` carries the source section_id."""
    fid = hashlib.sha256(
        f"{derived.get('rule_id')}:{derived.get('row_ref') or ''}".encode()
    ).hexdigest()[:12]
    severity = _SEVERITY_MAP.get(str(derived.get("severity")), FindingSeverity.info)
    message = derived.get("message") or None
    if isinstance(message, str) and not message.strip():
        message = None
    recommendation = derived.get("recommendation") or None
    if isinstance(recommendation, str) and not recommendation.strip():
        recommendation = None
    return Finding(
        id=fid,
        severity=severity,
        status=FindingStatus.open,
        category=section_id,
        title=str(derived.get("title") or ""),
        description=message,
        recommendation=recommendation,
    )


def _derive_columns(rows: list[dict[str, Any]]) -> list[TableColumn]:
    if not rows:
        return []
    return [TableColumn(id=key, label=key) for key in rows[0].keys()]


def _overall_status(counts: dict[str, int]) -> ArtifactStatus:
    if counts.get("critical", 0) > 0:
        return ArtifactStatus.critical
    if counts.get("warning", 0) > 0:
        return ArtifactStatus.warning
    return ArtifactStatus.good


_METRIC_SEV_TO_STATUS: dict[FindingSeverity, ArtifactStatus] = {
    FindingSeverity.critical: ArtifactStatus.critical,
    FindingSeverity.warning:  ArtifactStatus.warning,
    FindingSeverity.good:     ArtifactStatus.good,
    FindingSeverity.info:     ArtifactStatus.good,
}


def _verdict_overall_status(
    metric_sections: list[MetricSection],
    card_sections: list[CardSection],
) -> ArtifactStatus | None:
    """Overall status from the worst metric/card verdict, or None if nothing
    carries a (non-muted) severity. Metric severity is per-item (worst item);
    card severity is section-level."""
    rank = {ArtifactStatus.good: 0, ArtifactStatus.warning: 1, ArtifactStatus.critical: 2}
    severities: list[FindingSeverity] = []
    for section in metric_sections:
        sev = worst_metric_severity(section)
        if sev is not None:
            severities.append(sev)
    for card in card_sections:
        if card.severity is not None and card.severity != FindingSeverity.muted:
            severities.append(card.severity)

    worst: ArtifactStatus | None = None
    for sev in severities:
        status = _METRIC_SEV_TO_STATUS.get(sev, ArtifactStatus.good)
        if worst is None or rank.get(status, 0) > rank.get(worst, 0):
            worst = status
    return worst
