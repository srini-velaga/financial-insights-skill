---
description: "Financial insights Python API for analyzing credit card and bank statements, spending trends, cash flow, and card reward optimization"
alwaysApply: false
globs: ["**/fin_insights/**", "**/profiles/**", "**/*.csv", "**/*.pdf"]
---

# Financial Insights Tool

You have access to the `fin_insights` Python package for personal financial analysis. Use it by importing and calling functions directly — do NOT run CLI commands.

## Setup

```python
from pathlib import Path
from fin_insights.config import get_data_dir, get_db_path, ensure_state_dir
from fin_insights.db import get_connection

# Ask user for statement folder, or use current directory
data_dir = get_data_dir()  # defaults to cwd; pass a path to override
ensure_state_dir(data_dir)
conn = get_connection(get_db_path(data_dir))
```

If not installed: `pip install git+https://github.com/srini-velaga/financial-insights-skill.git`

## Ingesting Statements

```python
from fin_insights.ingest import ingest
result = ingest(data_dir, conn)
# result keys: files_scanned, files_processed, transactions_inserted, etc.
```

## Analytics Functions

Import from `fin_insights.analytics`:

| Function | Parameters | Returns |
|----------|-----------|---------|
| `get_category_breakdown(conn, month=None, year=None)` | `month`: "YYYY-MM", `year`: "YYYY" | `[{category, subcategory, total, transactions, percentage}]` |
| `get_cashflow(conn, months=None)` | `months`: last N months | `[{month, income, spending, net_cashflow, savings_rate}]` |
| `get_monthly_spending_by_category(conn, months=None)` | `months`: int | `[{category, month, total}]` |
| `get_month_over_month(conn, months=None)` | `months`: int | `[{category, month, total, change, pct_change}]` |
| `get_top_merchants(conn, limit=10, months=None)` | `limit`: int, `months`: int | `[{merchant, transactions, total}]` |
| `get_spending_by_card(conn, months=None)` | `months`: int | `[{institution, category, total, transactions}]` |

All analytics functions are cached automatically. Cache invalidates when new data is ingested.

## Ad-hoc DuckDB Queries

```python
conn.execute("SELECT ... FROM transactions WHERE ...").fetchall()
```

**transactions** table: `transaction_date` DATE, `description` VARCHAR, `description_clean` VARCHAR, `amount` DECIMAL(10,2) (positive=expense, negative=income), `institution` VARCHAR, `account_type` VARCHAR, `unified_category` VARCHAR, `unified_subcategory` VARCHAR

**Unified Categories (16):** Food & Dining, Transportation, Travel, Shopping, Bills & Utilities, Entertainment, Health, Home, Insurance & Financial, Business Services, Gifts & Donations, Fees & Adjustments, Payments & Credits, Income, Transfers, ATM & Cash

## Card Rewards

```python
from fin_insights.rewards import load_rewards_to_db, recommend_for_category, optimize_past_spending
config_path = data_dir / ".fin-insights" / "config" / "card_rewards.yaml"
load_rewards_to_db(conn, config_path)
results = recommend_for_category(conn, "Food & Dining")
missed = optimize_past_spending(conn, months=3)
```

## New Bank Support

For CSVs: read headers, generate a profile JSON, save to `{data_dir}/.fin-insights/profiles/`.
For PDFs: extract text with `pdfplumber`, identify patterns, parse transactions manually, insert with `fin_insights.db.insert_transactions()`.

## Data Location

State lives in `{data_dir}/.fin-insights/`. User provides their statement folder path. Never commit financial data to any repository. Always close the DuckDB connection when done.
