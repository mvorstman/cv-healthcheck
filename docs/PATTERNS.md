# Project patterns

Two patterns that recur across the codebase. Worth knowing before
adding new code or refactoring existing code.

---

## 1. Writes converge to canonical; reads stay diverse

When a refactor produces a tension between "unify the write path" and
"unify the read path," this codebase consistently chooses to unify
writes and let reads remain divergent. Four instances make this a
project signature, not a coincidence:

- **Option A (pre-ADR refactors, 2026-05-27).** The legacy SA/LS
  per-domain stores were retained as readable fallback paths after
  production writes moved canonical-only. New code writes to the
  canonical store; old code (and legacy fixtures) still reads the
  per-domain `latest.json` paths.
- **ADR 0001 (source-building fork).** The unified upload route
  (`POST /quick-hc/<subject_id>/import`) is the sole write path for
  artifacts. But source-building reads stay forked: `_legacy_builders`
  serves the six system subjects' custom view shapes (counters,
  findings_grid, workload, chart_growth); `_build_generic_subject`
  serves everything else. The canonical schema can't represent the
  legacy shapes, so the read-side fork is by necessity.
- **ADR 0002 (working/finalized split).** `ArtifactStore` writes only
  to `working/`. Reads come from `working/` for routine workspace
  rendering, from `finalized/<n>/` for the optional read-only
  finalization view (deferred), and via copy operations during
  finalize and reload.
- **Phase 5 finalize.** The finalize handler is the only code path
  that writes under `finalized/<n>/`. Every other write path —
  ArtifactStore, MCP staging promotion, all import flows — writes to
  `working/`. The immutability invariant is application-layer (no
  filesystem chmod), enforced by "exactly one writer."

When you find yourself wanting to unify a read path because there are
"too many" of them, check whether the divergence reflects a genuine
shape difference (ADR 0001) or audit-trail requirement (ADR 0002).
Unifying writes is almost always good; unifying reads often loses
information.

---

## 2. Verify before write

HANDOVER and CHANGELOG describe what the writer believed at write-
time. They're often slightly wrong by the time the next session reads
them — a file was renamed, a function was retired, a test was added
that contradicts the noted invariant.

Before acting on a HANDOVER claim, verify the actual state against the
codebase. Grep for the function name, `ls` the path, run the test
suite. The cost of verification is seconds; the cost of acting on a
stale claim is a confused refactor that breaks something downstream.

Two real instances this came up:

- The data flow audit (`docs/data_flow_audit.md`) Section 6 originally
  flagged `data/catalog/metrics/client_growth_summary.json` as missing
  from the working tree. The audit was wrong — the file was present
  but the `ls | head -3` invocation that built the audit had truncated
  the directory listing. A subsequent "diagnose and fix" session
  caught the error before making any code change, and updated the
  audit to retract surprise #4.
- During phase 3 implementation, HANDOVER said `init_db()` was still
  the test-fixture pattern in two files. Grep confirmed — but also
  surfaced that the legacy `schema.sql` it relied on was stale (only
  covered migration 0001's tables). The "verify before write" pass
  caught the footgun, which led to the interstitial cleanup that
  retired `init_db` entirely.

When in doubt, grep first. HANDOVER is a starting point, not a
contract.
