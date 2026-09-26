"""Test serverless portfolio holdings persistence, session recovery, and wallet self-healing."""

import sys
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import app
from database import (
    get_database_path,
    get_user_by_email,
    get_portfolio_rows,
    get_wallet,
    restore_user_to_db,
    STARTING_INR_BALANCE,
    STARTING_USDT_BALANCE,
)


def run_checks():
    client = app.test_client()

    # 1. Register test user
    email = "persistent_trader@example.com"
    pwd = "TraderPassword123!"
    res_reg = client.post(
        "/register",
        data={
            "full_name": "Persistent Trader",
            "email": email,
            "password": pwd,
            "confirm_password": pwd,
        },
        follow_redirects=False,
    )
    assert res_reg.status_code == 302, f"Expected 302 on register, got {res_reg.status_code}"

    user = get_user_by_email(email)
    assert user is not None
    user_id = user["id"]

    # 2. Buy Indian Stock (RELIANCE.NS) and Crypto (BTC)
    res_stock = client.post(
        "/trade",
        json={"symbol": "RELIANCE.NS", "asset_type": "stock", "side": "BUY", "quantity": 10},
    )
    assert res_stock.status_code == 200, f"Stock buy failed: {res_stock.data}"
    stock_data = res_stock.get_json()
    assert stock_data["ok"] is True
    assert "portfolio" in stock_data
    assert len(stock_data["portfolio"]) >= 1

    res_crypto = client.post(
        "/trade",
        json={"symbol": "BTC", "asset_type": "crypto", "side": "BUY", "quantity": 0.05},
    )
    assert res_crypto.status_code == 200, f"Crypto buy failed: {res_crypto.data}"
    crypto_data = res_crypto.get_json()
    assert crypto_data["ok"] is True
    assert len(crypto_data["portfolio"]) >= 2

    # Check holdings exist in DB before container wipe
    initial_holdings = get_portfolio_rows(user_id)
    assert len(initial_holdings) == 2, f"Expected 2 holdings in DB, found {len(initial_holdings)}"
    symbols_before = {h["symbol"] for h in initial_holdings}
    assert "RELIANCE.NS" in symbols_before
    assert "BTC" in symbols_before
    print("Holdings successfully created in SQLite DB.")

    # 3. Simulate Serverless Container Wipe (Lambda dies overnight)
    # Delete user and all associated tables from SQLite
    db_path = str(get_database_path())
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM portfolio WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM wallet WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM closed_trades WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    assert get_user_by_email(email) is None, "User should be completely wiped from SQLite"
    print("Simulated container wipe completed: SQLite database is fresh/empty.")

    # 4. User visits next day (/portfolio and /dashboard)
    res_port = client.get("/portfolio")
    assert res_port.status_code == 200, f"Expected 200 on next-day visit, got {res_port.status_code}"

    # Verify user was automatically restored in DB
    user_after = get_user_by_email(email)
    assert user_after is not None, "User should be auto-restored in DB"
    new_user_id = user_after["id"]

    # Verify holdings were automatically restored in DB!
    restored_holdings = get_portfolio_rows(new_user_id)
    assert len(restored_holdings) == 2, f"Expected 2 restored holdings, found {len(restored_holdings)}"
    symbols_after = {h["symbol"] for h in restored_holdings}
    assert "RELIANCE.NS" in symbols_after
    assert "BTC" in symbols_after
    print("SUCCESS: Portfolio holdings were 100% recovered and restored from session!")

    # Verify portfolio HTML contains the restored symbols
    assert b"RELIANCE" in res_port.data
    assert b"BTC" in res_port.data
    print("SUCCESS: Portfolio page correctly displays restored stocks and crypto!")

    # 5. Test Automatic Self-Healing for Lost Wallet Funds
    # Simulate a user whose container was wiped previously with 0 holdings but deducted cash
    orphan_profile = {"id": 99999, "full_name": "Orphan User", "email": "orphan@example.com"}
    deducted_wallet = {"inr": 850000.0, "usdt": 7500.0}
    # Restore with 0 holdings and 0 transactions
    orphan_id = restore_user_to_db(orphan_profile, wallet=deducted_wallet, watchlist=[], portfolio=[], transactions=[])
    w = get_wallet(orphan_id)
    # Self-healing should restore full starting balance because 0 holdings exist
    assert w["inr"] == STARTING_INR_BALANCE, f"Expected INR auto-healing to {STARTING_INR_BALANCE}, got {w['inr']}"
    assert w["usdt"] == STARTING_USDT_BALANCE, f"Expected USDT auto-healing to {STARTING_USDT_BALANCE}, got {w['usdt']}"
    print("SUCCESS: Automatic self-healing restored deducted balance for orphaned empty portfolio!")

    # 6. Test Reset Wallet endpoint
    res_reset = client.post("/wallet/reset", follow_redirects=True)
    assert res_reset.status_code == 200
    assert b"Your virtual practice wallet has been reset" in res_reset.data
    print("SUCCESS: Reset wallet endpoint functions properly!")

    print("ALL SERVERLESS PORTFOLIO RECOVERY CHECKS PASSED PERFECTLY!")


if __name__ == "__main__":
    run_checks()
