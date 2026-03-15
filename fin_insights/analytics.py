"""Analytics queries for financial insights."""

import json
from decimal import Decimal

import duckdb


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def to_json(data: dict | list) -> str:
    return json.dumps(data, indent=2, cls=DecimalEncoder, default=str)


def _interval_filter(months: int | None, col: str = "transaction_date") -> str:
    """Build an interval WHERE clause. months is always int, safe to interpolate."""
    if months is None:
        return ""
    return f"AND {col} >= CURRENT_DATE - INTERVAL '{int(months)}' MONTH"


def get_monthly_spending_by_category(conn: duckdb.DuckDBPyConnection, months: int | None = None) -> list[dict]:
    """Monthly spending totals by unified category."""
    interval = _interval_filter(months)

    rows = conn.execute(
        f"""SELECT unified_category,
                   DATE_TRUNC('month', transaction_date)::DATE AS month,
                   ROUND(SUM(amount), 2) AS total
            FROM transactions
            WHERE amount > 0 {interval}
            GROUP BY 1, 2
            ORDER BY 2 DESC, 3 DESC""",
    ).fetchall()

    return [{"category": r[0], "month": str(r[1]), "total": r[2]} for r in rows]


def get_month_over_month(conn: duckdb.DuckDBPyConnection, months: int | None = None) -> list[dict]:
    """Month-over-month spending change by category."""
    outer_where = ""
    if months:
        outer_where = f"WHERE month >= CURRENT_DATE - INTERVAL '{int(months)}' MONTH"

    rows = conn.execute(
        f"""WITH monthly AS (
                SELECT unified_category,
                       DATE_TRUNC('month', transaction_date)::DATE AS month,
                       ROUND(SUM(amount), 2) AS total
                FROM transactions
                WHERE amount > 0
                GROUP BY 1, 2
            )
            SELECT unified_category, month, total,
                   total - LAG(total) OVER (PARTITION BY unified_category ORDER BY month) AS change,
                   CASE WHEN LAG(total) OVER (PARTITION BY unified_category ORDER BY month) > 0
                        THEN ROUND((total - LAG(total) OVER (PARTITION BY unified_category ORDER BY month))
                                   / LAG(total) OVER (PARTITION BY unified_category ORDER BY month) * 100, 1)
                        ELSE NULL END AS pct_change
            FROM monthly
            {outer_where}
            ORDER BY month DESC, total DESC""",
    ).fetchall()

    return [
        {"category": r[0], "month": str(r[1]), "total": r[2], "change": r[3], "pct_change": r[4]}
        for r in rows
    ]


def get_top_merchants(conn: duckdb.DuckDBPyConnection, limit: int = 10, months: int | None = None) -> list[dict]:
    """Top merchants by total spend."""
    interval = _interval_filter(months)

    rows = conn.execute(
        f"""SELECT description_clean, COUNT(*) AS txn_count,
                   ROUND(SUM(amount), 2) AS total
            FROM transactions
            WHERE amount > 0 {interval}
            GROUP BY 1
            ORDER BY 3 DESC
            LIMIT {int(limit)}""",
    ).fetchall()

    return [{"merchant": r[0], "transactions": r[1], "total": r[2]} for r in rows]


def get_category_breakdown(
    conn: duckdb.DuckDBPyConnection,
    month: str | None = None,
    year: str | None = None,
) -> list[dict]:
    """Category breakdown with amounts and percentages."""
    where_parts = ["amount > 0"]
    params = []

    if month:
        where_parts.append("DATE_TRUNC('month', transaction_date)::DATE = ?::DATE")
        params.append(f"{month}-01")
    elif year:
        where_parts.append("EXTRACT(YEAR FROM transaction_date) = ?")
        params.append(int(year))

    where = " AND ".join(where_parts)

    rows = conn.execute(
        f"""WITH cats AS (
                SELECT unified_category, unified_subcategory,
                       ROUND(SUM(amount), 2) AS total,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE {where}
                GROUP BY 1, 2
            ),
            grand_total AS (
                SELECT ROUND(SUM(amount), 2) AS gt FROM transactions WHERE {where}
            )
            SELECT c.unified_category, c.unified_subcategory, c.total, c.txn_count,
                   ROUND(c.total / NULLIF(g.gt, 0) * 100, 1) AS pct
            FROM cats c, grand_total g
            ORDER BY c.total DESC""",
        params + params,
    ).fetchall()

    return [
        {
            "category": r[0],
            "subcategory": r[1],
            "total": r[2],
            "transactions": r[3],
            "percentage": r[4],
        }
        for r in rows
    ]


def get_cashflow(conn: duckdb.DuckDBPyConnection, months: int | None = None) -> list[dict]:
    """Monthly income vs spending with savings rate."""
    where = ""
    if months:
        where = f"WHERE transaction_date >= CURRENT_DATE - INTERVAL '{int(months)}' MONTH"

    rows = conn.execute(
        f"""SELECT DATE_TRUNC('month', transaction_date)::DATE AS month,
                   ROUND(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 2) AS income,
                   ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS spending,
                   ROUND(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END)
                         - SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS net_cashflow
            FROM transactions
            {where}
            GROUP BY 1
            ORDER BY 1 DESC""",
    ).fetchall()

    results = []
    for r in rows:
        income = r[1]
        spending = r[2]
        savings_rate = round((1 - float(spending) / float(income)) * 100, 1) if income and float(income) > 0 else None
        results.append({
            "month": str(r[0]),
            "income": income,
            "spending": spending,
            "net_cashflow": r[3],
            "savings_rate": savings_rate,
        })

    return results


def get_spending_by_card(conn: duckdb.DuckDBPyConnection, months: int | None = None) -> list[dict]:
    """Spending breakdown by institution/card."""
    interval = _interval_filter(months)

    rows = conn.execute(
        f"""SELECT institution, unified_category,
                   ROUND(SUM(amount), 2) AS total,
                   COUNT(*) AS txn_count
            FROM transactions
            WHERE amount > 0 {interval}
            GROUP BY 1, 2
            ORDER BY 1, 3 DESC""",
    ).fetchall()

    return [
        {"institution": r[0], "category": r[1], "total": r[2], "transactions": r[3]}
        for r in rows
    ]
