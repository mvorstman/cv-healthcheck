# ADR 0014 — Reports Plus dataset extraction as a dedicated declarative source type

- **Status:** Accepted
- **Date:** 2026-06-11
- **Deciders:** Michiel (sole maintainer)
- **Bounded by:** ADR 0006 (declarative extraction boundary — D1 one canonicalization path, D2 admissible declarative surface, D3 per-operator gate)
- **Within:** ADR 0008 (app-mediated auth — the AI/MCP layer holds no CommServe token)
- **Related:** ADR 0003 (Reports Plus REST extractor, GET-only protocol), ADR 0009 (MCP-authored Command Center API sources)

---

## Context

The goal of zero-code subject authoring requires `extraction_instructions` to reach every data family the platform collects from. One family has no declarative path: **Command Center Reports Plus datasets addressed directly**, served by the datasets engine at `/commandcenter/api/cr/reportsplusengine/datasets/...`.

Two existing source types come close but neither expresses it:

- **`rest` (ADR 0003).** Addresses Reports Plus datasets *indirectly*: `report_id` is required, the extractor GETs the live report definition, walks it for a name→guid map, and resolves `dataset_name` (the canonical reference; `dataset_guid` is only a fallback hint). A dataset addressed directly — without a containing report walk — does not fit this protocol.
- **`rest_command_center_api` (ADR 0007/0009).** Plain GETs of Command Center API resources (`/commandcenter/api/...`), generalized along the endpoint and shape axes. It carries no dataset-engine conventions: no composite addressing, no `parameter.*` query-parameter vocabulary.

What direct dataset addressing needs, per the 2026-06 engagement brief and partially confirmed by lab captures:

- **Address:** a dataset GUID path segment. Lab captures (`data/catalog/execution_validation.json`, 2026-05) show the bare-GUID form `datasets/{guid}/data` working. The brief additionally asserts a **composite** form `{reportGuid}:{componentGuid}` for report-component datasets; this form appears **nowhere in the repo's captures and is unverified** — it must be confirmed curl-first (via the ADR-0008 probe) before any code is written against it.
- **Query parameters:** `parameter.*`-prefixed values (lab-confirmed: `parameter.ccGroupId`, `parameter.slaDays`, …; brief asserts `parameter.timeframe` and list-valued `parameter.datasource[]`).
- **Existing plumbing:** `reportsplus/client.py` already builds on `/commandcenter/api/cr/reportsplusengine/datasets` and `get_dataset_data()` already accepts an arbitrary `parameters` dict. The gap is the declarative surface and its collect dispatch, not HTTP plumbing.

A known related quirk, recorded here so it is not "fixed" in the wrong place: the ADR-0008 probe handler reportedly returns 401 errorCode 5 for a leading-slash path while the collector requires the leading-slash form. Unverified against the live lab; `api_client._build_url` normalizes paths to a leading slash, so a trailing slash on `base_url` (double-`//` join) is the likely mechanism. If real, the fix belongs in the probe/app path handling — **not** in the stored-endpoint convention, which stays leading-slash relative.

## Decision

Introduce a **new declarative source type, `reportsplus_dataset`**, for subjects whose evidence is a directly-addressed Reports Plus dataset.

1. **Binding.** `subject_sources.source_type = "reportsplus_dataset"`. The source declares a `dataset_address` — either a bare dataset GUID or the composite `{reportGuid}:{componentGuid}` form — stored in `recognition_hints` (the ADR-0009 pattern; no schema migration).
2. **Section vocabulary.** Per-section `extraction_instructions` reuse the existing sanctioned surface unchanged: `output_as` (`table` / `card` / `findings` / `metric`), `column_map`, coercions, `null_values`, `fields` / `orderby` / `limit`, plus a `parameters` dict whose keys are the dataset engine's `parameter.*` query parameters (a list value serializes as a repeated `parameter.name[]` parameter). This is source selection plus structural projection only — **no new operator enters the declarative surface; nothing here passes or widens the ADR-0006 D3 gate.**
3. **One extractor, one tail.** A `ReportsPlusDatasetExtractor` fetches via the existing `reportsplus` client path and ends at `ExtractionResult`, feeding the unchanged `result_to_artifact` → `save_artifact` tail. ADR-0006 D1/D4.1 hold: per-source-family extractors are the established pattern (html / csv / rest / cc-api); the canonicalization path stays single.
4. **MCP authoring.** `propose_new_subject` vocabulary gains `reportsplus_dataset` with the `dataset_address` field. The AI-asserted address is untrusted input: app-side validation confirms the GUID / composite-GUID format and confines collection to read-only GETs under `/commandcenter/api/cr/reportsplusengine/datasets/`. The MCP layer asserts a classification plus an address — never a token, host, or write (ADR 0008).
5. **Curl-first gate.** Before implementation, the composite address form and the `parameter.timeframe` / `parameter.datasource[]` conventions are verified against the live lab through the ADR-0008 probe, and the captured shapes recorded. The `PackageDetails` dataset is **never** probed or collected (credential-exposure risk).

## Consequences

- A subject backed by a directly-addressed Reports Plus dataset becomes authorable purely as data, closing the last known source-family gap in the zero-code path.
- A third live-collection source type joins the dispatch in `/quick-hc/<subject_id>/collect` (today a binary CC-API-vs-REST branch); the dispatch becomes a by-source-type selection across three extractors.
- Touch points beyond the extractor: `_SOURCE_TYPE_TO_LABEL` (registry.py) gains a label; `result_to_artifact._SOURCE_TYPE_MAP` gains a mapping (live source — `collected_at` set); `subject_data_service` source metadata; `propose_new_subject` docstring vocabulary; address validation beside `cc_endpoint.py`.
- A second AI-asserted collection target exists (after ADR-0009's endpoint). Same mitigation shape: app-side format/read-only/path-prefix validation at persist and again at collect.
- The existing `rest` label "REST / Reports Plus" now sits beside "Reports Plus dataset"; the labels must make the indirect/direct distinction legible rather than synonymous.

## Alternatives considered

- **Parameter support on `rest_command_center_api`.** Rejected. The datasets engine is a different API family from CC-API resource GETs: its own addressing grammar (composite GUIDs), its own parameter convention (`parameter.*`), its own response envelope. Welding it into the CC-API extractor turns a protocol difference into runtime branching inside one extractor, and the catalog's labels / source metadata / collect routing all key off `source_type` — one type for two protocols blurs every one of those seams. ADR-0009 generalized that extractor along endpoint and shape axes deliberately; a protocol axis is where that generalization stops.
- **Extend `rest` (the ADR-0003 discovery path).** Rejected. Its contract is *name-as-canonical-reference resolved through a live report-definition walk* with `report_id` required — a deliberate ADR-0003 decision. Direct addressing bypasses the walk entirely; making `report_id` optional forks the protocol semantics inside one extractor and quietly demotes the canonical-reference contract to "sometimes".
- **Bespoke Python per subject.** Rejected. Defeats the zero-code goal for an operation that is pure source selection + structural projection, squarely inside ADR-0006 D2. Bespoke is for logic that *fails* the D3 gate, not for plumbing the platform lacks.

## Open questions

- **Artifact `SourceType` mapping.** Map `reportsplus_dataset` to `SourceType.rest` (consistent with the existing `rest` collection output) or to the legacy `SourceType.reportsplus_rest` (today only the retired SA adapter value). Recommendation: `SourceType.rest`; decide at build time.
- **Composite-address reality.** ~~If the curl-first gate shows the composite form is *not* a path segment, the address grammar in D1 adapts.~~ **Resolved 2026-06-11 by the gate** (`docs/research/adr0014-gate-findings.md`): the composite *is* a path segment and is the only working form for report-bound datasets; its second half is the report definition's per-report **entry `guid`** (not the underlying `dataSetGuid`). Bare GUIDs work for standalone datasets. The query convention is the generic `parameter.<datasetParamName>` (repeated `name[]` for lists); unknown names are **silently ignored** by the engine, so implementation must validate declared parameter names against the dataset's declared parameters and fail loudly on mismatch.

## Revisit triggers

- A dataset turns out to need a per-field transform outside the sanctioned coercion set → that transform goes through the ADR-0006 D3 gate individually; it does not widen this ADR.
- A fourth live source family appears → consider a shared live-collect dispatch/registration seam instead of a growing if/elif in the collect route.

## References

- Engagement brief: `HANDOVER.md` (2026-06-11 reconciliation — Fix 4).
- Lab captures: `data/catalog/execution_validation.json` (bare-GUID `datasets/{guid}/data` + `parameter.*`), `data/catalog/datasets_summary.json`.
- Existing plumbing: `src/cvhealthcheck/reportsplus/client.py` (`DATASETS_PATH`, `get_dataset_data`).
- Protocol precedents: ADR 0003 (`rest` discovery protocol), ADR 0009 (declared endpoint + untrusted-input validation pattern, `cc_endpoint.py`).
