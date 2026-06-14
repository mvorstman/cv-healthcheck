from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import DB_PATH, _connect


_CUSTOMER_COLUMNS = (
    "customer_id",
    "customer_name",
    "commcell_id",
    # commcell_hostname is READ-ONLY-LEGACY (migration 0032): still selected so
    # the read-time fallback works during the transition, never written.
    "commcell_hostname",
    # Identity-schema split (migration 0032, Fix 3):
    "connection_url",
    "commserve_name",
    "registration_code",
    "rp_server_url",
    "rp_scoping_id",
    "company_guid",
    # Fix-4 namespace-precision: the declared CommServe csGUID (migration 0037),
    # the same-namespace comparand for the identity verdict. TOFU-learned or
    # set manually; distinct from company_guid (tenant/company, not CommServe).
    "commserve_csguid",
    "contact_info",
    "notes",
    "created_at",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def slugify_customer_id(name: str, *, existing_ids: set[str] | None = None) -> str:
    """Turn a customer name into a stable id slug.

    Matches the convention set by the migration-seeded 'default' customer:
    lowercase, alphanumeric + underscores. On collision with an existing id,
    appends `_2`, `_3`, ... until unique.
    """
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if not base:
        base = f"customer_{uuid.uuid4().hex[:8]}"
    if not existing_ids:
        return base
    candidate = base
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _select_columns() -> str:
    return ", ".join(_CUSTOMER_COLUMNS)


def create_customer(
    customer_name: str,
    *,
    customer_id: str | None = None,
    commcell_id: str | None = None,
    connection_url: str | None = None,
    commserve_name: str | None = None,
    registration_code: str | None = None,
    rp_server_url: str | None = None,
    rp_scoping_id: str | None = None,
    company_guid: str | None = None,
    commserve_csguid: str | None = None,
    contact_info: str | None = None,
    notes: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    # commcell_hostname is READ-ONLY-LEGACY (migration 0032) — never written;
    # new rows get connection_url. The identity-schema columns are written
    # distinct from commcell_id (Fix 3 conflation fix).
    if not str(customer_name or "").strip():
        raise ValueError("customer_name is required.")
    path = db_path or DB_PATH
    now = _now()
    cid = customer_id or str(uuid.uuid4())
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO customers (customer_id, customer_name, commcell_id,"
            " connection_url, commserve_name, registration_code,"
            " rp_server_url, rp_scoping_id, company_guid, commserve_csguid,"
            " contact_info, notes, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cid,
                customer_name.strip(),
                commcell_id,
                connection_url,
                commserve_name,
                registration_code,
                rp_server_url,
                rp_scoping_id,
                company_guid,
                commserve_csguid,
                contact_info,
                notes,
                now,
                now,
            ),
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
            f"SELECT {_select_columns()} FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def list_customers(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    path = db_path or DB_PATH
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT {_select_columns()} FROM customers"
            " ORDER BY customer_name ASC, customer_id ASC",
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_customers_with_project_counts(
    *, db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Like list_customers but each row gets an additional 'project_count'
    field with the number of projects assigned to that customer.
    """
    path = db_path or DB_PATH
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT {_select_columns()},"
            "       (SELECT COUNT(*) FROM projects p"
            "        WHERE p.customer_id = customers.customer_id) AS project_count"
            " FROM customers"
            " ORDER BY customer_name ASC, customer_id ASC",
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_customer_projects(
    customer_id: str,
    *,
    db_path: Path | None = None,
) -> int:
    """Return the number of projects belonging to this customer."""
    path = db_path or DB_PATH
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def update_customer(
    customer_id: str,
    *,
    customer_name: str | None = None,
    commcell_id: str | None = None,
    connection_url: str | None = None,
    commserve_name: str | None = None,
    registration_code: str | None = None,
    rp_server_url: str | None = None,
    rp_scoping_id: str | None = None,
    company_guid: str | None = None,
    commserve_csguid: str | None = None,
    contact_info: str | None = None,
    notes: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """Update editable fields on a customer.

    Any field passed as None is left unchanged. To explicitly null a
    nullable column, pass an empty string and the caller can decide whether
    to coerce — this function only treats None as "no change."

    commcell_hostname is READ-ONLY-LEGACY (migration 0032) and is deliberately
    not updatable here — connection_url replaces it.
    """
    path = db_path or DB_PATH
    now = _now()
    updates: list[str] = []
    params: list[Any] = []
    field_map = {
        "customer_name": customer_name,
        "commcell_id": commcell_id,
        "connection_url": connection_url,
        "commserve_name": commserve_name,
        "registration_code": registration_code,
        "rp_server_url": rp_server_url,
        "rp_scoping_id": rp_scoping_id,
        "company_guid": company_guid,
        "commserve_csguid": commserve_csguid,
        "contact_info": contact_info,
        "notes": notes,
    }
    for column, value in field_map.items():
        if value is not None:
            updates.append(f"{column} = ?")
            params.append(value)
    if not updates:
        return False
    updates.append("updated_at = ?")
    params.append(now)
    params.append(customer_id)
    with _connect(path) as conn:
        cursor = conn.execute(
            f"UPDATE customers SET {', '.join(updates)} WHERE customer_id = ?",
            params,
        )
        conn.commit()
    return cursor.rowcount > 0


def learn_commserve_csguid(
    customer_id: str,
    csguid: str,
    *,
    db_path: Path | None = None,
) -> bool:
    """Trust-on-first-use: record the wire CommServe csGUID on a customer the
    FIRST time a verified live connect observes it (Fix-4 namespace-precision).

    SET-ONCE — the WHERE clause only writes when commserve_csguid is unset, so a
    later connect to a DIFFERENT CommServe (a changed GUID) is left to surface as
    a verdict `mismatch`, never silently auto-updated. Returns True iff a row was
    written (i.e. the GUID was newly learned). The manual customer-form override
    (update_customer) is the escape hatch to change an already-set value."""
    if not str(csguid or "").strip():
        return False
    path = db_path or DB_PATH
    now = _now()
    with _connect(path) as conn:
        cursor = conn.execute(
            "UPDATE customers SET commserve_csguid = ?, updated_at = ?"
            " WHERE customer_id = ?"
            "   AND (commserve_csguid IS NULL OR TRIM(commserve_csguid) = '')",
            (csguid, now, customer_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_customer(
    customer_id: str,
    *,
    db_path: Path | None = None,
) -> bool:
    """Delete a customer row.

    Returns True if a row was removed, False if no row matched.
    The caller is responsible for checking that the customer has no
    projects before calling — this function does not enforce that
    invariant. (The customers route does; tests can use this function
    directly to set up state.)
    """
    path = db_path or DB_PATH
    with _connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM customers WHERE customer_id = ?",
            (customer_id,),
        )
        conn.commit()
    return cursor.rowcount > 0


def validate_known_context(
    db: sqlite3.Connection, customer_id: str, project_id: str
) -> None:
    """D5: caller-asserted context is untrusted input — both ids must name
    existing rows (and the project must belong to the customer) before
    anything is written against them. Raises UnknownContextError."""
    from cvhealthcheck.context import UnknownContextError

    row = db.execute(
        "SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        raise UnknownContextError(f"unknown customer_id: {customer_id!r}")
    row = db.execute(
        "SELECT 1 FROM projects WHERE project_id = ? AND customer_id = ?",
        (project_id, customer_id),
    ).fetchone()
    if row is None:
        raise UnknownContextError(
            f"unknown project_id {project_id!r} for customer {customer_id!r}"
        )


def legacy_hostname_review_flags(
    db: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Customers whose legacy commcell_hostname did NOT migrate to
    connection_url — i.e. a non-URL-shaped value that migration 0032 left in
    place for manual fix (Fix 3 flag mechanism).

    Takes the caller's connection (the customers route's get_db()) so it
    reads the same DB. Returns one dict per flagged row (customer_id,
    customer_name, commcell_hostname). Expected EMPTY on the lab data (both
    non-NULL hostnames are URL-shaped); it ships so a non-URL legacy value
    surfaces on the customers page instead of silently vanishing when the
    column is later dropped."""
    rows = db.execute(
        "SELECT customer_id, customer_name, commcell_hostname"
        " FROM customers"
        " WHERE commcell_hostname IS NOT NULL"
        "   AND TRIM(commcell_hostname) != ''"
        "   AND connection_url IS NULL"
        " ORDER BY customer_name ASC, customer_id ASC"
    ).fetchall()
    return [_row_to_dict(row) for row in rows]
