# 0002 — Customer and Project as first-class entities

**Status:** Accepted
**Date:** 2026-05-26

## Context

cv-healthcheck today implicitly assumes one customer, one project, one set of data. The canonical `ArtifactStore` writes to `data/catalog/artifacts/<subject>/latest.json` with no scoping above the subject. The catalog DB (`data/app.db`) has `subjects`, `staged_artifacts`, `customers`, and `engagements` tables, but the artifact-storage paths and the workspace UI ignore the customer/engagement structure entirely — every artifact represents "the" data for "the" target. The current state is documented in `docs/data_flow_audit.md`.

This is fine on a dev machine. It breaks the moment the tool is used for real consulting work, where:

- A single consultant runs healthchecks for multiple customers, each with its own CommCell.
- Each customer engagement is a discrete project — typically with a project number and often tied to a TopDesk ticket reference.
- A delivered report becomes the audit-of-record for what the consultant told that customer at that point in time. If the customer later requests corrections, the corrected report supersedes the previous one, but both must remain traceable.
- The same subject (e.g. `license_summary`) collected for Customer A is unrelated to the same subject collected for Customer B; they should not overwrite each other.

The workflow the tool needs to support is concrete: customer requests a healthcheck → project is created (with project number, optionally a TopDesk ticket) → consultant collects data through REST, CSV, HTML → report is built and reviewed → report is delivered → customer reviews and approves → project is finalized. If a correction is needed later, a new ticket is created, the finalized project is reloaded for editing, edits land, and re-finalization produces a new immutable snapshot. The previous finalization remains as the historical record of what was originally delivered.

The current architecture has no place to put any of this.

## Decision

**Customer and Project become first-class entities in the catalog DB and in the storage layout. Artifacts are scoped to a project. Finalization produces immutable per-project snapshots; the rest of project state is mutable working storage.**

### Identity

- **Customer** is a first-class entity. Each customer carries identity (name), CommCell configuration (CommCell ID, hostname, optional company GUID for cases where the CommCell hosts multiple companies), and free-form contact/metadata fields (notes, contact info, anything else the consultant needs).
- **Project** is a first-class entity. Each project belongs to exactly one customer. A project carries a project number, an optional ticket reference, the assigned consultant, a creation timestamp, and a working-state-modified-at timestamp.
- **Customer creation supports two paths.** Manual entry is always available. CommCell-discovery is the convenience path: the user supplies CommCell credentials, the tool authenticates against the CommCell, fetches the identity fields (CommCell ID, version, hostname), and populates the customer record. Credentials are used once for discovery and discarded — not stored.
- **Creating a customer is mandatory** to use the tool. On first run, an empty database is migrated and a "Default" customer is auto-created with sensible placeholder fields. The user never sees a hard empty state; they can rename the default or create additional customers from the customer page when ready.

### Lifecycle

- **Projects have no `status` column.** A project's history is the sequence of its finalizations. A project that has been finalized once is no different in structure from a project that has been finalized three times or never finalized — only the count of `finalizations` rows differs.
- **The data unit for retention is the finalization, not time or count.** Each `finalize` action creates an immutable snapshot of the project's working state. All finalizations are kept forever. Working state between finalizations is overwritten freely.
- **Finalize is not a one-way trapdoor.** A finalized project can be reloaded for editing — corresponding to the real-world customer correction request. Edits land in working state; finalizing again produces the next snapshot. The previous finalization remains in the database as the audit-of-record of what was originally delivered. Each finalization records its own ticket reference (the ticket that triggered *this* finalization — which may be the original or a later correction), so the audit trail tells *why* each version was finalized.
- **Reload always loads the LATEST finalization.** Reloading older finalizations is explicitly not supported — if a consultant needs to start from an older state, that's a new project. If the working state has uncommitted changes from a previous editing pass, the UI warns and requires confirmation before discarding them.
- **Multiple open projects per customer are allowed.** A customer can have several projects in various states (some never finalized, some with multiple finalizations). The consultant works on one project at a time; the UI tracks an "active project" concept for what is currently in focus.

### Immutability

- **Immutability of finalizations is enforced at the database and application layer, NOT at the file system layer.** The application never writes to finalized snapshot paths once created — that is a code-level invariant, not a filesystem permission. Removal of finalizations requires direct database access; it is deliberately not exposed in the UI. Recovery from corruption is via database backup.
- This choice is intentional. Filesystem-level read-only flags would fight backup tools, complicate cross-platform deployment (no consistent semantics across Linux/Windows/macOS), and offer false security against an admin with disk access anyway. The integrity guarantee that matters is "the application never overwrites a finalization once made"; that's enforced by routing all writes through `ArtifactStore`-equivalent code that knows the working-vs-finalized distinction and refuses to touch the latter.

### Out of scope for v1

- **Multi-CommCell support per customer is not in v1.** Each customer has one CommCell. A consulting customer with multiple CommCells is currently modeled as multiple customer records or — if the user prefers — handled outside the tool until v2.
- **Multi-company-within-CommCell support is not in v1.** The optional company GUID field on `customers` is forward-looking; the tool does not branch behavior on it yet.
- **Existing canonical-store data on disk is not preserved during the migration.** The current `data/catalog/artifacts/<subject>/` layout is throwaway dev state; the migration deletes it cleanly and starts fresh under the new customer-scoped paths. (Migration is conditional: anything already under the new customer-scoped paths from a prior partial migration is left alone.)

### Data model

Tables, in prose:

- **`customers`** — identity and configuration for each customer. Fields: a primary key (UUID or short id), display name, CommCell ID, CommCell hostname, optional company GUID (forward-looking), a JSON column or sibling table for free-form contact/metadata, creation and last-modified timestamps. No retention setting — retention is implicit from the finalize/keep model.
- **`projects`** — one row per consulting engagement. Fields: primary key, customer foreign key, project number (string, human-readable, unique within customer), optional ticket reference (string), assigned consultant (string or user reference), creation timestamp, working-state-modified-at timestamp. No status field. No finalized-or-not boolean; that's derived from the `finalizations` sequence.
- **`finalizations`** — append-only audit log. Fields: primary key, project foreign key, finalization number (per-project monotonic integer, e.g. 1, 2, 3), finalized-at timestamp, finalized-by (consultant), ticket reference for *this* finalization, free-form notes. Once inserted, rows are never updated or deleted by the application.
- **Artifacts gain a `project_id` foreign key.** Where today's catalog has a single global artifact per subject, the new model has one per project per subject (in working state, latest only) plus one per project per subject per finalization (the immutable snapshots).

The existing `customers` and `engagements` tables in `data/app.db` predate this design. The implementation session decides whether to migrate them, rename them, or coexist; the ADR notes only that the conceptual model lives in the three tables above.

### Storage paths

- **Working state (mutable):** `data/catalog/artifacts/<customer_id>/<project_id>/working/<subject_id>/...`
- **Finalized snapshots (immutable by application convention):** `data/catalog/artifacts/<customer_id>/<project_id>/finalized/<finalization_number>/<subject_id>/...`

The current ArtifactStore filename convention (timestamped snapshots + `latest.json` mirror) carries over for working state. Under a project's `working/<subject_id>/` directory, `latest.json` is the current working state for that subject — overwritten on every save, just like today. Under a project's `finalized/<N>/<subject_id>/` directory, the file set is a frozen copy of the working state at the time of finalization.

The read path becomes: "for the active project, read from `working/<subject>/latest.json`; for a delivered report, read from the project's most-recent `finalized/<N>/<subject>/` directory." The implementation session works out the exact `ArtifactStore` interface change (likely a `project_context` parameter on save/load); the ADR's responsibility is to flag that the change is local to the store layer and does not require restructuring the canonical schema or the source-building paths.

### Active-project session state

The UI tracks an "active project" — the one the consultant is currently working on. This lives in the user's session (similar in spirit to the `#subject=<id>` URL fragment that preserves selected subject across redirects, but with a different scope: customer/project selection is session-scoped, subject selection is per-request). The mechanism is an implementation detail; the ADR commits only to "there is an active project per session, and the UI surfaces it consistently."

**Concurrent edits are out of scope.** cv-healthcheck is a single-user tool. One consultant works on one active project at a time. No locking, no multi-user conflict resolution.

### UI shape

The customer and project pages need to support: listing customers, creating/editing a customer (manual or CommCell-discovery), listing a customer's projects, creating a project, switching the active project, viewing a project's finalization history, finalizing the active project, and reloading a previously-finalized project for editing. The ADR commits to these capabilities existing; the implementation session decides nav placement, visual design, and form layout.

## Consequences

### Preserved (the goals this enables)

- **Multi-customer real-world use becomes possible.** A consultant can run healthchecks for ten customers without their data colliding.
- **Audit trail of delivered reports is preserved by design.** Every finalization is an immutable snapshot keyed by ticket reference and consultant; the history reconstructs what was delivered and why.
- **The consultant's actual workflow is the unit of organization.** Project number, ticket reference, finalize/reload — these are the consultant's primitives, not generic CRUD on artifacts.
- **First-run friendliness.** The auto-created "Default" customer means the tool boots into a usable state without forcing the user through an empty-state wizard. The single-customer dev experience is preserved as the v1 starting point.

### Accepted tradeoffs

- **The current single-customer layout is replaced; existing dev data is deleted by the migration.** A clean-cut migration is simpler than a customer-data preservation step, and the data on dev machines is throwaway. Anyone with non-throwaway data on a dev machine before this lands needs to capture it outside the tool first.
- **Immutability is an application-layer guarantee, not a filesystem one.** The integrity story relies on the application code never overwriting a finalized path. Database backups are the recovery mechanism. This is a deliberate tradeoff against the operational complexity of filesystem-level enforcement.
- **The catalog DB schema grows.** New `customers`, `projects`, `finalizations` tables (or migrations of existing ones) plus a foreign key on the artifact-tracking surface. Migrations are additive; the existing migration system at `src/cvhealthcheck/db/migrations/` handles this cleanly.

### Out of scope for this decision

- **Multi-CommCell and multi-company-within-CommCell support.** Listed in revisit triggers.
- **Cryptographic-checksum-backed immutability** (signed snapshots, hash chains). Not required by current audit needs; can be added later under the same storage layout.
- **Server-side report storage / sharing.** The consultant currently delivers reports out-of-band. Project storage is what the consultant works with; what gets sent to the customer is a separate concern.

### Relationship to ADR 0001

This decision is **orthogonal** to the source-building fork in ADR 0001. System subjects still flow through `_legacy_builders`; AI subjects still flow through `_build_generic_subject`. The customer/project work changes *where* artifacts are stored and *which* artifact a builder reads, not *how* the tile data is shaped. Both forks coexist without interaction.

There is a pattern symmetry worth noting: just as ADR 0001 separates a unified write path (the upload route) from a divergent read path (`_legacy_builders` vs `_build_generic_subject`), this decision separates a unified working write path (every save touches `working/`) from divergent read targets (working state for the editor, finalized snapshots for audit). The mental model "write goes one place, reads can go multiple places" is consistent across both.

### Future ADRs that build on this

- **ADR 0003 (REST extractor, next session).** The REST extractor will use the active project's storage path for the artifacts it collects. This ADR commits only that the path exists; ADR 0003 specifies how collection writes to it.

## Alternatives considered

- **α — Stay single-customer.** Keep the current architecture; document that multi-customer use requires separate cv-healthcheck installs. **Rejected.** Real consulting work requires multi-customer support; the install-per-customer workaround doesn't preserve the audit trail.
- **β — File-system readonly for finalized snapshots.** Use OS-level immutable attributes (e.g. `chattr +i` on Linux) to enforce that finalized files cannot be modified. **Rejected.** Fights backup tools, has no cross-platform equivalent (Windows ACLs are different in semantics from POSIX), and provides false security against admin access anyway. Application-layer enforcement is simpler and sufficient.
- **γ — Per-customer retention configuration.** Let each customer configure how many finalizations to keep, with auto-prune on excess. **Rejected.** Retention is implicit from the finalize/keep model — keep all, forever. Storage cost is negligible for the artifact sizes involved (hundreds of KB per snapshot); audit value is high. Adding configuration here is premature.
- **δ — Multi-tenant / multi-CommCell from v1.** Customers with multiple CommCells modeled as one customer with multiple CommCell records; companies-within-CommCell exposed as a sub-entity. **Rejected.** Scope expansion. The single-CommCell-per-customer model covers the common case and the ADR explicitly lists this as a revisit trigger.
- **ε — One-way trapdoor finalize.** Once finalized, a project can never be edited; a customer correction request requires creating a new project. **Rejected.** The real-world workflow is "open the existing project, fix the thing, re-finalize." Forcing new-project-per-correction loses the continuity in the project number / ticket history and creates artificial duplication. The reload-finalized-for-correction model preserves both the audit trail (every finalization stays) and the working continuity (one project = one consulting engagement, even across corrections).

## References

- Data flow audit: `docs/data_flow_audit.md` — describes the current single-customer storage layout that this ADR replaces.
- ADR 0001: `docs/adr/0001-source-building-fork.md` — orthogonal to this decision; pattern-symmetric in its "unified write, divergent read" shape.
- Forthcoming ADR 0003 (REST extractor) will build on this ADR's storage paths.

## Revisit triggers

Reopen this decision if and only if:

- Multi-CommCell per customer becomes a common pattern in real engagements (rather than the rare case it's expected to be at v1 launch).
- Multi-company-within-CommCell support is required by an actual customer engagement.
- Audit standards applicable to the consulting practice require filesystem-level or cryptographic-checksum immutability for delivered reports.
- Concurrent multi-user access becomes a requirement (two consultants editing the same project, or hand-off mid-engagement).

Don't reopen this for "the active-project concept is awkward," "the migration deleted my dev data," or "I want to keep older finalizations editable." The decision above already considered and rejected those motivations.
