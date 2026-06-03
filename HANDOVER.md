# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (ADR-0010 — **Evaluation band** layout slice 2 done; authoring follow-ups remain)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *ADR 0010 — Evaluation band: criteria + findings cards (layout slice 2)* (this commit).
**Test status:** **963 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md`; 2. `HANDOVER.md` (this file); 3. **`docs/adr/0010-row-scope-evaluation-rules.md`** (Accepted).
4. The most recent CHANGELOG entries (2026-06-03: Evaluation band slice 2; per-row verdict rendering slice 1; the scope/verdict engine slice; the `save_rule` `kind` fix).

---

## What was just completed — the Evaluation band (layout slice 2)

Compliance moved out of "Report Sections" into a new **"Evaluation" band** (after Report Sections) with two independently-includable cards: **"Evaluation criteria"** (read-only, no pill) and **"Findings"** (the moved compliance list, Warning pill). Plus an always-present **scope caption** on the data-table legend.

- **The pipe:** `result_to_artifact` bakes `metadata["evaluation"][section_id] = {scope, checks:[{rule_id, severity}]}`; `artifact_to_view` reads it to reband/retitle the compliance findings, build the criteria card, set a `band` on every section, and add a `scope_caption` to the table. `quick_hc.js` partitions Report vs Evaluation bands + renders the `criteria` type + caption.
- **Derived phrasing is INTERIM** — one marked place in `canonical_view.py` (`_scope_phrases`, `_RULE_SENTENCE`). Not an inference engine.
- **Verified headless:** server_groups → table (report) caption "manual server groups · automatic excluded"; Evaluation band → criteria (scope sentence + 2 warning checks, no pill) + Findings (11, Warning pill). The stored artifact was re-baked (runtime state).

**Visual confirmation is the operator's:** `./start.sh`, open server_groups → Report Sections has the data table + STATUS dots + a legend whose right reads the Scope caption; below, an Evaluation band with the two cards, each with its own checkmark; toggling either card out leaves the caption intact. Other subjects unchanged.

---

## Single recommended next action — authored rule `description` + scope label (retire the interim phrasing)

The criteria card's sentences are currently **derived** from the scope conditions / rule ids (interim, in `canonical_view._scope_phrases` / `_RULE_SENTENCE`). Replace with **authored** text rendered verbatim:

- Add an optional `description` field to a `row_match` rule (set at authoring time) and a `label` to a section scope; render them in the criteria card instead of deriving.
- This **pairs with the scope-authoring MCP tool** (`save_section_scope`, or a `scope` arg on `save_rule`'s bind) — still the open authoring follow-up. `save_rule` already persists the rule body; add `description`; `load_subject_section_scope` already reads scope; add the label.
- Then re-author `server_groups`' rules (`sg_empty_group`, `sg_naming_convention`) + scope with real descriptions/labels through the tool, and drop the interim mapping.

## Other follow-ups
- Check ordering in the criteria card follows the bound-rule order (currently naming then empty); an authored order/priority would fix it deterministically.
- The generated **report** (`quick_hc_report`) is a separate renderer from the workspace `secBody`; mirror the Evaluation band there if wanted (its own slice).
- A real Collect of `server_groups` re-bakes `_verdict` + the `evaluation` metadata identically (the re-bake here was a runtime convenience).

---

## ⚠️ Uncommitted in the working tree (carry forward)
`src/cvhealthcheck/mcp/server.py` still has the **uncommitted probe read-timeout hardening** (`timeout=30 → (5, 30)`) from the probe-hang session — untouched again this session. Decide whether to commit it (its own small commit).

---

## Settled — do not relitigate
- Scope is section-level; `row_ref = id, never name`. Verdict baked at canonicalization, no separate store (D5).
- `not_evaluated` = explicit gray, distinct from info-blue. Criteria card has no pill; Findings card keeps its Warning pill. Both Evaluation cards toggle independently; excluding them must not remove the table's scope caption.
- After touching `mcp/server.py` or restarting, **reconnect the MCP client** (`pkill -f cv-healthcheck-mcp`).
