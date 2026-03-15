"""Card reward recommendation engine."""

from pathlib import Path

import duckdb
import yaml

from fin_insights.analytics import DecimalEncoder


def load_rewards_config(config_path: Path) -> list[dict]:
    """Load card rewards from YAML config."""
    if not config_path.exists():
        return []

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return data.get("cards", [])


def load_rewards_to_db(conn: duckdb.DuckDBPyConnection, config_path: Path) -> int:
    """Load card rewards from YAML into the database. Returns count loaded."""
    cards = load_rewards_config(config_path)
    if not cards:
        return 0

    # Clear existing rewards
    conn.execute("DELETE FROM card_rewards")

    count = 0
    for card in cards:
        institution = card["institution"]
        card_name = card["card_name"]
        reward_type = card.get("reward_type", "cashback")
        annual_fee = card.get("annual_fee", 0)

        for category, rate in card.get("rates", {}).items():
            conn.execute(
                """INSERT INTO card_rewards
                   (institution, card_name, reward_type, category, reward_rate, annual_fee)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [institution, card_name, reward_type, category, rate, annual_fee],
            )
            count += 1

    return count


def recommend_for_category(conn: duckdb.DuckDBPyConnection, category: str) -> list[dict]:
    """Rank cards by reward rate for a given spending category."""
    rows = conn.execute(
        """SELECT card_name, institution, reward_type, reward_rate, annual_fee
           FROM card_rewards
           WHERE category = ? OR category = 'all'
           ORDER BY reward_rate DESC""",
        [category],
    ).fetchall()

    results = []
    seen_cards = set()
    for r in rows:
        card_key = f"{r[1]}_{r[0]}"
        if card_key in seen_cards:
            continue
        seen_cards.add(card_key)
        results.append({
            "card_name": r[0],
            "institution": r[1],
            "reward_type": r[2],
            "reward_rate": float(r[3]),
            "annual_fee": float(r[4]),
        })

    # Sort: specific category match first (higher rate), then 'all' catch-all
    results.sort(key=lambda x: x["reward_rate"], reverse=True)
    return results


def optimize_past_spending(
    conn: duckdb.DuckDBPyConnection,
    months: int = 1,
) -> list[dict]:
    """Analyze past spending and show missed reward opportunities.

    For each category where money was spent, shows which card was used,
    which card would have been optimal, and the difference.
    """
    # Get spending by institution and category
    spending = conn.execute(
        f"""SELECT institution, unified_category,
                  ROUND(SUM(amount), 2) AS total
           FROM transactions
           WHERE amount > 0
             AND transaction_date >= CURRENT_DATE - INTERVAL '{int(months)}' MONTH
           GROUP BY 1, 2
           ORDER BY 3 DESC""",
    ).fetchall()

    # Get all reward rates
    rewards = conn.execute(
        "SELECT institution, card_name, category, reward_rate FROM card_rewards"
    ).fetchall()

    # Build reward lookup: {(institution, category): (card_name, rate)}
    reward_map = {}
    for inst, card, cat, rate in rewards:
        key = (inst, cat)
        if key not in reward_map or float(rate) > float(reward_map[key][1]):
            reward_map[key] = (card, float(rate))

    # Build best rate per category across all cards
    best_by_category = {}
    for inst, card, cat, rate in rewards:
        rate_f = float(rate)
        if cat not in best_by_category or rate_f > best_by_category[cat][2]:
            best_by_category[cat] = (inst, card, rate_f)

    results = []
    for inst, category, total in spending:
        total_f = float(total)

        # What rate did the user get?
        used_rate = 0.0
        used_card = "Unknown"
        if (inst, category) in reward_map:
            used_card, used_rate = reward_map[(inst, category)]
        elif (inst, "all") in reward_map:
            used_card, used_rate = reward_map[(inst, "all")]

        earned = round(total_f * used_rate / 100, 2)

        # What's the best available?
        best_inst, best_card, best_rate = best_by_category.get(
            category, best_by_category.get("all", (inst, used_card, used_rate))
        )

        optimal_earned = round(total_f * best_rate / 100, 2)
        missed = round(optimal_earned - earned, 2)

        if missed > 0:
            results.append({
                "category": category,
                "amount_spent": total_f,
                "card_used": f"{inst} {used_card}",
                "rate_used": used_rate,
                "earned": earned,
                "optimal_card": f"{best_inst} {best_card}",
                "optimal_rate": best_rate,
                "optimal_earned": optimal_earned,
                "missed_rewards": missed,
            })

    results.sort(key=lambda x: x["missed_rewards"], reverse=True)
    return results
