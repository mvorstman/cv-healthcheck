-- =============================================================================
-- Migration 0016: backup_job_summary — three-face migration (ADR 0004 phase 7)
-- =============================================================================
-- The THIRD and last regressed-subject migration — closes ADR 0004's
-- regression-recovery arc. Four sections, all bound to the "Job details"
-- dataset of report "Backup Job Summary":
--
--   metric  (summary)          — Total Jobs (count of rows). Informational
--                                (render_mode "meta", NO rule/verdict).
--   card    (status_breakdown) — the six classify_job_status buckets as CEL
--                                counts. FIRST real build_card_section consumer.
--   findings(recent_failures)  — recent failed jobs.
--   table   (recent_jobs)      — clean columns + a "no jobs" empty-state.
--
-- DEFINING CONSTRAINT — the lab returns 0 rows (the "Job details" dataset on
-- this CommCell has totalRecordCount: 0). So phase 7's PASS posture is "empty
-- renders cleanly and informatively", NOT "see populated jobs":
--   * card  -> every bucket count is 0 (count() of an empty filter is 0, not
--              n/a) — the all-zero card, NO verdict, NO badge (empty-state A:
--              emptiness is shown, not graded).
--   * metric-> Total Jobs 0, informational, no verdict.
--   * table -> the declared empty_message instead of the bare "No data.".
--   * findings -> empty.
--
-- NO `conformance` block on any section. required_fields conformance fails on
-- 0 rows (present_fields is empty -> every required field "missing" -> the
-- section is dropped). On an empty-by-design subject that would erase all four
-- sections. Conformance (required_fields / cardinality min) is added when the
-- subject collects real data — a phase-8 item.
--
-- PHASE-8 correctness items (deferred, agreed at the phase-7 gate):
--   D2: the card's six buckets use exact-match CEL on the freetext `status`
--       ("Completed" etc.). classify_job_status's substring bucketing
--       ("Completed w/ one or more errors" -> "Completed with errors/warnings")
--       is Python-only and can't be expressed in the fixed CEL primitive set;
--       on the 0-row lab it's moot. Real-data bucket accuracy is phase 8.
--   recent_failures is bound to the whole "Job details" dataset; on real data
--       it must be filtered to failures (the same classifier) and mapped to
--       crit severity. Empty on this lab; correctness is phase 8.
--   metric is Total Jobs only — protected_clients_seen (a DISTINCT count) is
--       not expressible in the ADR's aggregation primitive set; left out
--       rather than widen the primitives (ADR stop-and-steer rule).
--
-- report_id "194" + dataset_name "Job details" + dataset_guid are per-deployment
-- (backlog #23 / #34); bindings resolve by dataset_name, the guid is a cache
-- hint. The raw source column NAMES below are authored from the normalizer's
-- aliases (normalize_backup_job_row) and are to be confirmed against a live /
-- raw capture (a 0-row response may carry no rows to read names from).
-- The four sections already exist from migration 0003; this flips
-- status_breakdown table->card and (re)binds their REST sources.
-- -----------------------------------------------------------------------------

-- status_breakdown was seeded as a `table` in 0003; phase 7 makes it a `card`.
-- (The CHECK already allows 'card' since migration 0012.)
UPDATE subject_sections
SET section_type = 'card'
WHERE subject_id = 'backup_job_summary' AND subject_version = 1
  AND section_id = 'backup_job_summary.status_breakdown';

DELETE FROM subject_section_sources
WHERE section_id IN (
        'backup_job_summary.summary',
        'backup_job_summary.status_breakdown',
        'backup_job_summary.recent_failures',
        'backup_job_summary.recent_jobs')
  AND source_id IN (
      SELECT id FROM subject_sources
      WHERE subject_id = 'backup_job_summary' AND subject_version = 1 AND source_type = 'rest'
  );

-- 1. metric — INFORMATIONAL Total Jobs headline (count of rows). 0 on the lab.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'backup_job_summary.summary', json('{
    "report_id": "194",
    "dataset_name": "Job details",
    "dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "output_as": "metric",
    "metric": {
        "render_mode": "meta",
        "items": [
            {"id": "total_jobs", "label": "Total Jobs", "source": "cel",
             "expr": "count(records)", "derived": true}
        ]
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'backup_job_summary' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 2. card — status breakdown: the six classify_job_status buckets as CEL counts.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'backup_job_summary.status_breakdown', json('{
    "report_id": "194",
    "dataset_name": "Job details",
    "dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "column_map": [
        {"source": "Job Status", "canonical": "status", "type": "string"}
    ],
    "output_as": "card",
    "card": {
        "columns": 3,
        "items": [
            {"label": "Completed", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Completed\"))"},
            {"label": "Failed", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Failed\"))"},
            {"label": "Completed with errors/warnings", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Completed with errors/warnings\"))"},
            {"label": "Running", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Running\"))"},
            {"label": "Killed", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Killed\"))"},
            {"label": "Other", "source": "cel",
             "expr": "count(records.filter(r, r.status == \"Other\"))"}
        ]
    }
}')
FROM subject_sources s
WHERE s.subject_id = 'backup_job_summary' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 3. findings — recent failures. Empty on the lab; failure-filtering + crit
--    severity mapping are phase-8 (see header).
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'backup_job_summary.recent_failures', json('{
    "report_id": "194",
    "dataset_name": "Job details",
    "dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "column_map": [
        {"source": "Client", "canonical": "parameter", "type": "string"},
        {"source": "Failure Reason", "canonical": "action", "type": "string"}
    ],
    "output_as": "findings"
}')
FROM subject_sources s
WHERE s.subject_id = 'backup_job_summary' AND s.subject_version = 1 AND s.source_type = 'rest';

-- 4. table — recent jobs, clean columns + a subject-specific empty-state.
INSERT INTO subject_section_sources (source_id, section_id, extraction_instructions)
SELECT s.id, 'backup_job_summary.recent_jobs', json('{
    "report_id": "194",
    "dataset_name": "Job details",
    "dataset_guid": "2638c3d3-adc7-4b61-bb24-2ba509229bf5",
    "column_map": [
        {"source": "Job Id", "canonical": "job_id", "type": "string"},
        {"source": "Client", "canonical": "client", "type": "string"},
        {"source": "Job Status", "canonical": "status", "type": "string"},
        {"source": "Start Time", "canonical": "start_time", "type": "string"},
        {"source": "Size", "canonical": "size", "type": "string"}
    ],
    "output_as": "table",
    "table": {"empty_message": "No jobs in the selected window"}
}')
FROM subject_sources s
WHERE s.subject_id = 'backup_job_summary' AND s.subject_version = 1 AND s.source_type = 'rest';
