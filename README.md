# Financial Insights Skill

AI-powered personal financial statement analyzer. Ingests credit card and checking account statements from any bank, normalizes them into a unified database, and provides spending insights, cash flow analysis, and card reward optimization.

## Install as a Claude Code Plugin

The recommended way to use this tool is as a **Claude Code plugin**. Once installed, just ask Claude natural language questions about your finances — no CLI commands needed.

```bash
# Add this repo as a plugin marketplace, then install
claude /plugin install financial-insights
```

Or install directly from the repo:

```bash
claude --plugin-dir /path/to/financial-insights-skill
```

Once installed, ask Claude things like:
- "What did I spend on food last month?"
- "Show me my top merchants this year"
- "Which credit card should I use for groceries?"
- "Ingest my new Chase statement"

## Alternative: Clone & Use Directly

```bash
# Clone the repo
git clone https://github.com/srini-velaga/financial-insights-skill.git
cd financial-insights-skill
uv sync

# The skill is automatically available when working in this directory
```

## How It Works

1. **Drop statements** into `~/financial-data/statements/{bank_name}/` (CSV preferred, PDF supported)
2. **Profiles auto-match** your files using header fingerprinting — no configuration needed for supported banks
3. **For new banks**, your AI agent (Claude Code / Cursor) auto-detects the CSV format and creates a reusable profile
4. **Ask Claude to ingest** — it calls the Python API directly to parse, normalize, and store transactions in DuckDB
5. **Ask questions** — Claude queries the database and gives you conversational insights

## Supported Banks (Built-in Profiles)

| Bank | Credit Card | Checking |
|------|:-----------:|:--------:|
| American Express | CSV | — |
| Chase | CSV | CSV |
| Discover | CSV | — |
| Wells Fargo | CSV | — |
| Bank of America | PDF | PDF |

Any other bank works via agent-assisted profile auto-detection.

## Agent Integration

Distributed as a **Claude Code Plugin** (with skill) and **Cursor Rules**. The AI agent calls Python functions directly from the `fin_insights` package — no CLI parsing needed.

### CLI (Optional)

A CLI is also available for manual use:

```bash
uv sync
fin-insights --help
fin-insights ingest
fin-insights insights --months 3
fin-insights categories --month 2025-01
fin-insights cashflow
fin-insights recommend optimize --months 3
```
