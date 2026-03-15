---
description: "Financial insights CLI tool for analyzing credit card and bank statements, spending trends, cash flow, and card reward optimization"
alwaysApply: false
globs: ["**/fin_insights/**", "**/profiles/**", "**/statements/**"]
---

# Financial Insights Tool

You have access to the `fin-insights` CLI tool for personal financial analysis.

## Commands

- `fin-insights init` — Set up data directory at ~/financial-data/
- `fin-insights ingest` — Parse new/modified statement files into DuckDB
- `fin-insights status` — Show processed files and transaction summary
- `fin-insights insights [--months N]` — Spending trends and top merchants
- `fin-insights categories [--month YYYY-MM]` — Category breakdown
- `fin-insights cashflow [--months N]` — Income vs spending, savings rate
- `fin-insights recommend load` — Load card rewards from YAML config
- `fin-insights recommend category "X"` — Best card for a category
- `fin-insights recommend optimize --months N` — Missed reward opportunities

Add `--format json` to any analytics command for machine-readable output.

## Workflow

1. Always run `ingest` first if the user has added new statements
2. Use `status` to confirm data is current
3. Run analytics commands based on the user's question
4. Interpret the output and provide conversational insights

## New Bank Support

When encountering statements from an unsupported bank:
1. Read the CSV headers and sample rows
2. Identify date, description, amount, and category columns
3. Generate a parser profile JSON and save to ~/financial-data/profiles/
4. If PDF-only, suggest CSV export from the bank's website
5. Confirm the profile with the user before saving

## Data Location

User data is at `$FIN_INSIGHTS_DATA` (default: `~/financial-data/`). This data should never be committed to any repository.
