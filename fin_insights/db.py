"""DuckDB database management."""

from pathlib import Path

import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id                  VARCHAR PRIMARY KEY,
    txn_fingerprint     VARCHAR NOT NULL UNIQUE,
    institution         VARCHAR NOT NULL,
    account_type        VARCHAR NOT NULL,
    card_name           VARCHAR,
    transaction_date    DATE NOT NULL,
    post_date           DATE,
    description         VARCHAR NOT NULL,
    description_clean   VARCHAR,
    amount              DECIMAL(10,2) NOT NULL,
    transaction_type    VARCHAR,
    original_category   VARCHAR,
    unified_category    VARCHAR NOT NULL,
    unified_subcategory VARCHAR,
    source_file         VARCHAR NOT NULL,
    location            VARCHAR,
    ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_log (
    file_path    VARCHAR PRIMARY KEY,
    file_hash    VARCHAR NOT NULL,
    institution  VARCHAR NOT NULL,
    file_type    VARCHAR NOT NULL,
    record_count INTEGER,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_rewards (
    institution  VARCHAR NOT NULL,
    card_name    VARCHAR NOT NULL,
    reward_type  VARCHAR NOT NULL,
    category     VARCHAR NOT NULL,
    reward_rate  DECIMAL(5,2) NOT NULL,
    promo_apr    DECIMAL(5,2),
    promo_end    DATE,
    annual_fee   DECIMAL(8,2) DEFAULT 0,
    PRIMARY KEY (institution, card_name, category)
);
"""


def get_connection(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection and ensure schema exists."""
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_SQL)
    return conn


def insert_transactions(conn: duckdb.DuckDBPyConnection, transactions: list) -> int:
    """Insert transactions, skipping duplicates by fingerprint. Returns count inserted."""
    inserted = 0
    for txn in transactions:
        try:
            conn.execute(
                """INSERT INTO transactions
                   (id, txn_fingerprint, institution, account_type, card_name,
                    transaction_date, post_date, description, description_clean,
                    amount, transaction_type, original_category, unified_category,
                    unified_subcategory, source_file, location)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    txn.id,
                    txn.fingerprint,
                    txn.institution,
                    txn.account_type,
                    txn.card_name,
                    txn.transaction_date,
                    txn.post_date,
                    txn.description,
                    txn.description_clean,
                    txn.amount,
                    txn.transaction_type,
                    txn.original_category,
                    txn.unified_category,
                    txn.unified_subcategory,
                    txn.source_file,
                    txn.location,
                ],
            )
            inserted += 1
        except duckdb.ConstraintException:
            # Duplicate fingerprint — skip silently
            pass
    return inserted


def log_processed_file(
    conn: duckdb.DuckDBPyConnection,
    file_path: str,
    file_hash: str,
    institution: str,
    file_type: str,
    record_count: int,
) -> None:
    """Record a processed file in the processing log."""
    conn.execute(
        """INSERT OR REPLACE INTO processing_log
           (file_path, file_hash, institution, file_type, record_count, processed_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        [file_path, file_hash, institution, file_type, record_count],
    )


def get_processed_file(conn: duckdb.DuckDBPyConnection, file_path: str) -> tuple | None:
    """Get processing log entry for a file. Returns (file_hash,) or None."""
    result = conn.execute(
        "SELECT file_hash FROM processing_log WHERE file_path = ?", [file_path]
    ).fetchone()
    return result


def delete_transactions_for_file(conn: duckdb.DuckDBPyConnection, source_file: str) -> None:
    """Remove all transactions from a specific source file (for re-ingestion)."""
    conn.execute("DELETE FROM transactions WHERE source_file = ?", [source_file])
    conn.execute("DELETE FROM processing_log WHERE file_path = ?", [source_file])
