---
description: "Financial insights Python API for analyzing credit card and bank statements, spending trends, cash flow, and card reward optimization"
alwaysApply: false
globs: ["**/fin_insights/**", "**/profiles/**", "**/statements/**"]
---

# Financial Insights Tool

You have access to the `fin_insights` Python package for personal financial analysis. Use it by importing and calling functions directly — do NOT run CLI commands.

## Setup

```python
import sys
sys.path.insert(0, "<path-to-financial-insights-skill-repo>")

from fin_insights.config import get_data_dir, get_db_path
from fin_insights.db import get_connection

data_dir = get_data_dir()  # uses FIN_INSIGHTS_DATA env var, or ~/financial-data/
conn = get_connection(get_db_path(data_dir))
```

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

## Ad-hoc DuckDB Queries

For questions that don't map to a canned function, query the database directly:

```python
conn.execute("SELECT ... FROM transactions WHERE ...").fetchall()
```

**transactions** table: `transaction_date` DATE, `description` VARCHAR, `description_clean` VARCHAR, `amount` DECIMAL(10,2) (positive=expense, negative=income), `institution` VARCHAR, `account_type` VARCHAR, `unified_category` VARCHAR, `unified_subcategory` VARCHAR

**Unified Categories (16):** Food & Dining, Transportation, Travel, Shopping, Bills & Utilities, Entertainment, Health, Home, Insurance & Financial, Business Services, Gifts & Donations, Fees & Adjustments, Payments & Credits, Income, Transfers, ATM & Cash

## Card Rewards

```python
from fin_insights.rewards import load_rewards_to_db, recommend_for_category, optimize_past_spending
config_path = data_dir / "config" / "card_rewards.yaml"
load_rewards_to_db(conn, config_path)
results = recommend_for_category(conn, "Food & Dining")
missed = optimize_past_spending(conn, months=3)
```

## New Bank Support

When encountering statements from an unsupported bank:
1. Read the CSV headers and sample rows
2. Identify date, description, amount, and category columns
3. Generate a parser profile JSON and save to ~/financial-data/profiles/
4. Confirm the profile with the user before saving

## Data Location

User data is at `$FIN_INSIGHTS_DATA` (default: `~/financial-data/`). This data should never be committed to any repository. Always close the DuckDB connection when done.
