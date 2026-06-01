"""ADR 0007 Phase 2 fix — migration 0027 lands migration 0026's intended effect
on a DB where 0026 is stamped-applied-but-ineffective (the broken-first-0026
state), and is idempotent on a fresh DB / on re-run.
"""
import sqlite3
from pathlib import Path

from cvhealthcheck.db.migrations import run_migrations

_MIG_0027 = (
    Path(__file__).resolve().parents[1]
    / "src/cvhealthcheck/db/migrations/0027_fix_environment_command_center_binding.sql"
).read_text()


def _env_source_types(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0] for r in conn.execute(
            "SELECT source_type FROM subject_sources WHERE subject_id='environment'"
        )
    }


def _check_widened(conn: sqlite3.Connection) -> bool:
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='subject_sources'"
    ).fetchone()[0]
    return "rest_command_center_api" in sql


def _fk_violations(conn: sqlite3.Connection) -> int:
    return len(conn.execute("PRAGMA foreign_key_check").fetchall())


def _cc_source_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM subject_sources"
        " WHERE subject_id='environment' AND source_type='rest_command_center_api'"
    ).fetchone()[0]


def _cc_binding_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM subject_section_sources sss"
        " JOIN subject_sources s ON s.id = sss.source_id"
        " WHERE s.subject_id='environment' AND s.source_type='rest_command_center_api'"
    ).fetchone()[0]


def _revert_to_broken_0026_state(conn: sqlite3.Connection) -> None:
    """Simulate the live DB after the broken first 0026: 4-value source_type
    CHECK and NO command-center source (but everything else intact)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        DELETE FROM subject_section_sources
          WHERE source_id IN (SELECT id FROM subject_sources WHERE source_type='rest_command_center_api');
        DELETE FROM subject_sources WHERE source_type='rest_command_center_api';
        CREATE TABLE _ss_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id TEXT NOT NULL,
            subject_version INTEGER NOT NULL DEFAULT 1, source_type TEXT NOT NULL,
            extractable INTEGER NOT NULL DEFAULT 1, non_extractable_reason TEXT,
            recognition_hints TEXT, added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            UNIQUE (subject_id, subject_version, source_type), CHECK (extractable IN (0,1)),
            CHECK (source_type IN ('html','csv','rest','json')),
            FOREIGN KEY (subject_id, subject_version)
              REFERENCES subjects(subject_id, version) DEFERRABLE INITIALLY DEFERRED);
        INSERT INTO _ss_old SELECT id,subject_id,subject_version,source_type,extractable,
            non_extractable_reason,recognition_hints,added_at FROM subject_sources;
        DROP TABLE subject_sources; ALTER TABLE _ss_old RENAME TO subject_sources;
        CREATE INDEX IF NOT EXISTS idx_subject_sources_subject ON subject_sources (subject_id, subject_version);
        CREATE INDEX IF NOT EXISTS idx_subject_sources_type ON subject_sources (source_type);
        """
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def test_0027_corrects_stamped_but_ineffective_0026_state(migrated_db_path: Path):
    conn = sqlite3.connect(str(migrated_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _revert_to_broken_0026_state(conn)
        # Broken precondition (the confirmed live state).
        assert _env_source_types(conn) == {"rest"}
        assert _check_widened(conn) is False
        rest_id_before = conn.execute(
            "SELECT id FROM subject_sources WHERE subject_id='environment' AND source_type='rest'"
        ).fetchone()[0]

        # Apply 0027 (the forward fix).
        conn.executescript(_MIG_0027)
        conn.commit()

        # Corrected: CHECK widened, command-center source + binding present, FK intact.
        assert _check_widened(conn) is True
        assert _env_source_types(conn) == {"rest", "rest_command_center_api"}
        assert _cc_source_count(conn) == 1 and _cc_binding_count(conn) == 1
        assert _fk_violations(conn) == 0
        # The existing rest row (id 7) and its live-card binding are preserved.
        assert conn.execute(
            "SELECT id FROM subject_sources WHERE subject_id='environment' AND source_type='rest'"
        ).fetchone()[0] == rest_id_before
        assert conn.execute(
            "SELECT COUNT(*) FROM subject_section_sources sss JOIN subject_sources s ON s.id=sss.source_id"
            " WHERE s.subject_id='environment' AND s.source_type='rest'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_0027_is_idempotent_on_fresh_db(migrated_db_path: Path):
    """run_migrations already applied 0027; re-executing it is a no-op (no dupe row,
    no error, CHECK stays widened, FK clean)."""
    conn = sqlite3.connect(str(migrated_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        assert _env_source_types(conn) == {"rest", "rest_command_center_api"}  # from run_migrations
        conn.executescript(_MIG_0027)   # re-run
        conn.commit()
        conn.executescript(_MIG_0027)   # and again
        conn.commit()
        assert _cc_source_count(conn) == 1 and _cc_binding_count(conn) == 1     # no dupes
        assert _check_widened(conn) is True
        assert _fk_violations(conn) == 0
    finally:
        conn.close()
