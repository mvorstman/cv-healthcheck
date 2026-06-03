# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (ADR-0010 — **authored rule descriptions + Option-B criteria render** (slice 3) done; scope-authoring follow-up remains)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *ADR 0010 — authored rule descriptions + Option-B criteria render (slice 3)* (this commit).
**Test status:** **975 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md`; 2. `HANDOVER.md` (this file); 3. **`docs/adr/0010-row-scope-evaluation-rules.md`** (Accepted).
4. The most recent CHANGELOG entries (2026-06-03: Evaluation band slice 2; per-row verdict rendering slice 1; the scope/verdict engine slice; the `save_rule` `kind` fix).

---

## What was just completed — authored rule descriptions + Option-B criteria render (slice 3)

The criteria card's per-check **Checks** lines are no longer derived from rule ids. Each check now renders the rule's **authored `description`** (falling back to its static title, **never the raw id**) over a **mechanically-rendered condition** in mono — Option B.

- **The data:** `save_rule` accepts an optional `description` (nullable; persisted/returned/listed). `result_to_artifact` bakes each check as `{rule_id, severity, description, title, condition_text}`; `evaluative/row_match.format_conditions()` renders the condition (every operator) at bake time.
- **The render:** `canonical_view._evaluation_criteria_view` maps each baked check to `{sev, primary, condition}` (primary = `description` or `_title_static(title)` or "Check"); `quick_hc.js`/`.css` show badge + primary + mono condition. The interim `_RULE_SENTENCE`/`_rule_sentence` deriver is **removed**.
- **Verified via the real path** (re-baked `server_groups` artifact, runtime state): three checks — naming `name not contains "GRP_"`, rommelgroep `name = "rommelgroep" and company = "Company_1"` (critical), empty `server_count = 0` — each with its authored description, no raw id. Scope sentence + table caption unchanged.

**Visual confirmation is the operator's:** `./start.sh`, open `server_groups` → Evaluation band → "Evaluation criteria" → Checks: three rows, each a severity badge + a plain-English description + the condition in mono underneath. No raw rule id anywhere.

---

## Single recommended next action — scope-authoring MCP tool + authored scope label (retire the LAST interim phrasing)

The **only** remaining interim derivation is the criteria card's **Scope sentence** + the table's **scope caption** (`canonical_view._scope_phrases`, still id/operator-derived). Retire it the same way the descriptions were:

- Add a **scope-authoring MCP tool** — `save_section_scope(subject_id, section_id, {conditions, label})`, or a `scope`/`scope_label` arg on `save_rule`'s `bind`. `load_subject_section_scope` already reads `evaluative.scope`; add a sibling `label`.
- Bake the authored `label` into `metadata["evaluation"][section_id]` (next to `scope`) and render it verbatim as the scope sentence/caption, dropping `_scope_phrases`.
- Then author `server_groups`' scope label (e.g. "Manual server groups. Automatic groups are excluded.") through the tool.

## Other follow-ups
- **Criteria check ORDER** follows the binding order (currently naming → rommelgroep → empty), which is not the logical reading order. An authored order/priority on the rule (or the binding) would make it deterministic.
- The generated **report** (`quick_hc_report`) is a separate renderer from the workspace `secBody`; mirror the Evaluation band there if wanted (its own slice).
- A real Collect of `server_groups` re-bakes `_verdict` + the `evaluation` metadata identically (the re-bake here was a runtime convenience).
- **`sg_naming_convention`** had its redundant `association == MANUAL` condition dropped this slice (the section scope gates that population) — keep new rules scope-aware to avoid re-introducing redundant conditions in the criteria render.

---

## ⚠️ Uncommitted in the working tree (carry forward)
`src/cvhealthcheck/mcp/server.py` still has the **uncommitted probe read-timeout hardening** (`timeout=30 → (5, 30)`) from the probe-hang session — untouched again this session. Decide whether to commit it (its own small commit).

---

## Settled — do not relitigate
- Scope is section-level; `row_ref = id, never name`. Verdict baked at canonicalization, no separate store (D5).
- `not_evaluated` = explicit gray, distinct from info-blue. Criteria card has **no pill** (it describes the assessment, not a verdict); the Findings card carries the **worst-severity** pill (now critical on `server_groups`, since `sg_rommelgroep_company_1` fires). Both Evaluation cards toggle independently; excluding them must not remove the table's scope caption.
- After touching `mcp/server.py` or restarting, **reconnect the MCP client** (`pkill -f cv-healthcheck-mcp`).
