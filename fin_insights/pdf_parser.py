"""PDF statement parser using pdfplumber and text pattern matching."""

import re
from datetime import datetime
from pathlib import Path

from fin_insights.categories import map_category
from fin_insights.models import Transaction

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# BofA transaction line pattern: MM/DD MM/DD DESCRIPTION REFNUM ACCTNUM AMOUNT
BOFA_TXN_PATTERN = re.compile(
    r"^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+(\d{4})\s+(\d{4})\s+([-]?\d+\.\d{2})$"
)

# Statement period pattern to extract year
BOFA_PERIOD_PATTERN = re.compile(
    r"(\w+ \d{1,2})\s*[-–]\s*(\w+ \d{1,2},?\s*\d{4})"
)


def parse_bofa_pdf(
    file_path: Path,
    category_mappings: dict,
    account_type: str = "credit_card",
) -> list[Transaction]:
    """Parse a Bank of America PDF statement."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing. Install with: uv sync --extra pdf")

    pdf = pdfplumber.open(str(file_path))
    year = _extract_year(pdf)
    transactions = []

    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        current_section = None
        for line in text.split("\n"):
            line = line.strip()

            # Track section headers
            if "Payments and Other Credits" in line:
                current_section = "credits"
                continue
            elif "Purchases and Adjustments" in line:
                current_section = "purchases"
                continue
            elif "Interest Charged" in line:
                current_section = "interest"
                continue
            elif line.startswith("TOTAL ") or line.startswith("2024 Totals"):
                continue

            match = BOFA_TXN_PATTERN.match(line)
            if not match:
                continue

            txn_date_str, post_date_str, description, _, _, amount_str = match.groups()

            try:
                txn_date = datetime.strptime(f"{txn_date_str}/{year}", "%m/%d/%Y").date()
                post_date = datetime.strptime(f"{post_date_str}/{year}", "%m/%d/%Y").date()
            except ValueError:
                continue

            amount = float(amount_str)

            # Determine transaction type
            if current_section == "credits" or amount < 0:
                txn_type = "payment" if account_type == "credit_card" else "deposit"
                # For credit card: negative = credit/payment, keep as-is
                # For purchases: positive = charge
            elif current_section == "interest":
                txn_type = "fee"
            else:
                txn_type = "purchase"

            # BofA has no categories — use keyword fallback
            unified_cat, unified_subcat = map_category(
                institution="bofa",
                original_category=None,
                profile_mappings=None,
                global_mappings=category_mappings,
                description=description,
            )

            transactions.append(
                Transaction(
                    institution="bofa",
                    account_type=account_type,
                    transaction_date=txn_date,
                    description=description,
                    amount=amount,
                    unified_category=unified_cat,
                    source_file=str(file_path),
                    post_date=post_date,
                    transaction_type=txn_type,
                    original_category=current_section,
                    unified_subcategory=unified_subcat,
                )
            )

    pdf.close()
    return transactions


def _extract_year(pdf) -> int:
    """Extract the statement year from the first page."""
    text = pdf.pages[0].extract_text() or ""
    match = BOFA_PERIOD_PATTERN.search(text)
    if match:
        date_str = match.group(2).replace(",", "").strip()
        # Try parsing "June 15 2024" format
        for fmt in ["%B %d %Y", "%b %d %Y"]:
            try:
                return datetime.strptime(date_str, fmt).year
            except ValueError:
                continue
    # Fallback: look for 4-digit year
    year_match = re.search(r"20\d{2}", text)
    if year_match:
        return int(year_match.group())
    return datetime.now().year
