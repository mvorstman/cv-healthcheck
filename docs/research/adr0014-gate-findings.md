# ADR-0014 curl-first gate — findings (2026-06-11)

Live verification of Reports Plus dataset addressing against the lab CommServe
(engine on the 11.34 lab VM), run entirely through the ADR-0008 loopback
(`scripts/adr0014_gate.py`; raw captures in `data/catalog/adr0014_gate/`,
gitignored — this document is the committed record). All probes read-only,
`limit`-bounded; `PackageDetails` untouched.

## 1. The composite address form is real — and the component half is the per-report entry guid

Test subject: License summary report (`id=206`,
`reportGuid=d7faef75-cf66-40a2-98ce-a2d0cc2a144b`), component
"Get Last Collection Time" (entry `guid=02878d11-7f2c-499b-a1c4-b40372639c17`,
inner `dataSetGuid=ff923e2a-13bc-45ee-bd09-8f613b6b68e3`).

| Address form | Result |
|---|---|
| `datasets/{dataSetGuid}/data` | **500** errorCode 15020 "could not find data set" |
| `datasets/{reportGuid}:{entryGuid}/data` | **200** — full dataset envelope |
| `datasets/{reportGuid}:{dataSetGuid}/data` | **500** errorCode 15020 |

So for **report-bound** datasets only the composite works, and the second half
is the page-level `dataSets.dataSet[]` **entry `guid`** (the per-report
component/instance), *not* the underlying `dataSetGuid`. In the live report
definition JSON these sit at: entry `guid` on the array element, with
`dataSet.{dataSetGuid,dataSetId,dataSetName}` nested one level down. (For some
entries the two GUIDs coincide; for the License summary core datasets they
differ — relying on `dataSetGuid` would silently address the wrong thing or
500.)

**Standalone/deployed** datasets keep working with the bare GUID:
`datasets/2b3e43c0-21fe-401d-ebf8-c485309262a7/data` (AuditTrailDataset) →
200. Both forms are first-class; a subject binding must be able to declare
either.

## 2. Response envelope is the familiar one

Both address forms return the standard dataset envelope the existing `rest`
extractor already consumes: `cacheId`, `columns[]`
(`dataField`/`displayName`/`name`/`type`/precision), `records`,
`recordsCount`, `totalRecordCount`, `failures`, `warnings`, `limit`,
`offset`. No new response parsing is needed in the ADR-0014 extractor.

## 3. Parameter convention: `parameter.<datasetParamName>`, `[]` suffix for lists — honored, but unknown names are silently ignored

Discriminating probes on AuditTrailDataset (782 audit rows in the lab), which
declares `userlist` (Integer, `isList: true`) among its `GetOperation`
parameters:

| Probe | totalRecordCount |
|---|---|
| `?limit=3` (no params) | 782 |
| `?limit=3&parameter.userlist[]=999999` (nonexistent user) | **0** |
| `?limit=3&parameter.userlist[]=1&parameter.userlist[]=2` | **759** |
| `?limit=3&parameter.noSuchParam=1` | 782, no `failures`, no warning |

Conclusions:

- The query key is `parameter.` + the **dataset parameter name** (the
  `GetOperation.parameters[].name`, e.g. `userlist`, `i_days`), not the
  report-level input id (e.g. `TimeFrame`). Report inputs are wired to dataset
  parameters inside the definition (`values: ["=input.TimeFrame"]` on
  parameter `i_days`); the datasets endpoint speaks the dataset-parameter
  vocabulary.
- List-valued parameters (`isList: true`) repeat as `parameter.name[]=v1&parameter.name[]=v2` and are honored.
- The brief's `parameter.timeframe` / `parameter.datasource[]` are instances
  of this one generic convention on whatever dataset was originally probed —
  there is no special timeframe/datasource machinery to build.
- **Silent-misconfiguration risk:** an unknown parameter name does not error —
  the engine ignores it and returns unfiltered/default-parameterized data.
  A typo'd parameter name in a subject binding would collect *wrong data
  successfully*. Implementation should cross-check declared parameter names
  against the dataset's declared `GetOperation.parameters` (available via the
  report definition or dataset metadata) and fail loudly on a mismatch, rather
  than trusting the 200.

## 4. Operational notes

- The "leading-slash 401 errorCode 5" quirk in the original brief did **not**
  reproduce as described: with a stale held token, *both* slash forms 401
  identically; with a fresh token, the leading-slash form (the stored-endpoint
  convention) works fine through the loopback. The 401s observed during the
  gate were stale-token artifacts, not path-normalization ones.
- Cause of the repeated "stale token": the dev app runs `flask run --debug`;
  the Werkzeug reloader restarts the child process on any `.py` change in the
  tree, wiping the ADR-0008 in-memory token store. Finish code edits before
  connecting; `.md`/`.json` writes are safe.
- `scripts/adr0014_gate.py` wart (cosmetic): capture slugs truncate at 60
  chars, so long composite addresses with different query strings overwrite
  one capture file. Fix alongside implementation; the findings above are the
  durable record.

## Implication for ADR-0014 D1 (binding shape)

`dataset_address` as a single opaque string (bare GUID or
`{reportGuid}:{entryGuid}`) is confirmed workable. Validation: one GUID, or
two GUIDs joined by `:`. Authoring guidance must say the composite's second
half is the report definition's per-report entry `guid` — discoverable from
`GET /cr/reportsplusengine/reports/{id}` (`scripts/adr0014_gate.py report
<id>` lists the pairs).
