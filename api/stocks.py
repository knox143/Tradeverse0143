"""Stock quote helpers with live real-time feeds, caching, and fallback adapters."""

import json
import os
import time
from datetime import date, datetime, timedelta
import requests

_stock_session = requests.Session()
_stock_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

# In-memory quote cache: symbol -> {"data": quote_dict, "ts": float}
_stock_cache = {}
_candle_cache = {}

STOCKS = [
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


def _get_cache_ttl():
    try:
        return int(os.environ.get("PRICE_CACHE_TTL_SECONDS") or 60)
    except (ValueError, TypeError):
        return 60


def _fetch_yahoo_quote(symbol):
    """Fetch live quote from Yahoo Finance API with strict timeout."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    try:
        resp = _stock_session.get(url, timeout=(2.5, 3.0))
        if resp.status_code != 200:
            return None
        payload = resp.json()
        result = payload.get("chart", {}).get("result")
        if not result:
            return None
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        if price is None:
            return None

        price = float(price)
        prev_close = float(prev_close) if prev_close else price
        change = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        currency = "INR" if symbol.upper().endswith(".NS") or symbol.upper().endswith(".BO") else "USDT"
        market = "India" if currency == "INR" else "Global"

        return {
            "symbol": symbol.upper(),
            "price": round(price, 2),
            "change": round(change, 2),
            "currency": currency,
            "market": market,
            "source": "Live Market",
        }
    except Exception:
        return None


def _get_twelve_data_quote(symbol, api_key):
    """Fetch quote from Twelve Data API."""
    if not api_key:
        return None
    try:
        resp = _stock_session.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": symbol, "apikey": api_key},
            timeout=(2.5, 3.0),
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") or not payload.get("close"):
            return None
        currency = "INR" if symbol.upper().endswith(".NS") or symbol.upper().endswith(".BO") else "USDT"
        return {
            "symbol": payload.get("symbol", symbol).upper(),
            "name": payload.get("name", symbol),
            "market": payload.get("exchange", "Live"),
            "price": float(payload["close"]),
            "change": float(payload.get("percent_change", 0)),
            "currency": currency,
            "sector": "Live market data",
            "source": "Twelve Data",
        }
    except Exception:
        return None


def _get_finnhub_quote(symbol, api_key):
    """Fetch quote from Finnhub API for US/Global stocks."""
    if not api_key:
        return None
    try:
        resp = _stock_session.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": api_key},
            timeout=(2.5, 3.0),
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        price = payload.get("c")
        if not price or float(price) <= 0:
            return None
        prev_close = payload.get("pc", price)
        change = payload.get("dp") or (((price - prev_close) / prev_close) * 100 if prev_close else 0)
        return {
            "symbol": symbol.upper(),
            "price": round(float(price), 2),
            "change": round(float(change), 2),
            "currency": "USDT",
            "market": "Global",
            "source": "Finnhub",
        }
    except Exception:
        return None


def get_stock_quote(symbol):
    """Return live real-time quote, checking cache, external providers, and local fallback."""
    normalized_symbol = symbol.upper().strip()

    # 1. Check in-memory cache
    cached = _stock_cache.get(normalized_symbol)
    now = time.time()
    if cached and (now - cached["ts"] < _get_cache_ttl()):
        return cached["data"].copy()

    # Find baseline metadata
    local_baseline = next((stock.copy() for stock in STOCKS if stock["symbol"] == normalized_symbol), None)

    # 2. Try Twelve Data if configured
    twelve_key = os.environ.get("TWELVE_DATA_API_KEY")
    live_quote = _get_twelve_data_quote(normalized_symbol, twelve_key) if twelve_key else None

    # 3. Try Yahoo Finance real-time feed
    if not live_quote:
        live_quote = _fetch_yahoo_quote(normalized_symbol)

    # 4. Try Finnhub if global
    if not live_quote and not (normalized_symbol.endswith(".NS") or normalized_symbol.endswith(".BO")):
        finnhub_key = os.environ.get("FINNHUB_API_KEY")
        if finnhub_key:
            live_quote = _get_finnhub_quote(normalized_symbol, finnhub_key)

    # Combine with local metadata
    if live_quote:
        if local_baseline:
            local_baseline.update(live_quote)
            final_quote = local_baseline
        else:
            final_quote = live_quote
            if "name" not in final_quote:
                final_quote["name"] = normalized_symbol
            if "sector" not in final_quote:
                final_quote["sector"] = "Equities"
    else:
        final_quote = local_baseline

    if final_quote:
        _stock_cache[normalized_symbol] = {"data": final_quote.copy(), "ts": now}
        return final_quote.copy()

    return None


def list_stocks(query="", market="All"):
    """Return stock records refreshed concurrently with latest real-time prices."""
    from concurrent.futures import ThreadPoolExecutor

    normalized_query = query.lower().strip()
    filtered = [
        stock.copy() for stock in STOCKS
        if (market in {"", "All"} or stock["market"] == market)
        and (not normalized_query or normalized_query in stock["symbol"].lower() or normalized_query in stock["name"].lower())
    ]
    if not filtered:
        return []

    def _refresh(stock):
        try:
            live = get_stock_quote(stock["symbol"])
            if live:
                stock["price"] = live["price"]
                stock["change"] = live["change"]
                stock["currency"] = live.get("currency", stock.get("currency", "INR"))
                if "source" in live:
                    stock["source"] = live["source"]
        except Exception:
            pass
        return stock

    workers = min(len(filtered), 8)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_refresh, filtered))


def generate_candles(symbol, current_price, days=45):
    """Fetch real historical candlestick data or fallback to calibrated generator."""
    cached = _candle_cache.get(symbol)
    now = time.time()
    if cached and (now - cached["ts"] < 300):
        return cached["candles"]

    # Try Yahoo Finance historical candles
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
        resp = _stock_session.get(url, timeout=(2.5, 3.5))
        if resp.status_code == 200:
            data = resp.json()["chart"]["result"][0]
        timestamps = data.get("timestamp", [])
        quotes = data.get("indicators", {}).get("quote", [{}])[0]
        candles = []
        for t, o, h, l, c in zip(timestamps, quotes.get("open", []), quotes.get("high", []), quotes.get("low", []), quotes.get("close", [])):
            if None not in (o, h, l, c):
                candles.append({
                    "time": datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
                    "open": round(float(o), 2),
                    "high": round(float(h), 2),
                    "low": round(float(l), 2),
                    "close": round(float(c), 2),
                })
        if candles:
            recent_candles = candles[-days:]
            _candle_cache[symbol] = {"candles": recent_candles, "ts": now}
            return recent_candles
    except Exception:
        pass

    # Fallback to calibrated generator
    seed = sum(ord(character) for character in symbol)
    price = float(current_price) * (0.92 + (seed % 9) / 100)
    fallback_candles = []
    for index in range(days):
        drift = (((seed + index * 13) % 17) - 8) / 230
        open_price = price
        close_price = max(0.01, open_price * (1 + drift))
        high_price = max(open_price, close_price) * (1.005 + ((seed + index) % 4) / 1000)
        low_price = min(open_price, close_price) * (0.995 - ((seed + index) % 3) / 1000)
        fallback_candles.append(
            {
                "time": (date.today() - timedelta(days=days - index - 1)).isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
            }
        )
        price = close_price
    return fallback_candles


# Vercel serverless fallback handler
def handler(*args, **kwargs):
    from app import app
    return app(*args, **kwargs)
