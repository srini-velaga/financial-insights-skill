# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal financial insights tool — a Python package (`fin_insights`) and optional CLI (`fin-insights`) that ingests credit card and checking account statements from any bank, normalizes them into a unified DuckDB database, and provides spending analysis, cash flow insights, and card reward optimization.

Distributed as a **Claude Code Skill + Cursor Rules**. The AI agent calls Python functions directly — no CLI parsing needed.

## Architecture

**Profile-based adaptive parser system**: instead of hardcoded parsers per bank, declarative JSON profiles describe each bank's CSV/PDF format. Profiles are matched to files via header fingerprinting (not folder names), so credit card and checking CSVs coexist in the same bank folder. The AI agent auto-generates profiles for unsupported banks by examining file headers.

```
Public repo (this)              User's statement folder (any path)
├── fin_insights/  (package)    ├── bank_a/statement.csv
├── profiles/      (defaults)   ├── bank_b/statement.pdf
├── config/        (templates)  └── .fin-insights/          (auto-created)
├── .claude/skills/                 ├── financial_insights.duckdb
└── .cursor/rules/                  ├── profiles/
                                    └── config/
```

## Build & Run

```bash
uv sync                          # install dependencies (dev)
uv run fin-insights --help        # run CLI
uv run fin-insights ingest        # scan cwd for statements → DuckDB
uv run fin-insights status        # show processed files
uv run fin-insights insights      # spending trends
uv run fin-insights categories    # category breakdown
uv run fin-insights cashflow      # income vs spending
uv run fin-insights recommend     # card reward optimization
uv run fin-insights install-skill # install skill into Claude Code
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
1. `--data-dir` CLI flag or explicit path argument
2. `FIN_INSIGHTS_DATA` env var
3. Current working directory

State (DB, profiles, config) lives in `{data_dir}/.fin-insights/`.

## Conventions

- **Amount sign**: positive = expense/debit, negative = income/credit (normalized regardless of bank convention)
- **Dates**: stored as ISO 8601 (YYYY-MM-DD) in DuckDB, parsed from bank-specific formats via profile config
- **Profile naming**: `{institution}_{account_type}.json` (e.g., `chase_credit.json`, `chase_checking.json`)
- **CLI output**: JSON by default (for agent consumption), `--format table` for human reading
- **Dependencies**: click, duckdb, pdfplumber, pyyaml — keep minimal

## Agent Integration

- **Claude Code**: `.claude/skills/financial-insights/SKILL.md` — describes Python API, profile auto-detection, LLM-assisted PDF parsing
- **Cursor**: `.cursor/rules/financial-insights.md` — same content adapted for Cursor's rules format
- Both instruct the agent to: call Python functions directly → auto-detect new bank formats → run ingest → provide conversational insights
- **Install for end users**: `pip install git+https://github.com/srini-velaga/financial-insights-skill.git && fin-insights install-skill`

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
