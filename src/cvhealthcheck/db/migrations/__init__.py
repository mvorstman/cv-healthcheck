"""
cvhealthcheck.db.migrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Lightweight SQL migration runner.

Replaces the single-shot `init_db()` + `schema.sql` approach with a
versioned migration sequence.  Each migration file is applied exactly
once; the `schema_migrations` table tracks what has been applied.

Usage (drop-in replacement for init_db() call in create_app and MCP server):

    from cvhealthcheck.db.migrations import run_migrations
    run_migrations()

Migration files live in src/cvhealthcheck/db/migrations/ and are named:
    0001_initial.sql
    0002_staged_artifacts.sql
    0003_report_inventory.sql
    ...

They are applied in lexicographic order.  A migration is skipped if its
name already appears in schema_migrations.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# This file is src/cvhealthcheck/db/migrations/__init__.py.
# parent  = src/cvhealthcheck/db/migrations/  (the SQL files live here)
# parents[4] = project root
_MIGRATIONS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = _PROJECT_ROOT / "data" / "app.db"


def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TEXT NOT NULL
                         DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)
    conn.commit()


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    return {
        row["migration_id"]
        for row in conn.execute("SELECT migration_id FROM schema_migrations")
    }


def run_migrations(db_path: Path = DB_PATH) -> None:
    """Apply all pending migrations in order."""
    conn = _get_connection(db_path)
    try:
        _ensure_migrations_table(conn)
        applied = _applied_migrations(conn)

        migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            logger.warning("No migration files found in %s", _MIGRATIONS_DIR)
            return

        for migration_file in migration_files:
            migration_id = migration_file.stem  # filename without .sql
            if migration_id in applied:
                logger.debug("Migration %s already applied — skipped", migration_id)
                continue

            logger.info("Applying migration %s", migration_id)
            sql = migration_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (migration_id) VALUES (?)",
                (migration_id,),
            )
            conn.commit()
            logger.info("Migration %s applied OK", migration_id)

    finally:
        conn.close()


def migration_status(db_path: Path = DB_PATH) -> list[dict]:
    """Return status of all known migrations — useful for health checks."""
    conn = _get_connection(db_path)
    try:
        _ensure_migrations_table(conn)
        applied = {
            row["migration_id"]: row["applied_at"]
            for row in conn.execute(
                "SELECT migration_id, applied_at FROM schema_migrations"
            )
        }
        result = []
        for f in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            mid = f.stem
            result.append({
                "migration_id": mid,
                "status": "applied" if mid in applied else "pending",
                "applied_at": applied.get(mid),
            })
        return result
    finally:
        conn.close()
