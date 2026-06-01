# ADR 0007 — Declarative single-object source + environment migration

- **Status:** Accepted (2026-06-01) — implemented and render-verified; see Outcome below.
- **Date:** 2026-06-01
- **Deciders:** Michiel (sole maintainer)
- **Depends on / ratifies:** ADR 0006 (declarative extraction boundary — currently *Proposed*). This ADR is the worked example that exercises 0006's boundary; accepting 0007 should move 0006 to *Accepted*.
- **Related:** ADR 0001 (source-building fork — the "bespoke" track this retires for `environment`), ADR 0004 (three-face vocab + CEL freeze), ADR 0003 (REST extractor + the `license_summary` "LS caveat").

---

## Context

The project's intent is **one uniform, declarative subject model**: how and where a subject is created should not determine its track. A subject is bespoke only when it is *bespoke by shape* — the canonical schema genuinely cannot represent what it is (e.g. `security_assessment`'s `counters` / `findings_grid` view shapes, per ADR 0001). A subject must **not** be bespoke merely *by plumbing* — because it is collected or served through a different pipe.

`environment` (CommCell Details) is the clearest case of bespoke-*by-plumbing*. Its shape is the most standard possible — an identity card, already proven generically by the `_card_test` subject. What keeps it off the uniform track today is entirely wiring:

- It is fed by the single-object Command Center call `GET /commandcenter/api/CommServ`, not a Reports-Plus dataset.
- It is **rebuilt live each request** by `_build_environment_subject` reading `data/catalog/rest/commserv.json`; it writes **nothing** to the artifact store.
- Two field values need shaping the declarative instruction format can't express: a **nested-path read** (`csTimeZone.TimeZoneName`, `commcell.commCellId`) and a **computed display** (CommCell ID shown as hex).

A read-only investigation (2026-06-01, against source at HEAD `6d00488`) confirmed the gap report and established the seams below. The decisive findings:

- **The downstream pipeline is already generic and source-agnostic.** `result_to_artifact` and the section builders render whatever spec the extractor carries. The gap is entirely *which extractor carries which spec*.
- **Field mapping is flat everywhere.** `column_map` is an untyped `list[dict]` resolved by `.get()` (`html.py:310-313`, `csv.py:312`, `rest.py:303`); the card path reads top-level keys only (`card_section.py:82-90`). Nested traversal is **never exercised** on the proven path.
- **`type` is coercion, not transform** (`html.py:347 _coerce`: `string`/`int`/`float`). There is no `hex`/format primitive anywhere, and **CEL is frozen** at six aggregations with widening explicitly forbidden (`evaluator.py:25-27`, `:110-117`).
- **`environment` collect → store does not exist.** The generic `/collect` route already does collect→store but is welded to `RESTExtractor` (`quick_hc.py:217-219`). `generated_at` is set at **collect** time (`result_to_artifact.py:52,168`) — so a stored environment artifact gets a collection timestamp for free.

The maintainer has decided: **`environment` becomes a stored-on-collect canonical artifact. No live view.** A Collect button reads CommCell Details, stores, evaluates, and renders the stored artifact like every other subject. The collection timestamp is kept via the canonical `generated_at` field.

---

## Decision

### D1 — New `command_center_api` single-object source type + extractor

Introduce a source type for single-object Command Center API responses (distinct from the Reports-Plus, row-oriented `RESTExtractor`). The extractor wraps the existing `get_commcell_identity` collector (`commcell.py:23-44`), emits an `ExtractionResult` whose record set is a **single record** (the CommServ object), and carries a **card spec**. It feeds the existing, unchanged `result_to_artifact` → `save_artifact` tail.

The generic `/collect` route is made **extractor-pluggable by source type** rather than hard-wired to `RESTExtractor` (`quick_hc.py:217-219`). All other route behaviour (active-customer / hostname / auth checks, store call) is reused as-is.

### D2 — Nested-path field selector (general read extension)

Extend the field selector so `"field"` (card/metric specs) and `"source"` (table specs) may be a **dot-separated path** (e.g. `"field": "csTimeZone.TimeZoneName"`). Resolution traverses nested dicts; a missing segment resolves to null, consistent with today's `.get()` behaviour. Implemented **once**, in the shared field-resolution helper used by the card/metric path — source-agnostic, useful to any future nested/single-object source.

This is **not** routed through CEL member-access. Although `celpy` could theoretically read nested fields, that path is unproven, pushes an extract-stage concern into the evaluate-stage expression layer, and does not solve D3.

### D3 — `hex` as a coercion-family value

Add `hex` to the existing `type` coercion set (`html.py:347 _coerce`), as a sibling of `string`/`int`/`float`. It reads the integer and formats it lowercase, no `0x` prefix (e.g. `13183` → `337f`). The **raw integer is preserved in metadata**, not discarded.

This is deliberately **not CEL** and does **not** violate the ADR 0004 freeze. CEL is an open expression/aggregation evaluator over records; a closed, enumerated coercion set is bounded by construction and is a sibling of what already exists. New coercion values are added only by explicit decision, not authored in instructions.

> **Decision rationale (settled 2026-05-31):** CommCell ID is displayed as **hex** because it matches what Command Center shows, which is what anyone cross-checking the report expects. The stored value is the formatted hex string with the raw integer in metadata — i.e. coercion-family, not a store-raw / defer-to-render design. The card path has no per-field render-format layer to defer into, and the parity target stores the formatted value.

### D4 — `environment` becomes stored-on-collect; live-serve retired

`environment` joins the standard lifecycle: **collect → store → evaluate → render**.

- A Collect button fires `GET /commandcenter/api/CommServ`; the raw payload remains as provenance (today's `commserv.json` becomes the raw source, not the served view).
- The `command_center_api` extractor (D1) produces a card-section `CanonicalArtifact`, written to `working/environment/latest.json` + a timestamped snapshot.
- `engine.evaluate` runs the existing per-field presence rule on **Version** (shipped this session) against the **stored** artifact — no new evaluate work.
- The renderer renders the stored artifact via the card path `_card_test` already proves.
- `generated_at` is the collect timestamp (`result_to_artifact.py:52,168`); this is the collection time, no new schema needed.

`_build_environment_subject` (`subject_data_service.py:617`) and the live-each-request rebuild are **retired** — but only after parity holds (see below).

---

## Parity requirement (gate before retiring the Python builder)

`_build_environment_subject` produces a **view-model dict**, not a `CanonicalArtifact` (confirmed `subject_data_service.py:617`). Parity is therefore defined at the card content/structure level, measured through the renderer:

**Structure must match exactly:** `view_mode="table"`, `meta="CommCell profile"`, `columns=4`, and the field set in schema order.

**Current visible card (parity target, lab data) — 9 rows:**

| Label | Value | Notes |
|---|---|---|
| CommCell Name | CS01 | flat read |
| CommCell ID | **see gate below** | nested read + hex coercion (D2 + D3) |
| CommCell GUID | C721DF1F-DB93-41A0-BD28-1EDEB944E34D | read directly |
| Version | 11 SP40.47 | flat read; carries the Version presence rule |
| OS Type | Unix | flat read |
| Current SP Version | 40 | flat read |
| Installed SP Version | 40 | flat read |
| Timezone | America/Danmarkshavn | nested read `csTimeZone.TimeZoneName` (clean, no `0:0:` prefix) |
| Hostname | cs01 | flat read |

- **`sev` / `reason` are excluded from parity** — they are evaluate-stage values re-derived by `_card_section_view`, not stored extract data.
- **Release Name is intentionally omitted** (it is not part of the current card).

### ⚠ CommCell ID value gate (open item inherited from 2026-05-31)

The currently rendered CommCell ID is **`2`**, derived from a cached `commserv.json` showing `commCellId: 2`. This **does not reconcile** with Command Center, which shows **`337f`** (= 13183 decimal). This was never resolved; it was parked pending a live capture.

**Therefore parity on CommCell ID is explicitly NOT "match today's output."** Matching `2` would bake in a known bug. The migration must, **curl-first**, fetch a live `GET CommServ` from the CommCell that actually shows `337f` and confirm which field yields it (expected: `commcell.commCellId == 13183`, hex `337f`). The CommCell ID row is *required* to diverge from today's `2`. If a live capture is not possible, the ID row is flagged unverified and the builder is **not** retired until it is confirmed.

The hex coercion mechanism (D3) is correct regardless of this; only the input value needs live confirmation.

---

## Consequences

**Positive**

- `environment` lands on the uniform declarative track; `_build_environment_subject` and the live-serve special case are retired. The two-track drift closes for this subject.
- D1–D3 are general: any future single-object / nested API source can reuse the source type, nested-path resolver, and coercion set.
- The Version presence rule and the card renderer are reused unchanged; the evaluate and render stages need no new work.

**Negative / cost**

- New code: a single-object extractor, source-type dispatch in `/collect`, a nested-path resolver, one coercion value, and a Collect-button gate generalization. All bounded; none touch the canonical model or CEL.

**Behaviour change to state plainly (so it is not later mistaken for a regression)**

- Today `environment` doubles as a live "are we connected, 200 OK *right now*" readout. Stored-on-collect makes connection health true **as of the last collect**. This is intended (no live view), but it is a deliberate change from current behaviour. (Compare the missing-Collect-button investigation of 2026-05-31 — a behaviour change that looked like a regression.)

---

## Implementation phases

Each phase is independently testable and commits on its own. Follow the project workflow: read `README.md` / `ROADMAP.md` / `DEVLOG.md` / `API_MAPPING.md` / `PROMPT.txt` and confirm git state first; run `python -m compileall src` and `pytest` before committing; **establish the current pytest baseline before starting** (last known 799 on 2026-05-31 — confirm live, do not assume). Validation failures are reported, not papered over.

### Phase 1 — Capability fixture (test-subject-first)

Prove D2 + D3 in isolation before any real subject depends on them, mirroring how the `_metric_test` / `_card_test` / `_chart_test` subjects de-risked ADR 0004.

- Add a `_nested_test` subject (or extend `_card_test`) with a **nested JSON fixture** and a field requiring `hex`.
- Implement the nested-path resolver (D2) in the shared field-resolution helper.
- Implement the `hex` coercion value (D3); keep the raw integer in metadata.
- Tests assert: dot-path reads a nested value; `hex` formats correctly (`13183` → `337f`, lowercase, no `0x`); raw int retained.
- **Gate:** capability green on the fixture before Phase 2.

### Phase 2 — Source type + collect seam

- Add the `command_center_api` source type and a single-object extractor wrapping `get_commcell_identity`, emitting an `ExtractionResult` (single record = the CommServ payload) with a card spec → existing `result_to_artifact` → `save_artifact`.
- Make `/collect` dispatch the extractor **by source type** (replace the hard-wired `RESTExtractor` at `quick_hc.py:217-219`); reuse the rest of the route unchanged.
- Generalize the Collect-button gate (`subject_data_service.py:269`) to "any source with a `collect_url`" (or give `command_center_api` the collect action), so the button surfaces for a non-Reports-Plus source. JS already renders on `kind === 'collect' && action.collectUrl` (`quick_hc.js:537`).
- **Gate:** a Collect on `environment` writes a stored artifact to `working/environment/`; no live-built card required to render.

### Phase 3 — Environment definition + parity-and-retire

- Author the declarative `environment` subject (card spec, schema-order fields per the parity table, nested paths for Timezone + CommCell ID, `hex` on CommCell ID, GUID read directly).
- **Curl-first:** confirm CommCell ID against a live `GET CommServ` (the value gate above). Do not proceed on the ID until confirmed.
- Diff the rendered stored card against the parity table: structure (`view_mode`/`meta`/`columns`) + all label/value pairs except `sev`/`reason`; CommCell ID confirmed live (expected `337f`, not today's `2`).
- Confirm the Version presence rule binds and evaluates against the stored artifact.
- **Only after parity holds:** retire `_build_environment_subject` and the live-serve path. State the connection-health behaviour change in `DEVLOG.md`.

---

## Confirmed source schema — `GET /commandcenter/api/CommServ` (v11.40)

```
hostName            string
releaseId           integer
csVersionInfo       string          ("11 SP{Revision}")
releaseName         string
osType              string          (Windows | Unix)
timeZone            string          (top-level; coexists with csTimeZone)
currentSPVersion    integer
installedSPVersion  integer
csTimeZone:       { TimeZoneID integer, TimeZoneName string }
commcell:         { commCellName string, commCellId integer, csGUID string }
```

No license fields exist in this response (confirmed). License data is a separate concern (`license_summary`) and does not belong on the environment card.

---

## Reference seams (file:line, from the 2026-06-01 read-only investigation)

- Field mapping (flat): `html.py:12,310-313`, `csv.py:312`, `rest.py:303,319,376-395`
- Coercion: `html.py:347 (_coerce)`
- CEL freeze: `evaluator.py:25-27, 110-117`; card CEL hatch `card_section.py:91`
- Card path (top-level read): `card_section.py:82-90`
- Generic `/collect` (collect→store, RESTExtractor-welded): `quick_hc.py:164,176,182,195,217-219,230,237`
- Environment today: detail GET `quick_hc.py:335,338`; collector `commcell.py:12,13,23-44,30,33`
- Bespoke builder (view-model dict, not artifact): `subject_data_service.py:617`; collect-button gate `:263,269,274-277`; JS `quick_hc.js:537,543`
- Artifact timestamp at collect time: `result_to_artifact.py:52,94-128,168`
- Spec-carrying contrast (reference for the new extractor): REST `rest.py:162-166`, fixture `fixture.py:102-106`

---

## Outcome (2026-06-01)

ADR 0007 shipped across Phases 1–3 (slice B completing the environment retirement) and is render-verified. The forward-looking Decision / Parity / Phases above are preserved as the original plan; this section records where the **as-built** implementation corrected it. Where they conflict, **this Outcome governs.**

- **Source type — reused, not new.** No `command_center_api` `SourceType` enum value was added (contrary to D1's framing). The existing **`SourceType.rest_commserve`** was reused, with the already-existing id constant `REST_COMMAND_CENTER_API_SOURCE_ID = "rest_command_center_api"`. Throughout the implementation, "command-center source type" means **`rest_commserve`**. What D1 actually delivered is the single-object `CommandCenterExtractor` + the by-source-type `/collect` dispatch — minus a new enum value.

- **CommCell ID = `2` — the ⚠ value gate is FALSE and is superseded by this note.** A live `GET /commandcenter/api/CommServ` returned `commcell.commCellId == 2`; the displayed value is `hex(2) = "2"`, which matches **both** the cached `commserv.json` and the live API. The `337f` in the gate came from a **different** CommServe (`commCellId 13183`) and should be disregarded. The gate's premise — that the ID is "required to diverge from `2`" / "expected `337f`" — is **wrong**; the rendered `2` is correct, not a baked-in bug, and parity on CommCell ID *is* "match today's output." The **hex coercion mechanism (D3) was correct**; only the *expected value* written into the gate was wrong.

- **Project log is `CHANGELOG.md`.** The Implementation-phases references to `DEVLOG.md` are stale — **no `DEVLOG.md` exists** (retired 2026-05-25). Session logging went to `CHANGELOG.md` (+ `HANDOVER.md`).

- **Live builder retired (slice B).** `_build_environment_subject` and its helper cluster were **deleted**; `environment` is removed from `_legacy_builders` and rendered by the generic "canonical store wins" path from its stored artifact — the sanctioned retirement of ADR 0001's fork **for `environment` specifically** (see ADR 0001's 2026-06-01 amendment). `_legacy_builders` now serves **five** subjects: `security_assessment`, `license_summary`, `client_growth`, `capacity_license`, `backup_job_summary`. The shared collectors `get_commcell_identity` and the `_command_center_*` helpers were **kept** — they feed the extractor, not the retired view builder.

- **Behaviour, as shipped.** `environment` no longer auto-renders from the global `commserv.json`: it is **not-collected until the first Collect**, then renders its stored artifact like every other subject. Connection health is "as of the last collect" — exactly the deliberate change the Consequences section flagged.

### Parked (open follow-ups)

- **(a) CommCell ID display convention.** Bare `2` vs zero-padded `0002` is unconfirmed against the Command Center UI. The *value* `2` is correct; only the padding convention is open.
- **(b) Stale row-7 `rest` source.** `environment`'s legacy plain-`rest` `subject_sources` row is left **inert** — its tab is suppressed, and its only reader (the deleted `_load_environment_card_block`) is gone. Optional future cleanup: delete it + its binding via an idempotent FK-safe migration, gated on confirming no FK dependency.
- **(c) Report-page provenance timestamps.** Still rendered as raw UTC; deferred to the report-page redesign.
