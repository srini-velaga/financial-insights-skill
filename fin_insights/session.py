"""Session logging and analysis caching."""

import json
import uuid
from hashlib import sha256

import duckdb


def data_state_hash(conn: duckdb.DuckDBPyConnection) -> str:
    """Compute a fingerprint of the current data state.

    Changes when transactions are inserted or files are re-ingested.
    """
    row = conn.execute(
        "SELECT COUNT(*), MAX(ingested_at) FROM transactions"
    ).fetchone()
    count = row[0] or 0
    max_ts = str(row[1] or "")
    return sha256(f"{count}|{max_ts}".encode()).hexdigest()[:16]


def get_cached(conn: duckdb.DuckDBPyConnection, cache_key: str) -> list | dict | None:
    """Return cached result if data hasn't changed since it was computed."""
    current_hash = data_state_hash(conn)
    row = conn.execute(
        "SELECT result_json FROM analysis_cache WHERE cache_key = ? AND data_hash = ?",
        [cache_key, current_hash],
    ).fetchone()
    if row:
        return json.loads(row[0])
    return None


def set_cached(
    conn: duckdb.DuckDBPyConnection,
    cache_key: str,
    query_type: str,
    parameters: dict | None,
    result: list | dict,
) -> None:
    """Store a query result in the cache."""
    current_hash = data_state_hash(conn)
    conn.execute(
        """INSERT OR REPLACE INTO analysis_cache
           (cache_key, query_type, parameters, result_json, data_hash, computed_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        [
            cache_key,
            query_type,
            json.dumps(parameters) if parameters else None,
            json.dumps(result, default=str),
            current_hash,
        ],
    )


def cached_query(
    conn: duckdb.DuckDBPyConnection,
    cache_key: str,
    query_type: str,
    parameters: dict | None,
    query_fn,
) -> list | dict:
    """Execute query_fn with caching. Returns cached result if data is unchanged."""
    cached = get_cached(conn, cache_key)
    if cached is not None:
        return cached
    result = query_fn()
    set_cached(conn, cache_key, query_type, parameters, result)
    return result


def log_query(
    conn: duckdb.DuckDBPyConnection,
    query_text: str,
    query_type: str | None = None,
    result_summary: str | None = None,
) -> None:
    """Record a query in the session log."""
    conn.execute(
        """INSERT INTO session_log (id, query_text, query_type, result_summary, created_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        [str(uuid.uuid4()), query_text, query_type, result_summary],
    )


def get_recent_queries(
    conn: duckdb.DuckDBPyConnection, limit: int = 20
) -> list[dict]:
    """Return recent queries from the session log."""
    rows = conn.execute(
        "SELECT query_text, query_type, result_summary, created_at "
        "FROM session_log ORDER BY created_at DESC LIMIT ?",
        [limit],
    ).fetchall()
    return [
        {"query": r[0], "type": r[1], "summary": r[2], "time": str(r[3])}
        for r in rows
    ]


def get_analyzed_months(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Return distinct months that have been queried in the session log."""
    rows = conn.execute(
        """SELECT DISTINCT
               REGEXP_EXTRACT(parameters, '"month":\\s*"(\\d{4}-\\d{2})"', 1) AS m
           FROM analysis_cache
           WHERE m IS NOT NULL AND m != ''
           ORDER BY m DESC"""
    ).fetchall()
    return [r[0] for r in rows]
