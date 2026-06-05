# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (Domain Labels Phase 2 — MCP read path landed; ADR-0012 recorded)
**Branch:** `feature/domain-labels` (off `feature/basic-healthcheck-report-output`)
**Last commit:** *feat(mcp): expose domain labels in list_subjects + label filter (Phase 2)*, then *docs(adr): record two-axis subject classification (ADR-0012)*.
**Test status:** **1029 passing** (was 1023; +6 new Phase 2 tests).

---

## What was just completed — Domain Labels Phases 1–2

A second, additive classification axis for subjects: `subjects.category` is the single / primary axis; domain labels are the additive, many-valued axis. Vocabularies are disjoint by construction. Recorded in **`docs/adr/0012-two-axis-subject-classification.md`**.

- **Phase 1 (schema)** — migration `0029_domain_labels.sql`: `domain_label` vocabulary (seeded compliance/governance/backup/reporting) + `subject_domain_labels` association (`subject_row_id` → `subjects.id` `ON DELETE CASCADE`, FK on `label`, `UNIQUE(subject_row_id, label)`). `db/domain_labels.py` read accessors. No subject labeled.
- **Phase 2 (MCP read)** — `list_subjects` returns `labels` per subject (always present; `[]` when none), via the bulk `subject_labels_map(db)` (one query, no N+1); optional `label` filter that is graceful-empty (unknown/zero-member → `[]`, never raises). Additive only; `category`/`category_label` unchanged; `list_subjects` does not collapse versions, so labels attach to the per-version `subjects.id`.

Settled (do not relitigate): `category` unchanged; labels additive; vocabularies disjoint; read filter never raises (reject-unknown is authoring-side, Phase 3).

---

## Single recommended next action — Phase 3 (MCP authoring)

Wire domain labels into the authoring path:
1. Add an optional `labels` argument to `propose_new_subject` (and the proposal/create flow) that associates the given labels with the new subject row.
2. **Reject unknown labels at authoring time** — validate each supplied label against the vocabulary via the existing accessor (`db/domain_labels.domain_label_vocabulary`), raising a clear error on an unknown term. This is the authoring-side guard that complements the structural FK; the read path stays graceful-empty.

Touches the authoring path + validation + tests only. After the change, restart the MCP server (`pkill -f cv-healthcheck-mcp`) and reconnect the client, or it serves stale modules. **Note:** two MCP server instances were observed running (PIDs from this session) — worth consolidating to one on restart.

## Later phases / backlog
- **Phase 4:** backfill subject → label assignments (data, not schema).
- **Backlog:** export the `category` `_LABELS` constant (function-local in `db/subjects.py::create_subject_from_proposal`, against a free-text column) to a shared importable source, so the disjointness invariant references one source of truth rather than a mirrored copy in the test.

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number after 0029 is 0030.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- After touching `mcp/server.py` or restarting, reconnect the MCP client (`pkill -f cv-healthcheck-mcp`), or it serves stale modules.
