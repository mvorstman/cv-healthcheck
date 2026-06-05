# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (ADR-0013 reporting direction accepted; Customer/Project Context Isolation promoted to gating Now initiative)
**Branch:** `main` — docs-only architecture direction changes are currently uncommitted/untracked.
**Test status:** Docs-only checkpoint; no `src` changed. Latest venv run was **1039 passing + 2 `test_mcp_smoke` initialize timeouts = the 1041 baseline** — the 2 are known environmental smoke timeouts (`tests/test_mcp_smoke.py` initialize), **not a regression**. (System `python -m pytest` lacks pytest; run via the venv.)

---

## Current state

- **Domain Labels v1 complete and merged to `main`** — the additive label axis alongside the single-valued `category`: schema (`0029`) · MCP read (`labels` in `list_subjects` + `label` filter) · MCP author (`labels` on `propose_new_subject`, loud reject-unknown) · sparse backfill (`0030`) · ADR-0012.
- **Category vocabulary centralized** — `CATEGORY_LABELS` / `CATEGORY_VOCABULARY` live in `db/categories.py` (single source of truth); `create_subject_from_proposal` and the Domain Labels disjointness invariant both read from it, no mirrored copy.
- **ADR-0013 accepted as the report-composition principle ADR** — subjects + evidence + evaluations are the foundation; reports are read-only views over canonical subjects; first Report Profile is only selected subjects, selected sections, and view mode; report/customer presentation overrides must not mutate canonical artifacts or hide contextual evaluation in composition.
- **ROADMAP updated to reflect ADR-0013** — Report Output Framework now explicitly starts with thin profiles over canonical subjects, no artifact mutation, and defers contextual evaluation, Health Domains, compliance/NIS2 profiles, and full profile persistence/schema.
- **Customer/Project Context Isolation is now a gating Now initiative** (from a read-only isolation audit) — report generation must never mix data across customers/projects; the top risks are cross-customer read fallback and global `commserv.json` identity bleed. ROADMAP's Report Output framework now `Depends on` it, and Sequencing places it before Reporting. Formalization into an ADR is deferred (no ADR-0014 yet).
- Working tree (docs-only checkpoint, not yet committed): `docs/adr/0013-subjects-as-foundation.md` (new), `docs/research/health_domains_notes.md` (new), `ROADMAP.md`, `README.md`, `docs/lab_environment.md`, `HANDOVER.md` (this file), and the deletion of `HEALTHCHECK_MATRIX.md`.

---

## Next-work decision (unactioned — for Michiel)

Recommended next build:

1. **Customer/Project Context Isolation (gating)** — close the HIGH cross-customer risks: scoped artifact reads with no global fallback, scoped environment/CommCell evidence (not a global `commserv.json`), scoped writes/uploads and composition selections, and an explicit active context (or "Default" as an unmistakable single-tenant lab mode). Per ROADMAP this **gates** the Report Output work below.
2. **Thin Quick HC Report Profile implementation (ADR-0013)** — *blocked on (1)*: a minimal view contract consumed by `QuickHcReportService` (selected subjects, selected sections, view mode). Preserve current HTML report behavior, keep Flask routes thin, do not persist profiles yet, do not mutate canonical artifacts, and do not move evaluation logic into `reportsplus`, collectors, or report composition. Does not proceed until (1) closes.
3. **Alternative if reporting pauses:** return to Rules & Evaluation maturity — summary-scope evaluation (`db/rules.py:264` TODO: `scope=summary` must reject `emit != once`, ADR-0010 §8) and display coercions (byte/bool, the ADR-0007 `type`-coercion family).

## Standing backlog
- **`propose_new_subject` does not validate `category` at authoring** — it accepts any value; `create_subject_from_proposal` title-cases unknowns via `CATEGORY_LABELS` (display only). Revisit only if `category` should become a closed vocabulary (the vocabulary is now importable, so this would be a small follow-up).
- **Catalog reconstructibility / Subject Inventory convergence** — `0030` backfills 4 rows onto AI-authored runtime subjects (`audit_trail`/`users`/`metrics_reporting`) that aren't seed-represented, so a from-scratch migration can't fully reconstruct the labeled catalog. Resolves naturally once those subjects are seed-represented under Subject Inventory convergence.
- **Quick HC registry `category_label` literals** — `quickhc/registry.py` carries per-tile `category_label="…"` strings (e.g. "Identity", "Licensing") not yet sourced from `CATEGORY_LABELS`. Candidate for the same consolidation onto the shared source.
- **Domain Labels first consumer still deferred** — ADR-0013 and ROADMAP explicitly defer Health Domain / compliance-profile consumers. A thin Report Profile may read subjects/sections but must not turn Domain Labels into a full domain engine yet.

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number is **0031**.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- The category vocabulary lives in `db/categories.py` (`CATEGORY_LABELS` / `CATEGORY_VOCABULARY`) — the single source of truth; don't re-mirror it.
- ADR-0013 governs report composition: reports are read-only views over canonical subjects; Report Profiles do not own evaluation logic; customer/report presentation overrides do not rewrite artifacts, verdicts, provenance, source metadata, or canonical data.
- The MCP server is **stdio** transport, spawned by the client. After changing `mcp/server.py`, restart the client so it respawns one fresh instance. **Don't `pkill -f cv-healthcheck-mcp` from a shell whose own command line contains that string — it self-matches and kills the shell; kill by PID instead.**
