# Financial Insights Skill

AI-powered personal financial statement analyzer. Ingests credit card and checking account statements from any bank, normalizes them into a unified database, and provides spending insights, cash flow analysis, and card reward optimization.

## Install

```bash
pip install git+https://github.com/srini-velaga/financial-insights-skill.git
fin-insights install-skill    # adds the skill to Claude Code
```

## Usage

1. Put your bank statement CSVs/PDFs in a folder (organized by bank subfolder or flat)
2. Open Claude Code in that folder (or provide the path when prompted)
3. Ask natural language questions:
   - "What did I spend on food last month?"
   - "Show me my top merchants this year"
   - "Which credit card should I use for groceries?"
   - "Ingest my new Chase statement"

The skill automatically:
- Detects your bank format using header fingerprinting
- Parses and normalizes transactions into DuckDB
- Caches analysis results (invalidates when new data is ingested)
- Tracks session history to avoid repeating work

All state is stored in `.fin-insights/` inside your statements folder.

## Supported Banks (Built-in Profiles)

| Bank | Credit Card | Checking |
|------|:-----------:|:--------:|
| American Express | CSV | — |
| Chase | CSV + PDF | CSV + PDF |
| Discover | CSV + PDF | — |
| Wells Fargo | CSV + PDF | — |
| Bank of America | PDF | PDF |

Any other bank works via auto-detection: the AI agent reads your file headers and generates a parser profile.

## Alternative: Clone & Use Directly

```bash
git clone https://github.com/srini-velaga/financial-insights-skill.git
cd financial-insights-skill
uv sync
# The skill is automatically available when working in this directory
```

## CLI (Optional)

A CLI is also available for manual use:

```bash
fin-insights --help
fin-insights ingest             # scan cwd for statements
fin-insights insights --months 3
fin-insights categories --month 2025-01
fin-insights cashflow
fin-insights recommend optimize --months 3
```

## Agent Integration

Distributed as a **Claude Code Skill** and **Cursor Rules**. The AI agent calls Python functions directly from the `fin_insights` package — no CLI parsing needed. See `.claude/skills/financial-insights/SKILL.md` for the full API reference.
