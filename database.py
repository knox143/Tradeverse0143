"""
TradeVerse Database Bridge (database.py)
========================================
Lightweight bridge delegating all database, auth, and trading queries
directly to the unified engine.py module.
"""

from engine import (
    STARTING_INR_BALANCE,
    STARTING_USDT_BALANCE,
    get_database_path,
    get_db,
    query_db,
    init_db as init_database,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_wallet,
    reset_wallet,
    restore_user_to_db,
    get_currency_for_asset,
    format_duration,
    execute_trade,
    calculate_portfolio,
    get_portfolio_rows,
    get_closed_trades,
    get_transactions,
    get_all_users,
    get_watchlist,
    toggle_watchlist as toggle_watchlist_item,
    remove_watchlist_item,
    get_learning_modules,
    get_quiz_questions,
    score_quiz,
)

def is_watchlist_item(user_id, symbol, asset_type):
    from engine import query_db
    row = query_db("SELECT 1 FROM watchlist WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                   (user_id, symbol.upper().strip(), asset_type), fetchone=True)
    return row is not None

def add_watchlist_item(user_id, symbol, asset_type):
    from engine import query_db
    try:
        query_db("INSERT INTO watchlist (user_id, symbol, asset_type) VALUES (%s, %s, %s)",
                 (user_id, symbol.upper().strip(), asset_type), commit=True)
        return True
    except Exception:
        return False
