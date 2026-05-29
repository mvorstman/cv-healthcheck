-- =============================================================================
-- Migration 0015: client_growth — three-face migration (ADR 0004 phase 6)
-- =============================================================================
-- Second regressed-subject migration. All three faces bind to "Client Count"
-- (report 318) — the tidy monthly series confirmed against the live dev-box
-- collect: MonthStart / Added / Removed / Total, 13 fully-populated rows, NO
-- sentinel (every value a real integer; the eleven leading 0/0/0 months are
-- genuine zeros, then Apr 2026 Added 8 / Removed 3 / Total 5, May 2026 Total 5).
-- So: NO gap/sentinel handling (continuous line, no n/a). (The pivoted
-- "ClientGrowthDetails" dataset — months-as-columns — is OUT of phase 6; it
-- would need an un-pivot/transpose the catalog can't express. Follow-up: a
-- transpose-primitive test case.)
--
-- METRIC IS INFORMATIONAL — no verdict. Unlike capacity_license (a ratio with a
-- natural ceiling -> warn/critical), client growth has no meaningful threshold
-- ("is N% growth good?" is customer-dependent). The metric is the latest-month
-- Total (+ net change) in render_mode "meta": plain key/value, NO severity,
-- NO badge, NO rule. The phase-plan's YoY-decline rule is DELIBERATELY DROPPED
-- (phase 6 supersedes it). capacity_license proved the evaluative metric path;
-- client_growth proves the informational one.
--
-- report_id "318" is per-deployment (backlog #23 / #34); bindings resolve by
-- dataset_name, the dataset_guid is a cache hint only. The three sections
-- (summary/chart/monthly_table) already exist from migration 0003; this only
-- (re)binds their REST sources.
-- -----------------------------------------------------------------------------

DELETE FROM subject_section_sources
WHERE section_id IN ('client_growth.summary','client_growth.chart','client_growth.monthly_table')
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'client_growth' AND subject_version = 1 AND source_type = 'rest'
  );

-- 1. metric — INFORMATIONAL (render_mode "meta", no rules): latest-month Total
--    headline + net change (Added - Removed) of the same latest month.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'client_growth.summary', json('{
    "report_id": "318",
    "dataset_name": "Client Count",
    "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    "fields": ["MonthStart", "Added", "Removed", "Total"],
    "orderby": "MonthStart Asc",
    "timestamp_fields": ["MonthStart"],
    "timestamp_format": "unix_seconds",
    "column_map": [
        {"source": "Added", "canonical": "added", "type": "number"},
        {"source": "Removed", "canonical": "removed", "type": "number"},
        {"source": "Total", "canonical": "total", "type": "number"}
    ],
    "output_as": "metric",
    "conformance": {"required_fields": ["added", "removed", "total"]},
    "metric": {
        "render_mode": "meta",
        "items": [
            {"id": "total", "label": "Total Clients", "source": "field", "field": "total", "agg": "latest"},
            {"id": "net_change", "label": "Net Change (latest month)", "source": "cel",
             "expr": "records[size(records)-1].added - records[size(records)-1].removed", "derived": true}
        ]
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'client_growth' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 2. chart — Total clients over months (line). Fully-populated series: no gaps.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'client_growth.chart', json('{
    "report_id": "318",
    "dataset_name": "Client Count",
    "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    "fields": ["MonthStart", "Total"],
    "orderby": "MonthStart Asc",
    "timestamp_fields": ["MonthStart"],
    "timestamp_format": "unix_seconds",
    "column_map": [
        {"source": "MonthStart", "canonical": "month", "type": "string"},
        {"source": "Total", "canonical": "total", "type": "number"}
    ],
    "output_as": "chart",
    "conformance": {"required_fields": ["month", "total"]},
    "chart": {
        "chart_type": "line",
        "x_axis": {"label": "Month"},
        "y_axis": {"label": "Total Clients"},
        "labels": {"source": "column", "column": "month"},
        "series": [{"id": "total", "label": "Total Clients", "column": "total"}]
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'client_growth' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 3. table — monthly rows, clean column names via column_map.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'client_growth.monthly_table', json('{
    "report_id": "318",
    "dataset_name": "Client Count",
    "dataset_guid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8",
    "fields": ["MonthStart", "Added", "Removed", "Total"],
    "orderby": "MonthStart Asc",
    "timestamp_fields": ["MonthStart"],
    "timestamp_format": "unix_seconds",
    "null_values": [null],
    "column_map": [
        {"source": "MonthStart", "canonical": "month", "type": "string"},
        {"source": "Added", "canonical": "added", "type": "number"},
        {"source": "Removed", "canonical": "removed", "type": "number"},
        {"source": "Total", "canonical": "total", "type": "number"}
    ],
    "output_as": "table",
    "conformance": {"required_fields": ["month", "added", "removed", "total"]}
}')
FROM subject_sources s
WHERE s.subject_id = 'client_growth' AND s.subject_version = 1 AND s.source_type = 'rest';
