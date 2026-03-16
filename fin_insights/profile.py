"""Parser profile system — declarative JSON profiles drive CSV/PDF parsing."""

import csv
import json
import logging
from datetime import datetime
from io import StringIO
from pathlib import Path

from fin_insights.categories import map_category
from fin_insights.config import get_builtin_profiles_dir, get_user_profiles_dir
from fin_insights.models import Transaction

logger = logging.getLogger(__name__)


def load_all_profiles(data_dir: Path) -> list[dict]:
    """Load all profiles from built-in and user directories. User profiles override built-in."""
    profiles = {}

    # Load built-in profiles
    builtin_dir = get_builtin_profiles_dir()
    if builtin_dir.exists():
        for p in builtin_dir.glob("*.json"):
            profile = json.loads(p.read_text())
            key = f"{profile['institution']}_{profile.get('account_type', 'unknown')}"
            profiles[key] = profile

    # User profiles override
    user_dir = get_user_profiles_dir(data_dir)
    if user_dir.exists():
        for p in user_dir.glob("*.json"):
            profile = json.loads(p.read_text())
            key = f"{profile['institution']}_{profile.get('account_type', 'unknown')}"
            profiles[key] = profile

    return list(profiles.values())


def match_profile(file_path: Path, profiles: list[dict]) -> dict | None:
    """Match a CSV file to a profile using header fingerprinting.

    Reads the first line (header) and checks against each profile's
    header_fingerprint array. Returns the best matching profile or None.
    """
    if file_path.suffix.lower() not in (".csv",):
        return None

    try:
        header_line = _read_header(file_path)
    except Exception as e:
        logger.warning("Failed to read header from %s: %s", file_path, e)
        return None

    if not header_line:
        return None

    # Parse header columns
    reader = csv.reader(StringIO(header_line))
    try:
        headers = [h.strip() for h in next(reader)]
    except StopIteration:
        return None

    best_match = None
    best_score = 0

    for profile in profiles:
        if profile.get("file_type", "csv") != "csv":
            continue

        fingerprint = profile.get("header_fingerprint", [])
        if not fingerprint:
            continue

        # Score: how many fingerprint columns are found in the file headers
        score = sum(1 for fp_col in fingerprint if fp_col in headers)

        # Require all fingerprint columns to match
        if score == len(fingerprint) and score > best_score:
            best_score = score
            best_match = profile

    return best_match


def _read_header(file_path: Path) -> str | None:
    """Read the header line from a CSV file, respecting skip_rows."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.readline().strip()


def parse_csv_with_profile(
    file_path: Path,
    profile: dict,
    category_mappings: dict,
) -> list[Transaction]:
    """Parse a CSV file using a profile's column definitions."""
    columns = profile["columns"]
    amount_handling = profile.get("amount_handling", {})
    institution = profile["institution"]
    account_type = profile.get("account_type", "credit_card")
    skip_rows = profile.get("skip_rows", 0)
    delimiter = profile.get("delimiter", ",")
    encoding = profile.get("encoding", "utf-8")
    profile_cat_mappings = profile.get("category_mappings")

    transactions = []

    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        # Skip leading rows if needed
        for _ in range(skip_rows):
            next(f, None)

        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            try:
                txn = _parse_row(
                    row=row,
                    columns=columns,
                    amount_handling=amount_handling,
                    institution=institution,
                    account_type=account_type,
                    profile_cat_mappings=profile_cat_mappings,
                    category_mappings=category_mappings,
                    source_file=str(file_path),
                )
                if txn:
                    transactions.append(txn)
            except Exception as e:
                logger.debug("Skipping unparseable row in %s: %s", file_path, e)
                continue

    return transactions


def _parse_row(
    row: dict,
    columns: dict,
    amount_handling: dict,
    institution: str,
    account_type: str,
    profile_cat_mappings: dict | None,
    category_mappings: dict,
    source_file: str,
) -> Transaction | None:
    """Parse a single CSV row into a Transaction using profile config."""
    # Transaction date (required)
    date_cfg = columns.get("transaction_date", {})
    date_str = _get_col(row, date_cfg.get("name"))
    if not date_str:
        return None
    txn_date = _parse_date(date_str, date_cfg.get("format", "%m/%d/%Y"))
    if not txn_date:
        return None

    # Post date (optional)
    post_date = None
    post_cfg = columns.get("post_date", {})
    if post_cfg.get("name"):
        post_str = _get_col(row, post_cfg["name"])
        if post_str:
            post_date = _parse_date(post_str, post_cfg.get("format", "%m/%d/%Y"))

    # Description (required)
    desc_cfg = columns.get("description", {})
    description = _get_col(row, desc_cfg.get("name"))
    if not description:
        return None

    # Amount
    amount = _parse_amount(row, columns, amount_handling)
    if amount is None:
        return None

    # Transaction type
    txn_type = None
    type_cfg = columns.get("transaction_type", {})
    if type_cfg.get("name"):
        txn_type = _get_col(row, type_cfg["name"])

    # Infer transaction type from amount if not provided
    if not txn_type:
        if amount < 0:
            txn_type = "payment" if account_type == "credit_card" else "deposit"
        else:
            txn_type = "purchase"

    # Category
    original_category = None
    cat_cfg = columns.get("category", {})
    if cat_cfg.get("name"):
        original_category = _get_col(row, cat_cfg["name"])

    # For profiles with dual category columns (e.g., Wells Fargo)
    subcat_cfg = columns.get("subcategory", {})
    original_subcat = None
    if subcat_cfg.get("name"):
        original_subcat = _get_col(row, subcat_cfg["name"])
        if original_category and original_subcat:
            # Combine for mapping lookup: "Master|Sub"
            combined_cat = f"{original_category}|{original_subcat}"
        else:
            combined_cat = original_category
    else:
        combined_cat = original_category

    unified_cat, unified_subcat = map_category(
        institution=institution,
        original_category=combined_cat,
        profile_mappings=profile_cat_mappings,
        global_mappings=category_mappings,
        description=description,
    )

    # Location (optional)
    location = None
    loc_cfg = columns.get("location", {})
    if loc_cfg.get("name"):
        location = _get_col(row, loc_cfg["name"])

    # Card name (optional)
    card_name = None
    card_cfg = columns.get("card_name", {})
    if card_cfg.get("name"):
        card_name = _get_col(row, card_cfg["name"])

    return Transaction(
        institution=institution,
        account_type=account_type,
        transaction_date=txn_date,
        description=description,
        amount=amount,
        unified_category=unified_cat,
        source_file=source_file,
        card_name=card_name,
        post_date=post_date,
        transaction_type=txn_type,
        original_category=original_category or combined_cat,
        unified_subcategory=unified_subcat,
        location=location,
    )


def _get_col(row: dict, col_name: str | None) -> str | None:
    """Get a column value from a row, returning None if empty."""
    if not col_name:
        return None
    val = row.get(col_name, "").strip()
    return val if val else None


def _parse_date(date_str: str, fmt: str) -> "datetime.date | None":
    """Parse a date string with the given format."""
    try:
        return datetime.strptime(date_str.strip(), fmt).date()
    except (ValueError, AttributeError):
        return None


def _parse_amount(row: dict, columns: dict, amount_handling: dict) -> float | None:
    """Parse amount from a row using the profile's amount handling config."""
    style = amount_handling.get("style", "single")
    strip_chars = amount_handling.get("strip_chars", "")
    sign_convention = amount_handling.get("sign_convention", "positive_is_charge")

    if style == "split":
        # Separate debit/credit columns
        debit_col = amount_handling.get("debit_column") or columns.get("amount", {}).get("name")
        credit_col = amount_handling.get("credit_column") or columns.get("credit", {}).get("name")

        debit_str = row.get(debit_col, "").strip() if debit_col else ""
        credit_str = row.get(credit_col, "").strip() if credit_col else ""

        debit = _clean_amount(debit_str, strip_chars)
        credit = _clean_amount(credit_str, strip_chars)

        if debit is not None:
            return abs(debit)  # positive = expense
        elif credit is not None:
            return -abs(credit)  # negative = income/credit
        return None
    else:
        # Single amount column
        amt_cfg = columns.get("amount", {})
        amt_str = row.get(amt_cfg.get("name", "Amount"), "").strip()
        amount = _clean_amount(amt_str, strip_chars)
        if amount is None:
            return None

        # Normalize sign convention to: positive=expense, negative=income
        if sign_convention == "negative_is_charge":
            return -amount  # flip: bank's negative charge → our positive expense
        elif sign_convention == "positive_is_charge":
            return amount
        else:
            return amount


def _clean_amount(amount_str: str, strip_chars: str = "") -> float | None:
    """Clean and parse an amount string."""
    if not amount_str:
        return None
    cleaned = amount_str
    for ch in strip_chars:
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
