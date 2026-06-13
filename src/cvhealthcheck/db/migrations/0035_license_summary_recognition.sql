-- 0035_license_summary_recognition.sql
--
-- ADR-0017 promotion, commit 3/4: broaden License Summary HTML recognition so the
-- live generic path can RECOGNIZE real workload-heavy exports. It can already
-- EXTRACT them (commit 1); recognition currently rejects them first.
--
-- Changes to the html source's recognition_hints:
--   * has_selector  ".reportstabletitle"  ->  ".reportstabletitle, h2"
--       accept either marker (the export wrapper OR a plain <h2> heading).
--   * DROP table_count (was 2, matched with != at recognition.py:152). Real
--     workload-heavy exports have 7 tables, so the exact count rejected them
--     before extraction — the direct cause of the live HTML failure. NOT replaced
--     with a different exact count.
--   * DROP first_table_headers (was ["License","Available Total","Used"], an exact
--     subset check). A workload export's FIRST table is "Capacity Licenses" with
--     headers like "Available Total (TB)" — the unit suffix fails the exact
--     subset, so this also rejected the file. Loosening it to match unit-suffixed
--     headers would be header-shape recognition, which ADR-0017 D3 retires; so it
--     is removed, not fuzzed.
--
-- title_contains "License summary" is RETAINED: it is what keeps the scoped-out
-- titleless classifier fixtures (no <title>/<h1>, no .reportstabletitle, no <h2>)
-- from recognizing — recognition does NOT fall back to header-shape.
--
-- Recognition ONLY — NO route switch, NO recipe change, NO REST change, NO
-- header-shape recognition. The csv/rest sources are untouched.

UPDATE subject_sources
   SET recognition_hints = json('{"title_contains": "License summary", "has_selector": ".reportstabletitle, h2"}')
 WHERE subject_id = 'license_summary'
   AND subject_version = 1
   AND source_type = 'html';
