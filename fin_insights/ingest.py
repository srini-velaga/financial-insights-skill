"""Ingestion pipeline — scan, parse, deduplicate, store."""

from hashlib import sha256
from pathlib import Path

import duckdb

from fin_insights import db
from fin_insights.categories import load_category_mappings
from fin_insights.config import get_statements_dir
from fin_insights.profile import load_all_profiles, match_profile, parse_csv_with_profile


def ingest(data_dir: Path, conn: duckdb.DuckDBPyConnection) -> dict:
    """Run the full ingestion pipeline.

    Returns a summary dict with counts of files processed and transactions inserted.
    """
    statements_dir = get_statements_dir(data_dir)
    if not statements_dir.exists():
        return {"error": f"Statements directory not found: {statements_dir}"}

    profiles = load_all_profiles(data_dir)
    if not profiles:
        return {"error": "No parser profiles found. Add profiles to get started."}

    category_mappings = load_category_mappings(data_dir)

    summary = {
        "files_scanned": 0,
        "files_processed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "transactions_inserted": 0,
        "transactions_duplicate": 0,
        "details": [],
    }

    # Walk all subdirectories for CSV files
    csv_files = sorted(statements_dir.rglob("*.csv")) + sorted(statements_dir.rglob("*.CSV"))
    # Deduplicate (case-insensitive filesystems)
    seen_paths = set()
    unique_files = []
    for f in csv_files:
        resolved = f.resolve()
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            unique_files.append(f)

    for file_path in unique_files:
        summary["files_scanned"] += 1
        result = _process_file(file_path, profiles, category_mappings, conn)
        summary["details"].append(result)

        if result["status"] == "processed":
            summary["files_processed"] += 1
            summary["transactions_inserted"] += result["inserted"]
            summary["transactions_duplicate"] += result["duplicates"]
        elif result["status"] == "skipped":
            summary["files_skipped"] += 1
        elif result["status"] == "failed":
            summary["files_failed"] += 1

    return summary


def _process_file(
    file_path: Path,
    profiles: list[dict],
    category_mappings: dict,
    conn: duckdb.DuckDBPyConnection,
) -> dict:
    """Process a single file. Returns a result dict."""
    rel_path = str(file_path)

    # Check if already processed
    file_hash = _file_hash(file_path)
    existing = db.get_processed_file(conn, rel_path)

    if existing and existing[0] == file_hash:
        return {"file": rel_path, "status": "skipped", "reason": "unchanged"}

    # If hash changed, remove old data
    if existing:
        db.delete_transactions_for_file(conn, rel_path)

    # Match profile
    profile = match_profile(file_path, profiles)
    if not profile:
        return {"file": rel_path, "status": "failed", "reason": "no matching profile"}

    # Parse
    try:
        transactions = parse_csv_with_profile(file_path, profile, category_mappings)
    except Exception as e:
        return {"file": rel_path, "status": "failed", "reason": str(e)}

    if not transactions:
        return {"file": rel_path, "status": "failed", "reason": "no transactions parsed"}

    # Store
    inserted = db.insert_transactions(conn, transactions)
    duplicates = len(transactions) - inserted

    # Log
    db.log_processed_file(
        conn=conn,
        file_path=rel_path,
        file_hash=file_hash,
        institution=profile["institution"],
        file_type="csv",
        record_count=inserted,
    )

    return {
        "file": rel_path,
        "status": "processed",
        "institution": profile["institution"],
        "account_type": profile.get("account_type", "unknown"),
        "total_parsed": len(transactions),
        "inserted": inserted,
        "duplicates": duplicates,
    }


def _file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return sha256(file_path.read_bytes()).hexdigest()
