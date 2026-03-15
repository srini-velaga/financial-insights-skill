"""CLI entry point for fin-insights."""

import json
import shutil
from pathlib import Path

import click

from fin_insights import __version__
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


@click.group()
@click.option("--data-dir", envvar="FIN_INSIGHTS_DATA", default=None, help="Path to data directory")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, data_dir):
    """Personal financial insights — analyze statements, track spending, optimize rewards."""
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = get_data_dir(data_dir)


@cli.command()
@click.pass_context
def init(ctx):
    """Set up the data directory structure."""
    data_dir = ctx.obj["data_dir"]

    # Create directory structure
    dirs_to_create = [
        get_statements_dir(data_dir),
        get_user_profiles_dir(data_dir),
        get_user_config_dir(data_dir),
    ]

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    # Copy example card rewards config if it doesn't exist
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

        # Show details for processed/failed files
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


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def status(ctx, fmt):
    """Show processed files and database summary."""
    data_dir = ctx.obj["data_dir"]
    db_path = get_db_path(data_dir)

    if not db_path.exists():
        click.echo("No database found. Run 'fin-insights ingest' first.")
        return

    conn = get_connection(db_path)

    try:
        # Processing log
        log_rows = conn.execute(
            """SELECT file_path, institution, file_type, record_count, processed_at
               FROM processing_log ORDER BY processed_at DESC"""
        ).fetchall()

        # Transaction summary
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
                    {
                        "file": r[0],
                        "institution": r[1],
                        "type": r[2],
                        "records": r[3],
                        "processed_at": str(r[4]),
                    }
                    for r in log_rows
                ],
                "summary": [
                    {
                        "account_type": r[0],
                        "institution": r[1],
                        "count": r[2],
                        "earliest": str(r[3]),
                        "latest": str(r[4]),
                    }
                    for r in txn_summary
                ],
            }
            click.echo(json.dumps(output, indent=2))
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
