"""Tests for the analytics query functions."""

from datetime import date, timedelta

import duckdb
import pytest

from fin_insights.analytics import (
    get_cashflow,
    get_category_breakdown,
    get_month_over_month,
    get_monthly_spending_by_category,
    get_spending_by_card,
    get_top_merchants,
)
from fin_insights.db import SCHEMA_SQL


@pytest.fixture
def conn():
    """In-memory DuckDB with schema and fixture transactions."""
    c = duckdb.connect(":memory:")
    c.execute(SCHEMA_SQL)

    today = date.today()
    this_month = today.replace(day=15)
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=15)

    txns = [
        # This month expenses
        ("t1", "fp1", "chase", "credit_card", None, this_month, None,
         "CHIPOTLE", "CHIPOTLE", 15.50, "purchase", "Restaurants",
         "Food & Dining", "Restaurants", "file1.csv", None),
        ("t2", "fp2", "chase", "credit_card", None, this_month, None,
         "WHOLE FOODS", "WHOLE FOODS", 85.00, "purchase", "Groceries",
         "Food & Dining", "Groceries", "file1.csv", None),
        ("t3", "fp3", "amex", "credit_card", None, this_month, None,
         "UBER", "UBER", 25.00, "purchase", "Ride Share",
         "Transportation", "Rideshare", "file2.csv", None),
        ("t4", "fp4", "chase", "credit_card", None, this_month, None,
         "AMAZON", "AMAZON", 45.99, "purchase", "Shopping",
         "Shopping", "Online", "file1.csv", None),
        # This month income
        ("t5", "fp5", "chase", "checking", None, this_month, None,
         "DIRECT DEPOSIT", "DIRECT DEPOSIT", -3000.00, "deposit", "Income",
         "Income", "Salary", "file3.csv", None),
        # Last month expenses
        ("t6", "fp6", "chase", "credit_card", None, last_month, None,
         "CHIPOTLE", "CHIPOTLE", 12.00, "purchase", "Restaurants",
         "Food & Dining", "Restaurants", "file1.csv", None),
        ("t7", "fp7", "amex", "credit_card", None, last_month, None,
         "SHELL GAS", "SHELL GAS", 55.00, "purchase", "Gas",
         "Transportation", "Gas", "file2.csv", None),
        # Last month income
        ("t8", "fp8", "chase", "checking", None, last_month, None,
         "DIRECT DEPOSIT", "DIRECT DEPOSIT", -3000.00, "deposit", "Income",
         "Income", "Salary", "file3.csv", None),
    ]

    for txn in txns:
        c.execute(
            """INSERT INTO transactions
               (id, txn_fingerprint, institution, account_type, card_name,
                transaction_date, post_date, description, description_clean,
                amount, transaction_type, original_category, unified_category,
                unified_subcategory, source_file, location)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            list(txn),
        )

    yield c
    c.close()


def test_get_category_breakdown_all(conn):
    """Category breakdown returns all expense categories."""
    data = get_category_breakdown(conn)
    assert len(data) > 0
    categories = {r["category"] for r in data}
    assert "Food & Dining" in categories
    assert "Transportation" in categories
    # Income (negative amounts) should not appear
    totals = {r["category"]: r["total"] for r in data}
    assert "Income" not in totals


def test_get_category_breakdown_with_month(conn):
    """Category breakdown filtered by month works correctly."""
    today = date.today()
    month_str = today.strftime("%Y-%m")
    data = get_category_breakdown(conn, month=month_str)
    assert len(data) > 0
    # Should only include this month's data
    total = sum(float(r["total"]) for r in data)
    assert abs(total - (15.50 + 85.00 + 25.00 + 45.99)) < 0.01


def test_get_category_breakdown_percentages(conn):
    """Percentages in category breakdown sum to ~100%."""
    data = get_category_breakdown(conn)
    total_pct = sum(float(r["percentage"]) for r in data)
    assert abs(total_pct - 100.0) < 0.5


def test_get_cashflow(conn):
    """Cashflow returns income, spending, and savings rate."""
    data = get_cashflow(conn)
    assert len(data) >= 2

    for row in data:
        assert "month" in row
        assert "income" in row
        assert "spending" in row
        assert "net_cashflow" in row
        assert float(row["income"]) > 0
        assert float(row["spending"]) > 0


def test_get_cashflow_with_months(conn):
    """Cashflow with months filter returns correct number of months."""
    data = get_cashflow(conn, months=1)
    assert len(data) >= 1


def test_get_monthly_spending_by_category(conn):
    """Monthly spending by category returns expected data."""
    data = get_monthly_spending_by_category(conn)
    assert len(data) > 0
    for row in data:
        assert "category" in row
        assert "month" in row
        assert "total" in row
        assert float(row["total"]) > 0


def test_get_month_over_month(conn):
    """Month-over-month returns change data."""
    data = get_month_over_month(conn)
    assert len(data) > 0
    # Food & Dining appears in both months, so change should be computed
    food_rows = [r for r in data if r["category"] == "Food & Dining"]
    assert len(food_rows) >= 2
    # The most recent month should have a non-None change
    has_change = any(r["change"] is not None for r in food_rows)
    assert has_change


def test_get_top_merchants(conn):
    """Top merchants returns merchants ordered by spend."""
    data = get_top_merchants(conn, limit=5)
    assert len(data) > 0
    assert len(data) <= 5
    # Verify ordering (descending by total)
    totals = [float(r["total"]) for r in data]
    assert totals == sorted(totals, reverse=True)


def test_get_top_merchants_limit(conn):
    """Top merchants respects limit parameter."""
    data = get_top_merchants(conn, limit=2)
    assert len(data) <= 2


def test_get_spending_by_card(conn):
    """Spending by card groups by institution."""
    data = get_spending_by_card(conn)
    assert len(data) > 0
    institutions = {r["institution"] for r in data}
    assert "chase" in institutions
    assert "amex" in institutions
