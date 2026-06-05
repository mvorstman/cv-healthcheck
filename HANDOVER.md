# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (Domain Labels Phase 3 — MCP authoring path landed)
**Branch:** `feature/domain-labels` (off `feature/basic-healthcheck-report-output`)
**Last commit:** *feat(mcp): accept + validate domain labels on propose_new_subject (Phase 3)*.
**Test status:** **1035 passing** (was 1029; +6 new Phase 3 tests).

---

## What was just completed — Domain Labels Phases 1–3

A second, additive classification axis for subjects (ADR-0012, `docs/adr/0012-two-axis-subject-classification.md`): `subjects.category` is the single / primary axis; domain labels are additive and many-valued; vocabularies are disjoint.

- **Phase 1 (schema)** — migration `0029_domain_labels.sql`: `domain_label` vocabulary (compliance/governance/backup/reporting) + `subject_domain_labels` association (FK to `subjects.id`, `ON DELETE CASCADE`; FK to `domain_label.label`; `UNIQUE`). `db/domain_labels.py` read accessors.
- **Phase 2 (MCP read)** — `list_subjects` returns `labels` per subject (`[]` when none, via bulk `subject_labels_map`); optional graceful-empty `label` filter.
- **Phase 3 (MCP authoring)** — optional `labels` on `propose_new_subject`, **loud-validated at authoring** (unknown → `ValueError`, nothing staged); persisted into `subject_domain_labels` at approval keyed on the new `subjects.id` (two-guard model: loud authoring validation + structural FK).

Settled (do not relitigate): `category` unchanged; labels additive; vocabularies disjoint; read filter graceful-empty; authoring validation loud; labels attach to the per-version `subjects.id` (no version bleed; re-propose replaces via cascade).

---

## Single recommended next action — Phase 4 (sparse backfill)

Apply the **approved sparse label set** to existing subjects via a new migration (next number **0030**), `category` untouched, data-only (no schema change):

| subject_id | labels |
|---|---|
| `security_assessment` | compliance, governance |
| `audit_trail` | compliance, governance |
| `users` | governance |
| `metrics_reporting` | governance |
| `backup_job_summary` | backup |
| `client_growth` | reporting |

Per ADR-0012 / the plan. Implementation notes:
- Backfill targets each subject's **active** version row (`subjects.id`) — resolve the id by `subject_id` + `status='active'` (or the relevant version) at migration time; do not hardcode ids.
- Use `INSERT OR IGNORE INTO subject_domain_labels` so re-runs are idempotent; the FK guarantees only vocabulary labels land.
- Verify each target subject exists in the seeded/real catalog before relying on it (some — e.g. `users`, `metrics_reporting`, `audit_trail` — are AI-authored runtime subjects; confirm presence and decide whether the backfill is a seed migration vs. runtime data). **If a target subject_id is absent from the migration-seeded catalog, stop and confirm scope** — a migration can only backfill rows it can resolve.
- Tests: each listed subject surfaces its labels via `list_subjects` / `list_subjects(label=…)`; `category`/`category_label` unchanged; idempotent re-run.

## Backlog
- **`category` not validated at authoring** — `propose_new_subject` accepts any category; `create_subject_from_proposal` silently title-cases unknowns (`_LABELS`, display only). Left unchanged per ADR-0012 / scope; revisit separately if category should become a closed vocabulary.
- **Export `_LABELS`** to a shared importable source so the disjointness invariant references one source of truth (the test currently mirrors the six terms).

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number is **0030**.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- The MCP server is **stdio** transport, spawned by the client. After changing `mcp/server.py`, restart the MCP client so it respawns one fresh instance (a bash relaunch of a stdio server does not persist). `pkill -f cv-healthcheck-mcp` clears stale duplicates.
