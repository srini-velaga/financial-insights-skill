---
name: financial-insights
description: Analyze credit card and bank statements for spending insights, category trends, cash flow analysis, and card reward optimization. Use when user asks about spending, finances, budgeting, statement analysis, or card recommendations.
---

# Financial Insights Skill

You have access to the `fin-insights` CLI tool for personal financial analysis.

## Setup Check

Before using any commands, verify the tool is installed:
```bash
fin-insights --version
```

If not installed, guide the user:
```bash
cd <path-to-financial-insights-skill-repo>
uv sync        # add --extra pdf for PDF statement support
```

## Core Workflow

### 1. Initialize (first time only)
```bash
fin-insights init
```
This creates `~/financial-data/` with `statements/`, `profiles/`, and `config/` subdirectories.

### 2. Ingest statements
```bash
fin-insights ingest
```
Run this whenever the user adds new statement files. It only processes new/modified files.

### 3. Check status
```bash
fin-insights status
```
Shows processed files, transaction counts, and date ranges.

### 4. Analyze spending
```bash
fin-insights insights [--months N]        # trends + top merchants
fin-insights categories [--month YYYY-MM] # category breakdown
fin-insights cashflow [--months N]        # income vs spending
```

### 5. Card recommendations
```bash
fin-insights recommend load                        # load rewards config
fin-insights recommend category "Food & Dining"    # best card for category
fin-insights recommend optimize --months 3         # missed reward opportunities
```

## Handling New Banks

When the user adds statements from a bank without a built-in profile:

1. Read the CSV file's first 5-10 lines to examine headers and sample data
2. Identify: date column(s), description, amount, category (if present)
3. Detect: date format, amount sign convention, delimiter
4. Generate a profile JSON following this structure:
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
6. If the bank only provides PDFs, suggest the user check if CSV export is available — CSV is preferred for accuracy
7. Confirm with the user before saving

## JSON Output for Analysis

Use `--format json` when you need to process the output programmatically:
```bash
fin-insights categories --month 2024-06 --format json
fin-insights insights --months 3 --format json
fin-insights cashflow --format json
```

## Data Directory

The user's data is at `$FIN_INSIGHTS_DATA` (default: `~/financial-data/`). Never commit this data to any repository. Structure:
- `statements/{bank}/` — raw CSV/PDF files
- `profiles/` — agent-generated parser profiles
- `config/card_rewards.yaml` — user's card reward rates
