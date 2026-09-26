"""
TradeVerse - Cryptocurrency API Engine
======================================
Is module me top crypto assets (BTC, ETH, SOL, etc.) ke real-time ticker prices,
intraday/multi-timeframe candlestick data, aur search/listing functions implement hain.

APIs & Free Tier Note:
- Primary Free Feed: Binance Public Ticker API (Tick-by-tick real-time quotes, free).
- Secondary Free Fallback: CoinGecko Public Markets API.
  * Optional: Set COINGECKO_API_KEY in .env or Vercel Environment Variables.
- In-memory Caching: In-memory cache (_crypto_cache) frequent redundant requests ko
  cache karke API rate limits ko protect karta hai.
"""

import os
import time
from datetime import date, datetime, timedelta
import requests

# Fast pooled HTTP session for low latency
_crypto_session = requests.Session()
_crypto_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# In-memory quote cache: symbol -> {"data": quote_dict, "ts": float}
_crypto_cache = {}
_crypto_candle_cache = {}

# ==============================================================================
# SECTION 1: DEFAULT CRYPTO ASSETS & BASELINE DATA
# Top cryptocurrency baseline pairs (All denominated in USDT).
# ==============================================================================
CRYPTO = [
    {"symbol": "BTC", "coin_id": "bitcoin", "name": "Bitcoin", "currency": "USDT", "price": 86_500.00, "change": 1.86, "rank": 1},
    {"symbol": "ETH", "coin_id": "ethereum", "name": "Ethereum", "currency": "USDT", "price": 3_250.00, "change": 0.73, "rank": 2},
    {"symbol": "BNB", "coin_id": "binancecoin", "name": "BNB", "currency": "USDT", "price": 620.00, "change": 1.15, "rank": 4},
    {"symbol": "SOL", "coin_id": "solana", "name": "Solana", "currency": "USDT", "price": 195.00, "change": -0.48, "rank": 5},
    {"symbol": "XRP", "coin_id": "ripple", "name": "XRP", "currency": "USDT", "price": 2.45, "change": 2.03, "rank": 3},
    {"symbol": "DOGE", "coin_id": "dogecoin", "name": "Dogecoin", "currency": "USDT", "price": 0.22, "change": 3.40, "rank": 7},
    {"symbol": "ADA", "coin_id": "cardano", "name": "Cardano", "currency": "USDT", "price": 0.85, "change": -0.90, "rank": 9},
    {"symbol": "MATIC", "coin_id": "matic-network", "name": "Polygon (POL)", "currency": "USDT", "price": 0.49, "change": -1.12, "rank": 28},
]


def _get_cache_ttl():
    """Cache TTL seconds return karta hai (Default: 60s)."""
    try:
        return int(os.environ.get("PRICE_CACHE_TTL_SECONDS") or 60)
    except (ValueError, TypeError):
        return 60


# ==============================================================================
# SECTION 2: LIVE QUOTE FETCHERS (BINANCE & COINGECKO)
# ==============================================================================
def _fetch_binance_quote(symbol):
    """Binance Public API se real-time 24hr ticker data lata hai."""
    ticker_sym = f"{symbol.upper()}USDT"
    endpoint = f"https://api.binance.com/api/v3/ticker/24hr?symbol={ticker_sym}"
    try:
        resp = _crypto_session.get(endpoint, timeout=(2.5, 3.0))
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if not payload or "lastPrice" not in payload:
            return None
        price = float(payload["lastPrice"])
        change = float(payload.get("priceChangePercent", 0))
        decimals = 4 if price < 1 else 2
        return {
            "symbol": symbol.upper(),
            "price": round(price, decimals),
            "change": round(change, 2),
            "currency": "USDT",
            "high": round(float(payload.get("highPrice", price)), decimals),
            "low": round(float(payload.get("lowPrice", price)), decimals),
            "volume": round(float(payload.get("volume", 0)), 2),
            "source": "Binance Live",
        }
    except Exception:
        return None


def _get_coingecko_quote(coin_id):
    """Retrieve public CoinGecko market data as secondary live fallback."""
    endpoint = (
        "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
        f"&ids={coin_id}&price_change_percentage=24h"
    )
    headers = {}
    api_key = os.environ.get("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    try:
        resp = _crypto_session.get(endpoint, headers=headers, timeout=(2.5, 3.0))
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if not payload:
            return None
        market = payload[0]
        price = float(market["current_price"])
        change = float(market.get("price_change_percentage_24h", 0))
        decimals = 4 if price < 1 else 2
        return {
            "price": round(price, decimals),
            "change": round(change, 2),
            "currency": "USDT",
            "source": "CoinGecko",
        }
    except Exception:
        return None


# ==============================================================================
# SECTION 3: CRYPTO QUOTE RESOLVER & IN-MEMORY CACHE
# Pehle cache check karta hai, fir Binance live price, fir CoinGecko fallback,
# aur offline hone par baseline data safely provide karta hai.
# ==============================================================================
def get_crypto_quote(symbol):
    """Crypto pair ka real-time quote fetch karta hai (Cache -> Binance -> CoinGecko -> Fallback)."""
    normalized_symbol = symbol.upper().strip()

    # 1. Check in-memory cache
    cached = _crypto_cache.get(normalized_symbol)
    now = time.time()
    if cached and (now - cached["ts"] < _get_cache_ttl()):
        return cached["data"].copy()

    # Baseline metadata
    local_baseline = next((coin.copy() for coin in CRYPTO if coin["symbol"] == normalized_symbol), None)

    # 2. Try Binance live quote (fastest, tick-by-tick real-time)
    live_quote = _fetch_binance_quote(normalized_symbol)

    # 3. Try CoinGecko fallback
    if not live_quote:
        coin_id = local_baseline["coin_id"] if local_baseline else normalized_symbol.lower()
        cg_quote = _get_coingecko_quote(coin_id)
        if cg_quote:
            live_quote = {
                "symbol": normalized_symbol,
                **cg_quote,
            }

    # Merge with local baseline
    if live_quote:
        if local_baseline:
            local_baseline.update(live_quote)
            final_quote = local_baseline
        else:
            final_quote = live_quote
            if "name" not in final_quote:
                final_quote["name"] = normalized_symbol
    else:
        final_quote = local_baseline

    if final_quote:
        final_quote["currency"] = "USDT"
        _crypto_cache[normalized_symbol] = {"data": final_quote.copy(), "ts": now}
        return final_quote.copy()

    return None


# ==============================================================================
# SECTION 4: CONCURRENT CRYPTO MARKET LISTING
# Crypto assets ko parallel me latest prices se update karta hai.
# ==============================================================================
def list_crypto(query=""):
    """Query filter ke adhar par refreshed crypto assets list return karta hai."""
    from concurrent.futures import ThreadPoolExecutor

    normalized_query = query.lower().strip()
    filtered = [
        coin.copy() for coin in CRYPTO
        if not normalized_query or normalized_query in coin["symbol"].lower() or normalized_query in coin["name"].lower()
    ]
    if not filtered:
        return []

    def _refresh(coin):
        try:
            live = get_crypto_quote(coin["symbol"])
            if live:
                coin["price"] = live["price"]
                coin["change"] = live["change"]
                coin["currency"] = "USDT"
                if "source" in live:
                    coin["source"] = live["source"]
        except Exception:
            pass
        return coin

    workers = min(len(filtered), 8)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_refresh, filtered))


# ==============================================================================
# SECTION 5: MULTI-TIMEFRAME CANDLESTICK GENERATOR (BINANCE KLINES)
# Binance API se 1m se lekar 5y tak real klines lata hai ya realistic offline
# candles generate karta hai.
# ==============================================================================
def generate_crypto_candles(symbol, current_price, timeframe="5y", days=None):
    """Crypto candlestick OHLC data fetch ya generate karta hai."""
    tf_raw = (timeframe or "5y").strip()
    if tf_raw in ("1M", "1mo", "1month"):
        tf = "1mo"
    elif tf_raw in ("3M", "3mo", "3months"):
        tf = "3mo"
    elif tf_raw in ("6M", "6mo", "6months"):
        tf = "6mo"
    else:
        tf = tf_raw.lower()

    config = {
        "1m": ("1m", 100),
        "5m": ("5m", 100),
        "10m": ("5m", 200),
        "30m": ("30m", 100),
        "1h": ("1h", 100),
        "8h": ("8h", 100),
        "1d": ("1d", 100),
        "7d": ("1w", 100),
        "1w": ("1w", 100),
        "1mo": ("1d", 30),
        "3mo": ("1d", 90),
        "6mo": ("1d", 180),
        "1y": ("1d", 365),
        "5y": ("1w", 260),
    }
    interval, limit = config.get(tf, ("1d", int(days or 45)))
    cache_key = f"{symbol.upper()}:{tf}"
    cached = _crypto_candle_cache.get(cache_key)
    now = time.time()
    if cached and (now - cached["ts"] < 300):
        return cached["candles"]

    is_intraday = tf in ("1m", "5m", "10m", "30m", "1h", "8h")

    # Try Binance klines
    try:
        ticker_sym = f"{symbol.upper()}USDT"
        url = f"https://api.binance.com/api/v3/klines?symbol={ticker_sym}&interval={interval}&limit={limit}"
        resp = _crypto_session.get(url, timeout=(2.0, 3.0))
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                if tf == "10m" and len(data) >= 2:
                    if len(data) % 2 != 0:
                        data = data[1:]
                    candles = []
                    for i in range(0, len(data), 2):
                        c1, c2 = data[i], data[i + 1]
                        c_time = int(c1[0] / 1000)
                        o = float(c1[1])
                        h = max(float(c1[2]), float(c2[2]))
                        l = min(float(c1[3]), float(c2[3]))
                        c = float(c2[4])
                        dec = 4 if c < 1 else 2
                        candles.append({
                            "time": c_time,
                            "open": round(o, dec),
                            "high": round(h, dec),
                            "low": round(l, dec),
                            "close": round(c, dec),
                        })
                else:
                    candles = []
                    for item in data:
                        c_time = int(item[0] / 1000) if is_intraday else datetime.fromtimestamp(item[0] / 1000).strftime("%Y-%m-%d")
                        o, h, l, c = float(item[1]), float(item[2]), float(item[3]), float(item[4])
                        dec = 4 if c < 1 else 2
                        candles.append({
                            "time": c_time,
                            "open": round(o, dec),
                            "high": round(h, dec),
                            "low": round(l, dec),
                            "close": round(c, dec),
                        })
                if candles:
                    _crypto_candle_cache[cache_key] = {"candles": candles, "ts": now}
                    return candles
    except Exception:
        pass

    # Offline calibrated generator fallback
    seed = sum(ord(character) for character in symbol) + 41
    price = float(current_price) * (0.90 + (seed % 8) / 100)
    count = 100 if tf == "10m" else limit
    candles = []
    step_map = {
        "1m": 60,
        "5m": 300,
        "10m": 600,
        "30m": 1800,
        "1h": 3600,
        "8h": 28800,
    }
    is_weekly = tf in ("7d", "1w", "5y")
    curr_sec = int(now)
    for index in range(count):
        drift = (((seed + index * 19) % 21) - 10) / 170
        open_price = price
        close_price = max(0.0001, open_price * (1 + drift))
        high_price = max(open_price, close_price) * (1.008 + ((seed + index) % 4) / 1000)
        low_price = min(open_price, close_price) * (0.992 - ((seed + index) % 3) / 1000)
        dec = 4 if close_price < 1 else 2
        if is_intraday:
            step = step_map.get(tf, 300)
            candle_time = curr_sec - (count - index - 1) * step
        elif is_weekly:
            candle_time = (date.today() - timedelta(weeks=count - index - 1)).isoformat()
        else:
            candle_time = (date.today() - timedelta(days=count - index - 1)).isoformat()
        candles.append(
            {
                "time": candle_time,
                "open": round(open_price, dec),
                "high": round(high_price, dec),
                "low": round(low_price, dec),
                "close": round(close_price, dec),
            }
        )
        price = close_price
    _crypto_candle_cache[cache_key] = {"candles": candles, "ts": now}
    return candles


# ==============================================================================
# SECTION 6: VERCEL SERVERLESS EXPORT
# Vercel serverless function entrypoint.
# ==============================================================================
def handler(*args, **kwargs):
    from app import app
    return app(*args, **kwargs)
