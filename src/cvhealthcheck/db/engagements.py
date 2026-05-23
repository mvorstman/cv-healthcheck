from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import DB_PATH, _connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_engagement(
    customer_id: str,
    name: str,
    *,
    engagement_id: str | None = None,
    commcell_id: str | None = None,
    status: str = "active",
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not str(name or "").strip():
        raise ValueError("name is required.")
    path = db_path or DB_PATH
    now = _now()
    eid = engagement_id or str(uuid.uuid4())
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO engagements"
            " (engagement_id, customer_id, name, commcell_id, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (eid, customer_id, name.strip(), commcell_id, status, now, now),
        )
        conn.commit()
    return get_engagement(eid, db_path=path)  # type: ignore[return-value]


def get_engagement(
    engagement_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT engagement_id, customer_id, name, commcell_id, status, created_at, updated_at"
            " FROM engagements WHERE engagement_id = ?",
            (engagement_id,),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_engagements(
    customer_id: str | None = None,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        if customer_id is not None:
            rows = conn.execute(
                "SELECT engagement_id, customer_id, name, commcell_id, status, created_at, updated_at"
                " FROM engagements WHERE customer_id = ?"
                " ORDER BY created_at ASC, engagement_id ASC",
                (customer_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT engagement_id, customer_id, name, commcell_id, status, created_at, updated_at"
                " FROM engagements ORDER BY created_at ASC, engagement_id ASC",
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_engagement(
    engagement_id: str,
    *,
    name: str,
    db_path: Path | None = None,
) -> bool:
    path = db_path or DB_PATH
    now = _now()
    with _connect(path) as conn:
        cursor = conn.execute(
            "UPDATE engagements SET name = ?, updated_at = ? WHERE engagement_id = ?",
            (name, now, engagement_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_engagement(
    engagement_id: str,
    *,
    db_path: Path | None = None,
) -> bool:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM engagements WHERE engagement_id = ?",
            (engagement_id,),
        )
        conn.commit()
    return cursor.rowcount > 0
