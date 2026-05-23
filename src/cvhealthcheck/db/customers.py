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


def create_customer(
    customer_name: str,
    *,
    customer_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not str(customer_name or "").strip():
        raise ValueError("customer_name is required.")
    path = db_path or DB_PATH
    now = _now()
    cid = customer_id or str(uuid.uuid4())
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO customers (customer_id, customer_name, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (cid, customer_name.strip(), now, now),
        )
        conn.commit()
    return get_customer(cid, db_path=path)  # type: ignore[return-value]


def get_customer(
    customer_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT customer_id, customer_name, created_at, updated_at"
            " FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_customers(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT customer_id, customer_name, created_at, updated_at"
            " FROM customers ORDER BY customer_name ASC, customer_id ASC",
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_customer(
    customer_id: str,
    *,
    customer_name: str,
    db_path: Path | None = None,
) -> bool:
    path = db_path or DB_PATH
    now = _now()
    with _connect(path) as conn:
        cursor = conn.execute(
            "UPDATE customers SET customer_name = ?, updated_at = ? WHERE customer_id = ?",
            (customer_name, now, customer_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_customer(
    customer_id: str,
    *,
    db_path: Path | None = None,
) -> bool:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM customers WHERE customer_id = ?",
            (customer_id,),
        )
        conn.commit()
    return cursor.rowcount > 0
