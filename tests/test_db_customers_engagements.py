from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cvhealthcheck.db.migrations import run_migrations
from cvhealthcheck.db.customers import (
    create_customer,
    delete_customer,
    get_customer,
    list_customers,
    update_customer,
)
from cvhealthcheck.db.engagements import (
    create_engagement,
    delete_engagement,
    get_engagement,
    list_engagements,
    update_engagement,
)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path=db_path)
    # Migration 0005 seeds the 'default' customer + project. Clear them
    # so existing assertions (e.g. list_customers_empty) start from a
    # clean slate.
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM projects")
    conn.execute("DELETE FROM customers")
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Customers — create
# ---------------------------------------------------------------------------


def test_create_customer_generates_id(db: Path) -> None:
    customer = create_customer("Acme Corp", db_path=db)
    assert customer["customer_id"]


def test_create_customer_with_explicit_id(db: Path) -> None:
    customer = create_customer("Acme Corp", customer_id="cust-001", db_path=db)
    assert customer["customer_id"] == "cust-001"


def test_create_customer_returns_all_fields(db: Path) -> None:
    customer = create_customer("Acme Corp", db_path=db)
    assert set(customer.keys()) == {
        "customer_id",
        "customer_name",
        "commcell_id",
        "commcell_hostname",
        "company_guid",
        "contact_info",
        "notes",
        "created_at",
        "updated_at",
    }
    assert customer["customer_name"] == "Acme Corp"


def test_create_customer_duplicate_id_raises(db: Path) -> None:
    create_customer("Acme Corp", customer_id="dup", db_path=db)
    with pytest.raises(sqlite3.IntegrityError):
        create_customer("Other Corp", customer_id="dup", db_path=db)


def test_create_customer_empty_name_raises(db: Path) -> None:
    with pytest.raises(ValueError):
        create_customer("", db_path=db)


# ---------------------------------------------------------------------------
# Customers — read / update / delete
# ---------------------------------------------------------------------------


def test_get_customer_returns_record(db: Path) -> None:
    created = create_customer("Acme Corp", customer_id="c1", db_path=db)
    fetched = get_customer("c1", db_path=db)
    assert fetched == created


def test_get_customer_not_found_returns_none(db: Path) -> None:
    assert get_customer("nonexistent", db_path=db) is None


def test_list_customers_empty(db: Path) -> None:
    assert list_customers(db_path=db) == []


def test_list_customers_returns_all(db: Path) -> None:
    create_customer("Acme", db_path=db)
    create_customer("Beta", db_path=db)
    assert len(list_customers(db_path=db)) == 2


def test_list_customers_ordered_by_name(db: Path) -> None:
    create_customer("Zebra Corp", db_path=db)
    create_customer("Acme Corp", db_path=db)
    names = [c["customer_name"] for c in list_customers(db_path=db)]
    assert names == ["Acme Corp", "Zebra Corp"]


def test_update_customer_name(db: Path) -> None:
    create_customer("Old Name", customer_id="c1", db_path=db)
    result = update_customer("c1", customer_name="New Name", db_path=db)
    assert result is True
    assert get_customer("c1", db_path=db)["customer_name"] == "New Name"


def test_update_customer_sets_updated_at(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    original = get_customer("c1", db_path=db)
    update_customer("c1", customer_name="Acme Updated", db_path=db)
    updated = get_customer("c1", db_path=db)
    assert updated["updated_at"] >= original["created_at"]


def test_update_customer_not_found_returns_false(db: Path) -> None:
    assert update_customer("missing", customer_name="X", db_path=db) is False


def test_delete_customer_returns_true(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    assert delete_customer("c1", db_path=db) is True
    assert get_customer("c1", db_path=db) is None


def test_delete_customer_not_found_returns_false(db: Path) -> None:
    assert delete_customer("nonexistent", db_path=db) is False


def test_delete_customer_removes_from_list(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_customer("Beta", customer_id="c2", db_path=db)
    delete_customer("c1", db_path=db)
    customers = list_customers(db_path=db)
    assert len(customers) == 1
    assert customers[0]["customer_id"] == "c2"


# ---------------------------------------------------------------------------
# Engagements — create
# ---------------------------------------------------------------------------


def test_create_engagement_generates_id(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    eng = create_engagement("c1", "Q1 Health Check", db_path=db)
    assert eng["engagement_id"]


def test_create_engagement_with_explicit_id(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    eng = create_engagement("c1", "Q1 Health Check", engagement_id="eng-001", db_path=db)
    assert eng["engagement_id"] == "eng-001"


def test_create_engagement_returns_all_fields(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    eng = create_engagement("c1", "Q1", db_path=db)
    assert {"engagement_id", "customer_id", "name", "status", "created_at", "updated_at"}.issubset(
        eng.keys()
    )
    assert eng["customer_id"] == "c1"
    assert eng["name"] == "Q1"
    assert eng["status"] == "active"


def test_create_engagement_duplicate_id_raises(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "E1", engagement_id="dup", db_path=db)
    with pytest.raises(sqlite3.IntegrityError):
        create_engagement("c1", "E2", engagement_id="dup", db_path=db)


def test_create_engagement_empty_name_raises(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    with pytest.raises(ValueError):
        create_engagement("c1", "", db_path=db)


# ---------------------------------------------------------------------------
# Engagements — read / update / delete
# ---------------------------------------------------------------------------


def test_get_engagement_by_id(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    created = create_engagement("c1", "Q1", engagement_id="e1", db_path=db)
    fetched = get_engagement("e1", db_path=db)
    assert fetched == created


def test_get_engagement_not_found_returns_none(db: Path) -> None:
    assert get_engagement("nonexistent", db_path=db) is None


def test_list_engagements_for_customer_empty(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    assert list_engagements("c1", db_path=db) == []


def test_list_engagements_for_customer(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "E1", db_path=db)
    create_engagement("c1", "E2", db_path=db)
    assert len(list_engagements("c1", db_path=db)) == 2


def test_list_engagements_filters_by_customer_id(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_customer("Beta", customer_id="c2", db_path=db)
    create_engagement("c1", "E1", db_path=db)
    create_engagement("c2", "E2", db_path=db)
    c1_engs = list_engagements("c1", db_path=db)
    assert len(c1_engs) == 1
    assert c1_engs[0]["customer_id"] == "c1"


def test_list_all_engagements(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_customer("Beta", customer_id="c2", db_path=db)
    create_engagement("c1", "E1", db_path=db)
    create_engagement("c2", "E2", db_path=db)
    assert len(list_engagements(db_path=db)) == 2


def test_update_engagement_name(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "Old Name", engagement_id="e1", db_path=db)
    result = update_engagement("e1", name="New Name", db_path=db)
    assert result is True
    assert get_engagement("e1", db_path=db)["name"] == "New Name"


def test_update_engagement_sets_updated_at(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "E1", engagement_id="e1", db_path=db)
    original = get_engagement("e1", db_path=db)
    update_engagement("e1", name="E1 Updated", db_path=db)
    updated = get_engagement("e1", db_path=db)
    assert updated["updated_at"] >= original["created_at"]


def test_update_engagement_not_found_returns_false(db: Path) -> None:
    assert update_engagement("missing", name="X", db_path=db) is False


def test_delete_engagement_returns_true(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "E1", engagement_id="e1", db_path=db)
    assert delete_engagement("e1", db_path=db) is True
    assert get_engagement("e1", db_path=db) is None


def test_delete_engagement_not_found_returns_false(db: Path) -> None:
    assert delete_engagement("nonexistent", db_path=db) is False


def test_delete_customer_cascades_to_engagements(db: Path) -> None:
    create_customer("Acme", customer_id="c1", db_path=db)
    create_engagement("c1", "E1", engagement_id="e1", db_path=db)
    delete_customer("c1", db_path=db)
    assert get_engagement("e1", db_path=db) is None
