# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal financial insights tool — a Python CLI (`fin-insights`) that ingests credit card and checking account statements from any bank, normalizes them into a unified DuckDB database, and provides spending analysis, cash flow insights, and card reward optimization.

Distributed as a **Claude Code Skill + Cursor Rules** so any AI agent can orchestrate the CLI.

## Architecture

**Profile-based adaptive parser system**: instead of hardcoded parsers per bank, declarative JSON profiles describe each bank's CSV/PDF format. Profiles are matched to files via header fingerprinting (not folder names), so credit card and checking CSVs coexist in the same bank folder. The AI agent auto-generates profiles for unsupported banks by examining file headers.

```
Public repo (this)              User's private data (~FIN_INSIGHTS_DATA)
├── fin_insights/  (CLI)        ├── statements/{bank}/  (CSVs/PDFs)
├── profiles/      (defaults)   ├── profiles/           (user/agent-generated)
├── config/        (templates)  ├── config/             (user's rewards YAML)
├── .claude/skills/             └── financial_insights.duckdb
└── .cursor/rules/
```

## Build & Run

```bash
uv sync                          # install dependencies
uv run fin-insights --help        # run CLI
uv run fin-insights init          # create user data directory
uv run fin-insights ingest        # parse statements → DuckDB
uv run fin-insights status        # show processed files
uv run fin-insights insights      # spending trends
uv run fin-insights categories    # category breakdown
uv run fin-insights cashflow      # income vs spending
uv run fin-insights recommend     # card reward optimization
```

## Testing

```bash
uv run pytest                     # run all tests
uv run pytest tests/test_profile.py -k test_header_matching  # single test
```

Tests use anonymized fixture data in `tests/fixtures/`. Never use real financial data in tests.

## Key Technical Decisions

### Database: DuckDB
Single-file, OLAP-optimized. Chosen because the workload is analytical (aggregations by month/category). Database lives in the user's data directory, never in this repo.

### Parser Profiles (`profiles/*.json`)
Each profile has a `header_fingerprint` array — the ingest engine reads a CSV's header row and matches against all profiles. A bank can have multiple profiles (credit card vs checking) differentiated by their distinct column headers.

Profile schema key fields:
- `institution`, `account_type` ("credit_card" / "checking")
- `header_fingerprint` — array of expected column headers for matching
- `columns` — maps semantic fields (transaction_date, amount, category) to CSV column names
- `amount_handling` — sign convention, split debit/credit columns, `$` stripping
- `category_mappings` — institution categories → unified taxonomy

### Deduplication (Two Layers)
1. **File level**: `processing_log` table tracks files by path + SHA-256 hash
2. **Transaction level**: `txn_fingerprint = SHA-256(date|amount|description_clean|institution|account_type)` as UNIQUE constraint

### Unified Category Taxonomy (16 categories)
Food & Dining, Transportation, Travel, Shopping, Bills & Utilities, Entertainment, Health, Home, Insurance & Financial, Business Services, Gifts & Donations, Fees & Adjustments, Payments & Credits, Income, Transfers, ATM & Cash

### Data Directory Resolution
1. `--data-dir` CLI flag
2. `FIN_INSIGHTS_DATA` env var
3. `~/financial-data/`

## Conventions

- **Amount sign**: positive = expense/debit, negative = income/credit (normalized regardless of bank convention)
- **Dates**: stored as ISO 8601 (YYYY-MM-DD) in DuckDB, parsed from bank-specific formats via profile config
- **Profile naming**: `{institution}_{account_type}.json` (e.g., `chase_credit.json`, `chase_checking.json`)
- **CLI output**: JSON by default (for agent consumption), `--format table` for human reading
- **Dependencies**: click, duckdb, pdfplumber, pyyaml — keep minimal

## Agent Integration

- **Claude Code**: `.claude/skills/financial-insights/SKILL.md` — describes workflow, CLI commands, profile auto-detection
- **Cursor**: `.cursor/rules/financial-insights.md` — same content adapted for Cursor's rules format
- Both instruct the agent to: check for profiles → auto-detect new bank formats → run ingest → provide conversational insights

## Shipped Default Profiles

| Profile | Bank | Type | Key Quirks |
|---------|------|------|------------|
| `amex_credit.json` | Amex | Credit | 11-col CSV, multi-line Extended Details, "Parent-Sub" categories |
| `chase_credit.json` | Chase | Credit | negative=charge, Type field for sale/payment |
| `chase_checking.json` | Chase | Checking | Details col for DEBIT/CREDIT |
| `discover_credit.json` | Discover | Credit | positive=charge, single-level category |
| `wells_fargo_credit.json` | Wells Fargo | Credit | $-prefixed amounts, dual category columns |
| `bofa_credit.json` | BofA | Credit | PDF-only, keyword-based categories |
| `bofa_checking.json` | BofA | Checking | PDF or CSV |
