"""Portfolio calculations kept separate from Flask routes and SQLite queries."""

from database import (
    STARTING_INR_BALANCE,
    STARTING_USDT_BALANCE,
    format_duration,
    get_all_users,
    get_currency_for_asset,
    get_portfolio_rows,
    get_wallet,
)


def calculate_portfolio(user_id, quote_lookup):
    """Build holding values, total cost, value, and unrealized profit or loss split by currency."""
    wallet = get_wallet(user_id)
    holdings = []

    inr_total_cost = 0.0
    inr_total_value = 0.0
    usdt_total_cost = 0.0
    usdt_total_value = 0.0

    for row in get_portfolio_rows(user_id):
        quote = quote_lookup(row["symbol"], row["asset_type"])
        current_price = float(quote["price"]) if quote else float(row["average_price"])
        quantity = float(row["quantity"])
        average_price = float(row["average_price"])
        cost_basis = quantity * average_price
        current_value = quantity * current_price
        profit_loss = current_value - cost_basis
        row_keys = row.keys() if hasattr(row, "keys") else []
        currency = row["currency"] if "currency" in row_keys and row["currency"] else get_currency_for_asset(row["symbol"], row["asset_type"])
        age_seconds = row["age_seconds"] if "age_seconds" in row_keys and row["age_seconds"] is not None else 0

        holding_dict = {
            **dict(row),
            "currency": currency,
            "current_price": current_price,
            "cost_basis": cost_basis,
            "current_value": current_value,
            "profit_loss": profit_loss,
            "profit_loss_percent": (profit_loss / cost_basis * 100) if cost_basis else 0,
            "change": quote.get("change", 0) if quote else 0,
            "position_age_formatted": format_duration(age_seconds),
        }
        holdings.append(holding_dict)

        if currency == "INR":
            inr_total_cost += cost_basis
            inr_total_value += current_value
        else:
            usdt_total_cost += cost_basis
            usdt_total_value += current_value

    inr_profit_loss = inr_total_value - inr_total_cost
    inr_profit_loss_percent = (inr_profit_loss / inr_total_cost * 100) if inr_total_cost else 0.0
    usdt_profit_loss = usdt_total_value - usdt_total_cost
    usdt_profit_loss_percent = (usdt_profit_loss / usdt_total_cost * 100) if usdt_total_cost else 0.0

    return {
        "wallet": wallet,
        "wallet_balance": wallet["inr"],
        "inr_wallet": wallet["inr"],
        "usdt_wallet": wallet["usdt"],
        "holdings": holdings,
        "inr_holdings": [h for h in holdings if h["currency"] == "INR"],
        "usdt_holdings": [h for h in holdings if h["currency"] == "USDT"],
        "inr_total_cost": inr_total_cost,
        "inr_total_value": inr_total_value,
        "inr_profit_loss": inr_profit_loss,
        "inr_profit_loss_percent": inr_profit_loss_percent,
        "usdt_total_cost": usdt_total_cost,
        "usdt_total_value": usdt_total_value,
        "usdt_profit_loss": usdt_profit_loss,
        "usdt_profit_loss_percent": usdt_profit_loss_percent,
        "total_cost": inr_total_cost,
        "total_value": inr_total_value,
        "total_profit_loss": inr_profit_loss,
        "total_profit_loss_percent": inr_profit_loss_percent,
    }


def calculate_leaderboard(quote_lookup):
    """Rank registered users by their combined percentage paper-account gain or loss."""
    entries = []
    for user in get_all_users():
        portfolio = calculate_portfolio(user["id"], quote_lookup)
        inr_account_value = portfolio["inr_wallet"] + portfolio["inr_total_value"]
        usdt_account_value = portfolio["usdt_wallet"] + portfolio["usdt_total_value"]

        inr_pl = inr_account_value - STARTING_INR_BALANCE
        inr_pl_percent = (inr_pl / STARTING_INR_BALANCE) * 100

        usdt_pl = usdt_account_value - STARTING_USDT_BALANCE
        usdt_pl_percent = (usdt_pl / STARTING_USDT_BALANCE) * 100

        combined_pl_percent = (inr_pl_percent + usdt_pl_percent) / 2

        entries.append(
            {
                "user_id": user["id"],
                "full_name": user["full_name"],
                "inr_account_value": inr_account_value,
                "usdt_account_value": usdt_account_value,
                "inr_profit_loss": inr_pl,
                "usdt_profit_loss": usdt_pl,
                "profit_loss_percent": combined_pl_percent,
                "inr_profit_loss_percent": inr_pl_percent,
                "usdt_profit_loss_percent": usdt_pl_percent,
            }
        )

    entries.sort(
        key=lambda entry: (
            -entry["profit_loss_percent"],
            -entry["inr_profit_loss"],
            entry["full_name"].lower(),
        )
    )
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return entries
