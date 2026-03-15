"""Ingestion pipeline — scan, parse, deduplicate, store."""

from hashlib import sha256
from pathlib import Path

import duckdb

from fin_insights import db
from fin_insights.categories import load_category_mappings
from fin_insights.config import get_statements_dir
from fin_insights.profile import load_all_profiles, match_profile, parse_csv_with_profile

# Supported file extensions
CSV_EXTENSIONS = {".csv"}
PDF_EXTENSIONS = {".pdf"}


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

    # Collect all CSV and PDF files
    all_files = []
    for ext in ("*.csv", "*.CSV", "*.pdf", "*.PDF"):
        all_files.extend(statements_dir.rglob(ext))

    # Deduplicate (case-insensitive filesystems)
    seen_paths = set()
    unique_files = []
    for f in sorted(all_files):
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
    suffix = file_path.suffix.lower()

    # Check if already processed
    file_hash = _file_hash(file_path)
    existing = db.get_processed_file(conn, rel_path)

    if existing and existing[0] == file_hash:
        return {"file": rel_path, "status": "skipped", "reason": "unchanged"}

    # If hash changed, remove old data
    if existing:
        db.delete_transactions_for_file(conn, rel_path)

    if suffix in CSV_EXTENSIONS:
        return _process_csv(file_path, rel_path, file_hash, profiles, category_mappings, conn)
    elif suffix in PDF_EXTENSIONS:
        return _process_pdf(file_path, rel_path, file_hash, profiles, category_mappings, conn)
    else:
        return {"file": rel_path, "status": "failed", "reason": f"unsupported format: {suffix}"}


def _process_csv(
    file_path: Path,
    rel_path: str,
    file_hash: str,
    profiles: list[dict],
    category_mappings: dict,
    conn: duckdb.DuckDBPyConnection,
) -> dict:
    """Process a CSV file."""
    profile = match_profile(file_path, profiles)
    if not profile:
        return {"file": rel_path, "status": "failed", "reason": "no matching profile"}

    try:
        transactions = parse_csv_with_profile(file_path, profile, category_mappings)
    except Exception as e:
        return {"file": rel_path, "status": "failed", "reason": str(e)}

    return _store_transactions(
        transactions, rel_path, file_hash, profile["institution"],
        profile.get("account_type", "unknown"), "csv", conn,
    )


def _process_pdf(
    file_path: Path,
    rel_path: str,
    file_hash: str,
    profiles: list[dict],
    category_mappings: dict,
    conn: duckdb.DuckDBPyConnection,
) -> dict:
    """Process a PDF file."""
    # Determine institution from parent folder name
    institution = file_path.parent.name.lower().replace(" ", "_")

    # Find matching PDF profile
    pdf_profiles = [
        p for p in profiles
        if p.get("file_type") == "pdf" and p["institution"] == institution
    ]

    if not pdf_profiles:
        return {"file": rel_path, "status": "failed", "reason": f"no PDF profile for {institution}"}

    profile = pdf_profiles[0]

    # Check if pdfplumber is available
    try:
        from fin_insights.pdf_parser import parse_bofa_pdf
    except ImportError:
        return {"file": rel_path, "status": "failed", "reason": "pdfplumber not installed (uv sync --extra pdf)"}

    if institution == "bofa":
        try:
            transactions = parse_bofa_pdf(
                file_path, category_mappings,
                account_type=profile.get("account_type", "credit_card"),
            )
        except Exception as e:
            return {"file": rel_path, "status": "failed", "reason": str(e)}
    else:
        return {"file": rel_path, "status": "failed", "reason": f"PDF parsing not implemented for {institution}"}

    return _store_transactions(
        transactions, rel_path, file_hash, institution,
        profile.get("account_type", "unknown"), "pdf", conn,
    )


def _store_transactions(
    transactions: list,
    rel_path: str,
    file_hash: str,
    institution: str,
    account_type: str,
    file_type: str,
    conn: duckdb.DuckDBPyConnection,
) -> dict:
    """Store parsed transactions and log the file."""
    if not transactions:
        return {"file": rel_path, "status": "failed", "reason": "no transactions parsed"}

    inserted = db.insert_transactions(conn, transactions)
    duplicates = len(transactions) - inserted

    db.log_processed_file(
        conn=conn,
        file_path=rel_path,
        file_hash=file_hash,
        institution=institution,
        file_type=file_type,
        record_count=inserted,
    )

    return {
        "file": rel_path,
        "status": "processed",
        "institution": institution,
        "account_type": account_type,
        "total_parsed": len(transactions),
        "inserted": inserted,
        "duplicates": duplicates,
    }


def _file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return sha256(file_path.read_bytes()).hexdigest()
