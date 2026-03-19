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
# BofA year-end: MM/DD/YY DESCRIPTION LOCATION AMOUNT
BOFA_YEAREND_TXN_PATTERN = re.compile(
    r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+\S+\s+([\d,]+\.\d{2})$"
)

# Statement period pattern to extract year
BOFA_PERIOD_PATTERN = re.compile(
    r"(\w+ \d{1,2})\s*[-–]\s*(\w+ \d{1,2},?\s*\d{4})"
)

# Chase checking: close date from "throughMonth DD, YYYY" (no space after "through" in PDF)
CHASE_CLOSE_PATTERN = re.compile(r"through\s*(\w+)\s+\d{1,2},?\s*(\d{4})")

# Discover: close date is the SECOND date in "MM/DD/YYYY -MM/DD/YYYY"
DISCOVER_CLOSE_PATTERN = re.compile(r"\d{2}/\d{2}/\d{4}\s*[-–]\s*(\d{2}/\d{2}/(\d{4}))")

# Wells Fargo: close date from "Statement Period MM/DD/YYYY to MM/DD/YYYY"
WF_CLOSE_PATTERN = re.compile(r"Statement Period\s+\S+\s+to\s+(\d{2}/\d{2}/(\d{4}))")

# Known Discover categories for extraction from PDF lines
DISCOVER_CATEGORIES = {
    "Supermarkets", "Restaurants", "Merchandise", "Gasoline",
    "Services", "Education", "Interest", "Fees", "Warehouse Clubs",
    "Medical Services", "Travel/ Entertainment", "Payments and Credits",
    "Awards and Rebate Credits", "Home Improvement", "Department Stores",
    "Automotive", "Sporting Goods", "Drug Stores", "Pet Supplies",
}


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


def _assign_year(month: int, close_month: int, close_year: int) -> int:
    """Assign year to a transaction: if month > close_month it's from the prior year."""
    if month > close_month:
        return close_year - 1
    return close_year


def _all_text(pdf) -> str:
    """Concatenate extracted text from all pages."""
    parts = []
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _parse_decimal(s: str) -> float | None:
    """Parse a decimal string like '1,234.56' or '-1,234.56'."""
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_chase_checking_pdf(
    file_path: Path,
    category_mappings: dict,
) -> list[Transaction]:
    """Parse a Chase College Checking PDF statement."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing.")

    pdf = pdfplumber.open(str(file_path))
    text = _all_text(pdf)
    pdf.close()

    # Extract close month/year from "through Month DD, YYYY"
    close_match = CHASE_CLOSE_PATTERN.search(text)
    if close_match:
        try:
            close_month = datetime.strptime(close_match.group(1)[:3], "%b").month
        except ValueError:
            close_month = 12
        close_year = int(close_match.group(2))
    else:
        year_m = re.search(r"20\d{2}", text)
        close_year = int(year_m.group()) if year_m else datetime.now().year
        close_month = 12

    # Detect account type from PDF content
    is_checking = "CHECKING" in text.upper()
    account_type = "checking" if is_checking else "credit_card"

    transactions = []
    for line in text.splitlines():
        line = line.strip()
        parts = line.split()
        if len(parts) < 3:
            continue
        if not re.match(r"^\d{2}/\d{2}$", parts[0]):
            continue
        if not re.match(r"^-?[\d,]+\.\d{2}$", parts[-1]):
            continue

        date_str = parts[0]

        # Checking: last two tokens are amount + running balance
        # Credit card: last token is amount (no balance column)
        if (is_checking and len(parts) >= 4 and
                re.match(r"^-?[\d,]+\.\d{2}$", parts[-2])):
            amount = _parse_decimal(parts[-2])
            description = " ".join(parts[1:-2])
        else:
            amount = _parse_decimal(parts[-1])
            description = " ".join(parts[1:-1])

        if amount is None or not description:
            continue

        month = int(date_str.split("/")[0])
        year = _assign_year(month, close_month, close_year)
        try:
            txn_date = datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
        except ValueError:
            continue

        if is_checking:
            # Bank: positive=deposit, negative=withdrawal → flip for our convention
            normalized = -amount
            txn_type = "deposit" if amount > 0 else "withdrawal"
        else:
            # Credit card: negative=payment, positive=charge
            normalized = amount  # already: negative=payment, positive=charge
            txn_type = "payment" if amount < 0 else "purchase"

        unified_cat, unified_subcat = map_category(
            institution="chase",
            original_category=None,
            profile_mappings=None,
            global_mappings=category_mappings,
            description=description,
        )
        transactions.append(Transaction(
            institution="chase",
            account_type=account_type,
            transaction_date=txn_date,
            description=description,
            amount=normalized,
            unified_category=unified_cat,
            source_file=str(file_path),
            transaction_type=txn_type,
            unified_subcategory=unified_subcat,
        ))

    return transactions


def parse_discover_pdf(
    file_path: Path,
    category_mappings: dict,
) -> list[Transaction]:
    """Parse a Discover credit card PDF statement."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing.")

    pdf = pdfplumber.open(str(file_path))
    text = _all_text(pdf)
    pdf.close()

    # Extract close month/year from second date in "MM/DD/YYYY -MM/DD/YYYY"
    close_match = DISCOVER_CLOSE_PATTERN.search(text)
    if close_match:
        close_date_str = close_match.group(1)   # MM/DD/YYYY (close date)
        close_year = int(close_match.group(2))
        close_month = int(close_date_str.split("/")[0])  # MM/DD/YYYY → index 0 is month
    else:
        year_m = re.search(r"20\d{2}", text)
        close_year = int(year_m.group()) if year_m else datetime.now().year
        close_month = 12

    transactions = []
    for line in text.splitlines():
        line = line.strip()
        parts = line.split()
        if len(parts) < 3:
            continue
        if not re.match(r"^\d{2}/\d{2}$", parts[0]):
            continue

        date_str = parts[0]

        # Find the rightmost $X.XX or -$X.XX token (ignore trailing cashback noise)
        amount_idx = None
        for i in range(len(parts) - 1, 0, -1):
            if re.match(r"^-?\$[\d,]+\.\d{2}$", parts[i]):
                amount_idx = i
                break
        if amount_idx is None:
            continue

        amount_str = parts[amount_idx]
        is_credit = amount_str.startswith("-")
        amount_val = _parse_decimal(amount_str.replace("$", ""))
        if amount_val is None:
            continue

        desc_tokens = parts[1:amount_idx]

        # Try to extract Discover category from the end of description
        original_category = None
        description = " ".join(desc_tokens)
        for n in range(min(4, len(desc_tokens)), 0, -1):
            candidate = " ".join(desc_tokens[-n:])
            if candidate in DISCOVER_CATEGORIES:
                original_category = candidate
                description = " ".join(desc_tokens[:-n]).strip()
                break

        if not description:
            continue

        month = int(date_str.split("/")[0])
        year = _assign_year(month, close_month, close_year)
        try:
            txn_date = datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
        except ValueError:
            continue

        # Our convention: positive=expense, negative=credit/payment
        if is_credit:
            normalized = -abs(amount_val)
            txn_type = "payment"
        else:
            normalized = abs(amount_val)
            txn_type = "purchase"

        unified_cat, unified_subcat = map_category(
            institution="discover",
            original_category=original_category,
            profile_mappings=None,
            global_mappings=category_mappings,
            description=description,
        )
        transactions.append(Transaction(
            institution="discover",
            account_type="credit_card",
            transaction_date=txn_date,
            description=description,
            amount=normalized,
            unified_category=unified_cat,
            source_file=str(file_path),
            transaction_type=txn_type,
            original_category=original_category,
            unified_subcategory=unified_subcat,
        ))

    return transactions


def parse_wells_fargo_pdf(
    file_path: Path,
    category_mappings: dict,
) -> list[Transaction]:
    """Parse a Wells Fargo credit card PDF statement."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing.")

    pdf = pdfplumber.open(str(file_path))
    text = _all_text(pdf)
    pdf.close()

    # Extract close month/year from "Statement Period ... to MM/DD/YYYY"
    close_match = WF_CLOSE_PATTERN.search(text)
    if close_match:
        close_date_str = close_match.group(1)
        close_year = int(close_match.group(2))
        close_month = int(close_date_str.split("/")[0])
    else:
        year_m = re.search(r"20\d{2}", text)
        close_year = int(year_m.group()) if year_m else datetime.now().year
        close_month = 12

    # Track section: "payments" or "purchases"
    section = None
    transactions = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Section detection
        lower = line.lower()
        if lower.startswith("payments"):
            section = "payments"
            continue
        if "purchases, balance transfers" in lower or lower.startswith("purchases"):
            section = "purchases"
            continue
        if lower.startswith("fees charged") or lower.startswith("interest charged"):
            section = None
            continue
        if lower.startswith("total ") or lower.startswith("notice") or line.startswith("-"):
            continue

        if section is None:
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        date_str = None
        description = None
        amount = None

        if section == "payments":
            # Format: MM/DD MM/DD REF DESC AMOUNT
            if (re.match(r"^\d{2}/\d{2}$", parts[0]) and
                    re.match(r"^\d{2}/\d{2}$", parts[1]) and
                    re.match(r"^[\d,]+\.\d{2}$", parts[-1])):
                date_str = parts[0]
                amount = -_parse_decimal(parts[-1])  # credit → negative
                description = " ".join(parts[3:-1])
        elif section == "purchases":
            # Format: CARD# MM/DD MM/DD REF DESC AMOUNT
            if (re.match(r"^\d{4}$", parts[0]) and
                    re.match(r"^\d{2}/\d{2}$", parts[1]) and
                    re.match(r"^\d{2}/\d{2}$", parts[2]) and
                    re.match(r"^[\d,]+\.\d{2}$", parts[-1])):
                date_str = parts[1]
                amount = _parse_decimal(parts[-1])  # charge → positive
                description = " ".join(parts[4:-1])

        if date_str is None or amount is None or not description:
            continue

        month = int(date_str.split("/")[0])
        year = _assign_year(month, close_month, close_year)
        try:
            txn_date = datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
        except ValueError:
            continue

        txn_type = "payment" if section == "payments" else "purchase"

        unified_cat, unified_subcat = map_category(
            institution="wells_fargo",
            original_category=None,
            profile_mappings=None,
            global_mappings=category_mappings,
            description=description,
        )
        transactions.append(Transaction(
            institution="wells_fargo",
            account_type="credit_card",
            transaction_date=txn_date,
            description=description,
            amount=amount,
            unified_category=unified_cat,
            source_file=str(file_path),
            transaction_type=txn_type,
            unified_subcategory=unified_subcat,
        ))

    return transactions


def parse_bofa_yearend_pdf(
    file_path: Path,
    category_mappings: dict,
) -> list[Transaction]:
    """Parse a Bank of America year-end summary PDF."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing.")

    pdf = pdfplumber.open(str(file_path))
    text = _all_text(pdf)
    pdf.close()

    # Extract year from "between January 1, YYYY"
    year_m = re.search(r"January 1,\s*(\d{4})", text)
    year = int(year_m.group(1)) if year_m else datetime.now().year

    in_txn_section = False
    transactions = []

    for line in text.splitlines():
        line = line.strip()
        if "Date Description" in line and "Amount" in line:
            in_txn_section = True
            continue
        if not in_txn_section:
            continue
        if line.startswith("Thank you") or line.startswith("Written disputes"):
            break

        parts = line.split()
        if len(parts) < 3:
            continue
        # Date format: MM/DD/YY
        if not re.match(r"^\d{2}/\d{2}/\d{2}$", parts[0]):
            continue
        if not re.match(r"^[\d,]+\.\d{2}$", parts[-1]):
            continue

        date_str = parts[0]
        amount = _parse_decimal(parts[-1])
        if amount is None:
            continue
        description = " ".join(parts[1:-2]) if len(parts) > 3 else parts[1]

        try:
            txn_date = datetime.strptime(f"{date_str}", "%m/%d/%y").date()
        except ValueError:
            continue

        unified_cat, unified_subcat = map_category(
            institution="bofa",
            original_category=None,
            profile_mappings=None,
            global_mappings=category_mappings,
            description=description,
        )
        transactions.append(Transaction(
            institution="bofa",
            account_type="credit_card",
            transaction_date=txn_date,
            description=description,
            amount=amount,
            unified_category=unified_cat,
            source_file=str(file_path),
            transaction_type="purchase",
            unified_subcategory=unified_subcat,
        ))

    return transactions
