"""Tests for the card rewards recommendation engine."""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from fin_insights.db import SCHEMA_SQL
from fin_insights.rewards import load_rewards_to_db, optimize_past_spending, recommend_for_category

EXAMPLE_REWARDS = Path(__file__).parent.parent / "config" / "card_rewards.example.yaml"


@pytest.fixture
def conn():
    """In-memory DuckDB with schema."""
    c = duckdb.connect(":memory:")
    c.execute(SCHEMA_SQL)
    yield c
    c.close()


@pytest.fixture
def conn_with_rewards(conn):
    """Connection with rewards loaded from example config."""
    load_rewards_to_db(conn, EXAMPLE_REWARDS)
    return conn


def test_load_rewards_to_db(conn):
    """Loading example rewards config inserts reward entries."""
    count = load_rewards_to_db(conn, EXAMPLE_REWARDS)
    assert count > 0

    rows = conn.execute("SELECT COUNT(*) FROM card_rewards").fetchone()[0]
    assert rows == count


def test_load_rewards_replaces_existing(conn):
    """Loading rewards twice replaces old entries, not duplicates."""
    count1 = load_rewards_to_db(conn, EXAMPLE_REWARDS)
    count2 = load_rewards_to_db(conn, EXAMPLE_REWARDS)
    assert count1 == count2

    rows = conn.execute("SELECT COUNT(*) FROM card_rewards").fetchone()[0]
    assert rows == count2


def test_load_rewards_missing_file(conn, tmp_path):
    """Loading from missing file returns 0."""
    count = load_rewards_to_db(conn, tmp_path / "nonexistent.yaml")
    assert count == 0


def test_recommend_for_category(conn_with_rewards):
    """Recommend for Food & Dining returns cards sorted by reward rate."""
    results = recommend_for_category(conn_with_rewards, "Food & Dining")
    assert len(results) > 0

    # Best card for Food & Dining should be chase (3%) or better
    rates = [r["reward_rate"] for r in results]
    assert rates == sorted(rates, reverse=True)

    # All results should have required fields
    for r in results:
        assert "card_name" in r
        assert "institution" in r
        assert "reward_rate" in r
        assert "annual_fee" in r


def test_recommend_for_all_category(conn_with_rewards):
    """Recommend for a category with no specific rates falls back to 'all'."""
    results = recommend_for_category(conn_with_rewards, "Home")
    assert len(results) > 0
    # Wells Fargo Active Cash has 2% on all
    wf = [r for r in results if r["institution"] == "wells_fargo"]
    assert len(wf) > 0
    assert wf[0]["reward_rate"] == 2.0


def test_optimize_past_spending(conn_with_rewards):
    """Optimize identifies missed reward opportunities."""
    today = date.today()
    this_month = today.replace(day=15)

    # Insert transactions: food spending on wells_fargo (2% all) instead of chase (3% food)
    conn_with_rewards.execute(
        """INSERT INTO transactions
           (id, txn_fingerprint, institution, account_type, card_name,
            transaction_date, post_date, description, description_clean,
            amount, transaction_type, original_category, unified_category,
            unified_subcategory, source_file, location)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ["t1", "fp1", "wells_fargo", "credit_card", None, this_month, None,
         "RESTAURANT", "RESTAURANT", 100.00, "purchase", "Food",
         "Food & Dining", "Restaurants", "file.csv", None],
    )

    results = optimize_past_spending(conn_with_rewards, months=1)
    assert len(results) > 0

    food_result = [r for r in results if r["category"] == "Food & Dining"]
    assert len(food_result) == 1
    assert food_result[0]["missed_rewards"] > 0
    assert food_result[0]["amount_spent"] == 100.00
