# ADR 0009 — MCP-authored and multi-object Command Center API sources

- **Status:** Accepted
- **Date:** 2026-06-02
- **Deciders:** Michiel (sole maintainer)
- **Extends:** ADR 0007 (declarative single-object Command Center API source + `environment` migration) — this ADR carries 0007's source path to (a) collection-shaped responses and (b) MCP-authored subjects. 0007's Decision and Outcome stand; nothing here reopens them.
- **Bounded by:** ADR 0006 (declarative extraction boundary — D1 single canonicalization path, D2 admissible declarative surface, D3 per-operator gate, D4.4 "fix the extractor, not the renderer").
- **Within:** ADR 0008 (cv-healthcheck is the trust boundary; the AI/MCP layer holds no CommServe token and never calls CommServe directly).

---

## Context

ADR 0007 established the Command Center API source track: the `CommandCenterExtractor`, the `rest_command_center_api` source binding (built on the existing `SourceType.rest_commserve`), and the `/collect` route dispatching an extractor **by source type**. It deliberately scoped itself to a **single-object** response (the `GET /commandcenter/api/CommServ` identity object → one record → a card spec) and to a subject seeded by **migration** (`environment`, via migrations 0026/0027).

Two real subjects now fall outside that scope:

- **Created via MCP, not migration.** `server_groups` — and any future AI-proposed subject — is authored through `propose_new_subject` → `create_subject_from_proposal`. A read-only investigation (against `feature/basic-healthcheck-report-output`, HEAD `0e31748`; reconfirm, HEAD may have moved) found the MCP vocabulary offers only `html` / `csv` / `rest` / `json`. An AI cannot classify a Command Center source, so it is forced to `rest`; its real endpoint (`/commandcenter/api/v4/servergroup`) lands **inert** inside `recognition_hints` and is never read back. The label map keys off `source_type` with no endpoint inspection, so `rest` flattens to "REST / Reports Plus", no source metadata surfaces, and Collect has no working endpoint.
- **Collection-shaped, not single-object.** `server_groups` is an inventory (membership counts, association type, company scope across many groups) served by a collection endpoint — multiple records, a table spec — not the single identity card 0007's extractor emits. (Exact shape to be confirmed curl-first; `server_groups` serves only as the end-to-end test case — see the acceptance test below.)

This is precisely the failure mode ADR 0007 names in its own Context: a subject must not be "bespoke merely by plumbing… because it is collected or served through a different pipe." `server_groups` is second-class only because of how it was created and the shape it returns — not because its shape is genuinely un-canonical. The uniform-track principle is already accepted; this ADR removes the two plumbing obstacles to honouring it.

The hidden cost the investigation surfaced: `CommandCenterExtractor` is welded both to `get_commcell_identity` (the CommServ identity GET) and to a single-record card emission. So merely binding a subject as `rest_command_center_api` **without more** would fix the label while routing Collect to the wrong endpoint and the wrong shape — a worse, silent failure than the current honest mislabel. The missing capability is the extractor, not the binding format.

---

## Decision

### D1 — Generalize the Command Center extractor along two axes

Extend the existing `CommandCenterExtractor` — **do not add a parallel extractor** (that would violate ADR 0006 D4.1, one canonicalization path) — so it accepts:

1. **An arbitrary relative endpoint** declared by the subject's source binding, defaulting to the CommServ identity endpoint when none is declared (so `environment` is unchanged).
2. **A collection (multi-record) response** projected into a **table** spec, in addition to the single-record card spec it emits today.

The extractor still ends at `ExtractionResult` and feeds the existing, unchanged `result_to_artifact` → `save_artifact` tail (ADR 0006 D1 / D4.1). Multi-record projection into rows/sections is **structural projection**, already sanctioned by ADR 0006 D2 — it adds no operator and does not widen CEL. **Any per-field transform** `server_groups` (or a later subject) turns out to require beyond the sanctioned coercion set (`string` / `int` / `float` / `timestamp` / `hex`) must clear the ADR 0006 D3 gate **individually**; this ADR pre-blesses none.

### D2 — MCP-authored Command Center API source declaration

Extend the authoring path so an AI proposal can declare a Command Center API source instead of being forced to `rest`:

- `propose_new_subject` accepts `rest_command_center_api` as a source kind, with an explicit **relative** endpoint (the documented vocabulary gains the type + endpoint field).
- On approval, `create_subject_from_proposal` persists a `rest_command_center_api` `subject_sources` row carrying the endpoint, plus the `subject_section_sources` binding — modelled on the human-authored migration template that wired `environment` (0026/0027). Label, source-metadata, and collect-routing already key off `source_type`, so they follow automatically; **no labeller change is required.**

The AI-asserted endpoint is **untrusted input.** The app validates it as a **relative, read-only** Command Center path before persisting or collecting against it (consistent with ADR 0008's principal / capability contract). The MCP layer asserts only a classification and a path string — never a token, never an absolute URL, never a write.

### D3 — Reject auto-derivation from the recognition hint

The endpoint will **not** be silently promoted from `recognition_hints` into a classified source at propose-time (the investigation's option (b)). Auto-derivation bypasses the authored, human-reviewed proposal seam that ADR 0006's "default in-bounds path" and ADR 0007's parity gate are built around, and it scatters endpoint truth across a hint, a derived row, and storage. Classification is **declared** (D2), not inferred.

### D4 — Trust boundary unchanged

Collect remains the app-side, in-process path (the app holds the token; ADR 0008). Nothing in D1–D3 gives the MCP/AI layer a token or a direct CommServe call; the only thing crossing from MCP is a classification plus a relative path string, validated app-side. A generalized extractor that takes a catalog-declared endpoint **must** keep the single app-side GET contract and must never let the MCP mint or carry a token.

---

## Acceptance test (validates the mechanism; `server_groups` is the throwaway test case)

`/v4/servergroup` is the **live REST call used to prove the import path end-to-end** once D1–D2 are built — **not** a `server_groups` subject to be authored, parity-proven, and shipped. `server_groups` is deleted and re-imported only as the test fixture; it is not a deliverable and may be discarded after. No repair migration is written; the fresh proposal *is* the test.

Per the project principle (curl first, code second):

1. Read-only `GET https://192.168.182.129:4433/commandcenter/api/v4/servergroup` (lab, self-signed, app-held token); record the live JSON shape — this is the real multi-record payload the generalized extractor (D1) is exercised against.
2. Re-import `server_groups` through the new authoring path (D2): propose it as a `rest_command_center_api` source with the `/v4/servergroup` endpoint, then approve it. Map only enough of the live shape to render a table — test scaffolding, not a production column map. (Any field that would need a transform outside the sanctioned coercion set still goes through ADR 0006 D3 rather than widening the declarative surface — but for a test that pressure shouldn't arise; if it does, that itself is a finding.)
3. Confirm the full loop: the subject classifies as **Command Center API** (not Reports Plus); the source panel shows the endpoint / host / "Validated"; and **Collect hits `/v4/servergroup`** (not the CommServ identity endpoint) and returns + renders data.

Success criterion is "the import path produces a correctly-classified, collectable CC-API source from an MCP proposal," **not** "`server_groups` is shipped."

---

## Consequences

- The catalog remains the single source of truth for what a subject collects; an AI proposal can now classify a Command Center source correctly at authoring time instead of being forced to `rest` and mislabelled.
- The CC-API source track now covers both single-object (card) and collection (table) responses through one extractor and one canonicalization path — no parallel producer (ADR 0006 D4.1 held).
- **The real blast radius is the extractor generalization**, not the binding shape. The endpoint and shape axes are where the work and the risk sit; the binding / label / metadata follow for free once `source_type` is `rest_command_center_api`.
- A new trust-relevant input appears — an AI-asserted endpoint. It is mitigated by app-side relative / read-only validation (ADR 0008), but it is the first time an MCP proposal influences a collection target and should be reviewed as such.
- This ADR sanctions the *mechanism*, not any `server_groups` mapping. `/v4/servergroup` is used only as the end-to-end test of the import path (see the acceptance test); a polished, parity-gated `server_groups` subject is explicitly **not** a goal here.

---

## Alternatives considered

- **Auto-derive the source from the hint endpoint (option b).** Rejected — see D3 (bypasses the review seam, scatters endpoint truth).
- **Bind `server_groups` as `rest_command_center_api` without generalizing the extractor (label-only).** Rejected — fixes the label but routes Collect to the CommServ identity endpoint and a single-record card shape, silently returning wrong data. Worse than the current honest mislabel.
- **A second, collection-specific Command Center extractor.** Rejected — violates ADR 0006 D4.1 (one canonicalization path) and reintroduces the per-shape coupling ADR 0007 retired. Generalize the one extractor instead.
- **Amend ADR 0007 in place.** Rejected — 0007 is Accepted, shipped, and carries a governing Outcome section; this extension is recorded as a new ADR that depends on it, matching how 0007 itself chains off 0006.

---

## Open questions

- **Single shared CC-API extractor vs. shape dispatch within it.** Whether the card / table distinction is a branch inside the one extractor or a thin shape-selector is an implementation choice; the invariant (one canonicalization path) holds either way. Confirm at build time.
- **Endpoint storage location.** The endpoint can live inside `recognition_hints` (no schema migration; the JSON column already exists) or a dedicated `subject_sources` column. The hint-carried option is the smaller change; confirm on disk it is clean before choosing.
- **Re-import vs. inert legacy row.** `environment` left its pre-migration plain-`rest` row inert (ADR 0007 Parked (b)). Re-importing `server_groups` should avoid leaving an equivalent inert `rest` row; confirm the delete path removes all of its `subject_sources` rows.

---

## Revisit triggers

- A proposed CC-API subject needs a per-field transform that fails ADR 0006 D3 yet recurs often → revisit the admissible-operator scope (not these invariants).
- Multi-user / multi-worker deployment (ADR 0008's accepted single-process constraint) → the app-side collect path and token store must be revisited before this source type is relied on under concurrency.
- Any future ADR introducing a second artifact producer → re-affirm ADR 0006 D1 / D4 against it.

---

## Reference seams (from the 2026-06-02 read-only investigation; reconfirm against disk — HEAD may have moved from `0e31748`)

- **Source binding:** `subject_sources` (migration 0027); `rest_command_center_api` template via migrations 0026/0027; persisted by `create_subject_from_proposal` (`db/subjects.py`).
- **Label / source-metadata:** `_SOURCE_TYPE_TO_LABEL` (`registry.py`); `_command_center_source_meta` + `_build_generic_sources` (`subject_data_service.py`); front-end source panel (`quick_hc.js`).
- **Extractor:** `CommandCenterExtractor` wrapping `get_commcell_identity` (`command_center.py`); by-source-type `/collect` dispatch (`quick_hc.py`).
- **MCP authoring:** `propose_new_subject` docstring / signature (`mcp/server.py`); approval write (`db/subjects.py`).
- **Canonicalization tail (unchanged):** `result_to_artifact` → `save_artifact`.
