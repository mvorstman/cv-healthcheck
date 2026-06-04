# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-04 (README pass 2 — internals relocated to owned docs; doc tree settled)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *docs: README pass 2 — relocate internals to owned docs, drop migration history, shrink README to overview+index* (this commit). Code: version operators in `5ad8b64`.
**Test status:** **1014 passing** (docs-only since; no source touched).

---

## Read this first

1. `README.md` (now overview + documentation index); 2. `HANDOVER.md` (this file); 3. **`docs/adr/0010-row-scope-evaluation-rules.md`** (Accepted) for the evaluation model.
- Architecture homes: `docs/architecture/quickhc.md`, `docs/subjects/security_assessment.md`, `docs/subjects/license_summary.md`.
- Recent CHANGELOG: the ADR-0010/0011 evaluation slices (2026-06-03/04) for the live rule engine.

---

## What was just completed — documentation restructure (docs-only, no code)

The documentation tree was settled this session across several commits:

- **ROADMAP.md** is a strategic roadmap (Vision database-first · Themes · Initiatives Now/Next/Later · Sequencing · Known Risks · Architectural Debt · Deferred Work). Enforceable principles live in **`docs/PATTERNS.md`** ("Standing conventions").
- **PROMPT.txt** is a timeless operating constitution (PROJECT PURPOSE → ARCHITECTURE PRINCIPLES → PROJECT BOUNDARY → DECISION HIERARCHY → DECISION MAKING → ENGINEERING RULES → DO NOT → VALIDATION REQUIREMENTS → DOCUMENTATION MODEL → START OF SESSION → SESSION WRAP-UP). State-free; the new DECISION HIERARCHY + DECISION MAKING sections carry the authority order and the pre-change checklist.
- **README pass 1** stripped session state, collapsed lab setup into `docs/lab_environment.md`, refreshed the doc index.
- **README pass 2** (this commit) relocated the large internals into three owned docs, deleted the Phase 2 / Lab Readiness migration narrative (history retained in CHANGELOG `2026-05-11`), preserved the operational CLI in README, moved the login-token workflow into `docs/lab_environment.md`, and reduced README to overview + index. Three new docs created: `docs/architecture/quickhc.md`, `docs/subjects/security_assessment.md`, `docs/subjects/license_summary.md`.

---

## In-flight engineering — next actions

### Single recommended next action — retire the last interim phrasing (scope label)
The **only** remaining interim derivation is the criteria card's **Scope sentence** + the table's **scope caption** (`canonical_view._scope_phrases`, still id/operator-derived). Retire it the way rule descriptions were:
- Add a **scope-authoring MCP tool** — `save_section_scope(subject_id, section_id, {conditions, label})`, or a `scope`/`scope_label` arg on `save_rule`'s `bind`. `load_subject_section_scope` already reads `evaluative.scope`; add a sibling `label`.
- Bake the authored `label` into `metadata["evaluation"][section_id]` and render it verbatim, dropping `_scope_phrases`.
- Then author `server_groups`' scope label (e.g. "Manual server groups. Automatic groups are excluded.").

### Pending (Michiel) — author the `commserve_software_cache.cache_configuration` transpose binding
The transpose materialization + property legend are in place, but the live subject's card is **not yet re-authored** as a transpose section (it still renders the empty card). Re-stage as `output_as:table` with `table.root_key:"commserveSoftwareCache"`, `table.transpose:[…12 settings…]`, `table.columns:[{id:"label",label:"Setting"},{id:"value",label:"Value"}]` (`result_to_artifact` then sets `view_mode:"property"`), and author `row_match` rules keyed on **`key`** (stable, never `label`) via MCP `save_rule`. A live re-collect needs a fresh Connect (the loopback token keeps expiring).

### Pending — card binding-shape re-stage (`metrics_reporting.status`, and the cache card)
Card sections read `card.items` with `label`/`field` (fully-qualified paths), not table vocabulary (`columns`/`root_key`). Re-stage `metrics_reporting`'s `status` card as `card.items` with `"type":"epoch_to_iso"` on the timestamp fields (`config.lastCollectionTime`/`lastUploadTime`/`nextUploadTime`; coercion already supported, `842d39c`). Worth an ADR note: **binding spec vocabulary diverges by section type** (table=`root_key`+`columns`, card=`items`) — the recurring mis-authoring trap.

### Now-initiative detail (kept out of the strategic ROADMAP)
- **Rules & Evaluation maturity:** summary-scope evaluation (the `db/rules.py:264` TODO — `scope=summary` must reject `emit != once`, ADR-0010 §8); display coercions (byte / bool, the ADR-0007 `type`-coercion family alongside `hex`/`epoch_to_iso`).
- **Quick HC canonical pipeline completion:** renderer-orchestration layer; retire the legacy subject-shaping fallback (`quickhc/subject_data_service.py`) once canonical parity is validated; the **Security Assessment REST/source-precedence fix** — tracked in `HEALTHCHECK_MATRIX.md`; the subject architecture is in `docs/subjects/security_assessment.md`.

### Open doc-state notes
- **API_MAPPING.md** — the 3 validated ADR-0009 CC endpoints are in the table (PROVEN). **`/v4/servergroup` is still NOT added** — deferred acceptance-test capture, no live-200 evidence; add it after a live `/v4/servergroup` capture (current token 401s — needs a fresh Connect).
- **DATA_SOURCE_MAPPING.md** — kept as-is; pending a keep-vs-fold-into-ROADMAP decision (it is an operating-mode source-strategy doc, not validated-API behavior, so it does **not** fold into API_MAPPING).

---

## Settled — do not relitigate
- Scope is section-level; `row_ref = id, never name`. Verdict baked at canonicalization, no separate store (ADR-0010 D5).
- `not_evaluated` = explicit gray, distinct from info-blue. The criteria card has **no pill** (it describes the assessment, not a verdict); the Findings card carries the **worst-severity** pill. Both Evaluation cards toggle independently; excluding them must not remove the table's scope caption.
- After touching `mcp/server.py` or restarting, **reconnect the MCP client** (`pkill -f cv-healthcheck-mcp`), or it serves stale modules.
