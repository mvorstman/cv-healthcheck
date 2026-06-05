# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (Domain Labels v1 complete — schema · read · author · backfill)
**Branch:** `feature/domain-labels` (off `feature/basic-healthcheck-report-output`)
**Last commit:** *feat(catalog): backfill domain labels for active subjects (Phase 4)*.
**Test status:** **1041 passing** (was 1035; +6 new Phase 4 tests).

---

## What was just completed — Domain Labels v1 (ADR-0012)

A second, additive classification axis for subjects. `subjects.category` is the single / primary axis; domain labels are additive and many-valued; the two vocabularies are disjoint. Now functionally complete end-to-end:

- **Phase 1 (`0029`)** — `domain_label` vocabulary (compliance/governance/backup/reporting) + `subject_domain_labels` association; `db/domain_labels.py` accessors.
- **Phase 2** — `list_subjects` returns `labels` per subject; graceful-empty `label` filter.
- **Phase 3** — `labels` on `propose_new_subject`, loud-validated at authoring; persisted at approval (two-guard: loud authoring validation + structural FK).
- **Phase 4 (`0030`)** — sparse backfill of the approved set onto active version rows (8 assignments across 6 subjects); idempotent; `category` untouched.

The post-commit live read smoke confirmed the real-catalog result (incl. the 4 runtime-only rows that the test-DB suite cannot exercise — see CHANGELOG Phase 4 Notes).

---

## Decisions for Michiel (no further build queued)

1. **Merge `feature/domain-labels`** into the base branch — that's your release call (not done here). The branch holds: `36d9d41` (P1) · `fe9e111` (P2) · `f7a9bf5` (ADR-0012) · `17ce251` (P3) · the Phase-4 commit.
2. **What's next** — either the **first downstream consumer** of labels (report profiles / health domains / rule packs that read the labels), or return to the parked **Rules & Evaluation** work: summary-scope evaluation (`db/rules.py:264` TODO — `scope=summary` must reject `emit != once`, ADR-0010 §8) and display coercions (byte/bool, the ADR-0007 `type`-coercion family).

## Standing backlog
- **Export `_LABELS`** (the `category` vocabulary) from its function-local spot in `db/subjects.py::create_subject_from_proposal` to a shared importable source, so the disjointness invariant references one source of truth (the test currently mirrors the six terms).
- **`propose_new_subject` does not validate `category`** — it accepts any value and `create_subject_from_proposal` silently title-cases unknowns (`_LABELS`, display only). Left unchanged per ADR-0012 / scope; revisit only if `category` should become a closed vocabulary.
- **Catalog reconstructibility** — `0030` backfills 4 rows onto AI-authored runtime subjects (`audit_trail`/`users`/`metrics_reporting`) that aren't seed-represented, so a from-scratch migration can't fully reconstruct the labeled catalog. Resolves naturally under **Subject Inventory convergence** (seed-represent the system/AI subjects).

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number is **0031**.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- The MCP server is **stdio** transport, spawned by the client. After changing `mcp/server.py`, restart the client so it respawns one fresh instance. **Don't `pkill -f cv-healthcheck-mcp` from a shell whose own command line contains that string — it self-matches and kills the shell; kill by PID instead.**
