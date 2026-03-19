# Financial Insights Skill

AI-powered personal financial statement analyzer. Drop your bank statements in a folder, open Claude Code, and ask natural language questions about your spending — no configuration needed.

## How It Works

1. Put your bank statement CSVs/PDFs in any folder (flat or organized by bank subfolder)
2. Install the skill and open Claude Code in that folder (or provide the path when asked)
3. Ask questions — Claude ingests, normalizes, and analyzes your data on demand

The skill automatically:
- Detects your bank format using header fingerprinting — no setup for supported banks
- Generates parser profiles for unsupported banks by reading your file headers
- Parses and normalizes transactions into a local DuckDB database
- Caches analysis results; invalidates automatically when new data is ingested
- Tracks session history to avoid re-running the same queries
- Extracts PDF statements using LLM-assisted text parsing

All state (database, profiles, config) is stored in `.fin-insights/` inside your statements folder. Nothing leaves your machine.

## Install

```bash
pip install git+https://github.com/srini-velaga/financial-insights-skill.git
fin-insights install-skill    # copies skill to ~/.claude/commands/
```

Then open Claude Code in your statements folder and ask anything:

```
"What did I spend on food last month?"
"Show me my top merchants this year"
"Which credit card should I use for groceries?"
"Ingest my new Chase statement"
"How does my spending compare month over month?"
```

## Supported Banks (Built-in Profiles)

| Bank | CSV | PDF |
|------|:---:|:---:|
| American Express | Credit | — |
| Chase | Credit + Checking | Credit + Checking |
| Discover | Credit | Credit |
| Wells Fargo | Credit | Credit |
| Bank of America | — | Credit + Checking |

Any other bank is supported via auto-detection: the skill reads your file headers and generates a reusable profile.

## Architecture

```
Your statements folder/
├── chase/statement_jan.csv
├── bofa/statement.pdf
└── .fin-insights/               ← auto-created on first ingest
    ├── financial_insights.duckdb
    ├── profiles/                ← auto-generated profiles for new banks
    └── config/                  ← card rewards config (optional)
```

- **Profile-based CSV parsing** — declarative JSON profiles match files via header fingerprinting, not folder names
- **LLM-assisted PDF parsing** — Claude reads PDF text directly; no fragile regex required for new banks
- **Two-layer deduplication** — file-level SHA-256 hash + per-transaction fingerprint prevent duplicates
- **Analysis caching** — results cached in DuckDB, invalidated when data changes
- **Session history** — queries logged so Claude doesn't repeat work within a session

## Alternative: Clone & Use Directly

```bash
git clone https://github.com/srini-velaga/financial-insights-skill.git
cd financial-insights-skill
uv sync
fin-insights install-skill
```

## CLI (Optional)

```bash
fin-insights ingest                      # scan cwd for statements → DuckDB
fin-insights status                      # show processed files and DB summary
fin-insights insights --months 3         # spending trends + top merchants
fin-insights categories --month 2025-01  # category breakdown
fin-insights cashflow                    # income vs spending
fin-insights recommend optimize          # missed reward opportunities
fin-insights install-skill               # install skill into Claude Code
```

## Agent Integration

Distributed as a **Claude Code Skill** (`.claude/skills/financial-insights/SKILL.md`) and **Cursor Rules** (`.cursor/rules/financial-insights.md`). The agent imports `fin_insights` Python functions directly — no CLI output parsing needed.
