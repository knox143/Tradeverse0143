"""
TradeVerse Core Engine (engine.py)
==================================
Unified, production-ready, low-latency engine for:
1. PostgreSQL Database & Connection Pooling (with resilient SQLite fallback)
2. Atomic Trade Execution (Buy/Sell, Weighted Average Cost, Ledger)
3. Custom Market API with 10-second TTL In-Memory Price Cache
4. Portfolio Calculations, Icons, and Auth Management
"""

import os
import sys
import json
import time
import math
import re
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup
import secrets
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Engine logger initialization
logger = logging.getLogger("tradeverse.engine")

# ==============================================================================
# SECTION 1: DATABASE POOL & CONCURRENT ACCESS (PostgreSQL + SQLite Fallback)
# ==============================================================================
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
_PG_POOL = None
_IS_POSTGRES = False

if DATABASE_URL:
    try:
        import psycopg2
        from psycopg2 import pool, extras
        # Normalize url scheme if necessary
        db_url = DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        _PG_POOL = pool.SimpleConnectionPool(minconn=1, maxconn=20, dsn=db_url)
        _IS_POSTGRES = True
    except Exception as e:
        sys.stderr.write(f"PostgreSQL pool init notice (falling back to SQLite): {e}\n")
        _PG_POOL = None
        _IS_POSTGRES = False

STARTING_INR_BALANCE = 1000000.00
STARTING_USDT_BALANCE = 10000.00

def get_sqlite_path():
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "/tmp/tradeverse.db"
    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "tradeverse.db")


@contextmanager
def get_db():
    """Yield an active database connection with transactional safety."""
    if _IS_POSTGRES and _PG_POOL:
        conn = _PG_POOL.getconn()
        try:
            yield conn
        finally:
            _PG_POOL.putconn(conn)
    else:
        import sqlite3
        conn = sqlite3.connect(get_sqlite_path(), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()


def query_db(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Execute raw SQL query with parameter translation between Postgres (%s) and SQLite (?)."""
    params = params or ()
    with get_db() as conn:
        cursor = conn.cursor()
        sql = query
        if not _IS_POSTGRES:
            sql = sql.replace("%s", "?")
        cursor.execute(sql, params)
        result = None
        if fetchone:
            row = cursor.fetchone()
            if row:
                result = dict(row) if hasattr(row, "keys") else dict(zip([col[0] for col in cursor.description], row))
        elif fetchall:
            rows = cursor.fetchall()
            if rows:
                if hasattr(rows[0], "keys"):
                    result = [dict(r) for r in rows]
                else:
                    cols = [col[0] for col in cursor.description]
                    result = [dict(zip(cols, r)) for r in rows]
            else:
                result = []
        if commit:
            conn.commit()
        return result


def init_db():
    """Initialize database tables with indexes for high concurrency."""
    with get_db() as conn:
        cursor = conn.cursor()
        if _IS_POSTGRES:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS wallet (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                inr_balance DOUBLE PRECISION NOT NULL DEFAULT 1000000.00,
                usdt_balance DOUBLE PRECISION NOT NULL DEFAULT 10000.00,
                cash_balance DOUBLE PRECISION NOT NULL DEFAULT 1000000.00,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol VARCHAR(32) NOT NULL,
                asset_type VARCHAR(16) NOT NULL,
                asset_name TEXT NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'INR',
                quantity DOUBLE PRECISION NOT NULL,
                average_price DOUBLE PRECISION NOT NULL,
                opened_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol, asset_type)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol VARCHAR(32) NOT NULL,
                asset_type VARCHAR(16) NOT NULL,
                asset_name TEXT NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'INR',
                trade_type VARCHAR(8) NOT NULL,
                quantity DOUBLE PRECISION NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                total_amount DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS closed_trades (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol VARCHAR(32) NOT NULL,
                asset_type VARCHAR(16) NOT NULL,
                asset_name TEXT NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'INR',
                quantity DOUBLE PRECISION NOT NULL,
                buy_price DOUBLE PRECISION NOT NULL,
                sell_price DOUBLE PRECISION NOT NULL,
                buy_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                sell_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0,
                duration_formatted VARCHAR(32) DEFAULT '0s',
                realized_pnl DOUBLE PRECISION NOT NULL,
                realized_pnl_percent DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol VARCHAR(32) NOT NULL,
                asset_type VARCHAR(16) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol, asset_type)
            );
            CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_closed_trades_user ON closed_trades(user_id);
            CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
            """)
        else:
            cursor.executescript("""
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
                inr_balance REAL NOT NULL DEFAULT 1000000.00,
                usdt_balance REAL NOT NULL DEFAULT 10000.00,
                cash_balance REAL NOT NULL DEFAULT 1000000.00,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                quantity REAL NOT NULL,
                average_price REAL NOT NULL,
                opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol, asset_type),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                trade_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                total_amount REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS closed_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                quantity REAL NOT NULL,
                buy_price REAL NOT NULL,
                sell_price REAL NOT NULL,
                buy_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sell_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0,
                duration_formatted TEXT DEFAULT '0s',
                realized_pnl REAL NOT NULL,
                realized_pnl_percent REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol, asset_type),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_closed_trades_user ON closed_trades(user_id);
            CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
            """)
        conn.commit()


def seed_demo_user():
    """Ensure at least one demo user exists."""
    u = query_db("SELECT id FROM users WHERE email = %s", ("demo@tradeverse.com",), fetchone=True)
    if not u:
        h = generate_password_hash("password123")
        if _IS_POSTGRES:
            res = query_db("INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                           ("Demo Trader", "demo@tradeverse.com", h), fetchone=True, commit=True)
            uid = res["id"]
        else:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                            ("Demo Trader", "demo@tradeverse.com", h))
                uid = cur.lastrowid
                conn.commit()
        query_db("INSERT INTO wallet (user_id, inr_balance, usdt_balance, cash_balance) VALUES (%s, %s, %s, %s)",
                 (uid, STARTING_INR_BALANCE, STARTING_USDT_BALANCE, STARTING_INR_BALANCE), commit=True)


# Initialize DB on load
try:
    init_db()
    seed_demo_user()
except Exception as e:
    sys.stderr.write(f"Database init notice: {e}\n")


# ==============================================================================
# SECTION 2: USER AUTH & WALLET HELPERS
# User account create karna, 4-digit OTP bhejna, wallet manage karna aur auth verify karna
# ==============================================================================
def generate_otp():
    """
    [4-DIGIT SECURE OTP GENERATOR]
    ---------------------------------------------------------
    • Kya karta hai: 4-digit ka random numeric OTP banata hai (1000 se 9999).
    • Kis liye hai: New user registration verify karne ke liye taaki fake accounts na banein.
    • Return: String format mein 4-digit OTP jaise "4829".
    """
    return str(secrets.randbelow(9000) + 1000)


def send_otp_email(to_email, otp, full_name="Trader"):
    """
    [4-DIGIT OTP EMAIL DISPATCHER]
    ---------------------------------------------------------
    • Kya karta hai: User ke Gmail / email par 4-digit verification code bhejta hai.
    • Kis liye hai: Jab new user register karega to uske Gmail pe OTP jayega,
      aur jab tak wo OTP verify nahi karega tab tak account create nahi hoga.
    • Kaise kaam karta hai:
      1. Environment variables (SMTP_USER, SMTP_PASS, SMTP_SERVER, SMTP_PORT) check karta hai.
      2. Agar credentials available hain to secure TLS (Port 587) ke sath live HTML email bhejta hai.
      3. Agar credentials abhi Vercel/.env mein set nahi hain to console/logger mein OTP print karta hai
         aur dev_mode=True return karta hai taaki local testing bina rukawat ke turant ho sake.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER") or os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD")

    subject = f"TradeVerse - Your 4-Digit Verification Code: {otp}"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f17; color: #e2e8f0; margin: 0; padding: 20px; }}
    .card {{ max-width: 500px; margin: 0 auto; background: #131b2a; border: 1px solid #1e293b; border-radius: 12px; padding: 32px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }}
    .logo {{ font-size: 24px; font-weight: 800; color: #38bdf8; margin-bottom: 16px; letter-spacing: -0.5px; }}
    .logo span {{ color: #818cf8; }}
    h2 {{ font-size: 20px; font-weight: 700; color: #f8fafc; margin-top: 0; }}
    p {{ font-size: 14px; line-height: 1.6; color: #94a3b8; }}
    .otp-box {{ background: #1e293b; border: 2px dashed #38bdf8; border-radius: 8px; text-align: center; padding: 18px; margin: 24px 0; }}
    .otp-code {{ font-size: 38px; font-weight: 900; letter-spacing: 12px; color: #38bdf8; font-family: monospace; }}
    .meta {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #1e293b; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Trade<span>Verse</span></div>
    <h2>Verify Your Email / ईमेल वेरीफाई करें</h2>
    <p>Hi {full_name},</p>
    <p>TradeVerse practice trading space mein aapka swagat hai. Apna account activate karne aur <strong>₹10,00,000 INR & 10,000 USDT</strong> virtual practice credits pane ke liye neeche diya gaya 4-digit code enter karein:</p>
    <div class="otp-box">
      <div class="otp-code">{otp}</div>
    </div>
    <p>Ye verification code <strong>10 minutes</strong> tak valid rahega. Agar aapne ye request nahi ki thi, to aap is email ko ignore kar sakte hain.</p>
    <div class="meta">
      TradeVerse Virtual Trading &bull; Strictly Paper Trading (No Real Money).
    </div>
  </div>
</body>
</html>"""

    if smtp_user and smtp_pass:
        clean_pass = str(smtp_pass).replace(" ", "").strip()
        clean_user = str(smtp_user).strip()
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"TradeVerse <{clean_user}>"
            msg["To"] = to_email

            text_part = MIMEText(f"Your TradeVerse verification code is: {otp}\nValid for 10 minutes.", "plain")
            html_part = MIMEText(html_content, "html")
            msg.attach(text_part)
            msg.attach(html_part)

            # Try Port 465 SSL first (most reliable on Vercel/serverless environments)
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=7) as server:
                    server.login(clean_user, clean_pass)
                    server.send_message(msg)
                return {"sent": True, "dev_mode": False}
            except Exception as e_ssl:
                logger.warning(f"SMTP SSL 465 attempt: {e_ssl}, trying port 587 STARTTLS...")
                # Fallback to Port 587 STARTTLS
                with smtplib.SMTP(smtp_server, smtp_port, timeout=7) as server:
                    server.starttls()
                    server.login(clean_user, clean_pass)
                    server.send_message(msg)
                return {"sent": True, "dev_mode": False}
        except Exception as e:
            logger.warning(f"SMTP delivery failed ({e}). Falling back to dev mode OTP.")
            return {"sent": True, "dev_mode": True, "otp": otp, "error": str(e)}
    else:
        logger.info(f"[TradeVerse OTP] Verification code for {to_email}: {otp}")
        return {"sent": True, "dev_mode": True, "otp": otp}


def create_user(full_name, email, password, is_hashed=False):
    """
    [NEW USER CREATION IN DATABASE]
    ---------------------------------------------------------
    • Kya karta hai: Naye user ko database (Postgres ya SQLite) mein save karta hai.
    • Wallet funding: User ke bante hi ₹10,00,000 INR aur 10,000 USDT virtual balance auto-credit hota hai.
    • Arguments:
      - full_name: User ka pura naam
      - email: User ka verified Gmail / email
      - password: Raw password string ya pre-computed password hash
      - is_hashed: Agar True ho to password ko dobara hash nahi karta
    • Return: Naye user ki database ID (uid)
    """
    email = email.lower().strip()
    h = password if is_hashed else generate_password_hash(password)
    existing = query_db("SELECT id FROM users WHERE email = %s", (email,), fetchone=True)
    if existing:
        raise ValueError("An account already exists for that email address.")
    if _IS_POSTGRES:
        res = query_db("INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                       (full_name.strip(), email, h), fetchone=True, commit=True)
        uid = res["id"]
    else:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                        (full_name.strip(), email, h))
            uid = cur.lastrowid
            conn.commit()
    query_db("INSERT INTO wallet (user_id, inr_balance, usdt_balance, cash_balance) VALUES (%s, %s, %s, %s)",
             (uid, STARTING_INR_BALANCE, STARTING_USDT_BALANCE, STARTING_INR_BALANCE), commit=True)
    return uid


def get_user_by_email(email):
    return query_db("SELECT * FROM users WHERE email = %s", ((email or "").lower().strip(),), fetchone=True)


def get_user_by_id(user_id):
    return query_db("SELECT * FROM users WHERE id = %s", (user_id,), fetchone=True)


def get_wallet(user_id):
    w = query_db("SELECT inr_balance, usdt_balance, cash_balance FROM wallet WHERE user_id = %s", (user_id,), fetchone=True)
    if w:
        inr = float(w.get("inr_balance", 0.0) or w.get("cash_balance", 0.0) or 0.0)
        usdt = float(w.get("usdt_balance", 0.0) or 0.0)
        return {"inr": inr, "usdt": usdt}
    return {"inr": STARTING_INR_BALANCE, "usdt": STARTING_USDT_BALANCE}


def reset_wallet(user_id):
    query_db("UPDATE wallet SET inr_balance = %s, usdt_balance = %s, cash_balance = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
             (STARTING_INR_BALANCE, STARTING_USDT_BALANCE, STARTING_INR_BALANCE, user_id), commit=True)


def restore_user_to_db(user_data, wallet=None, watchlist=None, portfolio=None, transactions=None, closed_trades=None):
    if not user_data or not user_data.get("email"):
        return None
    email = str(user_data["email"]).lower().strip()
    u = get_user_by_email(email)
    if u:
        uid = u["id"]
    else:
        full_name = str(user_data.get("full_name") or "Paper Trader").strip()
        p_hash = user_data.get("password_hash") or generate_password_hash("password123")
        if _IS_POSTGRES:
            res = query_db("INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                           (full_name, email, p_hash), fetchone=True, commit=True)
            uid = res["id"]
        else:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                            (full_name, email, p_hash))
                uid = cur.lastrowid
                conn.commit()

    inr_bal = float(wallet.get("inr", STARTING_INR_BALANCE)) if (wallet and "inr" in wallet) else STARTING_INR_BALANCE
    usdt_bal = float(wallet.get("usdt", STARTING_USDT_BALANCE)) if (wallet and "usdt" in wallet) else STARTING_USDT_BALANCE

    has_holdings = bool(portfolio and any(float(h.get("quantity", 0)) > 0 for h in portfolio))
    has_txns = bool(transactions and len(transactions) > 0)
    if not has_holdings and not has_txns:
        inr_bal = STARTING_INR_BALANCE
        usdt_bal = STARTING_USDT_BALANCE

    w = query_db("SELECT user_id FROM wallet WHERE user_id = %s", (uid,), fetchone=True)
    if not w:
        query_db("INSERT INTO wallet (user_id, inr_balance, usdt_balance, cash_balance) VALUES (%s, %s, %s, %s)",
                 (uid, inr_bal, usdt_bal, inr_bal), commit=True)
    elif wallet or (not has_holdings and not has_txns):
        query_db("UPDATE wallet SET inr_balance = %s, usdt_balance = %s, cash_balance = %s WHERE user_id = %s",
                 (inr_bal, usdt_bal, inr_bal, uid), commit=True)

    if portfolio and isinstance(portfolio, list):
        for h in portfolio:
            if isinstance(h, dict) and h.get("symbol") and float(h.get("quantity", 0)) > 0:
                query_db("""
                INSERT INTO portfolio (user_id, symbol, asset_type, asset_name, currency, quantity, average_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, asset_type) DO UPDATE SET
                    quantity = EXCLUDED.quantity, average_price = EXCLUDED.average_price, updated_at = CURRENT_TIMESTAMP
                """ if _IS_POSTGRES else """
                INSERT OR REPLACE INTO portfolio (user_id, symbol, asset_type, asset_name, currency, quantity, average_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (uid, str(h["symbol"]).upper().strip(), str(h.get("asset_type", "stock")),
                      str(h.get("asset_name", h["symbol"])), str(h.get("currency", "INR")),
                      float(h["quantity"]), float(h.get("average_price", 0))), commit=True)

    if transactions and isinstance(transactions, list):
        for tx in transactions:
            if isinstance(tx, dict) and tx.get("symbol"):
                query_db("""
                INSERT INTO transactions (user_id, symbol, asset_type, asset_name, currency, trade_type, quantity, price, total_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (uid, tx["symbol"], tx.get("asset_type", "stock"), tx.get("asset_name", tx["symbol"]),
                      tx.get("currency", "INR"), tx.get("trade_type") or tx.get("side", "BUY"),
                      float(tx.get("quantity", 0)), float(tx.get("price", 0)),
                      float(tx.get("total_amount", 0))), commit=True)

    if watchlist and isinstance(watchlist, list):
        for item in watchlist:
            sym = item.get("symbol") if isinstance(item, dict) else str(item)
            atype = item.get("asset_type", "stock") if isinstance(item, dict) else "stock"
            if sym:
                toggle_watchlist(uid, sym, atype)

    return uid


# ==============================================================================
# SECTION 3: RESILIENT REDIS CACHE & MARKET API ENGINE (<20ms LATENCY TARGET)
# ==============================================================================
REDIS_URL = os.environ.get("REDIS_URL")
_REDIS_CLIENT = None
_REDIS_POOL = None

# Cache TTL Configurations (in seconds)
STOCK_CACHE_TTL = 30       # quote:stock:{SYMBOL} -> TTL: 30s
CRYPTO_CACHE_TTL = 15      # quote:crypto:{COIN_ID} -> TTL: 15s
HISTORY_CACHE_TTL = 300    # history:{SYMBOL}:{INTERVAL} -> TTL: 300s (5m)

CRYPTO_COIN_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "MATIC": "matic-network",
    "POL": "matic-network",
}

def get_stock_cache_key(symbol: str) -> str:
    """Generate standard Redis key for stock quote: quote:stock:{SYMBOL}"""
    return f"quote:stock:{symbol.upper().strip()}"

def get_crypto_cache_key(coin_id_or_symbol: str) -> str:
    """Generate standard Redis key for crypto quote: quote:crypto:{COIN_ID}"""
    cleaned = str(coin_id_or_symbol).strip()
    coin_id = CRYPTO_COIN_MAP.get(cleaned.upper(), cleaned.lower())
    return f"quote:crypto:{coin_id}"

def get_history_cache_key(symbol: str, interval: str) -> str:
    """Generate standard Redis key for chart history: history:{SYMBOL}:{INTERVAL}"""
    return f"history:{symbol.upper().strip()}:{interval.strip()}"

def get_redis_client():
    """
    Return a thread-safe singleton Redis client with connection pooling.
    If Redis is unconfigured or offline, returns None gracefully.
    """
    global _REDIS_CLIENT, _REDIS_POOL
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    redis_url = os.environ.get("REDIS_URL") or REDIS_URL
    if not redis_url:
        return None

    try:
        import redis
        _REDIS_POOL = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            retry_on_timeout=False,
            max_connections=20
        )
        _REDIS_CLIENT = redis.Redis(connection_pool=_REDIS_POOL)
        return _REDIS_CLIENT
    except Exception as e:
        logger.warning(f"Redis initialization warning (falling back gracefully): {e}")
        return None

def is_redis_available() -> bool:
    """
    Resilient connection health check helper.
    Returns True if Redis is reachable and responding to PING, False otherwise.
    """
    try:
        client = get_redis_client()
        if client is None:
            return False
        return bool(client.ping())
    except Exception:
        return False

def redis_get(key: str):
    """Safely fetch and deserialize JSON from Redis. Returns None on miss or failure."""
    try:
        client = get_redis_client()
        if client is not None:
            val = client.get(key)
            if val is not None:
                return json.loads(val)
    except Exception as e:
        logger.debug(f"Redis GET bypassed for {key} (falling back): {e}")
    return None

def redis_setex(key: str, ttl: int, value) -> bool:
    """Safely serialize and store value in Redis with TTL. Returns True on success, False on failure."""
    try:
        client = get_redis_client()
        if client is not None:
            serialized = json.dumps(value) if not isinstance(value, str) else value
            return bool(client.setex(key, int(ttl), serialized))
    except Exception as e:
        logger.debug(f"Redis SETEX bypassed for {key} (falling back): {e}")
    return False

class CandleList(list):
    """
    A list of candle dictionaries with caching metadata and dict-like accessor compatibility.
    Guarantees backwards-compatibility whether accessed as a list or checked for .cached / ['cached'].
    """
    def __init__(self, items=None, cached=False):
        super().__init__(items or [])
        self.cached = bool(cached)

    def __getitem__(self, item):
        if item == "cached":
            return self.cached
        if item == "candles":
            return list(self)
        return super().__getitem__(item)

    def get(self, key, default=None):
        if key == "cached":
            return self.cached
        if key == "candles":
            return list(self)
        return default

_PRICE_CACHE = {}      # symbol -> {"data": dict, "ts": float}
_CANDLE_CACHE = {}     # key -> {"candles": list, "ts": float}
CACHE_TTL = 10         # Fallback in-memory cache TTL (seconds)

_session = requests.Session()
_session.headers.update({"User-Agent": "TradeVerse-MarketEngine/3.0"})

CUSTOM_MARKET_API_URL = os.environ.get("CUSTOM_MARKET_API_URL")

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "db17ushr01qhkqh8lr2gdb17ushr01qhkqh8lr30").strip()
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "a39be725ae064a3584d9be4d2fb8460e").strip()
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "CG-MVjPXU83MGtQ1BHYdjXmcAXZ").strip()

BASE_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "market": "India", "currency": "INR", "price": 1257.50, "change": 0.84, "sector": "Energy"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "market": "India", "currency": "INR", "price": 3920.00, "change": -0.31, "sector": "Technology"},
    {"symbol": "INFY.NS", "name": "Infosys", "market": "India", "currency": "INR", "price": 1840.75, "change": 1.18, "sector": "Technology"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "market": "India", "currency": "INR", "price": 1660.20, "change": 0.47, "sector": "Financials"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "market": "India", "currency": "INR", "price": 1235.40, "change": -0.19, "sector": "Financials"},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "market": "India", "currency": "INR", "price": 965.50, "change": 0.55, "sector": "Automotive"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "market": "India", "currency": "INR", "price": 782.30, "change": -0.42, "sector": "Financials"},
    {"symbol": "AAPL", "name": "Apple", "market": "Global", "currency": "USDT", "price": 217.96, "change": 1.42, "sector": "Technology"},
    {"symbol": "MSFT", "name": "Microsoft", "market": "Global", "currency": "USDT", "price": 521.30, "change": 0.67, "sector": "Technology"},
    {"symbol": "NVDA", "name": "NVIDIA", "market": "Global", "currency": "USDT", "price": 181.36, "change": 2.26, "sector": "Semiconductors"},
    {"symbol": "TSLA", "name": "Tesla", "market": "Global", "currency": "USDT", "price": 328.11, "change": -1.04, "sector": "Automotive"},
    {"symbol": "AMZN", "name": "Amazon", "market": "Global", "currency": "USDT", "price": 223.47, "change": 0.36, "sector": "Consumer"},
    {"symbol": "GOOGL", "name": "Alphabet (Google)", "market": "Global", "currency": "USDT", "price": 178.20, "change": 0.95, "sector": "Technology"},
]

BASE_CRYPTO = [
    {"symbol": "BTC", "name": "Bitcoin", "currency": "USDT", "price": 86500.00, "change": 1.86, "rank": 1},
    {"symbol": "ETH", "name": "Ethereum", "currency": "USDT", "price": 3250.00, "change": 0.73, "rank": 2},
    {"symbol": "BNB", "name": "BNB", "currency": "USDT", "price": 620.00, "change": 1.15, "rank": 4},
    {"symbol": "SOL", "name": "Solana", "currency": "USDT", "price": 195.00, "change": -0.48, "rank": 5},
    {"symbol": "XRP", "name": "XRP", "currency": "USDT", "price": 2.45, "change": 2.03, "rank": 3},
    {"symbol": "DOGE", "name": "Dogecoin", "currency": "USDT", "price": 0.22, "change": 3.40, "rank": 7},
    {"symbol": "ADA", "name": "Cardano", "currency": "USDT", "price": 0.85, "change": -0.90, "rank": 9},
    {"symbol": "MATIC", "name": "Polygon (POL)", "currency": "USDT", "price": 0.49, "change": -1.12, "rank": 28},
]


def get_currency_for_asset(symbol, asset_type):
    if asset_type == "crypto":
        return "USDT"
    upper = symbol.upper().strip()
    return "INR" if upper.endswith(".NS") or upper.endswith(".BO") else "USDT"


def fetch_custom_quote(symbol, asset_type):
    """
    Fetch live market quote using Cache-Aside pattern (<20ms cache latency target).
    1. Check Redis cache:
       - quote:stock:{SYMBOL} (TTL: 30s)
       - quote:crypto:{COIN_ID} (TTL: 15s)
       If hit, returns immediately with 'cached': True.
    2. If miss or Redis unavailable, fall back to in-memory cache or fetch external APIs.
    3. On successful fetch, write to Redis with SETEX and the corresponding TTL.
    """
    sym = symbol.upper().strip()
    now = time.time()

    # Step 1: Check Redis Cache First (<20ms)
    primary_redis_key = get_crypto_cache_key(sym) if asset_type == "crypto" else get_stock_cache_key(sym)
    alt_redis_key = f"quote:crypto:{sym}" if asset_type == "crypto" else None

    cached_quote = redis_get(primary_redis_key)
    if not cached_quote and alt_redis_key and alt_redis_key != primary_redis_key:
        cached_quote = redis_get(alt_redis_key)

    if cached_quote and isinstance(cached_quote, dict):
        res = cached_quote.copy()
        res["cached"] = True
        _PRICE_CACHE[sym] = {"data": res.copy(), "ts": now}
        return res

    # Fallback: In-memory cache
    if sym in _PRICE_CACHE and (now - _PRICE_CACHE[sym]["ts"] < CACHE_TTL):
        res = _PRICE_CACHE[sym]["data"].copy()
        res["cached"] = True
        return res

    # Step 2: Cache Miss / Redis Down -> Fetch Live API
    currency = get_currency_for_asset(sym, asset_type)
    baseline = next((item.copy() for item in (BASE_CRYPTO if asset_type == "crypto" else BASE_STOCKS) if item["symbol"] == sym), None)

    res = None

    # 1. Custom Market API if configured
    if CUSTOM_MARKET_API_URL:
        try:
            resp = _session.get(f"{CUSTOM_MARKET_API_URL}?symbol={sym}&type={asset_type}", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if "price" in data:
                    res = {
                        "symbol": sym,
                        "name": data.get("name", baseline["name"] if baseline else sym),
                        "price": float(data["price"]),
                        "change": float(data.get("change", 0.0)),
                        "currency": currency,
                        "market": data.get("market", "Custom Feed"),
                        "source": "Custom API",
                    }
        except Exception:
            pass

    # 2. Live Market APIs: CoinGecko, Finnhub, Twelve Data, Binance, Yahoo Finance
    if not res:
        if asset_type == "crypto":
            # Primary Crypto Feed: CoinGecko API with key
            coin_id = CRYPTO_COIN_MAP.get(sym, sym.lower())
            if COINGECKO_API_KEY and coin_id:
                try:
                    headers = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY.startswith("CG-") else {"x-cg-pro-api-key": COINGECKO_API_KEY}
                    resp = _session.get(
                        f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true",
                        headers=headers,
                        timeout=2.5
                    )
                    if resp.status_code == 200:
                        cg_data = resp.json().get(coin_id, {})
                        if "usd" in cg_data:
                            c_p = float(cg_data["usd"])
                            res = {
                                "symbol": sym,
                                "name": baseline["name"] if baseline else sym,
                                "price": round(c_p, 4 if c_p < 1 else 2),
                                "change": round(float(cg_data.get("usd_24h_change", 0.0)), 2),
                                "currency": "USDT",
                                "source": "CoinGecko API",
                            }
                except Exception:
                    pass

            # Secondary Crypto Feed: Binance Live Ticker
            if not res:
                try:
                    resp = _session.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT", timeout=1.8)
                    if resp.status_code == 200:
                        p = resp.json()
                        price = float(p["lastPrice"])
                        res = {
                            "symbol": sym,
                            "name": baseline["name"] if baseline else sym,
                            "price": round(price, 4 if price < 1 else 2),
                            "change": round(float(p.get("priceChangePercent", 0)), 2),
                            "currency": "USDT",
                            "source": "Binance Live",
                        }
                except Exception:
                    pass

            # Tertiary Crypto Feed: Finnhub Crypto
            if not res and FINNHUB_API_KEY:
                try:
                    resp = _session.get(
                        f"https://finnhub.io/api/v1/quote?symbol=BINANCE:{sym}USDT&token={FINNHUB_API_KEY}",
                        timeout=2.0
                    )
                    if resp.status_code == 200:
                        p = resp.json()
                        price = p.get("c")
                        if price and float(price) > 0:
                            res = {
                                "symbol": sym,
                                "name": baseline["name"] if baseline else sym,
                                "price": round(float(price), 4 if float(price) < 1 else 2),
                                "change": round(float(p.get("dp", 0.0)), 2),
                                "currency": "USDT",
                                "source": "Finnhub Crypto",
                            }
                except Exception:
                    pass
        else:
            # Equities / Stocks:
            # Primary Global Stock Feed: Finnhub API
            if FINNHUB_API_KEY and not (sym.endswith(".NS") or sym.endswith(".BO")):
                try:
                    resp = _session.get(
                        f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_API_KEY}",
                        timeout=2.0
                    )
                    if resp.status_code == 200:
                        p = resp.json()
                        price = p.get("c")
                        if price and float(price) > 0:
                            res = {
                                "symbol": sym,
                                "name": baseline["name"] if baseline else sym,
                                "price": round(float(price), 2),
                                "change": round(float(p.get("dp", 0.0)), 2),
                                "currency": currency,
                                "market": "Global",
                                "source": "Finnhub API",
                            }
                except Exception:
                    pass

            # Secondary Global Stock Feed: Twelve Data API
            if not res and TWELVE_DATA_API_KEY and not (sym.endswith(".NS") or sym.endswith(".BO")):
                try:
                    resp = _session.get(
                        f"https://api.twelvedata.com/quote?symbol={sym}&apikey={TWELVE_DATA_API_KEY}",
                        timeout=2.0
                    )
                    if resp.status_code == 200:
                        p = resp.json()
                        close_p = p.get("close")
                        if close_p and p.get("status") != "error":
                            res = {
                                "symbol": sym,
                                "name": baseline["name"] if baseline else (p.get("name") or sym),
                                "price": round(float(close_p), 2),
                                "change": round(float(p.get("percent_change", 0.0)), 2),
                                "currency": currency,
                                "market": "Global",
                                "source": "Twelve Data API",
                            }
                except Exception:
                    pass

            # Equities Feed (Indian stocks / Fallback): Yahoo Finance
            if not res:
                try:
                    resp = _session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d", timeout=2.0)
                    if resp.status_code == 200:
                        chart = resp.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                        price = chart.get("regularMarketPrice")
                        if price:
                            prev = chart.get("chartPreviousClose") or price
                            chg = ((float(price) - float(prev)) / float(prev) * 100) if prev else 0.0
                            res = {
                                "symbol": sym,
                                "name": baseline["name"] if baseline else sym,
                                "price": round(float(price), 2),
                                "change": round(chg, 2),
                                "currency": currency,
                                "market": "India" if currency == "INR" else "Global",
                                "source": "Yahoo Finance (Free Feed - 10-15m Delay)",
                            }
                except Exception:
                    pass

    if not res:
        res = baseline or {
            "symbol": sym,
            "name": sym,
            "price": 100.0,
            "change": 0.0,
            "currency": currency,
            "source": "Calibrated Baseline",
        }

    # Step 3: Write to Redis with SETEX using specified TTL
    ttl = CRYPTO_CACHE_TTL if asset_type == "crypto" else STOCK_CACHE_TTL
    cache_payload = res.copy()
    cache_payload["cached"] = True
    redis_setex(primary_redis_key, ttl, cache_payload)
    if alt_redis_key and alt_redis_key != primary_redis_key:
        redis_setex(alt_redis_key, ttl, cache_payload)

    # Update In-Memory fallback cache
    _PRICE_CACHE[sym] = {"data": res.copy(), "ts": now}

    res_out = res.copy()
    res_out["cached"] = False
    return res_out


def list_market(asset_type="stock", query="", market="All"):
    """Return all market assets refreshed with fast concurrency."""
    assets = [item.copy() for item in (BASE_CRYPTO if asset_type == "crypto" else BASE_STOCKS)]
    q = query.lower().strip()
    if q:
        assets = [a for a in assets if q in a["symbol"].lower() or q in a["name"].lower()]
    if asset_type == "stock" and market and market != "All":
        assets = [a for a in assets if a.get("market") == market]

    def _enrich(item):
        try:
            live = fetch_custom_quote(item["symbol"], asset_type)
            item["price"] = live["price"]
            item["change"] = live["change"]
            item["currency"] = live.get("currency", item["currency"])
            item["source"] = live.get("source", "Market Feed")
        except Exception:
            pass
        return item

    with ThreadPoolExecutor(max_workers=min(len(assets) or 1, 8)) as ex:
        return list(ex.map(_enrich, assets))


def get_market_candles(symbol, asset_type, timeframe="1y"):
    """
    Fetch candlestick OHLC data for TradingView chart with Resilient Redis Cache-Aside.
    Cache Key: history:{SYMBOL}:{INTERVAL} -> TTL: 300 seconds (5 minutes)
    """
    sym = symbol.upper().strip()
    local_key = f"{sym}:{asset_type}:{timeframe}"
    history_key = get_history_cache_key(sym, timeframe)
    now = time.time()

    # Step 1: Check Redis Cache First (<20ms)
    cached_history = redis_get(history_key)
    if cached_history:
        candles_list = cached_history if isinstance(cached_history, list) else cached_history.get("candles", [])
        if candles_list:
            _CANDLE_CACHE[local_key] = {"candles": candles_list, "ts": now}
            return CandleList(candles_list, cached=True)

    # Fallback: In-memory cache
    if local_key in _CANDLE_CACHE and (now - _CANDLE_CACHE[local_key]["ts"] < 60):
        return CandleList(_CANDLE_CACHE[local_key]["candles"], cached=True)

    candles = []
    interval = "1d"
    if asset_type == "crypto":
        # 1. Primary: CoinGecko OHLC API
        coin_id = CRYPTO_COIN_MAP.get(sym, sym.lower())
        if COINGECKO_API_KEY and coin_id:
            try:
                cg_days = 30 if timeframe == "1mo" else (7 if timeframe == "1w" else (1 if timeframe in ("1d", "24h") else 365))
                headers = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY.startswith("CG-") else {"x-cg-pro-api-key": COINGECKO_API_KEY}
                resp = _session.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={cg_days}",
                    headers=headers,
                    timeout=3.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        for bar in data:
                            if len(bar) >= 5:
                                t = datetime.fromtimestamp(bar[0] / 1000).strftime("%Y-%m-%d")
                                c = float(bar[4])
                                dec = 4 if c < 1 else 2
                                candles.append({
                                    "time": t,
                                    "open": round(float(bar[1]), dec),
                                    "high": round(float(bar[2]), dec),
                                    "low": round(float(bar[3]), dec),
                                    "close": round(c, dec),
                                })
            except Exception:
                pass

        # 2. Secondary: Binance klines
        if not candles:
            try:
                limit = 100
                if timeframe in ("1m", "5m", "15m", "1h"):
                    interval = timeframe
                resp = _session.get(f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval={interval}&limit={limit}", timeout=2.5)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data:
                        t = int(item[0] / 1000) if timeframe in ("1m", "5m", "15m", "1h") else datetime.fromtimestamp(item[0] / 1000).strftime("%Y-%m-%d")
                        c = float(item[4])
                        dec = 4 if c < 1 else 2
                        candles.append({
                            "time": t, "open": round(float(item[1]), dec),
                            "high": round(float(item[2]), dec), "low": round(float(item[3]), dec),
                            "close": round(c, dec),
                        })
            except Exception:
                pass
    else:
        # Stock:
        # 1. Primary: Twelve Data time_series for Global Stocks
        if TWELVE_DATA_API_KEY and not (sym.endswith(".NS") or sym.endswith(".BO")):
            try:
                resp = _session.get(
                    f"https://api.twelvedata.com/time_series?symbol={sym}&interval=1day&outputsize=45&apikey={TWELVE_DATA_API_KEY}",
                    timeout=3.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    values = data.get("values", [])
                    if values and isinstance(values, list):
                        for v in reversed(values):
                            candles.append({
                                "time": v["datetime"].split(" ")[0],
                                "open": round(float(v["open"]), 2),
                                "high": round(float(v["high"]), 2),
                                "low": round(float(v["low"]), 2),
                                "close": round(float(v["close"]), 2),
                            })
            except Exception:
                pass

        # 2. Secondary: Yahoo Finance
        if not candles:
            try:
                resp = _session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=3mo", timeout=2.5)
                if resp.status_code == 200:
                    data = resp.json()["chart"]["result"][0]
                    ts = data.get("timestamp", [])
                    q = data.get("indicators", {}).get("quote", [{}])[0]
                    for t, o, h, l, c in zip(ts, q.get("open", []), q.get("high", []), q.get("low", []), q.get("close", [])):
                        if None not in (o, h, l, c):
                            candles.append({
                                "time": datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
                                "open": round(float(o), 2), "high": round(float(h), 2),
                                "low": round(float(l), 2), "close": round(float(c), 2),
                            })
            except Exception:
                pass

    # High-accuracy procedural fallback if network drops
    if not candles:
        quote = fetch_custom_quote(sym, asset_type)
        cur_p = quote["price"]
        seed = sum(ord(c) for c in sym)
        p = cur_p * 0.95
        for i in range(45):
            drift = (((seed + i * 13) % 17) - 8) / 200
            op = p
            cp = max(0.01, op * (1 + drift))
            hp = max(op, cp) * 1.01
            lp = min(op, cp) * 0.99
            candles.append({
                "time": (date.today() - timedelta(days=45 - i)).isoformat(),
                "open": round(op, 2), "high": round(hp, 2), "low": round(lp, 2), "close": round(cp, 2),
            })
            p = cp

    # Step 3: Write to Redis with SETEX (TTL: 300 seconds / 5 minutes)
    if candles:
        redis_setex(history_key, HISTORY_CACHE_TTL, candles)
        if interval != timeframe:
            redis_setex(get_history_cache_key(sym, interval), HISTORY_CACHE_TTL, candles)

    _CANDLE_CACHE[local_key] = {"candles": candles, "ts": now}
    return CandleList(candles, cached=False)


# ==============================================================================
# SECTION 4: ATOMIC TRADING ENGINE
# ==============================================================================
def format_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"


def execute_trade(user_id, symbol, asset_type, asset_name, side, quantity, price):
    """Atomically apply a BUY or SELL order to the wallet, portfolio, ledger, and closed_trades."""
    sym = symbol.upper().strip()
    side = side.upper().strip()
    qty = float(quantity)
    prc = float(price)
    total_cost = round(qty * prc, 2)
    currency = get_currency_for_asset(sym, asset_type)

    if side not in {"BUY", "SELL"}:
        raise ValueError("Invalid trade side. Must be BUY or SELL.")
    if qty <= 0 or prc <= 0:
        raise ValueError("Quantity and price must be greater than zero.")

    with get_db() as conn:
        cursor = conn.cursor()
        def run_q(sql, params=()):
            q = sql if _IS_POSTGRES else sql.replace("%s", "?")
            cursor.execute(q, params)
            return cursor

        if not _IS_POSTGRES:
            cursor.execute("BEGIN IMMEDIATE")

        # 1. Fetch current wallet
        run_q("SELECT inr_balance, usdt_balance FROM wallet WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            raise ValueError("Virtual wallet not found.")
        w_row = dict(row) if hasattr(row, "keys") else {"inr_balance": row[0], "usdt_balance": row[1]}
        curr_bal = float(w_row["inr_balance"]) if currency == "INR" else float(w_row["usdt_balance"])

        # 2. Fetch current holding
        run_q("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s AND asset_type = %s",
              (user_id, sym, asset_type))
        h_row = cursor.fetchone()
        holding = (dict(h_row) if hasattr(h_row, "keys") else dict(zip([c[0] for c in cursor.description], h_row))) if h_row else None

        if side == "BUY":
            if total_cost > curr_bal + 0.0001:
                conn.rollback()
                cur_label = "₹ INR" if currency == "INR" else "USDT"
                raise ValueError(f"Insufficient virtual {cur_label} balance for this order.")

            if currency == "INR":
                run_q("UPDATE wallet SET inr_balance = inr_balance - %s, cash_balance = inr_balance - %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                      (total_cost, total_cost, user_id))
            else:
                run_q("UPDATE wallet SET usdt_balance = usdt_balance - %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                      (total_cost, user_id))

            if holding:
                old_qty = float(holding["quantity"])
                old_avg = float(holding["average_price"])
                new_qty = old_qty + qty
                new_avg = ((old_qty * old_avg) + total_cost) / new_qty
                run_q("UPDATE portfolio SET quantity = %s, average_price = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                      (new_qty, new_avg, user_id, sym, asset_type))
            else:
                run_q("INSERT INTO portfolio (user_id, symbol, asset_type, asset_name, currency, quantity, average_price) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      (user_id, sym, asset_type, asset_name, currency, qty, prc))

        else:  # SELL
            if not holding or float(holding["quantity"]) + 0.0000001 < qty:
                conn.rollback()
                raise ValueError("Cannot sell more units than you currently hold.")

            rem_qty = float(holding["quantity"]) - qty
            buy_price = float(holding["average_price"])
            realized_pnl = round((prc - buy_price) * qty, 2)
            realized_pnl_pct = round(((prc - buy_price) / buy_price) * 100, 2) if buy_price > 0 else 0.0

            if currency == "INR":
                run_q("UPDATE wallet SET inr_balance = inr_balance + %s, cash_balance = inr_balance + %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                      (total_cost, total_cost, user_id))
            else:
                run_q("UPDATE wallet SET usdt_balance = usdt_balance + %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                      (total_cost, user_id))

            run_q("""
            INSERT INTO closed_trades (user_id, symbol, asset_type, asset_name, currency, quantity, buy_price, sell_price, duration_seconds, duration_formatted, realized_pnl, realized_pnl_percent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, sym, asset_type, asset_name, currency, qty, buy_price, prc, 60, "1m", realized_pnl, realized_pnl_pct))

            if rem_qty <= 0.0000001:
                run_q("DELETE FROM portfolio WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                      (user_id, sym, asset_type))
            else:
                run_q("UPDATE portfolio SET quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                      (rem_qty, user_id, sym, asset_type))

        # Ledger transaction
        run_q("""
        INSERT INTO transactions (user_id, symbol, asset_type, asset_name, currency, trade_type, quantity, price, total_amount)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, sym, asset_type, asset_name, currency, side, qty, prc, total_cost))

        conn.commit()

    w_now = get_wallet(user_id)
    return {
        "ok": True,
        "symbol": sym,
        "side": side,
        "quantity": qty,
        "price": prc,
        "total_amount": total_cost,
        "currency": currency,
        "inr_balance": w_now["inr"],
        "usdt_balance": w_now["usdt"],
        "message": f"Successfully {side.lower()}ed {qty} {sym} @ {prc} {currency}",
    }


def calculate_portfolio(user_id):
    """Aggregate portfolio holdings with live quote values and profit/loss metrics."""
    wallet = get_wallet(user_id)
    rows = query_db("SELECT * FROM portfolio WHERE user_id = %s ORDER BY updated_at DESC", (user_id,), fetchall=True) or []
    holdings = []
    inr_val = 0.0
    usdt_val = 0.0
    inr_cost = 0.0
    usdt_cost = 0.0

    for r in rows:
        qty = float(r["quantity"])
        if qty <= 0.0000001:
            continue
        sym = r["symbol"]
        atype = r["asset_type"]
        cur = r.get("currency") or get_currency_for_asset(sym, atype)
        quote = fetch_custom_quote(sym, atype)
        cur_p = float(quote["price"]) if quote else float(r["average_price"])
        avg_p = float(r["average_price"])
        cost = qty * avg_p
        val = qty * cur_p
        pnl = val - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0

        if cur == "INR":
            inr_cost += cost
            inr_val += val
        else:
            usdt_cost += cost
            usdt_val += val

        holdings.append({
            **r,
            "currency": cur,
            "current_price": cur_p,
            "cost_basis": cost,
            "current_value": val,
            "profit_loss": pnl,
            "profit_loss_percent": pnl_pct,
            "change": quote.get("change", 0.0),
        })

    return {
        "wallet": wallet,
        "holdings": holdings,
        "total_holdings_count": len(holdings),
        "inr_total_cost": inr_cost,
        "inr_total_value": inr_val,
        "inr_profit_loss": inr_val - inr_cost,
        "inr_profit_loss_percent": ((inr_val - inr_cost) / inr_cost * 100) if inr_cost else 0.0,
        "inr_net_worth": wallet["inr"] + inr_val,
        "usdt_total_cost": usdt_cost,
        "usdt_total_value": usdt_val,
        "usdt_profit_loss": usdt_val - usdt_cost,
        "usdt_profit_loss_percent": ((usdt_val - usdt_cost) / usdt_cost * 100) if usdt_cost else 0.0,
        "usdt_net_worth": wallet["usdt"] + usdt_val,
    }


# ==============================================================================
# SECTION 5: PORTFOLIO & LEDGER QUERIES
# ==============================================================================
def get_database_path():
    return get_sqlite_path()


def get_portfolio_rows(user_id):
    if _IS_POSTGRES:
        sql = """SELECT *, EXTRACT(EPOCH FROM (NOW() - COALESCE(opened_at, updated_at)))::INTEGER AS age_seconds
                 FROM portfolio WHERE user_id = %s AND quantity > 0.0000001 ORDER BY updated_at DESC"""
    else:
        sql = """SELECT *, CAST((julianday('now') - julianday(COALESCE(opened_at, updated_at))) * 86400 AS INTEGER) AS age_seconds
                 FROM portfolio WHERE user_id = %s AND quantity > 0.0000001 ORDER BY updated_at DESC"""
    return query_db(sql, (user_id,), fetchall=True) or []


def get_closed_trades(user_id, limit=50):
    return query_db("SELECT * FROM closed_trades WHERE user_id = %s ORDER BY sell_time DESC, id DESC LIMIT %s",
                    (user_id, limit), fetchall=True) or []


def get_transactions(user_id, limit=20):
    return query_db("SELECT * FROM transactions WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
                    (user_id, limit), fetchall=True) or []


def get_all_users():
    return query_db("SELECT id, full_name, created_at FROM users ORDER BY id ASC", fetchall=True) or []


def get_learning_modules():
    return [
        {"id": 1, "title": "Paper trading, without pretend confidence", "category": "Beginner guide", "read_time": "7 min read", "difficulty": "Beginner", "image_path": "learning-market-basics.png", "description": "Learn order flow, virtual wallet, and risk checking before a trade.", "content": "Treat every virtual order as an opportunity to practice position sizing."},
        {"id": 2, "title": "Build a risk rule before a watchlist", "category": "Risk management", "read_time": "9 min read", "difficulty": "Beginner", "image_path": "learning-market-basics.png", "description": "Simple framework for trade size and loss limits.", "content": "Risk management starts before the buy button."},
        {"id": 3, "title": "Read a chart without chasing candles", "category": "Technical analysis", "read_time": "11 min read", "difficulty": "Intermediate", "image_path": "learning-market-basics.png", "description": "Trend, support, resistance, and volume as context.", "content": "Technical analysis is a language for probabilities."},
        {"id": 4, "title": "What a balance sheet is trying to tell you", "category": "Fundamental analysis", "read_time": "12 min read", "difficulty": "Intermediate", "image_path": "learning-market-basics.png", "description": "A friendly first look at revenue, margins, debt, and cash flow.", "content": "Fundamental analysis asks whether a business can create durable value."}
    ]


def get_quiz_questions():
    return [
        {"id": 1, "question": "What does diversification aim to reduce?", "options": ["Brokerage fees", "Single-asset risk", "The need for research", "Market opening hours"]},
        {"id": 2, "question": "When you buy more of a holding at a different price, what changes?", "options": ["Average price", "Ticker symbol", "Asset type", "Past transactions"]},
        {"id": 3, "question": "Why is a stop-loss plan useful in paper trading?", "options": ["It guarantees profit", "It helps define risk before a trade", "It removes volatility", "It predicts prices"]},
        {"id": 4, "question": "Which number compares a holding's market value with its purchase cost?", "options": ["Profit or loss", "Market cap", "Volume", "Spread"]},
        {"id": 5, "question": "A paper wallet in TradeVerse contains:", "options": ["Real bank funds", "Virtual trading credits", "Cryptographic keys", "Brokerage accounts"]}
    ]


def score_quiz(user_id, answers):
    answers_map = {"1": 1, "2": 0, "3": 1, "4": 0, "5": 1}
    questions = get_quiz_questions()
    score = 0
    feedback = []
    for q in questions:
        qid = str(q["id"])
        sel = answers.get(qid)
        correct_opt = answers_map.get(qid)
        is_corr = sel is not None and int(sel) == correct_opt
        score += int(is_corr)
        feedback.append({"question": q["question"], "is_correct": is_corr, "explanation": "Correct concept for risk and portfolio management."})
    return {"score": score, "total": len(questions), "feedback": feedback}


# ==============================================================================
# SECTION 6: WATCHLIST & ENGAGEMENT
# ==============================================================================
def get_watchlist(user_id):
    return query_db("SELECT * FROM watchlist WHERE user_id = %s ORDER BY created_at DESC", (user_id,), fetchall=True) or []


def toggle_watchlist(user_id, symbol, asset_type):
    sym = symbol.upper().strip()
    existing = query_db("SELECT id FROM watchlist WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                        (user_id, sym, asset_type), fetchone=True)
    if existing:
        query_db("DELETE FROM watchlist WHERE user_id = %s AND symbol = %s AND asset_type = %s",
                 (user_id, sym, asset_type), commit=True)
        return False
    else:
        query_db("INSERT INTO watchlist (user_id, symbol, asset_type) VALUES (%s, %s, %s)",
                 (user_id, sym, asset_type), commit=True)
        return True


def remove_watchlist_item(user_id, symbol, asset_type):
    query_db("DELETE FROM watchlist WHERE user_id = %s AND symbol = %s AND asset_type = %s",
             (user_id, symbol.upper().strip(), asset_type), commit=True)
    return True


# ==============================================================================
# SECTION 6: AUTHENTIC VECTOR ICONS
# ==============================================================================
SVGS = {
    # Cryptocurrencies
    "BTC": '<circle cx="16" cy="16" r="16" fill="#F7931A"/><path fill="#FFF" d="M23.1 14c.3-2-1.2-3.2-3.4-3.9l.7-2.8-1.7-.4-.7 2.7c-.5-.1-.9-.2-1.4-.3l.7-2.8-1.7-.4-.7 2.8c-.4-.1-.7-.2-1.1-.3l-2.4-.6-.5 1.8s1.3.3 1.2.3c.7.2.8.6.8 1l-.8 3.2v.1l-1.1 4.5c-.1.2-.3.5-.8.4 0 0-1.3-.3-1.3-.3l-.8 2 2.2.5c.4.1.8.2 1.2.3l-.7 2.9 1.7.4.7-2.8c.5.1.9.2 1.4.3l-.7 2.8 1.7.4.7-2.8c2.9.5 5.1.3 6-2.3.8-2.1 0-3.4-1.5-4.2 1.1-.3 1.9-1 2.2-2.5zm-3.9 5.5c-.5 2.1-4.1 1-5.3.7l.9-3.8c1.2.3 4.9.9 4.4 3.1zm.5-5.5c-.5 2-3.5 1-4.5.7l.9-3.5c1 .2 4.1.7 3.6 2.8z"/>',
    "ETH": '<circle cx="16" cy="16" r="16" fill="#627EEA"/><g fill="#FFF"><polygon fill-opacity=".6" points="16 4 16 16.3 23 13.2"/><polygon points="16 4 9 13.2 16 16.3"/><polygon fill-opacity=".6" points="16 22 16 28 23 18.2"/><polygon points="16 22 9 18.2 16 28"/><polygon fill-opacity=".2" points="16 16.3 23 13.2 16 10.1"/><polygon fill-opacity=".4" points="9 13.2 16 16.3 16 10.1"/></g>',
    "SOL": '<circle cx="16" cy="16" r="16" fill="#13151D"/><path fill="#00FFA3" d="M9.5 21.7c.1-.1.3-.2.5-.2h12.5c.3 0 .5.3.3.6l-2.3 2.3c-.1.1-.3.2-.5.2H7.5c-.3 0-.5-.3-.3-.6l2.3-2.3zm0-11.4c.1-.1.3-.2.5-.2h12.5c.3 0 .5.3.3.6l-2.3 2.3c-.1.1-.3.2-.5.2H7.5c-.3 0-.5-.3-.3-.6l2.3-2.3zm13 5.7c-.1-.1-.3-.2-.5-.2H9.5c-.3 0-.5.3-.3.6l2.3 2.3c.1.1.3.2.5.2h12.5c.3 0 .5-.3.3-.6l-2.3-2.3z"/>',
    "BNB": '<circle cx="16" cy="16" r="16" fill="#F3BA2F"/><g fill="#FFF"><polygon points="16 7 19.2 10.2 16 13.4 12.8 10.2"/><polygon points="22.2 13.4 25.4 16.6 22.2 19.8 19 16.6"/><polygon points="9.8 13.4 13 16.6 9.8 19.8 6.6 16.6"/><polygon points="16 19.8 19.2 23 16 26.2 12.8 23"/><polygon points="16 14.8 17.8 16.6 16 18.4 14.2 16.6"/></g>',
    "XRP": '<circle cx="16" cy="16" r="16" fill="#23292F"/><path fill="#FFF" d="M23.8 8h2.3l-5.6 5.5-2.2-2.2 4.1-4c.4-.4.9-.7 1.4-.7v1.4zm-15.6 0h2.3l4.1 4-2.2 2.2L6.8 8.7c.4 0 .9.3 1.4.7zm0 16h2.3l9.8-9.6 2.2 2.2-7.8 7.4h-6.5zm15.6 0h-2.3l-4.1-4 2.2-2.2 4.2 4.1v2.1z"/>',
    "DOGE": '<circle cx="16" cy="16" r="16" fill="#C2A633"/><path fill="#FFF" d="M12 8.5h6c4.5 0 7.5 3 7.5 7.5s-3 7.5-7.5 7.5h-6V8.5zm3.5 12h2.2c2.5 0 4.2-1.7 4.2-4.5s-1.7-4.5-4.2-4.5h-2.2v9zm-6.5-5.2h8.5v2H9v-2z"/>',
    "ADA": '<circle cx="16" cy="16" r="16" fill="#0033AD"/><circle cx="16" cy="16" r="3.2" fill="#FFFFFF"/><circle cx="16" cy="8.5" r="1.5" fill="#FFFFFF"/><circle cx="16" cy="23.5" r="1.5" fill="#FFFFFF"/><circle cx="8.5" cy="16" r="1.5" fill="#FFFFFF"/><circle cx="23.5" cy="16" r="1.5" fill="#FFFFFF"/><circle cx="10.7" cy="10.7" r="1.2" fill="#FFFFFF"/><circle cx="21.3" cy="10.7" r="1.2" fill="#FFFFFF"/><circle cx="10.7" cy="21.3" r="1.2" fill="#FFFFFF"/><circle cx="21.3" cy="21.3" r="1.2" fill="#FFFFFF"/>',
    "MATIC": '<circle cx="16" cy="16" r="16" fill="#8247E5"/><path fill="#FFFFFF" d="M21.5 13.5l-3.8-2.2c-.4-.2-1-.2-1.4 0l-3.8 2.2c-.4.2-.7.8-.7 1.2v4.4c0 .5.3 1 .7 1.2l3.8 2.2c.4.2 1 .2 1.4 0l3.8-2.2c.4-.2.7-.8.7-1.2v-4.4c0-.5-.3-1-.7-1.2zm-2.4 4.5l-2.4 1.4c-.4.2-.9.2-1.3 0l-2.4-1.4c-.4-.2-.6-.6-.6-.9v-2.8c0-.4.2-.7.6-.9l2.4-1.4c.4-.2.9-.2 1.3 0l2.4 1.4c.4.2.6.6.6.9v2.8c0 .3-.2.7-.6.9z"/>',
    "POL": '<circle cx="16" cy="16" r="16" fill="#8247E5"/><path fill="#FFFFFF" d="M21.5 13.5l-3.8-2.2c-.4-.2-1-.2-1.4 0l-3.8 2.2c-.4.2-.7.8-.7 1.2v4.4c0 .5.3 1 .7 1.2l3.8 2.2c.4.2 1 .2 1.4 0l3.8-2.2c.4-.2.7-.8.7-1.2v-4.4c0-.5-.3-1-.7-1.2zm-2.4 4.5l-2.4 1.4c-.4.2-.9.2-1.3 0l-2.4-1.4c-.4-.2-.6-.6-.6-.9v-2.8c0-.4.2-.7.6-.9l2.4-1.4c.4-.2.9-.2 1.3 0l2.4 1.4c.4.2.6.6.6.9v2.8c0 .3-.2.7-.6.9z"/>',

    # Global Stocks
    "AAPL": '<circle cx="16" cy="16" r="16" fill="#1A1A1A"/><path fill="#FFFFFF" d="M19.3 7.8c-.8 1-1.9 1.6-3 1.5-.2-1.1.3-2.2 1-2.9.8-.9 2-1.5 3-1.4.1 1-.2 2.1-1 2.8z"/><path fill="#FFFFFF" d="M22.5 17.8c0-3.1 2.5-4.6 2.6-4.7-1.4-2.1-3.7-2.4-4.5-2.4-1.9-.2-3.8 1.1-4.8 1.1-1 0-2.5-1.1-4.1-1.1-2.1 0-4 1.2-5.1 3.1-2.2 3.8-.6 9.4 1.5 12.5 1 1.5 2.3 3.1 3.9 3 1.6-.1 2.2-1 4-1 1.9 0 2.4 1 4.1 1 1.7 0 2.8-1.5 3.8-3 1.2-1.8 1.7-3.5 1.7-3.6-.1 0-3.1-1.2-3.1-4.9z"/>',
    "MSFT": '<rect width="32" height="32" rx="7" fill="#1B1B1B"/><rect x="6.5" y="6.5" width="8.8" height="8.8" rx="1.2" fill="#F25022"/><rect x="16.7" y="6.5" width="8.8" height="8.8" rx="1.2" fill="#7FBA00"/><rect x="6.5" y="16.7" width="8.8" height="8.8" rx="1.2" fill="#00A4EF"/><rect x="16.7" y="16.7" width="8.8" height="8.8" rx="1.2" fill="#FFB900"/>',
    "NVDA": '<rect width="32" height="32" rx="7" fill="#000000"/><path fill="#76B900" d="M19.4 8.2c-5.7 0-9.8 4.2-9.8 8.6 0 5 4.3 8.3 9.4 8.3 3.8 0 7.4-1.8 9-4.8-1.2 2-4.4 3.4-7.5 3.4-4.2 0-7.3-2.6-7.3-6.5 0-3.6 2.8-6.9 7.4-6.9 2.5 0 4.8 1 5.9 2.7-.9-2.9-4.1-4.8-7.1-4.8z"/><path fill="#FFFFFF" d="M19.4 12.2c-2.8 0-4.8 2.1-4.8 4.3 0 2.4 2.1 4.1 4.7 4.1 1.9 0 3.8-.9 4.6-2.5-.7 1.1-2.4 1.8-3.9 1.8-2 0-3.5-1.3-3.5-3.2 0-1.8 1.4-3.4 3.6-3.4 1.2 0 2.5.5 3.1 1.4-.5-1.5-2.1-2.5-3.8-2.5z"/><circle cx="19.4" cy="16.8" r="1.3" fill="#FFFFFF"/>',
    "TSLA": '<circle cx="16" cy="16" r="16" fill="#E82127"/><path fill="#FFFFFF" d="M16 8.5c2.6 0 5.6.6 7.8 1.8l.9-2.5C22 6.5 19 5.8 16 5.8s-6 .7-8.7 2l.9 2.5c2.2-1.2 5.2-1.8 7.8-1.8z"/><path fill="#FFFFFF" d="M14.5 12.2v13.5h3V12.2c2.4.2 4.6.8 6 1.7l.8-2.5c-2.5-1.4-6.1-2-8.3-2s-5.8.6-8.3 2l.8 2.5c1.4-.9 3.6-1.5 6-1.7z"/>',
    "AMZN": '<rect width="32" height="32" rx="7" fill="#131921"/><text x="16" y="16.5" font-family="Arial" font-size="14" font-weight="900" fill="#FFFFFF" text-anchor="middle">a</text><path d="M8 20.2c4.8 3.2 11.2 3.2 16 0" stroke="#FF9900" stroke-width="2.2" stroke-linecap="round" fill="none"/><path d="M22.5 18.5l2.4 2.2-2.8.5z" fill="#FF9900"/>',
    "GOOGL": '<rect width="32" height="32" rx="7" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1"/><path fill="#4285F4" d="M24.8 16.3c0-.6-.1-1.3-.2-1.9H16v3.6h5c-.2 1.2-.9 2.2-1.9 2.9v2.4h3.1c1.8-1.7 2.6-4.1 2.6-7z"/><path fill="#34A853" d="M16 25.2c2.5 0 4.6-.8 6.1-2.3l-3.1-2.4c-.8.6-1.9.9-3 .9-2.3 0-4.3-1.6-5-3.7H7.7v2.5c1.6 3.1 4.7 5 8.3 5z"/><path fill="#FBBC05" d="M11 17.7c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V11.2H7.7C7.1 12.5 6.8 14 6.8 15.7s.3 3.2.9 4.5l3.3-2.5z"/><path fill="#EA4335" d="M16 9.8c1.4 0 2.6.5 3.6 1.4l2.7-2.7C20.6 6.9 18.5 6.2 16 6.2c-3.6 0-6.7 2-8.3 5.1l3.3 2.5c.7-2.2 2.7-4 5-4z"/>',
    "GOOG": '<rect width="32" height="32" rx="7" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1"/><path fill="#4285F4" d="M24.8 16.3c0-.6-.1-1.3-.2-1.9H16v3.6h5c-.2 1.2-.9 2.2-1.9 2.9v2.4h3.1c1.8-1.7 2.6-4.1 2.6-7z"/><path fill="#34A853" d="M16 25.2c2.5 0 4.6-.8 6.1-2.3l-3.1-2.4c-.8.6-1.9.9-3 .9-2.3 0-4.3-1.6-5-3.7H7.7v2.5c1.6 3.1 4.7 5 8.3 5z"/><path fill="#FBBC05" d="M11 17.7c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V11.2H7.7C7.1 12.5 6.8 14 6.8 15.7s.3 3.2.9 4.5l3.3-2.5z"/><path fill="#EA4335" d="M16 9.8c1.4 0 2.6.5 3.6 1.4l2.7-2.7C20.6 6.9 18.5 6.2 16 6.2c-3.6 0-6.7 2-8.3 5.1l3.3 2.5c.7-2.2 2.7-4 5-4z"/>',
    "META": '<circle cx="16" cy="16" r="16" fill="#0081FB"/><path fill="#FFFFFF" d="M24.8 11.2c-1.4 0-2.8.8-3.9 2.2-1.3-1.6-2.9-2.4-4.9-2.4-2.8 0-5.4 1.8-6.7 4.7-1.1 2.4-.6 5.1 1.1 6.8 1.4 1.4 3.4 2.1 5.6 2.1 2 0 3.7-.8 4.9-2.4 1.1 1.4 2.5 2.2 3.9 2.2 2.6 0 4.8-2.2 4.8-5.6 0-3.5-2.2-5.6-4.8-5.6zm-8.8 9.2c-1.7 0-3.1-.5-4.1-1.6-1-1-1.4-2.6-.7-4.2.9-2.1 2.8-3.4 4.8-3.4 1.5 0 2.8.7 3.8 2.1-2 3.5-2.8 5.7-3.8 7.1zm8.8-1.6c-1.2 0-2.3-.7-3.3-2 1.3-2.5 2.2-4.9 3.3-5.2 1.2 0 2.1 1.1 2.1 3.6 0 2.5-.9 3.6-2.1 3.6z"/>',
    "NFLX": '<rect width="32" height="32" rx="7" fill="#000000"/><path fill="#E50914" d="M9 7h3.2v18H9zM19.8 7H23v18h-3.2z"/><path fill="#B81D24" d="M9 7h3.5l7.5 18h-3.5z"/>',

    # Indian Stocks
    "RELIANCE": '<circle cx="16" cy="16" r="16" fill="#062544"/><circle cx="16" cy="16" r="14.2" fill="#003B73"/><circle cx="16" cy="16" r="12.5" fill="#062544"/><g transform="translate(16,16)"><g fill="#E63946"><ellipse cx="0" cy="-6.5" rx="1.8" ry="4"/><ellipse cx="0" cy="6.5" rx="1.8" ry="4"/><ellipse cx="-6.5" cy="0" rx="4" ry="1.8"/><ellipse cx="6.5" cy="0" rx="4" ry="1.8"/><ellipse cx="-4.6" cy="-4.6" rx="2" ry="3.8" transform="rotate(-45,-4.6,-4.6)"/><ellipse cx="4.6" cy="-4.6" rx="2" ry="3.8" transform="rotate(45,4.6,-4.6)"/><ellipse cx="-4.6" cy="4.6" rx="2" ry="3.8" transform="rotate(45,-4.6,4.6)"/><ellipse cx="4.6" cy="4.6" rx="2" ry="3.8" transform="rotate(-45,4.6,4.6)"/></g><circle cx="0" cy="0" r="3.4" fill="#FFD166" stroke="#062544" stroke-width="0.8"/><circle cx="0" cy="0" r="1.4" fill="#E63946"/></g>',
    "TCS": '<circle cx="16" cy="16" r="16" fill="#005A9C"/><path fill="#FFFFFF" d="M8 10h16c.6 0 1 .4 1 1s-.4 1-1 1h-6.8v9c0 .6-.4 1-1 1s-1-.4-1-1v-9H8c-.6 0-1-.4-1-1s.4-1 1-1z"/><path fill="#FFFFFF" d="M11.5 8.2c2.7-1.6 6.3-1.6 9 0-1.3.6-2.9.9-4.5.9s-3.2-.3-4.5-.9z"/><text x="16" y="27.5" font-family="Arial" font-size="6" font-weight="900" fill="#FFFFFF" text-anchor="middle" letter-spacing="1">TCS</text>',
    "INFY": '<rect width="32" height="32" rx="7" fill="#007CC3"/><text x="16" y="21" font-family="Arial" font-size="9" font-style="italic" font-weight="800" fill="#FFFFFF" text-anchor="middle" letter-spacing="-0.5">infosys</text><circle cx="16" cy="9.5" r="1.6" fill="#FFFFFF"/>',
    "HDFCBANK": '<rect width="32" height="32" rx="6" fill="#004C8F"/><rect x="9.5" y="9.5" width="13" height="13" fill="#FFFFFF"/><rect x="7" y="13.5" width="18" height="5" fill="#ED1C24"/><rect x="13.5" y="7" width="5" height="18" fill="#ED1C24"/><rect x="13.5" y="13.5" width="5" height="5" fill="#004C8F"/>',
    "ICICIBANK": '<circle cx="16" cy="16" r="16" fill="#A81D23"/><path fill="#F37021" d="M12.5 8c3.5-2.8 8.5-1.5 10.5 2 1.5 2.5 1.2 5.8-.8 8-2.2 2.4-5.8 3-8.4 1.2 2.4.4 5.2-.2 6.8-2 1.6-1.9 1.6-4.6.3-6.5-1.6-2.2-4.8-2.9-7.2-1.5z"/><circle cx="14" cy="12" r="2.2" fill="#FFFFFF"/><rect x="12.5" y="16" width="3" height="8" rx="1.2" fill="#FFFFFF"/>',
    "TATAMOTORS": '<circle cx="16" cy="16" r="16" fill="#0D3B66"/><ellipse cx="16" cy="16" rx="12" ry="9" fill="none" stroke="#FFFFFF" stroke-width="1.6"/><path fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" d="M9.5 13.5c1.8-2.5 4-3.5 6.5-3.5s4.7 1 6.5 3.5"/><path fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" d="M13 14c1 3.5 2 6.5 3 8.5 1-2 2-5 3-8.5"/>',
    "SBIN": '<circle cx="16" cy="16" r="16" fill="#0082CA"/><circle cx="16" cy="14" r="5.6" fill="#FFFFFF"/><rect x="14.2" y="14" width="3.6" height="12" rx="1" fill="#0082CA"/><circle cx="16" cy="14" r="3.2" fill="#0082CA"/>',
    "WIPRO": '<rect width="32" height="32" rx="7" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1"/><circle cx="16" cy="16" r="3.2" fill="#388E3C"/><circle cx="16" cy="9" r="2.2" fill="#D32F2F"/><circle cx="23" cy="16" r="2.2" fill="#1976D2"/><circle cx="16" cy="23" r="2.2" fill="#FBC02D"/><circle cx="9" cy="16" r="2.2" fill="#7B1FA2"/>',
    "ITC": '<rect width="32" height="32" rx="7" fill="#002D62"/><polygon points="16 7, 24 23, 8 23" fill="#D4AF37"/><polygon points="16 10, 22 22, 10 22" fill="#002D62"/><text x="16" y="20.5" font-family="Arial" font-size="5" font-weight="900" fill="#D4AF37" text-anchor="middle">ITC</text>',
    "BHARTIARTL": '<circle cx="16" cy="16" r="16" fill="#ED1C24"/><path fill="#FFFFFF" d="M12 11c-2.8 0-4.5 2-4.5 5.5s1.7 5.5 4.5 5.5c1.8 0 3.2-.8 4-2.2v2H19V11h-3v2c-.8-1.4-2.2-2-4-2zm1.2 8.5c-1.8 0-2.8-1.3-2.8-3s1-3 2.8-3 2.8 1.3 2.8 3-1 3-2.8 3z"/>',
    "KOTAKBANK": '<circle cx="16" cy="16" r="16" fill="#EE2726"/><path fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" d="M11 19c-2-2-2-5 0-7s5-2 7 0l2 2c2 2 5 2 7 0s2-5 0-7"/>',
}


def get_asset_icon_svg(asset_type, symbol, size=36):
    raw = symbol.upper().strip()
    sym = raw.split(".")[0]
    content = SVGS.get(sym) or SVGS.get(raw)
    if not content:
        # Fallback monogram badge
        char = sym[:2]
        color = "#007d70" if asset_type == "stock" else "#F7931A"
        content = f'<rect width="32" height="32" rx="8" fill="{color}"/><text x="16" y="21" font-family="Arial" font-size="12" font-weight="bold" fill="#FFF" text-anchor="middle">{char}</text>'
    svg = f'<svg viewBox="0 0 32 32" width="{size}" height="{size}">{content}</svg>'
    return Markup(svg)
