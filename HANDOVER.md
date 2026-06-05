# Handover — Next Session

*Always overwritten at the end of every session. Forward-looking only — see `CHANGELOG.md` for what already happened.*

**Last updated:** 2026-06-05 (category vocabulary exported to shared `db.categories`)
**Branch:** `refactor/category-vocabulary` (off `main` at `e6feabb`) — pushed, **not merged** (separate decision).
**Test status:** **1041 passing**.

---

## What was just completed — category vocabulary → shared source (refactor only)

The function-local `_LABELS` dict in `db/subjects.py::create_subject_from_proposal` is lifted to `db/categories.py` as `CATEGORY_LABELS` (slug → display) + a derived `CATEGORY_VOCABULARY` (frozenset of slugs). `create_subject_from_proposal` imports it; the Domain Labels disjointness test now imports `CATEGORY_VOCABULARY` from the shared source instead of mirroring the six terms. Behavior-preserving (`CATEGORY_LABELS` == former `_LABELS`; unknown categories still accepted/title-cased). This **closes the "export `_LABELS`" backlog item.**

`main` itself is unchanged — it still holds Domain Labels v1 at `e6feabb` (the two release merges `b200657` then `8e5effe`). This branch awaits its own merge decision.

---

## Next-work decision (unactioned — for Michiel)

No further build is queued. Pick the direction:

1. **First downstream consumer of labels** — report profiles / health domains / rule packs that *read* the labels (the v1 axis is in place but nothing consumes it yet). — or —
2. **Return to parked Rules & Evaluation** — summary-scope evaluation (`db/rules.py:264` TODO: `scope=summary` must reject `emit != once`, ADR-0010 §8) and display coercions (byte/bool, the ADR-0007 `type`-coercion family).

## Standing backlog
- **`propose_new_subject` does not validate `category`** — it accepts any value; `create_subject_from_proposal` silently title-cases unknowns via `CATEGORY_LABELS` (display only). Left unchanged per ADR-0012 / scope; revisit only if `category` should become a closed vocabulary (the vocabulary is now importable, so this would be a small follow-up).
- **Catalog reconstructibility** — `0030` backfills 4 rows onto AI-authored runtime subjects (`audit_trail`/`users`/`metrics_reporting`) that aren't seed-represented, so a from-scratch migration can't fully reconstruct the labeled catalog. Resolves naturally under **Subject Inventory convergence** (seed-represent the system/AI subjects).
- **Registry-tile `category_label` literals** — `quickhc/registry.py` carries per-tile `category_label="…"` strings (e.g. "Identity", "Licensing") not yet sourced from `CATEGORY_LABELS`. Candidate for the same consolidation onto the shared source.

---

## Settled — do not relitigate
- Migrations are forward-only numbered SQL (`schema_migrations`); no down-migrations. Next number is **0031**.
- Connections come from `db/database.get_db` (`row_factory = Row`, `PRAGMA foreign_keys = ON`).
- The category vocabulary lives in `db/categories.py` (`CATEGORY_LABELS` / `CATEGORY_VOCABULARY`) — the single source of truth; don't re-mirror it.
- The MCP server is **stdio** transport, spawned by the client. After changing `mcp/server.py`, restart the client so it respawns one fresh instance. **Don't `pkill -f cv-healthcheck-mcp` from a shell whose own command line contains that string — it self-matches and kills the shell; kill by PID instead.**
