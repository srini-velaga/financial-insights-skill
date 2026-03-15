"""CLI entry point for fin-insights."""

import json
import shutil
from pathlib import Path

import click

from fin_insights import __version__
from fin_insights.analytics import (
    DecimalEncoder,
    get_cashflow,
    get_category_breakdown,
    get_month_over_month,
    get_monthly_spending_by_category,
    get_spending_by_card,
    get_top_merchants,
    to_json,
)
from fin_insights.config import (
    get_builtin_config_dir,
    get_data_dir,
    get_db_path,
    get_statements_dir,
    get_user_config_dir,
    get_user_profiles_dir,
)
from fin_insights.db import get_connection
from fin_insights.ingest import ingest
from fin_insights.rewards import load_rewards_to_db, optimize_past_spending, recommend_for_category


def _get_conn(ctx):
    """Get a DB connection from context, creating schema if needed."""
    data_dir = ctx.obj["data_dir"]
    db_path = get_db_path(data_dir)
    if not db_path.exists():
        click.echo("No database found. Run 'fin-insights ingest' first.")
        raise SystemExit(1)
    return get_connection(db_path)


@click.group()
@click.option("--data-dir", envvar="FIN_INSIGHTS_DATA", default=None, help="Path to data directory")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, data_dir):
    """Personal financial insights — analyze statements, track spending, optimize rewards."""
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = get_data_dir(data_dir)


# ── Init ────────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def init(ctx):
    """Set up the data directory structure."""
    data_dir = ctx.obj["data_dir"]

    dirs_to_create = [
        get_statements_dir(data_dir),
        get_user_profiles_dir(data_dir),
        get_user_config_dir(data_dir),
    ]

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    example_rewards = get_builtin_config_dir() / "card_rewards.example.yaml"
    user_rewards = get_user_config_dir(data_dir) / "card_rewards.yaml"
    if example_rewards.exists() and not user_rewards.exists():
        shutil.copy2(example_rewards, user_rewards)

    click.echo(f"Data directory initialized at: {data_dir}")
    click.echo(f"  statements/  — drop your bank CSVs/PDFs here (organize by bank folder)")
    click.echo(f"  profiles/    — auto-generated parser profiles for your banks")
    click.echo(f"  config/      — card rewards and category overrides")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Create folders in statements/ for each bank (e.g., statements/chase/)")
    click.echo("  2. Download CSV exports from your banks and place them in the folders")
    click.echo("  3. Run: fin-insights ingest")


# ── Ingest ──────────────────────────────────────────────────────────────

@cli.command(name="ingest")
@click.pass_context
def ingest_cmd(ctx):
    """Scan statements and import new/modified files into the database."""
    data_dir = ctx.obj["data_dir"]
    statements_dir = get_statements_dir(data_dir)

    if not statements_dir.exists():
        click.echo(f"Statements directory not found: {statements_dir}")
        click.echo("Run 'fin-insights init' first.")
        return

    db_path = get_db_path(data_dir)
    conn = get_connection(db_path)

    try:
        result = ingest(data_dir, conn)

        if "error" in result:
            click.echo(f"Error: {result['error']}")
            return

        click.echo(f"Scan complete:")
        click.echo(f"  Files scanned:    {result['files_scanned']}")
        click.echo(f"  Files processed:  {result['files_processed']}")
        click.echo(f"  Files skipped:    {result['files_skipped']} (unchanged)")
        click.echo(f"  Files failed:     {result['files_failed']}")
        click.echo(f"  Txns inserted:    {result['transactions_inserted']}")
        click.echo(f"  Txns duplicate:   {result['transactions_duplicate']} (skipped)")

        for detail in result["details"]:
            if detail["status"] == "processed":
                click.echo(
                    f"  + {detail['file']} "
                    f"({detail['institution']}/{detail['account_type']}: "
                    f"{detail['inserted']} new, {detail['duplicates']} dup)"
                )
            elif detail["status"] == "failed":
                click.echo(f"  ! {detail['file']} — {detail['reason']}")
    finally:
        conn.close()


# ── Status ──────────────────────────────────────────────────────────────

@cli.command()
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def status(ctx, fmt):
    """Show processed files and database summary."""
    conn = _get_conn(ctx)

    try:
        log_rows = conn.execute(
            """SELECT file_path, institution, file_type, record_count, processed_at
               FROM processing_log ORDER BY processed_at DESC"""
        ).fetchall()

        txn_summary = conn.execute(
            """SELECT account_type, institution, COUNT(*) as count,
                      MIN(transaction_date) as earliest, MAX(transaction_date) as latest
               FROM transactions
               GROUP BY account_type, institution
               ORDER BY account_type, institution"""
        ).fetchall()

        total_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        if fmt == "json":
            output = {
                "total_transactions": total_txns,
                "files": [
                    {"file": r[0], "institution": r[1], "type": r[2],
                     "records": r[3], "processed_at": str(r[4])}
                    for r in log_rows
                ],
                "summary": [
                    {"account_type": r[0], "institution": r[1], "count": r[2],
                     "earliest": str(r[3]), "latest": str(r[4])}
                    for r in txn_summary
                ],
            }
            click.echo(to_json(output))
        else:
            click.echo(f"Total transactions: {total_txns}")
            click.echo()
            if txn_summary:
                click.echo("Summary by account:")
                for r in txn_summary:
                    click.echo(f"  {r[1]} ({r[0]}): {r[2]} txns [{r[3]} to {r[4]}]")
                click.echo()
            if log_rows:
                click.echo("Processed files:")
                for r in log_rows:
                    click.echo(f"  {r[1]:15s} {r[2]:4s} {r[3]:5d} records  {r[0]}")
            else:
                click.echo("No files processed yet.")
    finally:
        conn.close()


# ── Insights ────────────────────────────────────────────────────────────

@cli.command()
@click.option("--months", type=int, default=None, help="Limit to last N months")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def insights(ctx, months, fmt):
    """Show spending trends, top merchants, and month-over-month changes."""
    conn = _get_conn(ctx)

    try:
        mom = get_month_over_month(conn, months)
        merchants = get_top_merchants(conn, limit=10, months=months)

        if fmt == "json":
            click.echo(to_json({"month_over_month": mom, "top_merchants": merchants}))
        else:
            # Month-over-month summary
            if mom:
                click.echo("Month-over-month spending by category:")
                click.echo(f"  {'Category':25s} {'Month':12s} {'Total':>10s} {'Change':>10s} {'%':>7s}")
                click.echo("  " + "-" * 67)
                for r in mom:
                    change_str = f"{r['change']:+.2f}" if r["change"] is not None else ""
                    pct_str = f"{r['pct_change']:+.1f}%" if r["pct_change"] is not None else ""
                    click.echo(
                        f"  {r['category']:25s} {r['month']:12s} "
                        f"${float(r['total']):>9.2f} {change_str:>10s} {pct_str:>7s}"
                    )
                click.echo()

            if merchants:
                click.echo("Top 10 merchants by spend:")
                click.echo(f"  {'Merchant':40s} {'Txns':>5s} {'Total':>10s}")
                click.echo("  " + "-" * 58)
                for r in merchants:
                    click.echo(f"  {r['merchant']:40s} {r['transactions']:>5d} ${float(r['total']):>9.2f}")
    finally:
        conn.close()


# ── Categories ──────────────────────────────────────────────────────────

@cli.command()
@click.option("--month", type=str, default=None, help="Filter by month (YYYY-MM)")
@click.option("--year", type=str, default=None, help="Filter by year (YYYY)")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def categories(ctx, month, year, fmt):
    """Show spending breakdown by category."""
    conn = _get_conn(ctx)

    try:
        data = get_category_breakdown(conn, month=month, year=year)

        if fmt == "json":
            click.echo(to_json(data))
        else:
            period = month or year or "all time"
            click.echo(f"Category breakdown ({period}):")
            click.echo(f"  {'Category':25s} {'Subcategory':20s} {'Total':>10s} {'Txns':>5s} {'%':>6s}")
            click.echo("  " + "-" * 70)
            for r in data:
                subcat = r["subcategory"] or ""
                click.echo(
                    f"  {r['category']:25s} {subcat:20s} "
                    f"${float(r['total']):>9.2f} {r['transactions']:>5d} {float(r['percentage']):>5.1f}%"
                )

            total = sum(float(r["total"]) for r in data)
            click.echo("  " + "-" * 70)
            click.echo(f"  {'TOTAL':46s} ${total:>9.2f}")
    finally:
        conn.close()


# ── Cashflow ────────────────────────────────────────────────────────────

@cli.command()
@click.option("--months", type=int, default=None, help="Limit to last N months")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def cashflow(ctx, months, fmt):
    """Show monthly income vs spending and savings rate."""
    conn = _get_conn(ctx)

    try:
        data = get_cashflow(conn, months)

        if fmt == "json":
            click.echo(to_json(data))
        else:
            click.echo("Monthly cash flow:")
            click.echo(f"  {'Month':12s} {'Income':>12s} {'Spending':>12s} {'Net':>12s} {'Savings':>8s}")
            click.echo("  " + "-" * 60)
            for r in data:
                savings = f"{r['savings_rate']:.1f}%" if r["savings_rate"] is not None else "N/A"
                click.echo(
                    f"  {r['month']:12s} "
                    f"${float(r['income']):>11.2f} "
                    f"${float(r['spending']):>11.2f} "
                    f"${float(r['net_cashflow']):>11.2f} "
                    f"{savings:>8s}"
                )
    finally:
        conn.close()


# ── Recommend ───────────────────────────────────────────────────────────

@cli.group()
def recommend():
    """Card reward recommendations."""
    pass


@recommend.command(name="load")
@click.pass_context
def rewards_load(ctx):
    """Load card rewards from config into the database."""
    data_dir = ctx.obj["data_dir"]
    config_path = get_user_config_dir(data_dir) / "card_rewards.yaml"

    if not config_path.exists():
        click.echo(f"No card rewards config found at: {config_path}")
        click.echo("Run 'fin-insights init' to create a template, then edit it.")
        return

    conn = _get_conn(ctx)
    try:
        count = load_rewards_to_db(conn, config_path)
        click.echo(f"Loaded {count} reward rate entries from {config_path}")
    finally:
        conn.close()


@recommend.command(name="category")
@click.argument("category")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def recommend_category(ctx, category, fmt):
    """Rank cards by reward rate for a spending category."""
    conn = _get_conn(ctx)

    try:
        # Check if rewards are loaded
        count = conn.execute("SELECT COUNT(*) FROM card_rewards").fetchone()[0]
        if count == 0:
            click.echo("No card rewards loaded. Run 'fin-insights recommend load' first.")
            return

        results = recommend_for_category(conn, category)

        if fmt == "json":
            click.echo(to_json(results))
        else:
            if not results:
                click.echo(f"No cards found with rewards for '{category}'")
                return

            click.echo(f"Best cards for '{category}':")
            click.echo(f"  {'Card':35s} {'Rate':>6s} {'Type':>10s} {'Annual Fee':>10s}")
            click.echo("  " + "-" * 65)
            for r in results:
                click.echo(
                    f"  {r['institution'] + ' ' + r['card_name']:35s} "
                    f"{r['reward_rate']:>5.1f}% "
                    f"{r['reward_type']:>10s} "
                    f"${r['annual_fee']:>9.2f}"
                )
    finally:
        conn.close()


@recommend.command(name="optimize")
@click.option("--months", type=int, default=1, help="Analyze last N months (default: 1)")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def recommend_optimize(ctx, months, fmt):
    """Show missed reward opportunities from past spending."""
    conn = _get_conn(ctx)

    try:
        count = conn.execute("SELECT COUNT(*) FROM card_rewards").fetchone()[0]
        if count == 0:
            click.echo("No card rewards loaded. Run 'fin-insights recommend load' first.")
            return

        results = optimize_past_spending(conn, months)

        if fmt == "json":
            click.echo(to_json(results))
        else:
            if not results:
                click.echo("No missed reward opportunities found — you're using the optimal cards!")
                return

            total_missed = sum(r["missed_rewards"] for r in results)
            click.echo(f"Missed reward opportunities (last {months} month{'s' if months > 1 else ''}):")
            click.echo(f"  {'Category':25s} {'Spent':>10s} {'Used':>20s} {'Earned':>8s} {'Best':>20s} {'Could':>8s} {'Missed':>8s}")
            click.echo("  " + "-" * 105)
            for r in results:
                click.echo(
                    f"  {r['category']:25s} "
                    f"${r['amount_spent']:>9.2f} "
                    f"{r['card_used']:>20s} "
                    f"${r['earned']:>7.2f} "
                    f"{r['optimal_card']:>20s} "
                    f"${r['optimal_earned']:>7.2f} "
                    f"${r['missed_rewards']:>7.2f}"
                )
            click.echo("  " + "-" * 105)
            click.echo(f"  {'TOTAL MISSED':25s} {'':>10s} {'':>20s} {'':>8s} {'':>20s} {'':>8s} ${total_missed:>7.2f}")
    finally:
        conn.close()
