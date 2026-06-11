# HANDOVER — Declarative ("in-data") report authoring: engine work

You are continuing development on **cv-healthcheck**, a modular Commvault
operational health check platform (Python/Flask, Pydantic v2 canonical
artifact schema, MCP server for AI-assisted subject authoring).

## Goal

Make it possible to add **any** report subject purely as data
(`extraction_instructions` in a subject definition) with **zero bespoke
Python**. Simple subjects already work this way across HTML/CSV/REST and
Command Center API sources.

## State after the 2026-06-11 reconciliation (scope confirmed by Michiel)

An earlier version of this brief, written outside the repo, listed four
engine fixes. Step-0 validation against the repo found three of them
already resolved or moot:

- **Fix 1 — `_resolve_field_path` list indexing: shipped.** Commit
  `819c723` (2026-06-04); numeric path segments index into lists, dict-key
  semantics win. Tests: `tests/test_resolve_field_path.py`. **Closed.**
- **Fix 2 — "staging validator strips ADR-0009 fields": not reproducible.**
  A proposal carrying every ADR-0009 field (declared `endpoint`, extra
  `recognition_hints`, card spec, table `root_key`/`columns`/`transpose`)
  round-trips byte-identical through `propose_new_subject` storage and
  `create_subject_from_proposal`. A guard test now pins this:
  `tests/test_proposal_field_roundtrip.py`. **Closed (guarded).**
- **Fix 3 — `wrap_object_as_row` hint: superseded.** Commit `d1860c4` made
  the single-object → one-row-table dict auto-wrap *unconditional* in
  `_project_table_rows` (`extractors/command_center.py`); the hint is
  deliberately not plumbed. Covered in
  `tests/test_cc_api_multi_object_adr0009.py`. **Closed (no hint needed.)**
- **Fix 4 — Reports Plus dataset extraction: the one genuine gap.**
  No declarative path targets directly-addressed Reports Plus datasets
  (`/commandcenter/api/cr/reportsplusengine/datasets/...`). Design decided
  as a **new source type** in **ADR-0014 (Proposed — awaiting human
  approval)**: `docs/adr/0014-reportsplus-dataset-source-type.md`.
  **Do not implement before the ADR is accepted.**

## Next step (after ADR-0014 approval)

Implement `reportsplus_dataset` per the ADR, in this order:

1. **Curl-first gate** (via the ADR-0008 probe; the MCP layer never holds a
   token): verify the composite `{reportGuid}:{componentGuid}` address form
   and the `parameter.timeframe` / `parameter.datasource[]` conventions
   against the live lab; record captured shapes. The bare-GUID form and
   `parameter.*` params are already evidenced in
   `data/catalog/execution_validation.json`.
2. Address validation (format + read-only + path-prefix), beside
   `extractors/cc_endpoint.py`.
3. `ReportsPlusDatasetExtractor` ending at `ExtractionResult`, feeding the
   unchanged `result_to_artifact` → `save_artifact` tail (ADR-0006 D1/D4.1).
4. Collect dispatch (third branch in `/quick-hc/<subject_id>/collect`),
   label map, `_SOURCE_TYPE_MAP`, source metadata, `propose_new_subject`
   vocabulary.
5. Tests per piece; full suite stays green (baseline: 1030 passed,
   2026-06-11).

Known related quirk (verify before "fixing"): the probe handler reportedly
401s (errorCode 5) on a leading-slash path while the collector requires the
leading-slash form. `api_client._build_url` normalizes to a leading slash,
so a trailing slash on `base_url` is the likely mechanism. If real, fix it
in the probe/app path handling — never by changing the stored-endpoint
convention (leading-slash relative).

## Parked — legacy-builder conversion (decision 2026-06-11)

The six legacy Python builders (`report_service._report_builders`) are:
environment, security_assessment, license_summary, client_growth,
capacity_license, backup_job_summary. ("Health" in the earlier brief =
**security_assessment**.)

Converting License Summary (and security_assessment) to declarative form is
**parked, not planned**: ADR-0006 D5 registers License Summary as
*sanctioned bespoke, indefinite* (its param-substitution and per-row
formulas failed the D3 gate), and ADR-0013 lists "License Summary generic
extractor migration" as a non-goal. Those decisions stand.

**Re-assessment trigger:** after Fix 4 ships, re-assess whether License
Summary's blockers can now pass the declarative gate (ADR-0006 D3). If yes,
that re-assessment becomes the evidence for an ADR superseding D5's
register entry; if no, D5 remains correct. Do not start this without
explicit confirmation.

## Hard constraints (non-negotiable)

- **Never approve staged artifacts.** Approval is always the human's
  manual step via the web interface. Do not call approval endpoints, do
  not set `reviewed_by`, do not bypass staging.
- ADR-0008 trust boundary stays intact: no credentials in the AI/MCP layer;
  live reads go through the loopback probe only.
- Never probe or collect the `PackageDetails` catalog dataset
  (credential-exposure risk).
- `delete_subject` removes **all** versions; re-proposing without
  `supersedes` creates duplicate actives — be careful with both.
- Keep the legacy builder path working; conversion is parked (above).

## Validation

- `python -m compileall src`
- `venv/bin/python -m pytest` (existing tests must keep passing)

## Commit granularity

One commit per coherent piece; ADR drafts committed separately.
