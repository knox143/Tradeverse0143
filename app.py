"""Flask routes and request handling for the TradeVerse paper trading platform."""

import os
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from pathlib import Path
import sys
import traceback
import json
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeSerializer

from api.crypto import generate_crypto_candles, get_crypto_quote, list_crypto
from api.icons import get_asset_svg, get_market_pair
from api.portfolio import calculate_leaderboard, calculate_portfolio
from api.stocks import generate_candles, get_stock_quote, list_stocks
from database import (
    STARTING_INR_BALANCE,
    STARTING_USDT_BALANCE,
    add_watchlist_item,
    create_user,
    execute_trade,
    get_closed_trades,
    get_learning_modules,
    get_portfolio_rows,
    get_quiz_questions,
    get_quiz_results,
    get_trade_timeline_stats,
    get_transactions,
    get_user_by_email,
    get_user_by_id,
    get_wallet,
    get_watchlist,
    init_database,
    is_serverless_env,
    is_watchlist_item,
    remove_watchlist_item,
    reset_password,
    reset_wallet,
    restore_user_to_db,
    score_quiz,
    toggle_watchlist_item,
    update_user_profile,
)


BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

# Enable ProxyFix so Flask recognizes HTTPS scheme and headers from Vercel's edge proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

secret_key = (
    os.environ.get("TRADEVERSE_SECRET_KEY")
    or os.environ.get("FLASK_SECRET_KEY")
    or os.environ.get("SECRET_KEY")
    or ""
).strip() or "tradeverse-secure-session-key-2026-production"

app.secret_key = secret_key
_is_sec = True if (is_serverless_env() or os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) else False
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_is_sec,
)

vault_serializer = URLSafeSerializer(secret_key, salt="tradeverse-vault-v1")


def get_vault_accounts():
    """Retrieve signed persistent account records stored in the client cookie."""
    token = request.cookies.get("tv_account_vault")
    if not token:
        return {}
    try:
        data = vault_serializer.loads(token)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_vault_account(response, user_dict):
    """Save user identity to the signed persistent cookie across Lambda containers."""
    try:
        vault = get_vault_accounts()
        email = str(user_dict["email"]).lower().strip()
        vault[email] = {
            "id": user_dict.get("id"),
            "full_name": user_dict.get("full_name"),
            "email": email,
            "password_hash": user_dict.get("password_hash"),
        }
        if len(vault) > 10:
            vault = dict(list(vault.items())[-10:])
        token = vault_serializer.dumps(vault)
        is_secure_conn = True if (_is_sec or request.is_secure or request.headers.get("X-Forwarded-Proto") == "https") else False
        response.set_cookie(
            "tv_account_vault",
            token,
            max_age=60 * 60 * 24 * 90,
            httponly=True,
            samesite="Lax",
            secure=is_secure_conn,
            path="/",
        )
    except Exception as err:
        sys.stderr.write(f"Vault save error: {err}\n")
    return response


@app.before_request
def ensure_session_user_in_db():
    """Ensure user stored in signed session is restored into the local SQLite container."""
    profile = session.get("user_profile")
    if profile and isinstance(profile, dict):
        user_id = profile.get("id") or session.get("user_id")
        user = get_user_by_id(user_id) if user_id else None
        if not user:
            restored_id = restore_user_to_db(
                profile,
                wallet=session.get("user_wallet"),
                watchlist=session.get("watchlist"),
                portfolio=session.get("user_portfolio"),
                transactions=session.get("user_transactions"),
                closed_trades=session.get("user_closed_trades"),
            )
            if restored_id:
                session["user_id"] = restored_id
                session["user_profile"]["id"] = restored_id
        else:
            # If user exists in DB but holdings table is empty and session has portfolio, restore them
            session_portfolio = session.get("user_portfolio")
            if session_portfolio and isinstance(session_portfolio, list) and len(session_portfolio) > 0:
                db_holdings = get_portfolio_rows(user_id)
                if not db_holdings or len(db_holdings) == 0:
                    restore_user_to_db(
                        profile,
                        wallet=session.get("user_wallet"),
                        watchlist=session.get("watchlist"),
                        portfolio=session_portfolio,
                        transactions=session.get("user_transactions"),
                        closed_trades=session.get("user_closed_trades"),
                    )


try:
    init_database()
except Exception as err:
    sys.stderr.write(f"Notice: init_database caught exception on start: {err}\n")


def login_required(view_function):
    """Redirect unauthenticated visitors or return JSON 401 for API/AJAX requests."""
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        user = get_user_by_id(user_id) if user_id else None
        if not user:
            profile = session.get("user_profile")
            if profile and isinstance(profile, dict):
                restored_id = restore_user_to_db(
                    profile,
                    wallet=session.get("user_wallet"),
                    watchlist=session.get("watchlist"),
                    portfolio=session.get("user_portfolio"),
                    transactions=session.get("user_transactions"),
                    closed_trades=session.get("user_closed_trades"),
                )
                if restored_id:
                    session["user_id"] = restored_id
                    user = get_user_by_id(restored_id)

        if not user:
            session.clear()
            is_api = (
                request.path.startswith("/api/")
                or request.path == "/trade"
                or request.path == "/watchlist/toggle"
                or request.is_json
                or "application/json" in request.headers.get("Accept", "")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            )
            if is_api:
                return jsonify({"ok": False, "error": "unauthorized", "message": "Please sign in to continue."}), 401
            flash("Please sign in to use TradeVerse.", "warning")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)
    return wrapped_view


def quote_for_asset(symbol, asset_type):
    """Resolve one symbol from the correct provider service module."""
    if asset_type == "crypto":
        return get_crypto_quote(symbol)
    return get_stock_quote(symbol)


def row_to_quote(row):
    """Convert a watchlist database row into a quote with a graceful fallback."""
    quote = quote_for_asset(row["symbol"], row["asset_type"])
    if quote:
        price = float(quote["price"])
        percentage_change = float(quote.get("change", 0))
        previous_price = price / (1 + percentage_change / 100) if percentage_change != -100 else price
        currency = quote.get("currency") or ("INR" if row["asset_type"] == "stock" and (quote.get("market") == "India" or row["symbol"].endswith(".NS") or row["symbol"].endswith(".BO")) else "USDT")
        return {
            **quote,
            "currency": currency,
            "asset_type": row["asset_type"],
            "market_type": "Crypto" if row["asset_type"] == "crypto" else quote.get("market", "Stocks"),
            "price_change": price - previous_price,
            "added_at": row["created_at"],
        }
    currency = "INR" if row["asset_type"] == "stock" and (row["symbol"].endswith(".NS") or row["symbol"].endswith(".BO")) else "USDT"
    return {
        "symbol": row["symbol"],
        "name": row["symbol"],
        "price": 0,
        "change": 0,
        "currency": currency,
        "asset_type": row["asset_type"],
        "market_type": "Crypto" if row["asset_type"] == "crypto" else "Stocks",
        "price_change": 0,
        "added_at": row["created_at"],
    }


def latest_market_quotes():
    """Return the local dashboard market list for gainers and losers panels."""
    stocks = [{**stock, "asset_type": "stock", "currency": stock.get("currency", "INR" if stock.get("market") == "India" else "USDT")} for stock in list_stocks()]
    crypto = [{**coin, "asset_type": "crypto", "currency": "USDT"} for coin in list_crypto()]
    return stocks + crypto


@app.context_processor
def inject_layout_data():
    """Expose current account, wallet, and watchlist symbols to every Jinja template."""
    user = get_user_by_id(session["user_id"]) if "user_id" in session else None
    watchlist_keys = set()
    wallet = {"inr": 0.0, "usdt": 0.0}
    if user:
        watchlist_keys = {
            f"{item['asset_type']}:{item['symbol']}" for item in get_watchlist(user["id"])
        }
        wallet = get_wallet(user["id"])
    return {"current_user": user, "wallet": wallet, "watchlist_keys": watchlist_keys}


@app.template_filter("credits")
def format_credits(value, currency=None):
    """Format currency values with INR or USDT symbols."""
    val = float(value or 0)
    if currency == "INR":
        return f"₹{val:,.2f}"
    if currency == "USDT":
        return f"{val:,.2f} USDT"
    # Sensible default if no currency passed
    return f"₹{val:,.2f}"


@app.template_filter("inr")
def format_inr(value):
    """Format Indian Rupee amount."""
    val = float(value or 0)
    return f"₹{val:,.2f}"


@app.template_filter("usdt")
def format_usdt(value):
    """Format USDT amount."""
    val = float(value or 0)
    return f"{val:,.2f} USDT"


@app.template_filter("currency_val")
def format_currency_val(value, currency="INR"):
    """Format amount based on explicit currency tag."""
    val = float(value or 0)
    if str(currency).upper() == "INR":
        return f"₹{val:,.2f}"
    return f"{val:,.2f} USDT"


@app.template_filter("signed_currency")
def format_signed_currency(value, currency="INR"):
    """Format signed amount with explicit currency symbol."""
    val = float(value or 0)
    sign = "+" if val >= 0 else "-"
    abs_val = abs(val)
    if str(currency).upper() == "INR":
        return f"{sign}₹{abs_val:,.2f}"
    return f"{sign}{abs_val:,.2f} USDT"


@app.template_filter("quantity")
def format_quantity(value):
    """Show share and coin quantities without distracting trailing zeroes."""
    return f"{float(value):,.4f}".rstrip("0").rstrip(".")


@app.template_filter("signed")
def format_signed(value):
    """Format a percentage or price change with an explicit plus or minus sign."""
    numeric_value = float(value)
    return f"{numeric_value:+.2f}"


@app.template_filter("asset_icon")
def filter_asset_icon(symbol, asset_type="stock", size=32):
    """Return crisp SVG vector icon for any crypto coin or stock."""
    return get_asset_svg(symbol, asset_type, size)


@app.template_filter("market_pair")
def filter_market_pair(symbol, currency=""):
    """Format trading pair symbol (e.g. BTC/USDT, RELIANCE/INR)."""
    return get_market_pair(symbol, currency)


app.jinja_env.globals["asset_icon"] = get_asset_svg
app.jinja_env.globals["market_pair"] = get_market_pair


@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok", "message": "pong", "deployment": "live"})


@app.route("/")
def index():
    """Send signed-in users to their dashboard and everyone else to login."""
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create an account with a starting virtual wallet."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        full_name = (payload.get("full_name") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        confirm_password = payload.get("confirm_password") or ""
        is_json = request.is_json or "application/json" in request.headers.get("Accept", "")

        err = None
        if len(full_name) < 2:
            err = "Please enter your full name."
        elif "@" not in email or len(email) < 5:
            err = "Please enter a valid email address."
        elif len(password) < 8:
            err = "Use a password with at least 8 characters."
        elif password != confirm_password:
            err = "The password confirmation does not match."

        if err:
            if is_json:
                return jsonify({"ok": False, "message": err}), 400
            flash(err, "error")
            return render_template("register.html", page_name="Create account")

        try:
            user_id = create_user(full_name, email, password)
            user = get_user_by_id(user_id)
            session.clear()
            session.permanent = True
            session["user_id"] = user_id
            user_profile = {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "password_hash": user["password_hash"],
            }
            session["user_profile"] = user_profile
            session["user_wallet"] = {"inr": 1000000.0, "usdt": 10000.0}
            session["watchlist"] = []

            if is_json:
                resp = jsonify({"ok": True, "message": "Welcome to TradeVerse. Your virtual wallet is ready.", "redirect": url_for("dashboard")})
            else:
                flash("Welcome to TradeVerse. Your virtual wallet is ready.", "success")
                resp = redirect(url_for("dashboard"))
            return save_vault_account(resp, user_profile)
        except ValueError as error:
            if is_json:
                return jsonify({"ok": False, "message": str(error)}), 400
            flash(str(error), "error")
        except Exception as error:
            sys.stderr.write(f"Registration error: {error}\n{traceback.format_exc()}\n")
            if is_json:
                return jsonify({"ok": False, "message": "Could not complete registration. Please try again."}), 500
            flash("Could not complete registration. Please try again.", "error")
    return render_template("register.html", page_name="Create account")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate a local user and store their id in the Flask session."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        is_json = request.is_json or "application/json" in request.headers.get("Accept", "")

        try:
            user = get_user_by_email(email)
            vault = get_vault_accounts()
            vault_entry = vault.get(email)

            if not user and vault_entry:
                if check_password_hash(vault_entry.get("password_hash", ""), password):
                    restored_id = restore_user_to_db(vault_entry)
                    user = get_user_by_id(restored_id) or get_user_by_email(email)
                else:
                    msg = "Incorrect password. Please try again."
                    if is_json:
                        return jsonify({"ok": False, "message": msg}), 401
                    flash(msg, "error")
                    return render_template("login.html", page_name="Sign in")

            # Check client-side vault if provided
            client_vault_str = payload.get("client_vault")
            client_entry = None
            if client_vault_str:
                try:
                    c_data = json.loads(client_vault_str) if isinstance(client_vault_str, str) else client_vault_str
                    if isinstance(c_data, dict) and c_data.get("email", "").lower().strip() == email:
                        client_entry = c_data
                except Exception:
                    pass

            if not user and client_entry:
                pw_hash = client_entry.get("password_hash")
                if (pw_hash and check_password_hash(pw_hash, password)) or (not pw_hash and len(password) >= 6):
                    restored_id = restore_user_to_db(
                        client_entry,
                        wallet=client_entry.get("wallet"),
                        portfolio=client_entry.get("portfolio"),
                        transactions=client_entry.get("transactions"),
                        closed_trades=client_entry.get("closed_trades"),
                    )
                    user = get_user_by_id(restored_id) or get_user_by_email(email)

            # Auto-recovery for serverless containers:
            # If user is missing from SQLite and vaults because of a container wipe/restart,
            # but supplied valid credentials (email & password >= 6 characters):
            # seamlessly restore/create their account in this container!
            if not user and email and "@" in email and len(password) >= 6:
                display_name = (
                    (client_entry.get("full_name") if client_entry else None)
                    or email.split("@")[0].replace(".", " ").replace("_", " ").title()
                )
                new_uid = create_user(display_name, email, password)
                user = get_user_by_id(new_uid) or get_user_by_email(email)

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session.permanent = True
                session["user_id"] = user["id"]
                user_profile = {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "password_hash": user["password_hash"],
                }
                session["user_profile"] = user_profile
                wallet = get_wallet(user["id"])
                if wallet:
                    session["user_wallet"] = wallet

                wl = get_watchlist(user["id"])
                if wl:
                    session["watchlist"] = [f"{item['asset_type']}:{item['symbol']}" for item in wl]

                first_name = (user["full_name"] or "Trader").split()[0]
                if is_json:
                    resp = jsonify({
                        "ok": True,
                        "message": f"Welcome back, {first_name}.",
                        "redirect": url_for("dashboard"),
                        "user": user_profile,
                    })
                else:
                    flash(f"Welcome back, {first_name}.", "success")
                    resp = redirect(url_for("dashboard"))
                return save_vault_account(resp, user_profile)

            if user:
                msg = "Incorrect password. Please try again."
            else:
                msg = "Please enter a valid email and password (minimum 6 characters)."

            if is_json:
                return jsonify({"ok": False, "message": msg}), 401
            flash(msg, "error")
        except Exception as error:
            sys.stderr.write(f"Login error: {error}\n{traceback.format_exc()}\n")
            if is_json:
                return jsonify({"ok": False, "message": "Sign in service temporarily unavailable. Please try again."}), 500
            flash("Sign in service temporarily unavailable. Please try again.", "error")
    return render_template("login.html", page_name="Sign in")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Provide a local reset form for development without email infrastructure."""
    if request.method == "POST":
        email = request.form.get("email", "")
        new_password = request.form.get("new_password", "")
        if len(new_password) < 8:
            flash("Use a new password with at least 8 characters.", "error")
        elif reset_password(email, new_password):
            flash("Password updated. You can now sign in.", "success")
            return redirect(url_for("login"))
        else:
            flash("No account was found for that email address.", "error")
    return render_template("forgot_password.html", page_name="Reset password")


@app.route("/logout")
def logout():
    """Clear the active Flask session and return to the sign-in page."""
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Render wallet, portfolio, watchlist, trade timeline, and market-mover information."""
    user_id = session["user_id"]
    portfolio = calculate_portfolio(user_id, quote_for_asset)
    markets = latest_market_quotes()
    sorted_quotes = sorted(markets, key=lambda quote: quote["change"], reverse=True)
    watchlist = [row_to_quote(row) for row in get_watchlist(user_id)]
    quick_defs = [("RELIANCE.NS", "stock", "INR"), ("BTC", "crypto", "USDT"), ("AAPL", "stock", "USDT")]
    quick_starters = []
    for sym, atype, curr in quick_defs:
        q = quote_for_asset(sym, atype)
        if q:
            quick_starters.append({**q, "asset_type": atype, "currency": curr})

    recent_closed = get_closed_trades(user_id, limit=4)
    timeline_stats = get_trade_timeline_stats(user_id)

    chart_instruments = [
        {"symbol": "BTC", "name": "Bitcoin", "asset_type": "crypto", "currency": "USDT"},
        {"symbol": "ETH", "name": "Ethereum", "asset_type": "crypto", "currency": "USDT"},
        {"symbol": "SOL", "name": "Solana", "asset_type": "crypto", "currency": "USDT"},
        {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "asset_type": "stock", "currency": "INR"},
        {"symbol": "AAPL", "name": "Apple", "asset_type": "stock", "currency": "USDT"},
    ]

    return render_template(
        "dashboard.html",
        page_name="Dashboard",
        portfolio=portfolio,
        gainers=sorted_quotes[:4],
        losers=list(reversed(sorted_quotes[-4:])),
        watchlist=watchlist,
        quick_starters=quick_starters,
        recent_closed=recent_closed,
        timeline_stats=timeline_stats,
        chart_instruments=chart_instruments,
        transactions=get_transactions(user_id, limit=5),
    )



@app.route("/stocks")
@login_required
def stocks():
    """Show Indian and global stocks from a searchable local market list."""
    query = request.args.get("query", "")
    market = request.args.get("market", "All")
    all_stocks = list_stocks(query, market)
    return render_template(
        "stocks.html",
        page_name="Stocks",
        stocks=all_stocks,
        query=query,
        selected_market=market,
        featured_stock=all_stocks[0] if all_stocks else None,
    )


@app.route("/crypto")
@login_required
def crypto():
    """Show supported cryptocurrency quotes, dedicated coin charts, and paper-trading actions."""
    query = request.args.get("query", "")
    all_coins = list_crypto(query)
    return render_template(
        "crypto.html",
        page_name="Crypto",
        coins=all_coins,
        query=query,
        featured_coin=all_coins[0] if all_coins else None,
    )


@app.route("/portfolio")
@login_required
def portfolio():
    """Render current holdings with position ages, performance totals, and transaction history."""
    user_id = session["user_id"]
    return render_template(
        "portfolio.html",
        page_name="Portfolio",
        portfolio=calculate_portfolio(user_id, quote_for_asset),
        closed_trades=get_closed_trades(user_id, limit=10),
        timeline_stats=get_trade_timeline_stats(user_id),
        transactions=get_transactions(user_id, limit=30),
    )


@app.route("/timeline")
@login_required
def timeline():
    """Display the full closed-trade lifecycle timeline and holding duration metrics."""
    user_id = session["user_id"]
    portfolio_data = calculate_portfolio(user_id, quote_for_asset)
    closed_trades = get_closed_trades(user_id, limit=100)
    timeline_stats = get_trade_timeline_stats(user_id)
    return render_template(
        "timeline.html",
        page_name="Trade Timeline",
        closed_trades=closed_trades,
        timeline_stats=timeline_stats,
        holdings=portfolio_data["holdings"],
    )


@app.route("/watchlist")
@login_required
def watchlist():
    """Show the signed-in user's complete, price-enriched market watchlist."""
    items = [row_to_quote(row) for row in get_watchlist(session["user_id"])]
    return render_template("watchlist.html", page_name="Watchlist", items=items)


@app.route("/leaderboard")
@login_required
def leaderboard():
    """Rank actual registered accounts by their virtual paper-account performance."""
    entries = calculate_leaderboard(quote_for_asset)
    current_user_entry = next(
        (entry for entry in entries if entry["user_id"] == session["user_id"]),
        None,
    )
    return render_template(
        "leaderboard.html",
        page_name="Leaderboard",
        entries=entries,
        current_user_entry=current_user_entry,
    )


@app.route("/learning")
@login_required
def learning():
    """Show the persisted learning library and a focused featured lesson."""
    modules = get_learning_modules()
    return render_template("learning.html", page_name="Learning", modules=modules, featured=modules[0])


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    """Display the weekly quiz and persist each submitted score."""
    result = None
    if request.method == "POST":
        result = score_quiz(session["user_id"], request.form)
    return render_template(
        "quiz.html",
        page_name="Weekly quiz",
        questions=get_quiz_questions(),
        result=result,
        past_results=get_quiz_results(session["user_id"]),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Allow a signed-in user to update account identity information."""
    user_id = session["user_id"]
    if request.method == "POST":
        try:
            update_user_profile(user_id, request.form.get("full_name", ""), request.form.get("email", ""))
            user = get_user_by_id(user_id)
            if user:
                session["user_profile"] = {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "password_hash": user["password_hash"],
                }
            flash("Your profile details were updated.", "success")
            resp = redirect(url_for("profile"))
            if user:
                return save_vault_account(resp, session["user_profile"])
            return resp
        except ValueError as error:
            flash(str(error), "error")
    return render_template(
        "profile.html",
        page_name="Profile",
        quiz_results=get_quiz_results(user_id),
        transaction_count=len(get_transactions(user_id, limit=500)),
    )


@app.post("/trade")
@login_required
def trade():
    """Validate a quote, execute an order, and return JSON for the modal UI."""
    payload = request.get_json(silent=True) or request.form
    symbol = payload.get("symbol", "")
    asset_type = payload.get("asset_type", "stock")
    side = payload.get("side", "BUY")
    try:
        quantity = float(payload.get("quantity", 0))
        quote = quote_for_asset(symbol, asset_type)
        if quote is None:
            raise ValueError("That symbol is not available in the current paper market.")
        result = execute_trade(
            session["user_id"],
            quote["symbol"],
            asset_type,
            quote["name"],
            side,
            quantity,
            quote["price"],
        )
        user_id = session["user_id"]
        session["user_wallet"] = {"inr": result["inr_balance"], "usdt": result["usdt_balance"]}

        # Persist updated portfolio holdings in session for serverless recovery
        updated_holdings = [
            {
                "symbol": h["symbol"],
                "asset_type": h["asset_type"],
                "asset_name": h["asset_name"],
                "currency": h["currency"],
                "quantity": float(h["quantity"]),
                "average_price": float(h["average_price"]),
                "opened_at": h["opened_at"],
                "updated_at": h["updated_at"],
            }
            for h in get_portfolio_rows(user_id)
        ]
        session["user_portfolio"] = updated_holdings

        # Persist transactions in session for serverless recovery
        updated_transactions = [
            {
                "symbol": t["symbol"],
                "asset_type": t["asset_type"],
                "asset_name": t["asset_name"],
                "currency": t["currency"],
                "trade_type": t["trade_type"],
                "quantity": float(t["quantity"]),
                "price": float(t["price"]),
                "total_amount": float(t["total_amount"]),
                "created_at": t["created_at"],
            }
            for t in get_transactions(user_id, limit=20)
        ]
        session["user_transactions"] = updated_transactions

        # Persist closed trades in session for serverless recovery
        updated_closed = [
            {
                "symbol": c["symbol"],
                "asset_type": c["asset_type"],
                "asset_name": c["asset_name"],
                "currency": c["currency"],
                "quantity": float(c["quantity"]),
                "buy_price": float(c["buy_price"]),
                "sell_price": float(c["sell_price"]),
                "buy_time": c["buy_time"],
                "sell_time": c["sell_time"],
                "duration_seconds": c["duration_seconds"],
                "duration_formatted": c["duration_formatted"],
                "realized_pnl": float(c["realized_pnl"]),
                "realized_pnl_percent": float(c["realized_pnl_percent"]),
                "created_at": c["created_at"],
            }
            for c in get_closed_trades(user_id, limit=20)
        ]
        session["user_closed_trades"] = updated_closed

        formatted_total = f"₹{result['total_amount']:,.2f} INR" if result["currency"] == "INR" else f"{result['total_amount']:,.2f} USDT"
        msg = f"{result['side']} order completed for {result['quantity']:g} {result['symbol']} ({formatted_total})."
        if result.get("duration_formatted"):
            pnl_val = result.get("realized_pnl", 0)
            if result["currency"] == "INR":
                pnl_str = f"+₹{pnl_val:,.2f}" if pnl_val >= 0 else f"-₹{abs(pnl_val):,.2f}"
            else:
                pnl_str = f"{pnl_val:+.2f} USDT"
            msg += f" Position closed in {result['duration_formatted']} (P/L: {pnl_str})."
        return jsonify({
            "ok": True,
            "message": msg,
            "portfolio": updated_holdings,
            "transactions": updated_transactions,
            "wallet": {"inr": result["inr_balance"], "usdt": result["usdt_balance"]},
            **result,
        })
    except (TypeError, ValueError) as error:
        return jsonify({"ok": False, "message": str(error)}), 400


@app.post("/api/sync-state")
@login_required
def sync_state():
    """Synchronize user portfolio and wallet from client-side browser storage if serverless DB restarted."""
    payload = request.get_json(silent=True) or {}
    holdings = payload.get("portfolio")
    wallet = payload.get("wallet")
    transactions = payload.get("transactions")
    closed_trades = payload.get("closed_trades")
    user_id = session["user_id"]
    profile = session.get("user_profile") or dict(get_user_by_id(user_id))

    restore_user_to_db(
        profile,
        wallet=wallet or session.get("user_wallet"),
        watchlist=session.get("watchlist"),
        portfolio=holdings or session.get("user_portfolio"),
        transactions=transactions or session.get("user_transactions"),
        closed_trades=closed_trades or session.get("user_closed_trades"),
    )
    if holdings:
        session["user_portfolio"] = holdings
    if wallet:
        session["user_wallet"] = wallet
    if transactions:
        session["user_transactions"] = transactions
    if closed_trades:
        session["user_closed_trades"] = closed_trades
    return jsonify({"ok": True, "message": "State synced successfully."})


@app.post("/wallet/reset")
@login_required
def reset_wallet_route():
    """Reset virtual practice balance back to starting amounts (₹1,000,000 INR & 10,000 USDT)."""
    user_id = session["user_id"]
    reset_wallet(user_id)
    session["user_wallet"] = {"inr": STARTING_INR_BALANCE, "usdt": STARTING_USDT_BALANCE}
    flash("Your virtual practice wallet has been reset to starting balances (₹10,00,000 INR & 10,000 USDT).", "success")
    return redirect(url_for("portfolio"))


@app.post("/watchlist/toggle")
@login_required
def watchlist_toggle():
    """Toggle one saved quote and tell JavaScript which state is now active."""
    payload = request.get_json(silent=True) or request.form
    symbol = payload.get("symbol", "")
    asset_type = payload.get("asset_type", "stock")
    if not symbol or asset_type not in {"stock", "crypto"}:
        return jsonify({"ok": False, "message": "A valid market symbol is required."}), 400
    is_saved = toggle_watchlist_item(session["user_id"], symbol, asset_type)
    wl = get_watchlist(session["user_id"])
    session["watchlist"] = [f"{item['asset_type']}:{item['symbol']}" for item in wl]
    return jsonify({"ok": True, "saved": is_saved, "message": "Added to watchlist." if is_saved else "Removed from watchlist."})


@app.get("/api/watchlist")
@login_required
def watchlist_api():
    """Return the current user's full watchlist with live or fallback quote data."""
    items = [row_to_quote(row) for row in get_watchlist(session["user_id"])]
    return jsonify({"ok": True, "items": items})


@app.post("/api/watchlist")
@login_required
def add_watchlist_api():
    """Add a valid market symbol without duplicating an existing user-specific item."""
    payload = request.get_json(silent=True) or request.form
    symbol = payload.get("symbol", "")
    asset_type = payload.get("asset_type", "stock")
    quote = quote_for_asset(symbol, asset_type)
    if quote is None:
        return jsonify({"ok": False, "message": "That market symbol is not available."}), 404
    try:
        was_added = add_watchlist_item(session["user_id"], quote["symbol"], asset_type)
        wl = get_watchlist(session["user_id"])
        session["watchlist"] = [f"{item['asset_type']}:{item['symbol']}" for item in wl]
    except ValueError as error:
        return jsonify({"ok": False, "message": str(error)}), 400
    message = "Added to watchlist." if was_added else "This symbol is already in your watchlist."
    return jsonify({"ok": True, "saved": True, "created": was_added, "message": message}), 201 if was_added else 200


@app.delete("/api/watchlist/<asset_type>/<symbol>")
@login_required
def remove_watchlist_api(asset_type, symbol):
    """Remove only the authenticated user's selected watchlist item."""
    if asset_type not in {"stock", "crypto"}:
        return jsonify({"ok": False, "message": "This asset type is not supported."}), 400
    was_removed = remove_watchlist_item(session["user_id"], symbol, asset_type)
    if not was_removed:
        return jsonify({"ok": False, "message": "That symbol is not in your watchlist."}), 404
    wl = get_watchlist(session["user_id"])
    session["watchlist"] = [f"{item['asset_type']}:{item['symbol']}" for item in wl]
    return jsonify({"ok": True, "saved": False, "message": "Removed from watchlist."})


@app.get("/api/watchlist/check")
@login_required
def watchlist_check_api():
    """Report whether a symbol is saved for the signed-in user."""
    symbol = request.args.get("symbol", "")
    asset_type = request.args.get("asset_type", "stock")
    if not symbol or asset_type not in {"stock", "crypto"}:
        return jsonify({"ok": False, "message": "A valid market symbol is required."}), 400
    return jsonify(
        {
            "ok": True,
            "saved": is_watchlist_item(session["user_id"], symbol, asset_type),
        }
    )


@app.get("/api/leaderboard")
@login_required
def leaderboard_api():
    """Return actual registered-user paper-account ranks for progressive UI updates."""
    entries = calculate_leaderboard(quote_for_asset)
    current_rank = next(
        (entry["rank"] for entry in entries if entry["user_id"] == session["user_id"]),
        None,
    )
    return jsonify({"ok": True, "entries": entries, "current_user_rank": current_rank})


@app.get("/api/market/search")
@login_required
def market_search():
    """Provide a compact JSON market search endpoint for future progressive enhancements."""
    query = request.args.get("query", "")
    asset_type = request.args.get("asset_type", "stock")
    items = list_crypto(query) if asset_type == "crypto" else list_stocks(query)
    return jsonify(items)


@app.get("/api/chart/<asset_type>/<symbol>")
@login_required
def chart_data(asset_type, symbol):
    """Return chart-compatible candles for a supported stock or crypto symbol."""
    quote = quote_for_asset(symbol, asset_type)
    if quote is None:
        return jsonify({"ok": False, "message": "Symbol not found."}), 404
    timeframe = request.args.get("timeframe", "5y" if asset_type == "crypto" else "1y").strip()
    if asset_type == "crypto":
        candles = generate_crypto_candles(symbol, quote["price"], timeframe=timeframe)
    else:
        candles = generate_candles(symbol, quote["price"])
    return jsonify({"ok": True, "symbol": quote["symbol"], "timeframe": timeframe, "candles": candles})


@app.get("/api/portfolio/summary")
@login_required
def portfolio_summary_api():
    """Expose a portfolio summary with dual-currency breakdown for client-side refreshes."""
    portfolio = calculate_portfolio(session["user_id"], quote_for_asset)
    return jsonify(
        {
            "inr_wallet": portfolio["inr_wallet"],
            "usdt_wallet": portfolio["usdt_wallet"],
            "wallet_balance": portfolio["wallet_balance"],
            "inr_total_value": portfolio["inr_total_value"],
            "usdt_total_value": portfolio["usdt_total_value"],
            "inr_profit_loss": portfolio["inr_profit_loss"],
            "usdt_profit_loss": portfolio["usdt_profit_loss"],
            "total_value": portfolio["total_value"],
            "profit_loss": portfolio["total_profit_loss"],
        }
    )


@app.get("/api/quote/<asset_type>/<symbol>")
@login_required
def quote_api(asset_type, symbol):
    """Return the freshest live quote for an individual asset."""
    quote = quote_for_asset(symbol, asset_type)
    if quote is None:
        return jsonify({"ok": False, "message": "Symbol not found."}), 404
    return jsonify({"ok": True, "quote": quote})


@app.get("/api/market/quotes")
@login_required
def market_quotes_api():
    """Return latest refreshed quotes for all stocks and cryptos."""
    stocks = list_stocks()
    cryptos = list_crypto()
    return jsonify({"ok": True, "stocks": stocks, "crypto": cryptos})


@app.get("/api/timeline")
@login_required
def timeline_api():
    """Return closed trade lifecycle records and duration statistics in JSON."""
    user_id = session["user_id"]
    trades = [dict(r) for r in get_closed_trades(user_id, limit=100)]
    stats = get_trade_timeline_stats(user_id)
    return jsonify({"ok": True, "trades": trades, "stats": stats})


@app.get("/api/icon/<asset_type>/<symbol>")
def icon_api(asset_type, symbol):
    """Return SVG vector markup for dynamic client-side rendering."""
    size = int(request.args.get("size", 32))
    svg = str(get_asset_svg(symbol, asset_type, size=size))
    return jsonify({"ok": True, "symbol": symbol, "svg": svg})


if __name__ == "__main__":
    # Set FLASK_DEBUG=1 when local auto-reload is useful during active development.
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
