# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-03 (ADR-0010 — section scope + per-row verdict **engine slice** done; **layout slice next**)
**Branch:** `feature/basic-healthcheck-report-output`
**Last commit:** *ADR 0010 — section-level evaluation scope + per-row verdict (engine slice)* (this commit).
**Test status:** **948 passing** under `pytest` and `python -m pytest`.

---

## Read this first

1. `README.md` — what the project is, how to run it.
2. `HANDOVER.md` (this file) — what to do next.
3. **`docs/adr/0010-row-scope-evaluation-rules.md`** — the governing ADR (*Accepted*).
4. The most recent CHANGELOG entries (2026-06-03: the scope/verdict engine slice; the `save_rule` `kind` fix; Phase 2b/2a/1).

---

## What was just completed — scope + per-row verdict (ENGINE slice)

An explicit evaluated **population** per section and a real **per-row verdict**:

- **`evaluative.scope`** on a section's binding — AND-ed conditions (same operators as `row_match`). In-scope iff all conditions hold; absent ⇒ all rows in scope. Loaded by `db.rules.load_subject_section_scope`, carried on `ExtractionResult.section_scope`.
- **`evaluate_section_rows`** — rules run only on in-scope rows; every row gets a verdict (out-of-scope `not_evaluated` / in-scope clean `good` / flagged worst severity). Shared `matches_conditions` backs rule + scope predicates.
- **Verdict baked** onto `TableSection` items as `_verdict` at canonicalization (D5, no separate store); `evaluate_subject` returns the same `row_verdicts` so the dry-run matches the bake.
- **Verified live:** `server_groups` scope `association == "MANUAL"` → findings 14→11; verdicts 5 good / 9 warning / 7 not_evaluated; rommelgroep 19 & 41 distinct, each warning.

---

## Single recommended next action — the LAYOUT slice

Render the per-row verdict in the Quick HC report / UI. The data is on the artifact: each `TableSection` row carries `_verdict` ∈ {`good`,`warning`,`critical`,`not_evaluated`}, and `<subject>.compliance` carries the findings.

- The table renderer is `secBody` (`type === 'table'`) in `quick_hc.js`; the verdict has to ride to the view first — `canonical_view.artifact_to_view`'s table branch currently projects only declared `columns` (so `_verdict` is dropped). Decide how the row verdict reaches the view (e.g. a parallel `row_verdicts` list on the section, or a verdict dot per row).
- **`not_evaluated` must render distinctly** from good and from info — set explicitly, no `?? 'info'` fallback (mirror the CommCell field treatment: `effState = it.sev ?? it.state ?? 'info'`, quick_hc.js:266 — but row verdict must not collapse into that default).

## Other follow-ups

- **MCP tool to author section scope** — `save_section_scope(subject_id, section_id, conditions)`, or a `scope` arg on `save_rule`'s `bind`. This slice set `server_groups` scope **directly** in the catalog (gitignored runtime state); there's no tool yet. Validate scope conditions the same way `validate_row_match_rule` validates rule conditions (operators / between-value2 / columns-exist).
- Re-author the live rules + scope via the (future) tools so they're explicit/versioned.

---

## ⚠️ Uncommitted in the working tree (carry forward)

`src/cvhealthcheck/mcp/server.py` still has the **uncommitted probe read-timeout hardening** (`timeout=30 → (5, 30)`) from the probe-hang session — deliberately kept out of the last two commits. Not touched this session. Decide whether to commit it (its own small commit).

---

## Settled — do not relitigate
- Scope is **section-level**; every rule bound to the section inherits it.
- `row_ref = id, never name` (server_groups has two `rommelgroep`, ids 19/41).
- Verdict baked at canonicalization; no separate findings/verdict store (D5).
- `row_match` is its own evaluator grain (D3); one `<subject>.compliance` FindingsSection per subject.
- After touching `mcp/server.py` or restarting the MCP server, **reconnect the client** (`pkill -f cv-healthcheck-mcp`).
