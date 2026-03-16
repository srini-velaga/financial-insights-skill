---
name: financial-insights
description: Analyze credit card and bank statements for spending insights, category trends, cash flow analysis, and card reward optimization. Use when user asks about spending, finances, budgeting, statement analysis, or card recommendations.
---

# Financial Insights Skill

You have access to the `fin_insights` Python package for personal financial analysis. Use it by importing and calling functions directly — do NOT run CLI commands.

## Setup

### 1. Add the package to your Python path

The `fin_insights` package is bundled with this plugin. Find the plugin's install directory (the directory containing this skill file's parent `skills/` folder) and add it to `sys.path`:

```python
import sys
from pathlib import Path

# Find the plugin root (contains fin_insights/ package)
# Look for fin_insights package in common plugin locations
plugin_candidates = [
    p for p in [
        Path.home() / ".claude" / "plugins" / "financial-insights",
        *Path.home().glob(".claude/plugins/*/financial-insights"),
    ]
    if (p / "fin_insights").is_dir()
]

if plugin_candidates:
    sys.path.insert(0, str(plugin_candidates[0]))
else:
    # Fallback: search for the repo by checking known paths or ask the user
    # You can also check if fin_insights is already importable
    pass

# Ensure duckdb is available
try:
    import duckdb
except ImportError:
    # Install duckdb if needed: pip install duckdb
    pass
```

If the plugin path cannot be auto-detected, ask the user where they cloned the `financial-insights-skill` repo and use that path.

### 2. Initialize data directory (first time only)

```python
from pathlib import Path
from fin_insights.config import get_data_dir, get_statements_dir, get_user_profiles_dir, get_user_config_dir

data_dir = get_data_dir()  # uses FIN_INSIGHTS_DATA env var, or ~/financial-data/
for sub_dir in [get_statements_dir(data_dir), get_user_profiles_dir(data_dir), get_user_config_dir(data_dir)]:
    sub_dir.mkdir(parents=True, exist_ok=True)
```

### 3. Connect to the database

```python
from fin_insights.config import get_data_dir, get_db_path
from fin_insights.db import get_connection

data_dir = get_data_dir()
conn = get_connection(get_db_path(data_dir))
# Always close when done: conn.close()
```

## Ingesting Statements

When the user adds new statement files to `statements/{bank}/`:

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

Example:
```python
data = get_category_breakdown(conn, month="2025-01")
for row in data:
    print(f"{row['category']}: ${row['total']}")
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

**processing_log** table:
- `file_path` VARCHAR, `file_hash` VARCHAR, `institution` VARCHAR
- `file_type` VARCHAR, `record_count` INTEGER, `processed_at` TIMESTAMP

**card_rewards** table:
- `institution` VARCHAR, `card_name` VARCHAR, `reward_type` VARCHAR
- `category` VARCHAR, `reward_rate` DECIMAL(5,2), `annual_fee` DECIMAL(8,2)

### Unified Categories (16)

Food & Dining, Transportation, Travel, Shopping, Bills & Utilities, Entertainment, Health, Home, Insurance & Financial, Business Services, Gifts & Donations, Fees & Adjustments, Payments & Credits, Income, Transfers, ATM & Cash

### Example Queries

```sql
-- Total food spending last month
SELECT ROUND(SUM(amount), 2) FROM transactions
WHERE unified_category = 'Food & Dining' AND amount > 0
  AND transaction_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1' MONTH)
  AND transaction_date < DATE_TRUNC('month', CURRENT_DATE);

-- Top 5 merchants this year
SELECT description_clean, COUNT(*) AS txns, ROUND(SUM(amount), 2) AS total
FROM transactions WHERE amount > 0 AND EXTRACT(YEAR FROM transaction_date) = 2025
GROUP BY 1 ORDER BY 3 DESC LIMIT 5;

-- Monthly spending trend
SELECT DATE_TRUNC('month', transaction_date)::DATE AS month, ROUND(SUM(amount), 2) AS total
FROM transactions WHERE amount > 0
GROUP BY 1 ORDER BY 1 DESC;
```

## Card Reward Optimization

```python
from fin_insights.rewards import load_rewards_to_db, recommend_for_category, optimize_past_spending

# Load rewards config (user edits ~/financial-data/config/card_rewards.yaml)
config_path = data_dir / "config" / "card_rewards.yaml"
load_rewards_to_db(conn, config_path)

# Best card for a category
results = recommend_for_category(conn, "Food & Dining")
# Returns: [{card_name, institution, reward_type, reward_rate, annual_fee}]

# Missed reward opportunities over past N months
missed = optimize_past_spending(conn, months=3)
# Returns: [{category, amount_spent, card_used, earned, optimal_card, optimal_earned, missed_rewards}]
```

## Handling New Banks

When the user adds statements from an unsupported bank:

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
5. Save to `~/financial-data/profiles/{bank_name}_{account_type}.json`
6. Confirm with the user before saving

## Conventions

- **Amount sign**: positive = expense/debit, negative = income/credit
- **Data directory**: `$FIN_INSIGHTS_DATA` env var or `~/financial-data/`
- Never commit user financial data to any repository
- Always close the DuckDB connection when done
