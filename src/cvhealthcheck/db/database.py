from __future__ import annotations

import sqlite3
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = _PROJECT_ROOT / "data" / "app.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    return _connect(db_path or DB_PATH)
