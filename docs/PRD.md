# Product Requirements Document — Financial Insights Skill

| Field       | Value                                      |
|-------------|--------------------------------------------|
| Status      | Living document                            |
| Version     | 0.1                                        |
| Author      | Srini Velaga                               |
| Last updated | 2026-03-21                                |
| Branch      | `skill-first-architecture`                 |

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [Users](#3-users)
4. [Use Cases](#4-use-cases)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Architecture Overview](#7-architecture-overview)
8. [Data Model](#8-data-model)
9. [Python API Contract](#9-python-api-contract)
10. [CLI Interface](#10-cli-interface)
11. [Parser Profile Spec](#11-parser-profile-spec)
12. [Skill Distribution Model](#12-skill-distribution-model)
13. [Supported Banks](#13-supported-banks)
14. [Out of Scope](#14-out-of-scope)
15. [Open Questions and Future Work](#15-open-questions-and-future-work)
16. [Glossary](#16-glossary)

---

## 1. Problem Statement

Personal finance tools either require you to connect bank accounts via third-party services (privacy risk), or force you through rigid import flows designed for a single bank's export format. Neither approach works well when:

- You have statements from 4+ banks in different CSV/PDF formats
- You care about data privacy and don't want credentials leaving your machine
- You want to ask free-form questions ("how did my grocery spending change this year?") rather than navigate rigid dashboards

**The gap:** there is no lightweight, privacy-first tool that lets you drop a folder of mixed bank statements and immediately ask conversational questions about your finances.

---

## 2. Goals and Non-Goals

### Goals

- **G1 — Privacy-first local analysis.** All data stays on the user's machine. No cloud sync, no account linking, no telemetry.
- **G2 — Zero-config for supported banks.** Statements from Chase, Amex, Discover, Wells Fargo, BofA work without any setup beyond pointing to the folder.
- **G3 — Auto-adapt to new banks.** When the AI agent encounters an unknown CSV format, it reads the headers and generates a reusable parser profile without user intervention.
- **G4 — Conversational interface.** Users ask natural-language questions; Claude ingests, analyzes, and responds — no SQL or configuration required.
- **G5 — Unified view across banks.** Transactions from all banks and account types are normalized into a single schema with a shared category taxonomy.
- **G6 — Card reward optimization.** Given the user's credit cards and their reward rates, identify which card to use for each category to maximize rewards earned.
- **G7 — Easy distribution.** Anyone can install via `pip install git+<repo>` and activate via `fin-insights install-skill`.

### Non-Goals

- **NG1 — Real-time data.** This is not a live feed; it only processes downloaded statement files.
- **NG2 — Budget setting or alerts.** No future budgets, notifications, or goals — pure historical analysis.
- **NG3 — Investment accounts.** Brokerage, 401k, and crypto accounts are out of scope.
- **NG4 — Multi-user or shared state.** Designed for a single person's statements on a single machine.
- **NG5 — Web UI.** The interface is Claude Code (or Cursor). No standalone web app.
- **NG6 — Automatic statement downloads.** Users download their own files; this tool only parses what they provide.

---

## 3. Users

### Primary User: Srini (Owner)

A technically proficient individual who:
- Downloads statements from 4–6 credit cards and 1–2 checking accounts
- Wants to ask spending questions at the end of each month
- Is comfortable with terminal tools but doesn't want to write SQL
- Uses Claude Code as their primary AI coding/productivity tool

### Secondary Users: Contributors and Power Users

Developers who:
- Want to add support for a new bank (write a profile JSON)
- Want to extend the analytics layer (add a new Python function)
- Are familiar with Python, DuckDB, and basic JSON schemas

---

## 4. Use Cases

### UC-1: Monthly Spending Review

> "What did I spend on food and dining in February?"

Agent calls `get_category_breakdown(conn, month="2026-02")`, formats the result as a natural-language summary with dollar amounts and top merchants.

### UC-2: Trend Analysis

> "How has my spending on Transportation changed over the past 6 months?"

Agent calls `get_month_over_month(conn, months=6)`, filters to Transportation, formats as a table with month-over-month percentage changes.

### UC-3: Cash Flow Check

> "Am I spending more than I earn?"

Agent calls `get_cashflow(conn, months=3)`, reports income, spending, net cash flow, and savings rate per month from checking account data.

### UC-4: Top Merchant Discovery

> "Where am I spending the most money?"

Agent calls `get_top_merchants(conn, limit=15)`, presents ranked list with transaction counts and totals.

### UC-5: Card Reward Optimization

> "Which card should I use when buying groceries?"

Agent calls `recommend_for_category(conn, "Food & Dining")`, returns ranked cards by reward rate. If no rewards config exists, prompts user to fill in `card_rewards.yaml`.

### UC-6: Missed Rewards Audit

> "How much did I leave on the table by not using the right card?"

Agent calls `optimize_past_spending(conn, months=3)`, shows each category where a better card would have earned more, with dollar amounts.

### UC-7: First Ingest — Supported Bank

> User drops `chase_jan_2026.csv` in their statements folder. Agent calls `ingest(data_dir, conn)`. Profile is auto-matched via header fingerprint. 200 transactions inserted, 0 duplicates.

### UC-8: First Ingest — New Bank

> User drops `capital_one_statement.csv`. Agent reads first 10 lines, inspects headers, generates a profile JSON, saves it to `.fin-insights/profiles/capital_one_credit.json`, re-runs ingest.

### UC-9: PDF Statement Parsing

> User drops a BofA PDF statement. Agent uses `pdfplumber` to extract text, reads transaction lines, creates `Transaction` objects, inserts into database.

### UC-10: Incremental Ingest

> User re-runs ingest after adding 3 new files. Already-processed files are skipped (hash match). Only new files are parsed. No duplicate transactions inserted.

---

## 5. Functional Requirements

### 5.1 Ingestion

| ID   | Requirement |
|------|-------------|
| F-01 | The system MUST scan a user-provided directory recursively for `.csv` and `.pdf` files. |
| F-02 | The system MUST skip files inside `.fin-insights/` during scanning. |
| F-03 | The system MUST match each CSV file to a parser profile using header fingerprinting. |
| F-04 | The system MUST skip already-processed files whose SHA-256 hash is unchanged. |
| F-05 | If a file's hash has changed, the system MUST delete its old transactions before re-ingesting. |
| F-06 | The system MUST normalize all amounts to: positive = expense/debit, negative = income/credit. |
| F-07 | The system MUST strip currency symbols (`$`, `,`) from amounts. |
| F-08 | The system MUST parse dates using the format specified in the parser profile. |
| F-09 | The system MUST map institution-specific categories to the 16-category unified taxonomy. |
| F-10 | The ingest function MUST return a summary dict: `files_scanned`, `files_processed`, `files_skipped`, `files_failed`, `transactions_inserted`, `transactions_duplicate`, `details`. |
| F-11 | Unmatched CSV files MUST be reported as `failed` with reason `"no matching profile"`. |
| F-12 | The system MUST support CSV delimiter options (comma, tab, semicolon) per profile. |
| F-13 | The system MUST support `skip_rows` per profile for headers with leading metadata rows. |

### 5.2 Deduplication

| ID   | Requirement |
|------|-------------|
| F-20 | Transaction fingerprints MUST be computed as `SHA-256(date|amount|description_clean|institution|account_type)`. |
| F-21 | Duplicate fingerprints MUST be silently skipped; the count MUST be reported in ingest summary. |
| F-22 | File-level dedup MUST use SHA-256 of the file's full byte content. |

### 5.3 Analytics

| ID   | Requirement |
|------|-------------|
| F-30 | `get_category_breakdown(conn, month, year)` MUST return per-category totals with transaction counts and percentage of total. |
| F-31 | `get_cashflow(conn, months)` MUST return monthly income, spending, net cash flow, and savings rate. |
| F-32 | `get_monthly_spending_by_category(conn, months)` MUST return category totals per calendar month. |
| F-33 | `get_month_over_month(conn, months)` MUST return absolute and percentage change vs. prior month per category. |
| F-34 | `get_top_merchants(conn, limit, months)` MUST return merchants ranked by total spend with transaction count. |
| F-35 | `get_spending_by_card(conn, months)` MUST return spending broken down by institution and category. |
| F-36 | All analytics functions MUST exclude payments, credits, and transfers from expense aggregations (amount > 0 filter). |
| F-37 | All analytics functions MUST support an optional `months` parameter to restrict to the last N calendar months. |

### 5.4 Caching

| ID   | Requirement |
|------|-------------|
| F-40 | All analytics results MUST be cached in the `analysis_cache` table with a data-state hash. |
| F-41 | Cache MUST be invalidated when new transactions are inserted (data-state hash changes). |
| F-42 | Cache hits MUST return immediately without re-querying the transactions table. |

### 5.5 Card Rewards

| ID   | Requirement |
|------|-------------|
| F-50 | `load_rewards_to_db(conn, config_path)` MUST load card reward rates from a YAML file into the `card_rewards` table. |
| F-51 | `recommend_for_category(conn, category)` MUST return cards ranked by reward rate for the given spending category. |
| F-52 | `optimize_past_spending(conn, months)` MUST compare the card actually used against the highest-reward card available for each category, and report missed rewards in dollars. |
| F-53 | Rewards config MUST support both percentage cashback and points/miles with a `reward_type` field. |

### 5.6 Parser Profiles

| ID   | Requirement |
|------|-------------|
| F-60 | Profiles MUST be JSON files with a `header_fingerprint` array for matching. |
| F-61 | The system MUST load profiles from two locations: the package's `profiles/` directory (defaults) and `.fin-insights/profiles/` (user overrides). |
| F-62 | User profiles in `.fin-insights/profiles/` MUST take precedence over package defaults. |
| F-63 | Profiles MUST support split debit/credit columns (`style: "split"`) in addition to single signed-amount columns. |
| F-64 | The AI agent MUST be able to generate and save new profiles for unknown CSV formats. |
| F-65 | Profile filenames MUST follow `{institution}_{account_type}.json` convention. |

### 5.7 PDF Parsing

| ID   | Requirement |
|------|-------------|
| F-70 | PDF text MUST be extracted using `pdfplumber`. |
| F-71 | For known banks (BofA, Chase, Discover, Wells Fargo), built-in regex parsers MUST be available as fallbacks. |
| F-72 | For unknown PDF banks, the AI agent MUST act as the parser: read extracted text and create `Transaction` objects. |
| F-73 | PDF profiles MUST match by institution name (parent folder), not by header fingerprinting. |

### 5.8 CLI

| ID   | Requirement |
|------|-------------|
| F-80 | CLI MUST support commands: `ingest`, `status`, `insights`, `categories`, `cashflow`, `recommend`, `install-skill`. |
| F-81 | CLI output MUST default to JSON (for agent consumption); `--format table` MUST produce human-readable output. |
| F-82 | `install-skill` MUST copy `SKILL.md` to `~/.claude/commands/financial-insights.md`. |
| F-83 | CLI MUST accept `--data-dir` flag to specify the statements folder explicitly. |

### 5.9 Data Directory Resolution

| ID   | Requirement |
|------|-------------|
| F-90 | Data directory MUST be resolved in this priority: (1) explicit argument/flag, (2) `FIN_INSIGHTS_DATA` env var, (3) current working directory. |
| F-91 | All state (database, profiles, config) MUST be stored in `{data_dir}/.fin-insights/`. |
| F-92 | The state directory MUST be auto-created on first access. |

---

## 6. Non-Functional Requirements

### 6.1 Privacy & Security

| ID   | Requirement |
|------|-------------|
| NF-01 | No user financial data MUST ever be committed to this repository. Fixture files MUST use anonymized synthetic data. |
| NF-02 | The database MUST be stored exclusively on the user's local machine. |
| NF-03 | No network calls MUST be made during statement parsing or analysis. |
| NF-04 | SQL queries that incorporate user-controlled parameters MUST use parameterized queries or explicit whitelist validation to prevent injection. |

### 6.2 Performance

| ID   | Requirement |
|------|-------------|
| NF-10 | Ingesting a 500-transaction CSV MUST complete in under 5 seconds on a modern laptop. |
| NF-11 | Analytics queries on a database with 10,000 transactions MUST return results in under 2 seconds. |
| NF-12 | Analysis caching MUST reduce repeat query time to under 100ms for cached results. |

### 6.3 Reliability

| ID   | Requirement |
|------|-------------|
| NF-20 | A parse failure on one file MUST NOT prevent other files from being processed. |
| NF-21 | The ingest function MUST always return a valid summary dict, even if all files fail. |
| NF-22 | Duplicate transaction inserts MUST be silently skipped without crashing. |

### 6.4 Compatibility

| ID   | Requirement |
|------|-------------|
| NF-30 | The package MUST support Python >= 3.10. |
| NF-31 | The package MUST run on macOS, Linux, and Windows (WSL). |
| NF-32 | Core dependencies MUST be limited to: `click`, `duckdb`, `pdfplumber`, `pyyaml`. |

### 6.5 Maintainability

| ID   | Requirement |
|------|-------------|
| NF-40 | Adding support for a new bank's CSV format MUST require only a new JSON profile file — no Python changes. |
| NF-41 | Adding a new analytics function MUST require only a new Python function in `analytics.py` and an entry in the SKILL.md API table. |
| NF-42 | All tests MUST use anonymized fixture data in `tests/fixtures/`. |

---

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Agent (Claude)                       │
│   Reads SKILL.md → imports fin_insights → calls functions   │
└────────────────────────┬────────────────────────────────────┘
                         │ Python function calls
┌────────────────────────▼────────────────────────────────────┐
│                   fin_insights package                      │
│                                                             │
│  config.py     — data dir & path resolution                 │
│  ingest.py     — scan, match, parse, deduplicate, store     │
│  profile.py    — load/match/apply parser profiles           │
│  pdf_parser.py — regex parsers for known PDF banks          │
│  db.py         — DuckDB schema, CRUD, connection            │
│  analytics.py  — query functions + caching                  │
│  rewards.py    — card reward loading & optimization         │
│  session.py    — query caching & session history            │
│  categories.py — unified taxonomy & category mapping        │
│  models.py     — Transaction dataclass + fingerprinting     │
│  cli.py        — optional Click CLI (wraps above)           │
└────────────────────────┬────────────────────────────────────┘
                         │ reads/writes
┌────────────────────────▼────────────────────────────────────┐
│              {data_dir}/.fin-insights/                      │
│                                                             │
│  financial_insights.duckdb   — all persistent state         │
│  profiles/*.json             — user-defined profiles        │
│  config/card_rewards.yaml    — reward rates per card        │
└─────────────────────────────────────────────────────────────┘

Public repo (this)              User's statement folder
├── fin_insights/               ├── chase/jan_2026.csv
├── profiles/   (defaults)      ├── bofa/statement.pdf
├── config/     (templates)     └── .fin-insights/  (auto-created)
├── .claude/skills/
└── .cursor/rules/
```

### Component Responsibilities

| Component       | Responsibility |
|----------------|----------------|
| `config.py`    | Data dir resolution (flag → env → cwd), path helpers |
| `ingest.py`    | Orchestrate scan → match → parse → dedup → store |
| `profile.py`   | Load JSON profiles, match by header fingerprint, parse CSV rows |
| `pdf_parser.py`| Bank-specific regex parsers for BofA, Chase, Discover, Wells Fargo PDFs |
| `db.py`        | DuckDB connection, schema creation, insert/delete/query primitives |
| `analytics.py` | Canned aggregation queries, all with optional time filters |
| `rewards.py`   | YAML config → DB, category recommendation, missed-reward audit |
| `session.py`   | `analysis_cache` read/write, `session_log` for query history |
| `categories.py`| Unified 16-category taxonomy, profile-driven category mapping |
| `models.py`    | `Transaction` dataclass, SHA-256 fingerprint, description cleaning |
| `cli.py`       | Click CLI wrappers, `install-skill` command |

---

## 8. Data Model

### `transactions`

| Column              | Type           | Notes |
|---------------------|----------------|-------|
| `id`                | VARCHAR PK     | UUID |
| `txn_fingerprint`   | VARCHAR UNIQUE | SHA-256 for dedup |
| `institution`       | VARCHAR        | e.g., `"chase"`, `"amex"` |
| `account_type`      | VARCHAR        | `"credit_card"` or `"checking"` |
| `card_name`         | VARCHAR?       | e.g., `"Sapphire Reserve"` |
| `transaction_date`  | DATE           | ISO 8601 |
| `post_date`         | DATE?          | ISO 8601 |
| `description`       | VARCHAR        | Raw merchant string |
| `description_clean` | VARCHAR        | Uppercased, whitespace-normalized |
| `amount`            | DECIMAL(10,2)  | Positive = expense, negative = income |
| `transaction_type`  | VARCHAR?       | `purchase`, `payment`, `deposit`, `transfer`, `fee`, `refund` |
| `original_category` | VARCHAR?       | Bank-assigned category |
| `unified_category`  | VARCHAR        | One of 16 standard categories |
| `unified_subcategory` | VARCHAR?     | Optional sub-label |
| `source_file`       | VARCHAR        | Path to originating file |
| `location`          | VARCHAR?       | City/state if available |
| `ingested_at`       | TIMESTAMP      | Auto-set on insert |

### `processing_log`

| Column         | Type       | Notes |
|----------------|------------|-------|
| `file_path`    | VARCHAR PK | Absolute path |
| `file_hash`    | VARCHAR    | SHA-256 of file contents |
| `institution`  | VARCHAR    |       |
| `file_type`    | VARCHAR    | `"csv"` or `"pdf"` |
| `record_count` | INTEGER    | Transactions inserted |
| `processed_at` | TIMESTAMP  |       |

### `card_rewards`

| Column        | Type           | Notes |
|---------------|----------------|-------|
| `institution` | VARCHAR PK(1)  |       |
| `card_name`   | VARCHAR PK(2)  |       |
| `category`    | VARCHAR PK(3)  | Unified category name or `"all"` |
| `reward_type` | VARCHAR        | `"cashback"`, `"points"`, `"miles"` |
| `reward_rate` | DECIMAL(5,2)   | Percentage (e.g., 3.00 = 3%) |
| `annual_fee`  | DECIMAL(8,2)   | Dollars |

### `analysis_cache`

| Column        | Type      | Notes |
|---------------|-----------|-------|
| `cache_key`   | VARCHAR PK| `"{query_type}:{params}"` |
| `query_type`  | VARCHAR   |       |
| `parameters`  | VARCHAR   | JSON-encoded params |
| `result_json` | VARCHAR   | Serialized result |
| `data_hash`   | VARCHAR   | Hash of transactions table state |
| `computed_at` | TIMESTAMP |       |

### `session_log`

| Column          | Type      | Notes |
|-----------------|-----------|-------|
| `id`            | VARCHAR PK| UUID |
| `query_text`    | VARCHAR   | Natural-language question asked |
| `query_type`    | VARCHAR?  | e.g., `"category_breakdown"` |
| `result_summary`| VARCHAR?  | Short summary of the answer |
| `created_at`    | TIMESTAMP |       |

### Unified Category Taxonomy (16 categories)

| Category                | Examples |
|------------------------|---------|
| Food & Dining          | Restaurants, coffee, groceries |
| Transportation         | Gas, rideshare, parking, tolls |
| Travel                 | Flights, hotels, car rental |
| Shopping               | Retail, online shopping |
| Bills & Utilities      | Phone, internet, electricity |
| Entertainment          | Streaming, events, hobbies |
| Health                 | Doctor, pharmacy, gym |
| Home                   | Furniture, hardware, home services |
| Insurance & Financial  | Insurance premiums, investment fees |
| Business Services      | SaaS tools, professional services |
| Gifts & Donations      | Charity, gifts |
| Fees & Adjustments     | Late fees, bank fees, adjustments |
| Payments & Credits     | Credit card payments, refunds |
| Income                 | Payroll, freelance deposits |
| Transfers              | Between own accounts |
| ATM & Cash             | ATM withdrawals |

---

## 9. Python API Contract

The AI agent imports and calls these functions directly. CLI output is secondary.

### Setup

```python
from fin_insights.config import get_data_dir, get_db_path, ensure_state_dir
from fin_insights.db import get_connection

data_dir = get_data_dir()          # or get_data_dir("/path/to/statements")
ensure_state_dir(data_dir)
conn = get_connection(get_db_path(data_dir))
# Always close: conn.close()
```

### Ingestion

```python
from fin_insights.ingest import ingest

result = ingest(data_dir, conn)
# Returns: {files_scanned, files_processed, files_skipped, files_failed,
#           transactions_inserted, transactions_duplicate, details: [...]}
```

### Analytics

```python
from fin_insights.analytics import (
    get_category_breakdown,       # → [{category, subcategory, total, transactions, percentage}]
    get_cashflow,                 # → [{month, income, spending, net_cashflow, savings_rate}]
    get_monthly_spending_by_category,  # → [{category, month, total}]
    get_month_over_month,         # → [{category, month, total, change, pct_change}]
    get_top_merchants,            # → [{merchant, transactions, total}]
    get_spending_by_card,         # → [{institution, category, total, transactions}]
)
```

All analytics functions accept `conn` as the first argument and an optional `months: int` to restrict to the last N months.

### Card Rewards

```python
from fin_insights.rewards import load_rewards_to_db, recommend_for_category, optimize_past_spending

config_path = data_dir / ".fin-insights" / "config" / "card_rewards.yaml"
load_rewards_to_db(conn, config_path)
recommend_for_category(conn, "Food & Dining")    # → [{card_name, institution, reward_type, reward_rate, annual_fee}]
optimize_past_spending(conn, months=3)            # → [{category, amount_spent, card_used, rate_used, earned, optimal_card, ...}]
```

### Direct SQL

For ad-hoc questions not covered by canned functions:

```python
rows = conn.execute("SELECT ... FROM transactions WHERE ...").fetchall()
```

---

## 10. CLI Interface

The CLI is secondary to the Python API. It exists for quick one-off checks and the `install-skill` command.

```
fin-insights [--data-dir PATH] COMMAND [OPTIONS]

Commands:
  ingest        Scan data-dir for statements and load into DuckDB
  status        Show processing log and transaction count summary
  insights      Spending trends: top categories and merchants
  categories    Category breakdown; --month YYYY-MM or --year YYYY
  cashflow      Monthly income vs spending; --months N
  recommend     Card recommendations; optimize for missed rewards
  install-skill Copy SKILL.md to ~/.claude/commands/
```

Global options:
- `--data-dir PATH` — override the statement folder path
- `--format [json|table]` — output format (default: json)
- `--months N` — restrict to last N months (where applicable)

---

## 11. Parser Profile Spec

Parser profiles are JSON files describing how to read a specific bank's CSV format.

### Required Fields

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `institution`        | string  | Machine-readable bank ID (e.g., `"chase"`) |
| `display_name`       | string  | Human-readable name (e.g., `"Chase"`) |
| `account_type`       | string  | `"credit_card"` or `"checking"` |
| `file_type`          | string  | `"csv"` or `"pdf"` |
| `header_fingerprint` | array   | Expected column headers for CSV matching |
| `columns`            | object  | Maps semantic fields to CSV column names |
| `amount_handling`    | object  | Sign convention and formatting |

### `columns` Object

```json
{
  "transaction_date": { "name": "Date", "format": "%m/%d/%Y" },
  "post_date":        { "name": "Post Date", "format": "%m/%d/%Y" },
  "description":      { "name": "Description" },
  "amount":           { "name": "Amount" },
  "category":         { "name": "Category" }
}
```

### `amount_handling` Object

```json
{
  "style": "single",                      // "single" | "split"
  "sign_convention": "positive_is_charge", // "positive_is_charge" | "negative_is_charge"
  "strip_chars": "$,"                     // characters to remove before parsing
}
```

For split columns (`style: "split"`):
```json
{
  "style": "split",
  "debit_col": "Debit",
  "credit_col": "Credit",
  "strip_chars": "$,"
}
```

### Optional Fields

| Field              | Description |
|--------------------|-------------|
| `delimiter`        | CSV delimiter (default: `","`) |
| `has_header`       | Whether first row is a header (default: `true`) |
| `skip_rows`        | Rows to skip before the header (default: `0`) |
| `encoding`         | File encoding (default: `"utf-8"`) |
| `category_mappings`| Dict mapping bank categories to `[unified_category, subcategory]` |
| `notes`            | Human-readable export instructions for this bank |

### Example

```json
{
  "institution": "chase",
  "display_name": "Chase",
  "account_type": "credit_card",
  "file_type": "csv",
  "delimiter": ",",
  "header_fingerprint": ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"],
  "columns": {
    "transaction_date": { "name": "Transaction Date", "format": "%m/%d/%Y" },
    "description": { "name": "Description" },
    "amount": { "name": "Amount" },
    "category": { "name": "Category" }
  },
  "amount_handling": {
    "style": "single",
    "sign_convention": "negative_is_charge",
    "strip_chars": "$,"
  },
  "category_mappings": {
    "Food & Drink": ["Food & Dining", "General"]
  },
  "notes": "Export from chase.com > Activity > Download account activity. Select CSV."
}
```

---

## 12. Skill Distribution Model

The tool is distributed as a **Claude Code Skill** (and Cursor Rules). This means:

1. Users install the Python package: `pip install git+https://github.com/srini-velaga/financial-insights-skill.git`
2. Users run `fin-insights install-skill`, which copies `SKILL.md` to `~/.claude/commands/financial-insights.md`
3. When the user asks a financial question in Claude Code, the skill activates and guides Claude to import and call Python functions directly

### Why skill-first (not CLI-first)?

The AI agent calling Python functions directly produces richer, more flexible output than parsing CLI JSON. The agent can combine multiple function calls, apply judgment about what's relevant, and format answers conversationally.

### Skill file locations

| File | Purpose |
|------|---------|
| `.claude/skills/financial-insights/SKILL.md` | Canonical skill definition (this repo) |
| `fin_insights/skill_data/SKILL.md` | Packaged copy (distributed via pip) |
| `~/.claude/commands/financial-insights.md` | Installed location (after `install-skill`) |
| `.cursor/rules/financial-insights.md` | Cursor IDE equivalent |

---

## 13. Supported Banks

### Built-in Profiles (v0.1)

| Profile file              | Bank            | Type           | Format | Key Quirk |
|---------------------------|-----------------|----------------|--------|-----------|
| `amex_credit.json`        | American Express| Credit card    | CSV    | 11 columns, "Parent-Sub" categories, multi-line Extended Details |
| `chase_credit.json`       | Chase           | Credit card    | CSV    | Negative = charge, `Type` field for sale/payment |
| `chase_checking.json`     | Chase           | Checking       | CSV    | `Details` column distinguishes DEBIT/CREDIT |
| `discover_credit.json`    | Discover        | Credit card    | CSV    | Positive = charge, single-level category |
| `wells_fargo_credit.json` | Wells Fargo     | Credit card    | CSV    | `$`-prefixed amounts, dual category columns |
| `bofa_credit.json`        | Bank of America | Credit card    | PDF    | PDF-only, keyword-based categories |
| `bofa_checking.json`      | Bank of America | Checking       | PDF/CSV| Two-column amount format in PDF |

### Adding New Banks

- **CSV**: Create a profile JSON in `.fin-insights/profiles/` with the correct `header_fingerprint`. No code changes required.
- **PDF**: The AI agent reads extracted text and creates `Transaction` objects directly. For recurring use, a profile JSON with `file_type: "pdf"` signals PDF format; the agent handles parsing.

---

## 14. Out of Scope

These items are explicitly not in scope for v0.1:

- Real-time or live bank connections (Plaid, open banking APIs)
- Push notifications or spending alerts
- Future budget planning or spending goals
- Investment account tracking (brokerage, 401k, crypto)
- Multi-user support or shared/synced databases
- Web or mobile UI
- Automatic statement downloads
- Tax categorization or export (TurboTax, etc.)
- Currency conversion for foreign-currency transactions
- Custom subcategory definitions by user

---

## 15. Open Questions and Future Work

### Open Questions

| ID  | Question | Status |
|-----|----------|--------|
| OQ-1 | Should the unified category taxonomy be user-configurable, or is 16 fixed categories sufficient? | Open |
| OQ-2 | For PDF parsing, should we build a more structured extraction pipeline (table detection via pdfplumber) vs. relying on LLM text reading? | Open |
| OQ-3 | How should multi-page PDFs be handled when transaction data spans pages? | Partially addressed via `pdfplumber` multi-page iteration |
| OQ-4 | Should `card_rewards.yaml` support multiplier rules (e.g., 5x on first $1500/quarter)? | Open |
| OQ-5 | Should the skill work in Cursor's agent mode via the `.cursor/rules/` file the same way it does in Claude Code? | Needs validation |

### Future Work (Post v0.1)

| Priority | Feature |
|----------|---------|
| High | Chase PDF credit card statement parser |
| High | Amex PDF statement parser |
| High | Capital One CSV profile (popular bank without built-in support) |
| Medium | `get_anomalies()` — flag unusual spending vs. personal baseline |
| Medium | `get_recurring_charges()` — detect subscription and recurring payments |
| Medium | `export_to_csv(conn, output_path)` — export normalized transactions |
| Medium | GitHub Actions CI with test coverage enforcement |
| Low | Citi, US Bank, TD Bank profiles |
| Low | `get_year_over_year()` — compare same months across years |
| Low | CLI `--format csv` output option |
| Low | Homebrew tap for easier install on macOS |

---

## 16. Glossary

| Term | Definition |
|------|-----------|
| **Profile** | A JSON file describing how to parse a specific bank's CSV/PDF format. Matched to files via header fingerprinting. |
| **Header fingerprint** | An array of expected column names used to identify which profile matches a CSV file. |
| **Unified category** | One of 16 standardized spending categories applied to all transactions regardless of bank. |
| **Data directory** | The folder containing the user's bank statement files. Specified by the user or defaults to cwd. |
| **State directory** | `.fin-insights/` inside the data directory. Contains the DuckDB file, user profiles, and config. |
| **Ingest** | The process of scanning statement files, parsing transactions, deduplicating, and storing in DuckDB. |
| **Fingerprint** | SHA-256 hash of `date|amount|description_clean|institution|account_type`. Used to detect duplicate transactions across overlapping statements. |
| **Skill** | A Claude Code plugin defined by a Markdown file with frontmatter. The `financial-insights` skill tells Claude how to use the `fin_insights` Python package. |
| **LLM-assisted parsing** | Using Claude itself to read PDF text and extract transactions when no regex parser exists — more robust than regex for variable-format PDFs. |
| **Analysis cache** | DuckDB table storing serialized query results keyed by query type + parameters + data state hash. Invalidated on new ingest. |
| **Session log** | DuckDB table recording natural-language questions and their answers within a conversation session, preventing repeated work. |
