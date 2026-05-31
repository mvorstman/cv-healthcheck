-- =============================================================================
-- Migration 0014: capacity_license — three-face migration (ADR 0004 phase 5)
-- =============================================================================
-- First REAL subject migrated onto the three-face vocabulary. All three faces
-- bind to the ONE dataset that actually returns data on the configured lab,
-- "Capacity License Usage" (report 318): a monthly per-entity series carrying
-- Month / Entity Name / Used Capacity / Purchased Capacity. (The richer
-- "...Details" dataset errors on this lab — CacheDB parameter rejection — and
-- "...Summary Chart" returns 0 rows, so neither is usable here; the steering
-- decision was Option A: bind all three faces to "Capacity License Usage".)
--
-- Sentinel (verified against the live dev-box collect): inactive months return
-- -1 (NOT null, as the 0003 comment and the gw02 captures implied), active-zero
-- months return 0. The canonical path treats -1 AND null as the inactive
-- sentinel (-> n/a metric, gap in the line); 0 is a real value.
--
-- report_id "318" is PER-DEPLOYMENT (it varies per CommCell — backlog #23). This
-- binds against the one configured lab; cross-deployment report discovery is a
-- deferred backlog item, NOT phase 5. Bindings resolve by dataset_name +
-- report_id; any dataset_guid is a cache hint only (the extractor resolves the
-- live name -> GUID from report 318's definition).
--
-- Sections: capacity_license.summary (metric, exists) gains a REST binding;
-- capacity_license.table (table, exists) is re-bound with a column_map +
-- Purchased + conformance; capacity_license.chart (chart) is NEW.
-- -----------------------------------------------------------------------------

-- New chart section (capacity_license.summary + .table already exist from 0003).
INSERT OR IGNORE INTO subject_sections
    (subject_id, subject_version, section_id, title, section_type, default_selected, sort_order)
VALUES
    ('capacity_license', 1, 'capacity_license.chart',
     'Used Capacity trend', 'chart', 1, 3);

-- Re-seed all three REST bindings cleanly (the old single table binding is
-- replaced; summary + chart are added).
DELETE FROM subject_section_sources
WHERE section_id IN ('capacity_license.summary','capacity_license.table','capacity_license.chart')
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'capacity_license' AND subject_version = 1 AND source_type = 'rest'
  );

-- 1. metric — point-in-time utilisation from the latest month's Used / Purchased.
--    -1/null -> muted n/a; Purchased == 0 -> muted n/a (div-by-zero guard);
--    warn >= 70, critical >= 90.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'capacity_license.summary', json('{
    "report_id": "318",
    "dataset_name": "Capacity License Usage",
    "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
    "fields": ["Month", "Entity Name", "Used Capacity", "Purchased Capacity"],
    "orderby": "Month Asc",
    "parameters": {"type": 2},
    "column_map": [
        {"source": "Used Capacity", "canonical": "used_capacity", "type": "number"},
        {"source": "Purchased Capacity", "canonical": "purchased_capacity", "type": "number"}
    ],
    "output_as": "metric",
    "conformance": {"required_fields": ["used_capacity", "purchased_capacity"]},
    "metric": {
        "semantic": {"sentinel": -1},
        "items": [
            {"id": "used", "label": "Used Capacity", "unit": "MB", "source": "field", "field": "used_capacity"},
            {"id": "purchased", "label": "Purchased", "unit": "MB", "source": "field", "field": "purchased_capacity"},
            {"id": "utilisation_pct", "label": "Utilisation", "unit": "%", "source": "cel",
             "expr": "used / purchased * 100.0",
             "sentinel_when": "used == null || purchased == null || purchased == 0",
             "derived": true}
        ],
        "evaluative": {
            "rules": [
                {"rule_id": "capacity_utilisation", "target": "utilisation_pct", "kind": "threshold",
                 "comparison": ">=", "bands": [{"at": 90, "severity": "critical"}, {"at": 70, "severity": "warning"}],
                 "default_severity": "good", "mute_on_sentinel": true}
            ]
        }
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'capacity_license' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 2. table — monthly detail rows, clean column names via column_map.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'capacity_license.table', json('{
    "report_id": "318",
    "dataset_name": "Capacity License Usage",
    "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
    "fields": ["Month", "Entity Name", "Used Capacity", "Purchased Capacity"],
    "orderby": "Month Asc",
    "parameters": {"type": 2},
    "size_unit": "MB",
    "null_values": [null],
    "column_map": [
        {"source": "Month", "canonical": "month", "type": "string"},
        {"source": "Entity Name", "canonical": "entity", "type": "string"},
        {"source": "Used Capacity", "canonical": "used_capacity", "type": "number"},
        {"source": "Purchased Capacity", "canonical": "purchased_capacity", "type": "number"}
    ],
    "output_as": "table",
    "conformance": {"required_fields": ["month", "used_capacity", "purchased_capacity"]},
    "note": "-1 or null = license not active that month, not a data error"
}')
FROM subject_sources s
WHERE s.subject_id = 'capacity_license' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 3. chart — absolute Used Capacity over months (line). -1/null months -> gaps.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'capacity_license.chart', json('{
    "report_id": "318",
    "dataset_name": "Capacity License Usage",
    "dataset_guid": "43c5c8f8-5864-48de-8153-f85a91abd93a",
    "fields": ["Month", "Used Capacity"],
    "orderby": "Month Asc",
    "parameters": {"type": 2},
    "column_map": [
        {"source": "Month", "canonical": "month", "type": "string"},
        {"source": "Used Capacity", "canonical": "used_capacity", "type": "number"}
    ],
    "output_as": "chart",
    "conformance": {"required_fields": ["month", "used_capacity"]},
    "chart": {
        "chart_type": "line",
        "x_axis": {"label": "Month"},
        "y_axis": {"label": "Used Capacity (MB)"},
        "labels": {"source": "column", "column": "month"},
        "series": [{"id": "used_capacity", "label": "Used Capacity", "column": "used_capacity"}],
        "gap_values": [-1]
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'capacity_license' AND s.subject_version = 1 AND s.source_type = 'rest';
