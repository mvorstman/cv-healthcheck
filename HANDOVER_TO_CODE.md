# cv-healthcheck — Report Inventory: Handover to Claude Code

**Date:** 2026-05-24
**Branch:** `feature/basic-healthcheck-report-output`
**Handover from:** Design + dry-run session in Claude.ai
**Handover to:** Claude Code implementation session

---

## What this document is

A complete handover from the design session to Claude Code. Everything decided in the design session is recorded here. Claude Code should read this document top to bottom before touching any file. Nothing in this document requires revisiting — these decisions are settled.

---

## 1. What has been built so far (do not change)

The existing application is a Flask + FastMCP server that produces healthcheck snapshots for Commvault environments.

**Entry points:**
- `cv-healthcheck` → `cvhealthcheck.cli:main`
- `cv-healthcheck-mcp` → `cvhealthcheck.mcp.server:main`

**Key existing components (stable, do not restructure):**
- `src/cvhealthcheck/artifacts/models.py` — Pydantic v2 canonical artifact schema (v1, frozen)
- `src/cvhealthcheck/artifacts/store.py` — `ArtifactStore` disk persistence
- `src/cvhealthcheck/db/schema.sql` — existing DDL (customers, engagements, staged_artifacts)
- `src/cvhealthcheck/db/staging.py` — CRUD for staged_artifacts
- `src/cvhealthcheck/mcp/server.py` — 6 MCP tools (get_canonical_schema, list_subjects, save_staged_artifact, list_staged_artifacts, approve_staged_artifact, reject_staged_artifact)
- `src/cvhealthcheck/quickhc/registry.py` — `QUICK_HC_TILES` tuple (6 TileDefinition entries)
- `src/cvhealthcheck/web/routes/staging.py` — staging review UI routes

**Test count:** 343 passing. Do not break any existing test.

**Constraints:**
- Raw SQL only — no ORM
- No Flask dependencies in adapter/registry/db layers
- Additive only — no breaking changes to existing tables or APIs
- Pydantic v2 canonical schema v1 is frozen — do not change `models.py`

---

## 2. Two new files that have been produced — use them exactly as written

### File 1: `src/cvhealthcheck/db/migrations/0003_report_inventory.sql`

This file has been written, tested against the existing schema in a clean SQLite in-memory database, and verified. It:

- Adds 8 columns to `staged_artifacts` via `ALTER TABLE`
- Creates 5 new tables: `subjects`, `subject_sections`, `subject_sources`, `subject_section_sources`, `collector_schemas`
- Seeds all 6 existing subjects from `QUICK_HC_TILES` with correct section and source bindings
- Is idempotent when run through the migration runner (not standalone)

**Do not modify this file.** If something looks wrong, raise it as a question before changing it.

The verification query at the bottom of the file produces this expected output when correct:

```
subject_id             v  status   sections  sources  bindings
environment            1  active   1         1        0
security_assessment    1  active   10        3        6
license_summary        1  active   4         3        4
client_growth          1  active   3         3        2
capacity_license       1  active   2         3        2
backup_job_summary     1  active   4         1        0
```

### File 2: `src/cvhealthcheck/db/migrations.py`

The migration runner module. Replaces the single-shot `init_db()` approach with a versioned migration sequence tracked in a `schema_migrations` table. Already written and verified.

---

## 3. Integration tasks — do these in order

### Task 1: Create migration directory structure

```
src/cvhealthcheck/db/migrations/
    __init__.py                      (empty)
    0001_initial_schema.sql          (RENAME from src/cvhealthcheck/db/schema.sql — no content changes)
    0003_report_inventory.sql        (the new file from handover)
```

Note: There is no `0002` — this is intentional. Lexicographic ordering handles gaps cleanly.

### Task 2: Move the migration runner into place

Put the `migrations.py` content at `src/cvhealthcheck/db/migrations.py` — **not** inside the `migrations/` directory. It sits alongside `database.py`, `staging.py`, etc.

Directory after task 1 and 2:
```
src/cvhealthcheck/db/
    __init__.py
    database.py
    migrations.py           ← the runner (new file)
    schema.sql              ← keep in place for reference, but init_db() is deprecated
    staging.py
    customers.py
    engagements.py
    migrations/
        __init__.py
        0001_initial_schema.sql
        0003_report_inventory.sql
```

### Task 3: Update `create_app()` in `src/cvhealthcheck/web/app.py`

Replace:
```python
init_db()
```
With:
```python
from cvhealthcheck.db.migrations import run_migrations
run_migrations()
```

### Task 4: Update the MCP server in `src/cvhealthcheck/mcp/server.py`

The MCP server currently calls `init_db()` at module level. Replace it with:
```python
from cvhealthcheck.db.migrations import run_migrations
run_migrations()
```

### Task 5: Update `conftest.py`

The existing autouse fixture `_isolate_canonical_stores` patches artifact stores. Add a second autouse fixture that runs migrations against the test database. The existing `db_path` fixture (or equivalent) in the test suite should be passed to `run_migrations(db_path=...)`.

Look at the existing test patterns in `test_db_staging.py` and `test_staging_routes.py` to understand how the test database is currently set up, then extend that pattern. Do not replace it — extend it so `schema_migrations`, `subjects`, `subject_sections`, `subject_sources`, `subject_section_sources`, and `collector_schemas` are present in every test that uses the database.

### Task 6: Update `list_subjects()` MCP tool

Currently `list_subjects()` reads from `QUICK_HC_TILES`. Change it to read from the `subjects` table:

```python
@mcp.tool()
def list_subjects(status: str | None = None) -> list[dict]:
    """List all subjects in the Report Inventory catalog."""
    db = get_db()
    query = "SELECT subject_id, version, title, description, category, category_label, status, created_by FROM subjects"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY category, title"
    return [dict(row) for row in db.execute(query, params)]
```

The existing `list_subjects()` returns `[{id, title, description}]`. The new version returns more fields. This is additive — Claude Desktop can handle extra fields, and the existing staging UI does not call `list_subjects()` directly.

### Task 7: Add two new MCP tools

Add these two tools to `src/cvhealthcheck/mcp/server.py`. Use the same patterns as the existing 6 tools.

#### `propose_new_subject`

```python
@mcp.tool()
def propose_new_subject(
    subject_id: str,
    version: int,
    title: str,
    description: str,
    category: str,
    sections: list[dict],
    extraction_instructions: dict,
    ai_notes: str,
    supersedes: int | None = None,
    change_notes: str | None = None,
    related_subjects: list[str] | None = None,
) -> dict:
    """
    Propose a new subject (report type) for the Report Inventory.

    Parameters
    ----------
    subject_id : str
        Snake-case identifier, e.g. "storage_utilization"
    version : int
        Version number. Use 1 for new subjects, increment for updates to existing.
    title : str
        Human-readable title, e.g. "Storage Utilization"
    description : str
        One-sentence description of what this report covers.
    category : str
        One of: identity | security | licensing | performance | operations | storage
    sections : list[dict]
        Each entry: {"section_id": str, "title": str, "section_type": str,
                     "default_selected": bool, "sort_order": int}
        section_type: findings | table | metric | chart
    extraction_instructions : dict
        Keys are source types ("html", "csv", "rest", "json").
        Each value is a dict with:
          - "extractable": bool
          - "non_extractable_reason": str | None  ("charts_only" | "client_side_rendered")
          - "recognition_hints": dict
          - "sections": dict mapping section_id → extraction instruction dict
    ai_notes : str
        Notes on confidence, data quality, empty-export caveats, etc.
    supersedes : int | None
        The subjects.id of the version this supersedes (for versioning).
    change_notes : str | None
        What changed from the superseded version.
    related_subjects : list[str] | None
        subject_id values of related subjects (e.g. dashboard → drill-down).
    """
    import json
    from uuid import uuid4

    proposal_json = json.dumps({
        "subject_id": subject_id,
        "version": version,
        "title": title,
        "description": description,
        "category": category,
        "sections": sections,
        "extraction_instructions": extraction_instructions,
        "supersedes": supersedes,
        "change_notes": change_notes,
        "related_subjects": related_subjects or [],
    })

    stage_id = f"stage_{uuid4().hex}"
    db = get_db()
    db.execute(
        """
        INSERT INTO staged_artifacts
            (stage_id, subject_id, artifact_type, subject_version,
             source_type, status, artifact_json, ai_notes, created_at)
        VALUES (?, ?, 'subject_proposal', ?, 'ai', 'pending', ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        """,
        (stage_id, subject_id, version, proposal_json, ai_notes),
    )
    db.commit()
    return {"stage_id": stage_id, "subject_id": subject_id, "status": "pending"}
```

#### `list_proposed_subjects`

```python
@mcp.tool()
def list_proposed_subjects(status: str | None = None) -> list[dict]:
    """
    List subject proposals in the staging queue.

    Parameters
    ----------
    status : str | None
        Filter by status: "pending" | "approved" | "rejected" | None (all)
    """
    import json

    db = get_db()
    query = """
        SELECT stage_id, subject_id, subject_version, status,
               artifact_json, ai_notes, created_at, reviewed_at, reviewed_by
        FROM staged_artifacts
        WHERE artifact_type = 'subject_proposal'
    """
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    rows = db.execute(query, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["proposal"] = json.loads(d.pop("artifact_json"))
        except Exception:
            d["proposal"] = {}
        result.append(d)
    return result
```

### Task 8: Write tests for the new code

Write tests for:

1. **Migration runner** — `tests/test_migrations.py`
   - Fresh database gets all tables after `run_migrations()`
   - Running twice is safe (idempotent)
   - `schema_migrations` contains `0001_initial_schema` and `0003_report_inventory` after both run
   - `subjects` table contains exactly 6 rows after migration

2. **`list_subjects()` MCP tool** — extend `tests/test_mcp_server.py`
   - Returns 6 subjects after migration
   - `status` filter works
   - Each subject has `subject_id`, `title`, `category`, `status` fields

3. **`propose_new_subject()` MCP tool** — extend `tests/test_mcp_server.py`
   - Creates a row in `staged_artifacts` with `artifact_type = 'subject_proposal'`
   - Returns `stage_id` and `status: "pending"`
   - The proposal JSON round-trips cleanly

4. **`list_proposed_subjects()` MCP tool** — extend `tests/test_mcp_server.py`
   - Empty when nothing proposed
   - Returns proposals after `propose_new_subject()` call
   - `status` filter works

Follow the test patterns from `test_mcp_server.py` exactly — use the same fixtures, same monkeypatching approach.

### Task 9: Run the full test suite

```bash
pytest -x -q
```

Must pass all 343 existing tests plus the new ones. Fix any failures before proceeding. Do not comment out or skip existing tests.

---

## 4. Architecture decisions — do not relitigate these

These were decided in the design session. If something looks wrong, note it but implement as specified.

**Five-layer architecture:**
1. `subjects` + `subject_sections` = catalog / definition layer
2. `subject_sources` + `subject_section_sources` = acquisition / extraction layer
3. `staged_artifacts` (with new columns) = review / verification layer
4. `ArtifactStore` / `latest.json` = approved canonical outputs layer
5. Compliance rules = evaluation layer (future — not in this session)

**`staged_artifacts` is the single staging mechanism.** Subject proposals use `artifact_type = 'subject_proposal'`, regular artifacts use `artifact_type = 'artifact'`. The existing `approve_staged_artifact` and `reject_staged_artifact` MCP tools work for both types — no changes needed to them.

**`subjects` owns the contract for the collector tool.** The collector tool (future, out of scope) will be built to match schemas cv-healthcheck defines. `collector_schemas` table exists as a stub — leave it empty.

**`list_tiles()` from the database is the eventual goal, not this session.** The `list_subjects()` MCP tool is updated to read from db (Task 6). The Flask `QUICK_HC_TILES` tuple in `registry.py` is NOT changed in this session — changing it requires frontend work that is a separate task.

**Canonical artifact schema v1 is frozen.** Do not touch `models.py`.

**`ArtifactStore` relative path is a known issue** (gap #2 in context report). Do not fix it in this session — it is tracked as technical debt.

---

## 5. Schema reference — what the new tables look like

```sql
-- subjects: one row per (subject_id, version)
subjects (
    id              INTEGER PK AUTOINCREMENT,
    subject_id      TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    superseded_by   INTEGER REFERENCES subjects(id),
    title           TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL,
    category_label  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',  -- active|superseded|proposed|disabled
    created_by      TEXT NOT NULL DEFAULT 'system',  -- system|ai|user
    preferred_source TEXT,                            -- html|csv|rest|json
    related_subjects TEXT,                            -- JSON array of subject_id strings
    change_notes    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (subject_id, version)
)

-- subject_sections: sections within a subject
subject_sections (
    id               INTEGER PK AUTOINCREMENT,
    subject_id       TEXT NOT NULL,
    subject_version  INTEGER NOT NULL DEFAULT 1,
    section_id       TEXT NOT NULL,  -- e.g. "security_assessment.access_security"
    title            TEXT NOT NULL,
    section_type     TEXT NOT NULL,  -- findings|table|metric|chart
    default_selected INTEGER NOT NULL DEFAULT 1,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    UNIQUE (subject_id, subject_version, section_id)
)

-- subject_sources: one row per (subject, version, source_type)
subject_sources (
    id                     INTEGER PK AUTOINCREMENT,
    subject_id             TEXT NOT NULL,
    subject_version        INTEGER NOT NULL DEFAULT 1,
    source_type            TEXT NOT NULL,  -- html|csv|rest|json
    extractable            INTEGER NOT NULL DEFAULT 1,
    non_extractable_reason TEXT,           -- charts_only|client_side_rendered|NULL
    recognition_hints      TEXT,           -- JSON object
    added_at               TEXT NOT NULL,
    UNIQUE (subject_id, subject_version, source_type)
)

-- subject_section_sources: extraction instructions per section per source
subject_section_sources (
    id                      INTEGER PK AUTOINCREMENT,
    source_id               INTEGER NOT NULL REFERENCES subject_sources(id) ON DELETE CASCADE,
    section_id              TEXT NOT NULL,
    extraction_instructions TEXT,  -- JSON object (structure documented in 0003 migration)
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE (source_id, section_id)
)

-- collector_schemas: stub, currently empty
collector_schemas (
    schema_id   TEXT PK,
    version     INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    json_schema TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (schema_id, version)
)

-- staged_artifacts: new columns added by 0003 migration
-- (existing columns unchanged)
staged_artifacts new columns:
    artifact_type        TEXT NOT NULL DEFAULT 'artifact'
                         -- 'artifact' | 'subject_proposal'
    subject_version      INTEGER
    verification_status  TEXT   -- NULL|pending|passed|failed|skipped
    verification_sources TEXT   -- JSON array of source types compared
    verification_notes   TEXT
    verified_at          TEXT
    user_edits_json      TEXT   -- manual edits made in staging UI
    filter_state_json    TEXT   -- captured filter state from import
```

---

## 6. What is NOT in scope for this session

These were explicitly deferred. Do not implement them:

- Generic HTML/CSV/REST extractor engine
- Staging UI changes for subject proposals (beyond what exists)
- `QUICK_HC_TILES` → database migration in the Flask frontend
- Compliance rules table and engine
- Per-customer compliance rule overrides
- `ArtifactStore` path anchoring fix
- REST authentication / credentials table
- Collector tool JSON schema definitions
- Docx report generation
- Artifact pruning / rotation
- `customers` and `engagements` UI / routes

---

## 7. How to verify the work is complete

After all 9 tasks are done, this sequence should work end-to-end:

```bash
# 1. Apply migrations to a fresh database
python -c "from cvhealthcheck.db.migrations import run_migrations; run_migrations()"

# 2. Confirm schema
sqlite3 data/app.db ".tables"
# Expected: collector_schemas customers engagements schema_migrations
#           staged_artifacts subject_section_sources subject_sections
#           subject_sources subjects

# 3. Confirm seed data
sqlite3 data/app.db "SELECT subject_id, version, status FROM subjects ORDER BY id;"
# Expected: 6 rows — environment, security_assessment, license_summary,
#           client_growth, capacity_license, backup_job_summary

# 4. Full test suite
pytest -x -q
# Expected: 343 + new tests, all passing

# 5. Start MCP server and confirm new tools available
cv-healthcheck-mcp
# In Claude Desktop: list_subjects() should return 6 subjects from db
#                    propose_new_subject() should create a staged row
#                    list_proposed_subjects() should return it
```

---

## 8. Context from dry runs — useful for future sessions, not this one

Seven reports were dry-run analysed to inform the schema design. The conclusions:

| Report | Source | Extractable | Notes |
|---|---|---|---|
| Storage Utilization | HTML | Yes (tables + KPIs) | Empty data; structure good |
| Growth & Trends dashboard | HTML | No | Charts-only |
| Growth & Trends | CSV | Yes (multi-section) | `None_Total` column name artefact |
| Growth & Trends | API viewer (.xlsx) | Reference only | Dataset GUIDs for REST bindings |
| Agent Dedupe Savings | HTML | Yes (pivot table) | Dynamic weekly columns |
| License Summary | HTML | Yes | Populated; two tables |
| Security Assessment | HTML | Yes | Populated; 6 findings sections |
| Cloud Storage Egress & Ingress | HTML | Yes | Empty; structure good |
| User & User Group Permissions | HTML | No | Client-side rendered, empty DOM |

These subjects are candidates for the next batch of `propose_new_subject` calls once the MCP tools are live. Not needed for this implementation session.

---

## 9. Open questions for Michiel (not for Claude Code to decide)

These require human input before they can be implemented:

1. **Naming convention for the `0002` gap** — if there is an unreleased migration between schema.sql and this one, what is it? If not, confirm `0001_initial_schema.sql` + `0003_report_inventory.sql` with no `0002` is correct.

2. **`reviewed_by` field** — currently a free-text string. Will this eventually reference a `users` table, or is the consultant name sufficient for now?

3. **The staging UI for subject proposals** — `approve_staged_artifact` in the web routes currently calls `ArtifactStore().save_artifact(artifact)`, which validates the JSON as a `CanonicalArtifact`. A `subject_proposal` artifact is not a `CanonicalArtifact` — the approve route will fail for subject proposals. This needs a route-level branch: if `artifact_type == 'subject_proposal'`, write to `subjects`/`subject_sections`/`subject_sources` tables instead of the artifact store. This is deferred from this session but Michiel should be aware it's the next piece of staging UI work.
