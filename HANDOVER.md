# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (post category-vocabulary merge)
**Branch:** `main` — single branch locally and on origin, no feature branches outstanding.
**Test status:** **1041 passing**.

---

## Current state

- **Domain Labels v1 complete and merged to `main`** — the additive label axis alongside the single-valued `category`: schema (`0029`) · MCP read (`labels` in `list_subjects` + `label` filter) · MCP author (`labels` on `propose_new_subject`, loud reject-unknown) · sparse backfill (`0030`) · ADR-0012.
- **Category vocabulary centralized** — `CATEGORY_LABELS` / `CATEGORY_VOCABULARY` live in `db/categories.py` (single source of truth); `create_subject_from_proposal` and the Domain Labels disjointness invariant both read from it, no mirrored copy.
- `main` is in sync with `origin/main` (the category-vocabulary refactor landed via its merge commit on top of Domain Labels v1's two release merges).

---

## Next-work decision (unactioned — for Michiel)

No further build is queued. Pick the direction:

1. **First downstream Domain Labels consumer** — report profiles / health domains / rule packs that *read* the labels (the v1 axis is in place but nothing consumes it yet). — or —
2. **Return to Rules & Evaluation** — summary-scope evaluation (`db/rules.py:264` TODO: `scope=summary` must reject `emit != once`, ADR-0010 §8) and display coercions (byte/bool, the ADR-0007 `type`-coercion family).

## Standing backlog
- **`propose_new_subject` does not validate `category` at authoring** — it accepts any value; `create_subject_from_proposal` title-cases unknowns via `CATEGORY_LABELS` (display only). Revisit only if `category` should become a closed vocabulary (the vocabulary is now importable, so this would be a small follow-up).
- **Catalog reconstructibility / Subject Inventory convergence** — `0030` backfills 4 rows onto AI-authored runtime subjects (`audit_trail`/`users`/`metrics_reporting`) that aren't seed-represented, so a from-scratch migration can't fully reconstruct the labeled catalog. Resolves naturally once those subjects are seed-represented under Subject Inventory convergence.
- **Quick HC registry `category_label` literals** — `quickhc/registry.py` carries per-tile `category_label="…"` strings (e.g. "Identity", "Licensing") not yet sourced from `CATEGORY_LABELS`. Candidate for the same consolidation onto the shared source.

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number is **0031**.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- The category vocabulary lives in `db/categories.py` (`CATEGORY_LABELS` / `CATEGORY_VOCABULARY`) — the single source of truth; don't re-mirror it.
- The MCP server is **stdio** transport, spawned by the client. After changing `mcp/server.py`, restart the client so it respawns one fresh instance. **Don't `pkill -f cv-healthcheck-mcp` from a shell whose own command line contains that string — it self-matches and kills the shell; kill by PID instead.**
