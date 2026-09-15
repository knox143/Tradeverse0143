import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash


BASE_DIRECTORY = Path(__file__).resolve().parent
SEED_DATABASE_PATH = BASE_DIRECTORY / "database" / "tradeverse.db"


def is_serverless_env():
    """Determine if running in Vercel or a read-only serverless container."""
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return True
    try:
        check_file = BASE_DIRECTORY / ".write_check"
        check_file.touch()
        check_file.unlink()
        return False
    except Exception:
        return True


def get_database_path():
    """Return writable DB path, copying seed DB to /tmp in serverless environments."""
    if is_serverless_env():
        tmp_db = Path("/tmp/tradeverse.db")
        if not tmp_db.exists() or tmp_db.stat().st_size == 0:
            try:
                tmp_db.parent.mkdir(parents=True, exist_ok=True)
                seed_candidates = [
                    SEED_DATABASE_PATH,
                    BASE_DIRECTORY.parent / "database" / "tradeverse.db",
                    Path("/var/task/database/tradeverse.db"),
                ]
                copied = False
                for seed in seed_candidates:
                    if seed.exists() and seed.stat().st_size > 0:
                        shutil.copyfile(str(seed), str(tmp_db))
                        copied = True
                        break
                if not copied:
                    tmp_db.touch()
            except Exception as err:
                sys.stderr.write(f"Warning initializing /tmp database: {err}\n")
        try:
            os.chmod(str(tmp_db), 0o666)
        except Exception:
            pass
        return tmp_db
    return SEED_DATABASE_PATH


STARTING_INR_BALANCE = 1_000_000.00
STARTING_USDT_BALANCE = 10_000.00
STARTING_WALLET_BALANCE = STARTING_INR_BALANCE


def format_duration(seconds):
    """Format duration in seconds into a friendly human-readable time string."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s" if seconds > 0 else "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    rem_minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {rem_minutes}m" if rem_minutes > 0 else f"{hours}h"
    days = hours // 24
    rem_hours = hours % 24
    if days < 30:
        return f"{days}d {rem_hours}h" if rem_hours > 0 else f"{days}d"
    return f"{days}d"


_tables_initialized = False


def ensure_tables():
    """Ensure schema exists before queries run in ephemeral serverless environments."""
    global _tables_initialized
    if _tables_initialized:
        return
    _tables_initialized = True
    try:
        db_path = get_database_path()
        with closing(sqlite3.connect(str(db_path), timeout=10.0)) as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            if not row:
                _init_database_tables()
    except Exception as e:
        _tables_initialized = False
        sys.stderr.write(f"ensure_tables notice: {e}\n")


def get_connection():
    """Open a SQLite connection configured to return dictionary-like rows."""
    db_path = get_database_path()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if is_serverless_env() and db_path.exists():
        try:
            os.chmod(str(db_path), 0o666)
        except Exception:
            pass

    ensure_tables()

    connection = sqlite3.connect(str(db_path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA busy_timeout = 10000")
    except Exception:
        pass
    return connection


def _migrate_database(connection):
    """Ensure existing tables have multi-currency columns and closed_trades timeline tracking."""
    wallet_cols = [row[1] for row in connection.execute("PRAGMA table_info(wallet)").fetchall()]
    if "inr_balance" not in wallet_cols:
        connection.execute("ALTER TABLE wallet ADD COLUMN inr_balance REAL NOT NULL DEFAULT 1000000.00")
        connection.execute("UPDATE wallet SET inr_balance = 1000000.00")
    if "usdt_balance" not in wallet_cols:
        connection.execute("ALTER TABLE wallet ADD COLUMN usdt_balance REAL NOT NULL DEFAULT 10000.00")
        connection.execute("UPDATE wallet SET usdt_balance = 10000.00")

    port_cols = [row[1] for row in connection.execute("PRAGMA table_info(portfolio)").fetchall()]
    if "currency" not in port_cols:
        connection.execute("ALTER TABLE portfolio ADD COLUMN currency TEXT NOT NULL DEFAULT 'USDT'")
        connection.execute(
            "UPDATE portfolio SET currency = 'INR' WHERE symbol LIKE '%.NS' OR symbol LIKE '%.BO'"
        )
    if "opened_at" not in port_cols:
        connection.execute("ALTER TABLE portfolio ADD COLUMN opened_at TEXT NOT NULL DEFAULT ''")
        connection.execute("UPDATE portfolio SET opened_at = updated_at")


    tx_cols = [row[1] for row in connection.execute("PRAGMA table_info(transactions)").fetchall()]
    if "currency" not in tx_cols:
        connection.execute("ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'USDT'")
        connection.execute(
            "UPDATE transactions SET currency = 'INR' WHERE symbol LIKE '%.NS' OR symbol LIKE '%.BO'"
        )

    # Ensure closed_trades table exists
    connection.execute("""
    CREATE TABLE IF NOT EXISTS closed_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
        asset_name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        quantity REAL NOT NULL CHECK (quantity > 0),
        buy_price REAL NOT NULL CHECK (buy_price > 0),
        sell_price REAL NOT NULL CHECK (sell_price > 0),
        buy_time TEXT NOT NULL,
        sell_time TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL DEFAULT 0,
        duration_formatted TEXT NOT NULL DEFAULT '0s',
        realized_pnl REAL NOT NULL,
        realized_pnl_percent REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_closed_trades_user_sell ON closed_trades(user_id, sell_time DESC)")

    # Backfill closed trades from historical transactions if closed_trades is currently empty
    closed_count = connection.execute("SELECT COUNT(*) FROM closed_trades").fetchone()[0]
    if closed_count == 0:
        sells = connection.execute("SELECT * FROM transactions WHERE trade_type = 'SELL' ORDER BY id ASC").fetchall()
        for sell in sells:
            matching_buy = connection.execute(
                """SELECT * FROM transactions WHERE user_id = ? AND symbol = ? AND trade_type = 'BUY' AND id < ?
                ORDER BY id DESC LIMIT 1""",
                (sell["user_id"], sell["symbol"], sell["id"])
            ).fetchone()
            buy_time = matching_buy["created_at"] if matching_buy else sell["created_at"]
            buy_price = float(matching_buy["price"]) if matching_buy else float(sell["price"]) * 0.98
            sell_price = float(sell["price"])
            sell_time = sell["created_at"]
            dur_sec = 1800
            try:
                t_b = datetime.fromisoformat(str(buy_time).replace("Z", "").split(".")[0])
                t_s = datetime.fromisoformat(str(sell_time).replace("Z", "").split(".")[0])
                dur_sec = max(1, int((t_s - t_b).total_seconds()))
            except Exception:
                pass
            pnl = round((sell_price - buy_price) * float(sell["quantity"]), 2)
            pnl_pct = round(((sell_price - buy_price) / buy_price) * 100, 2) if buy_price > 0 else 0.0
            connection.execute(
                """INSERT INTO closed_trades
                (user_id, symbol, asset_type, asset_name, currency, quantity, buy_price, sell_price,
                 buy_time, sell_time, duration_seconds, duration_formatted, realized_pnl, realized_pnl_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sell["user_id"], sell["symbol"], sell["asset_type"], sell["asset_name"],
                    sell["currency"], sell["quantity"], buy_price, sell_price,
                    buy_time, sell_time, dur_sec, format_duration(dur_sec), pnl, pnl_pct
                )
            )



def init_database():
    """Create the normalized application tables and seed reusable learning data."""
    try:
        _init_database_tables()
    except Exception as err:
        print(f"Notice during init_database: {err}")


def _init_database_tables():
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS wallet (
        user_id INTEGER PRIMARY KEY,
        inr_balance REAL NOT NULL DEFAULT 1000000.00 CHECK (inr_balance >= 0),
        usdt_balance REAL NOT NULL DEFAULT 10000.00 CHECK (usdt_balance >= 0),
        cash_balance REAL NOT NULL DEFAULT 1000000.00,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
        asset_name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        quantity REAL NOT NULL CHECK (quantity > 0),
        average_price REAL NOT NULL CHECK (average_price > 0),
        opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, symbol, asset_type),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
        asset_name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        trade_type TEXT NOT NULL CHECK (trade_type IN ('BUY', 'SELL')),
        quantity REAL NOT NULL CHECK (quantity > 0),
        price REAL NOT NULL CHECK (price > 0),
        total_amount REAL NOT NULL CHECK (total_amount > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS closed_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
        asset_name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        quantity REAL NOT NULL CHECK (quantity > 0),
        buy_price REAL NOT NULL CHECK (buy_price > 0),
        sell_price REAL NOT NULL CHECK (sell_price > 0),
        buy_time TEXT NOT NULL,
        sell_time TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL DEFAULT 0,
        duration_formatted TEXT NOT NULL DEFAULT '0s',
        realized_pnl REAL NOT NULL,
        realized_pnl_percent REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, symbol, asset_type),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS learning_modules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        read_time TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        image_path TEXT NOT NULL,
        content TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS quiz (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        correct_option INTEGER NOT NULL,
        explanation TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS quiz_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        total_questions INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON transactions(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_closed_trades_user ON closed_trades(user_id, sell_time DESC);
    CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
    """
    with closing(get_connection()) as connection:
        connection.executescript(schema)
        _migrate_database(connection)
        _seed_learning_modules(connection)
        _seed_quiz_questions(connection)
        _seed_demo_user(connection)
        connection.commit()


def _seed_demo_user(connection):
    """Ensure at least one ready-to-use demo account exists."""
    try:
        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            p_hash = generate_password_hash("password123")
            cursor = connection.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo Trader", "demo@tradeverse.com", p_hash),
            )
            u_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO wallet (user_id, inr_balance, usdt_balance, cash_balance) VALUES (?, ?, ?, ?)",
                (u_id, STARTING_INR_BALANCE, STARTING_USDT_BALANCE, STARTING_INR_BALANCE),
            )
    except Exception as err:
        sys.stderr.write(f"Notice during _seed_demo_user: {err}\n")


def _seed_learning_modules(connection):
    """Insert the starter learning library only when the table is empty."""
    if connection.execute("SELECT COUNT(*) FROM learning_modules").fetchone()[0]:
        return

    modules = [
        (
            "Paper trading, without pretend confidence",
            "Beginner guide",
            "Learn the order flow, virtual wallet, and habit of checking risk before a trade.",
            "7 min read",
            "Beginner",
            "learning-market-basics.png",
            "Paper trading is a rehearsal. Treat every virtual order as an opportunity to practice position sizing, entries, exits, and review.",
        ),
        (
            "Build a risk rule before a watchlist",
            "Risk management",
            "A simple framework for trade size, loss limits, and avoiding one-position portfolios.",
            "9 min read",
            "Beginner",
            "learning-market-basics.png",
            "Risk management starts before the buy button. Decide the maximum amount you can lose and the size of a position before seeing the price move.",
        ),
        (
            "Read a chart without chasing candles",
            "Technical analysis",
            "Use trend, support, resistance, and volume as context instead of certainty.",
            "11 min read",
            "Intermediate",
            "learning-market-basics.png",
            "Technical analysis is a language for probabilities. A chart can organize evidence, but it cannot promise the next move.",
        ),
        (
            "What a balance sheet is trying to tell you",
            "Fundamental analysis",
            "A friendly first look at revenue, margins, debt, and cash flow.",
            "12 min read",
            "Intermediate",
            "learning-market-basics.png",
            "Fundamental analysis asks whether a business can create durable value. Start with how it earns, spends, borrows, and generates cash.",
        ),
    ]
    connection.executemany(
        """INSERT INTO learning_modules
        (title, category, description, read_time, difficulty, image_path, content)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        modules,
    )


def _seed_quiz_questions(connection):
    """Insert five practical multiple-choice questions for the weekly quiz."""
    if connection.execute("SELECT COUNT(*) FROM quiz").fetchone()[0]:
        return

    questions = [
        (
            "What does diversification aim to reduce?",
            ["Brokerage fees", "Single-asset risk", "The need for research", "Market opening hours"],
            1,
            "Diversification spreads exposure across investments, reducing the impact of any single holding.",
        ),
        (
            "When you buy more of a holding at a different price, what changes?",
            ["Average price", "Ticker symbol", "Asset type", "Past transactions"],
            0,
            "The average price becomes the weighted average of the existing and new shares.",
        ),
        (
            "Why is a stop-loss plan useful in paper trading?",
            ["It guarantees profit", "It helps define risk before a trade", "It removes volatility", "It predicts prices"],
            1,
            "A risk plan creates a decision boundary before emotion gets involved.",
        ),
        (
            "Which number compares a holding's market value with its purchase cost?",
            ["Profit or loss", "Market cap", "Volume", "Spread"],
            0,
            "Profit or loss is current value minus the total cost basis.",
        ),
        (
            "A paper wallet in TradeVerse contains: ",
            ["Real bank funds", "Virtual trading credits", "Cryptographic keys", "Brokerage accounts"],
            1,
            "TradeVerse uses virtual credits so you can practice without risking real money.",
        ),
    ]
    connection.executemany(
        "INSERT INTO quiz (question, options_json, correct_option, explanation) VALUES (?, ?, ?, ?)",
        [(question, json.dumps(options), answer, explanation) for question, options, answer, explanation in questions],
    )


def create_user(full_name, email, password):
    """Create a user and a starting virtual wallet, returning the new user id."""
    password_hash = generate_password_hash(password)
    with closing(get_connection()) as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (full_name.strip(), email.lower().strip(), password_hash),
            )
            user_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO wallet (user_id, inr_balance, usdt_balance, cash_balance) VALUES (?, ?, ?, ?)",
                (user_id, STARTING_INR_BALANCE, STARTING_USDT_BALANCE, STARTING_INR_BALANCE),
            )
            connection.commit()
            return user_id
        except sqlite3.IntegrityError as error:
            connection.rollback()
            if "email" in str(error).lower() or "unique" in str(error).lower():
                raise ValueError("An account already exists for that email address.") from error
            raise ValueError(f"Registration failed: {error}") from error
        except sqlite3.Error as error:
            connection.rollback()
            raise ValueError(f"Database error during registration: {error}") from error


def get_user_by_email(email):
    """Find one user by email address or return None when the account is missing."""
    with closing(get_connection()) as connection:
        return connection.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()


def get_user_by_id(user_id):
    """Find one user by primary key for session-aware page rendering."""
    with closing(get_connection()) as connection:
        return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_all_users():
    """Return the registered accounts used by the paper-trading leaderboard."""
    with closing(get_connection()) as connection:
        return connection.execute(
            "SELECT id, full_name, created_at FROM users ORDER BY id"
        ).fetchall()


def update_user_profile(user_id, full_name, email):
    """Update a user's editable profile fields after checking email uniqueness."""
    with closing(get_connection()) as connection:
        try:
            connection.execute(
                """UPDATE users SET full_name = ?, email = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (full_name.strip(), email.lower().strip(), user_id),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ValueError("That email address is already in use.") from error


def reset_password(email, new_password):
    """Replace a password for the local demonstration reset flow."""
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?""",
            (generate_password_hash(new_password), email.lower().strip()),
        )
        connection.commit()
        return cursor.rowcount > 0


def get_wallet(user_id):
    """Return a user's current paper-credit balances for both INR and USDT."""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT inr_balance, usdt_balance, cash_balance FROM wallet WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            inr = float(row["inr_balance"]) if row["inr_balance"] is not None else float(row["cash_balance"] or 0.0)
            usdt = float(row["usdt_balance"]) if row["usdt_balance"] is not None else 0.0
            return {"inr": inr, "usdt": usdt}
        return {"inr": 0.0, "usdt": 0.0}


def get_wallet_balance(user_id, currency="INR"):
    """Return a user's current paper-credit balance for the given currency."""
    wallet = get_wallet(user_id)
    if currency and currency.upper() == "USDT":
        return wallet["usdt"]
    return wallet["inr"]


def get_currency_for_asset(symbol, asset_type):
    """Determine whether an asset is traded in INR or USDT."""
    if asset_type == "crypto":
        return "USDT"
    upper_symbol = symbol.upper().strip()
    if upper_symbol.endswith(".NS") or upper_symbol.endswith(".BO") or upper_symbol in {
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"
    }:
        return "INR"
    return "USDT"


def get_portfolio_rows(user_id):
    """Return all current holdings for a user with calculated position age."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """SELECT *,
            CAST((julianday('now') - julianday(COALESCE(opened_at, updated_at))) * 86400 AS INTEGER) AS age_seconds
            FROM portfolio WHERE user_id = ?
            ORDER BY updated_at DESC, asset_name ASC""",
            (user_id,),
        ).fetchall()


def get_closed_trades(user_id, limit=50):
    """Return closed trade lifecycle records with holding duration for the timeline."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """SELECT * FROM closed_trades WHERE user_id = ?
            ORDER BY sell_time DESC, id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()


def get_trade_timeline_stats(user_id):
    """Aggregate overall closed trade performance including average duration and win rate."""
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """SELECT duration_seconds, realized_pnl, realized_pnl_percent, currency
            FROM closed_trades WHERE user_id = ?""",
            (user_id,),
        ).fetchall()
        total_trades = len(rows)
        if total_trades == 0:
            return {
                "total_closed_trades": 0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "avg_duration_formatted": "0s",
                "quickest_trade_formatted": "N/A",
                "longest_trade_formatted": "N/A",
                "total_inr_pnl": 0.0,
                "total_usdt_pnl": 0.0,
            }

        wins = sum(1 for r in rows if r["realized_pnl"] > 0)
        losses = sum(1 for r in rows if r["realized_pnl"] < 0)
        durations = [r["duration_seconds"] for r in rows]
        avg_dur = sum(durations) // total_trades
        min_dur = min(durations)
        max_dur = max(durations)

        inr_pnl = sum(r["realized_pnl"] for r in rows if r["currency"] == "INR")
        usdt_pnl = sum(r["realized_pnl"] for r in rows if r["currency"] == "USDT")

        return {
            "total_closed_trades": total_trades,
            "win_count": wins,
            "loss_count": losses,
            "win_rate": round((wins / total_trades) * 100, 1),
            "avg_duration_formatted": format_duration(avg_dur),
            "quickest_trade_formatted": format_duration(min_dur),
            "longest_trade_formatted": format_duration(max_dur),
            "total_inr_pnl": round(inr_pnl, 2),
            "total_usdt_pnl": round(usdt_pnl, 2),
        }


def get_transactions(user_id, limit=20):
    """Return recent trades so users can inspect their paper-trading history."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """SELECT * FROM transactions WHERE user_id = ?
            ORDER BY created_at DESC, id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()


def execute_trade(user_id, symbol, asset_type, asset_name, side, quantity, price):
    """Atomically apply a BUY or SELL order to the wallet, portfolio, ledger, and closed_trades timeline."""
    normalized_symbol = symbol.upper().strip()
    normalized_side = side.upper().strip()
    quantity = float(quantity)
    price = float(price)
    total_amount = round(quantity * price, 2)
    currency = get_currency_for_asset(normalized_symbol, asset_type)

    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Choose either BUY or SELL for the order.")
    if asset_type not in {"stock", "crypto"}:
        raise ValueError("This asset type is not available for paper trading.")
    if quantity <= 0 or price <= 0:
        raise ValueError("Quantity and price must be greater than zero.")

    duration_formatted = None
    realized_pnl = None
    realized_pnl_percent = None

    with closing(get_connection()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            wallet = connection.execute(
                "SELECT inr_balance, usdt_balance, cash_balance FROM wallet WHERE user_id = ?", (user_id,)
            ).fetchone()
            if wallet is None:
                raise ValueError("Your paper wallet could not be found.")

            curr_balance = float(wallet["inr_balance"]) if currency == "INR" else float(wallet["usdt_balance"])

            holding = connection.execute(
                """SELECT * FROM portfolio
                WHERE user_id = ? AND symbol = ? AND asset_type = ?""",
                (user_id, normalized_symbol, asset_type),
            ).fetchone()

            if normalized_side == "BUY":
                if total_amount > curr_balance + 0.0001:
                    currency_label = "₹ (INR)" if currency == "INR" else "USDT"
                    raise ValueError(f"Your virtual wallet does not have enough {currency_label} credits for this order.")

                if currency == "INR":
                    connection.execute(
                        """UPDATE wallet SET inr_balance = inr_balance - ?, cash_balance = inr_balance - ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
                        (total_amount, total_amount, user_id),
                    )
                else:
                    connection.execute(
                        """UPDATE wallet SET usdt_balance = usdt_balance - ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
                        (total_amount, user_id),
                    )

                if holding:
                    old_quantity = float(holding["quantity"])
                    old_average = float(holding["average_price"])
                    new_quantity = old_quantity + quantity
                    new_average = ((old_quantity * old_average) + total_amount) / new_quantity
                    connection.execute(
                        """UPDATE portfolio SET quantity = ?, average_price = ?,
                        asset_name = ?, currency = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                        (new_quantity, new_average, asset_name, currency, holding["id"]),
                    )
                else:
                    connection.execute(
                        """INSERT INTO portfolio
                        (user_id, symbol, asset_type, asset_name, currency, quantity, average_price, opened_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                        (user_id, normalized_symbol, asset_type, asset_name, currency, quantity, price),
                    )
            else:
                if holding is None or float(holding["quantity"]) + 0.0000001 < quantity:
                    raise ValueError("You cannot sell more units than you currently hold.")
                remaining_quantity = float(holding["quantity"]) - quantity

                if currency == "INR":
                    connection.execute(
                        """UPDATE wallet SET inr_balance = inr_balance + ?, cash_balance = inr_balance + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
                        (total_amount, total_amount, user_id),
                    )
                else:
                    connection.execute(
                        """UPDATE wallet SET usdt_balance = usdt_balance + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
                        (total_amount, user_id),
                    )

                # Timeline calculation for closed trade
                holding_keys = holding.keys() if hasattr(holding, "keys") else []
                buy_time = holding["opened_at"] if "opened_at" in holding_keys and holding["opened_at"] else holding["updated_at"]
                buy_price = float(holding["average_price"])
                sell_price = price
                sell_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                duration_seconds = 60
                try:
                    t_buy = datetime.fromisoformat(str(buy_time).replace("Z", "").split(".")[0])
                    t_sell = datetime.fromisoformat(sell_time)
                    duration_seconds = max(1, int((t_sell - t_buy).total_seconds()))
                except Exception:
                    pass

                duration_formatted = format_duration(duration_seconds)
                realized_pnl = round((sell_price - buy_price) * quantity, 2)
                realized_pnl_percent = round(((sell_price - buy_price) / buy_price) * 100, 2) if buy_price > 0 else 0.0

                connection.execute(
                    """INSERT INTO closed_trades
                    (user_id, symbol, asset_type, asset_name, currency, quantity, buy_price, sell_price,
                     buy_time, sell_time, duration_seconds, duration_formatted, realized_pnl, realized_pnl_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        normalized_symbol,
                        asset_type,
                        asset_name,
                        currency,
                        quantity,
                        buy_price,
                        sell_price,
                        buy_time,
                        sell_time,
                        duration_seconds,
                        duration_formatted,
                        realized_pnl,
                        realized_pnl_percent,
                    ),
                )

                if remaining_quantity <= 0.0000001:
                    connection.execute("DELETE FROM portfolio WHERE id = ?", (holding["id"],))
                else:
                    connection.execute(
                        """UPDATE portfolio SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?""",
                        (remaining_quantity, holding["id"]),
                    )

            connection.execute(
                """INSERT INTO transactions
                (user_id, symbol, asset_type, asset_name, currency, trade_type, quantity, price, total_amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    normalized_symbol,
                    asset_type,
                    asset_name,
                    currency,
                    normalized_side,
                    quantity,
                    price,
                    total_amount,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    wallet_now = get_wallet(user_id)
    result = {
        "symbol": normalized_symbol,
        "side": normalized_side,
        "quantity": quantity,
        "price": price,
        "total_amount": total_amount,
        "currency": currency,
        "inr_balance": wallet_now["inr"],
        "usdt_balance": wallet_now["usdt"],
        "wallet_balance": wallet_now["inr"] if currency == "INR" else wallet_now["usdt"],
    }
    if normalized_side == "SELL":
        result["duration_formatted"] = duration_formatted
        result["duration_seconds"] = duration_seconds
        result["realized_pnl"] = realized_pnl
        result["realized_pnl_percent"] = realized_pnl_percent
    return result



def get_watchlist(user_id):
    """Return a user's saved market symbols in reverse-added order."""
    with closing(get_connection()) as connection:
        return connection.execute(
            "SELECT * FROM watchlist WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()


def is_watchlist_item(user_id, symbol, asset_type):
    """Check whether a symbol is already saved for one user and asset type."""
    normalized_symbol = symbol.upper().strip()
    with closing(get_connection()) as connection:
        return connection.execute(
            """SELECT 1 FROM watchlist
            WHERE user_id = ? AND symbol = ? AND asset_type = ?""",
            (user_id, normalized_symbol, asset_type),
        ).fetchone() is not None


def add_watchlist_item(user_id, symbol, asset_type):
    """Save a symbol once and return False instead of creating a duplicate row."""
    normalized_symbol = symbol.upper().strip()
    if asset_type not in {"stock", "crypto"}:
        raise ValueError("This asset type cannot be saved to the watchlist.")
    with closing(get_connection()) as connection:
        try:
            connection.execute(
                "INSERT INTO watchlist (user_id, symbol, asset_type) VALUES (?, ?, ?)",
                (user_id, normalized_symbol, asset_type),
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError:
            connection.rollback()
            return False


def remove_watchlist_item(user_id, symbol, asset_type):
    """Remove one user's saved symbol without affecting another user's list."""
    normalized_symbol = symbol.upper().strip()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """DELETE FROM watchlist
            WHERE user_id = ? AND symbol = ? AND asset_type = ?""",
            (user_id, normalized_symbol, asset_type),
        )
        connection.commit()
        return cursor.rowcount > 0


def toggle_watchlist_item(user_id, symbol, asset_type):
    """Add a symbol to the watchlist or remove it when it is already saved."""
    normalized_symbol = symbol.upper().strip()
    if is_watchlist_item(user_id, normalized_symbol, asset_type):
        remove_watchlist_item(user_id, normalized_symbol, asset_type)
        return False
    return add_watchlist_item(user_id, normalized_symbol, asset_type)


def get_learning_modules():
    """Return the complete beginner-friendly course list."""
    with closing(get_connection()) as connection:
        return connection.execute("SELECT * FROM learning_modules ORDER BY id").fetchall()


def get_quiz_questions():
    """Return quiz questions with parsed options while keeping answers server-side."""
    with closing(get_connection()) as connection:
        questions = connection.execute("SELECT * FROM quiz ORDER BY id").fetchall()
    return [
        {
            "id": question["id"],
            "question": question["question"],
            "options": json.loads(question["options_json"]),
        }
        for question in questions
    ]


def score_quiz(user_id, answers):
    """Check quiz answers, store a result, and return a concise score summary."""
    with closing(get_connection()) as connection:
        questions = connection.execute("SELECT * FROM quiz ORDER BY id").fetchall()
        score = 0
        feedback = []
        for question in questions:
            selected = answers.get(str(question["id"]))
            is_correct = selected is not None and int(selected) == question["correct_option"]
            score += int(is_correct)
            feedback.append(
                {
                    "question": question["question"],
                    "is_correct": is_correct,
                    "explanation": question["explanation"],
                }
            )
        connection.execute(
            "INSERT INTO quiz_results (user_id, score, total_questions) VALUES (?, ?, ?)",
            (user_id, score, len(questions)),
        )
        connection.commit()
        return {"score": score, "total": len(questions), "feedback": feedback}


def get_quiz_results(user_id, limit=5):
    """Return a small list of a user's past quiz attempts."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """SELECT * FROM quiz_results WHERE user_id = ?
            ORDER BY created_at DESC, id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
