"""Tests for the ingestion pipeline."""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from fin_insights.config import get_db_path
from fin_insights.db import get_connection
from fin_insights.ingest import ingest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def data_dir(tmp_path):
    """Set up a temporary data directory with sample statements."""
    # Copy fixtures into institution folders (directly in data_dir, no statements/ subdir)
    for name, folder in [
        ("sample_chase_credit.csv", "chase"),
        ("sample_amex_credit.csv", "amex"),
        ("sample_discover_credit.csv", "discover"),
        ("sample_wells_fargo_credit.csv", "wells_fargo"),
    ]:
        dest = tmp_path / folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURES / name, dest / name)

    return tmp_path


@pytest.fixture
def db_conn(data_dir):
    conn = get_connection(get_db_path(data_dir))
    yield conn
    conn.close()


def test_ingest_all_files(data_dir, db_conn):
    """Ingest all sample CSVs and verify transaction counts."""
    result = ingest(data_dir, db_conn)

    assert result["files_scanned"] == 4
    assert result["files_processed"] == 4
    assert result["files_failed"] == 0
    assert result["transactions_inserted"] > 0


def test_ingest_idempotent(data_dir, db_conn):
    """Running ingest twice doesn't duplicate data."""
    result1 = ingest(data_dir, db_conn)
    first_count = result1["transactions_inserted"]

    result2 = ingest(data_dir, db_conn)
    assert result2["files_skipped"] == 4
    assert result2["transactions_inserted"] == 0

    total = db_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert total == first_count


def test_ingest_dedup_across_files(data_dir, db_conn):
    """Duplicate transactions from a second copy are deduplicated."""
    # First ingest
    ingest(data_dir, db_conn)
    count_after_first = db_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    # Copy the same Chase CSV with a different name
    src = data_dir / "chase" / "sample_chase_credit.csv"
    dst = data_dir / "chase" / "sample_chase_credit_copy.csv"
    shutil.copy2(src, dst)

    result = ingest(data_dir, db_conn)

    # The copy should be processed but transactions should be duplicates
    assert result["files_processed"] == 1
    assert result["transactions_duplicate"] > 0

    count_after_second = db_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert count_after_second == count_after_first


def test_ingest_chase_amounts_positive(data_dir, db_conn):
    """Chase negative amounts (charges) are normalized to positive."""
    ingest(data_dir, db_conn)

    purchases = db_conn.execute(
        "SELECT amount FROM transactions WHERE institution = 'chase' AND transaction_type = 'purchase'"
    ).fetchall()

    for (amount,) in purchases:
        assert amount > 0, f"Chase purchase should be positive, got {amount}"


def test_ingest_wells_fargo_strips_dollar(data_dir, db_conn):
    """Wells Fargo $-prefixed amounts are parsed correctly."""
    ingest(data_dir, db_conn)

    amounts = db_conn.execute(
        "SELECT amount FROM transactions WHERE institution = 'wells_fargo'"
    ).fetchall()

    assert len(amounts) > 0
    for (amount,) in amounts:
        assert isinstance(amount, (int, float, Decimal))


def test_ingest_categories_mapped(data_dir, db_conn):
    """Verify categories are mapped to unified taxonomy."""
    ingest(data_dir, db_conn)

    categories = db_conn.execute(
        "SELECT DISTINCT unified_category FROM transactions"
    ).fetchall()
    cat_names = {r[0] for r in categories}

    assert "Food & Dining" in cat_names


def test_processing_log_populated(data_dir, db_conn):
    """Verify processing log tracks all files."""
    ingest(data_dir, db_conn)

    log = db_conn.execute("SELECT COUNT(*) FROM processing_log").fetchone()[0]
    assert log == 4
