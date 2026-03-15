# Financial Insights Skill

AI-powered personal financial statement analyzer. Ingests credit card and checking account statements from any bank, normalizes them into a unified database, and provides spending insights, cash flow analysis, and card reward optimization.

## Quick Start

```bash
# Install
uv sync

# Initialize your data directory
fin-insights init

# Add your bank statements to ~/financial-data/statements/{bank}/
# Then ingest them
fin-insights ingest

# View status
fin-insights status
```

## How It Works

1. **Drop statements** into `~/financial-data/statements/{bank_name}/` (CSV preferred, PDF supported)
2. **Profiles auto-match** your files using header fingerprinting — no configuration needed for supported banks
3. **For new banks**, your AI agent (Claude Code / Cursor) auto-detects the CSV format and creates a reusable profile
4. **Run `fin-insights ingest`** to parse, normalize, and store transactions in DuckDB
5. **Query insights** with `fin-insights insights`, `categories`, `cashflow`, and `recommend`

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

Works as a **Claude Code Skill** and **Cursor Rules** — your AI agent knows how to orchestrate the CLI, auto-detect new bank formats, and provide conversational financial insights.
