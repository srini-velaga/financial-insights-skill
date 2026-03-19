---
name: financial-insights
description: Analyze credit card and bank statements for spending insights, category trends, cash flow analysis, and card reward optimization. Use when user asks about spending, finances, budgeting, statement analysis, or card recommendations.
---

# Financial Insights Skill

You have access to the `fin_insights` Python package for personal financial analysis. Use it by importing and calling functions directly — do NOT run CLI commands.

## Setup

```python
from pathlib import Path
from fin_insights.config import get_data_dir, get_db_path, ensure_state_dir
from fin_insights.db import get_connection

# Ask user for their statement folder, or use current directory
# Example: data_dir = get_data_dir("/Users/me/bank-statements")
data_dir = get_data_dir()  # defaults to cwd; pass a path to override
ensure_state_dir(data_dir)
conn = get_connection(get_db_path(data_dir))
# Always close when done: conn.close()
```

If `fin_insights` is not importable, the user needs to install:
```
pip install git+https://github.com/srini-velaga/financial-insights-skill.git
```

**First-time setup:** Ask the user where their bank statements are. They can provide any local folder path. The database and state are stored in `.fin-insights/` inside that folder.

## Ingesting Statements

Scans the data directory recursively for CSV/PDF files (skips `.fin-insights/`):

```python
from fin_insights.ingest import ingest

result = ingest(data_dir, conn)
# result keys: files_scanned, files_processed, files_skipped, files_failed,
#              transactions_inserted, transactions_duplicate, details
```

## Analytics Functions

Import from `fin_insights.analytics`:

```python
from fin_insights.analytics import (
    get_category_breakdown,
    get_cashflow,
    get_monthly_spending_by_category,
    get_month_over_month,
    get_top_merchants,
    get_spending_by_card,
)
```

| Function | Parameters | Returns |
|----------|-----------|---------|
| `get_category_breakdown(conn, month=None, year=None)` | `month`: "YYYY-MM", `year`: "YYYY" | `[{category, subcategory, total, transactions, percentage}]` |
| `get_cashflow(conn, months=None)` | `months`: int, last N months | `[{month, income, spending, net_cashflow, savings_rate}]` |
| `get_monthly_spending_by_category(conn, months=None)` | `months`: int | `[{category, month, total}]` |
| `get_month_over_month(conn, months=None)` | `months`: int | `[{category, month, total, change, pct_change}]` |
| `get_top_merchants(conn, limit=10, months=None)` | `limit`: int, `months`: int | `[{merchant, transactions, total}]` |
| `get_spending_by_card(conn, months=None)` | `months`: int | `[{institution, category, total, transactions}]` |

All analytics functions are automatically cached. Results are invalidated when new data is ingested.

## Session History

Before running a query, check if it was already answered:

```python
from fin_insights.session import get_recent_queries, log_query

# Check what was already analyzed
recent = get_recent_queries(conn, limit=10)

# After answering a question, log it
log_query(conn, "What did I spend on food in January?", "category_breakdown", "Food & Dining: $342.50")
```

## Ad-hoc DuckDB Queries

For questions that don't map to a canned function, query the database directly:

```python
conn.execute("SELECT ... FROM transactions WHERE ...").fetchall()
```

### Schema

**transactions** table:
- `transaction_date` DATE, `post_date` DATE
- `description` VARCHAR, `description_clean` VARCHAR
- `amount` DECIMAL(10,2) — positive = expense, negative = income/credit
- `institution` VARCHAR, `account_type` VARCHAR ("credit_card" / "checking")
- `unified_category` VARCHAR, `unified_subcategory` VARCHAR
- `original_category` VARCHAR, `source_file` VARCHAR, `location` VARCHAR

**Unified Categories (16):** Food & Dining, Transportation, Travel, Shopping, Bills & Utilities, Entertainment, Health, Home, Insurance & Financial, Business Services, Gifts & Donations, Fees & Adjustments, Payments & Credits, Income, Transfers, ATM & Cash

## Card Reward Optimization

```python
from fin_insights.rewards import load_rewards_to_db, recommend_for_category, optimize_past_spending

config_path = data_dir / ".fin-insights" / "config" / "card_rewards.yaml"
load_rewards_to_db(conn, config_path)
results = recommend_for_category(conn, "Food & Dining")
missed = optimize_past_spending(conn, months=3)
```

## Handling New Banks (CSV)

When encountering statements from an unsupported bank:

1. Read the CSV's first 5-10 lines to examine headers and sample data
2. Identify: date column(s), description, amount, category (if present)
3. Detect: date format, amount sign convention, delimiter
4. Generate a profile JSON:
```json
{
  "institution": "bank_name",
  "display_name": "Bank Name",
  "account_type": "credit_card",
  "file_type": "csv",
  "delimiter": ",",
  "has_header": true,
  "skip_rows": 0,
  "encoding": "utf-8",
  "header_fingerprint": ["Col1", "Col2", "Col3"],
  "columns": {
    "transaction_date": { "name": "Date Column", "format": "%m/%d/%Y" },
    "description": { "name": "Description Column" },
    "amount": { "name": "Amount Column" }
  },
  "amount_handling": {
    "style": "single",
    "sign_convention": "positive_is_charge",
    "strip_chars": "$,"
  },
  "category_mappings": {}
}
```
5. Save to `{data_dir}/.fin-insights/profiles/{bank_name}_{account_type}.json`
6. Confirm with the user before saving

## Handling PDFs (LLM-Assisted)

For PDF bank statements, YOU are the parser. Do not rely on automated PDF parsing for unknown banks.

1. Extract text from the PDF:
```python
import pdfplumber
pdf = pdfplumber.open(str(pdf_path))
text = "\n".join(page.extract_text() or "" for page in pdf.pages)
pdf.close()
```

2. Read the extracted text and identify:
   - Transaction line pattern (date, description, amount positions)
   - Statement period / close date (for year inference)
   - Section headers (purchases, payments, fees)
   - Amount sign convention

3. Parse transactions from the text and create Transaction objects:
```python
from fin_insights.models import Transaction
from fin_insights.categories import map_category
from fin_insights.categories import load_category_mappings

category_mappings = load_category_mappings(data_dir)

txn = Transaction(
    institution="bank_name",
    account_type="credit_card",
    transaction_date=date_obj,
    description="MERCHANT NAME",
    amount=42.50,  # positive=expense, negative=income
    unified_category="Food & Dining",
    source_file=str(pdf_path),
)
```

4. Insert into the database:
```python
from fin_insights.db import insert_transactions
inserted = insert_transactions(conn, transactions)
```

For known banks (BofA, Chase, Discover, Wells Fargo), built-in regex parsers exist as fallback in `fin_insights.pdf_parser`.

## Conventions

- **Amount sign**: positive = expense/debit, negative = income/credit
- **Data directory**: User-provided path or current working directory
- **State directory**: `{data_dir}/.fin-insights/` — contains DB, profiles, config
- Never commit user financial data to any repository
- Always close the DuckDB connection when done
