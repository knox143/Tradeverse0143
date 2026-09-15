"""Crypto quote helpers with live real-time feeds, caching, and fallback adapters."""

import json
import os
import time
from datetime import date, datetime, timedelta
import requests

_crypto_session = requests.Session()
_crypto_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

# In-memory quote cache: symbol -> {"data": quote_dict, "ts": float}
_crypto_cache = {}
_crypto_candle_cache = {}

# Starter / fallback crypto assets
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
    try:
        return int(os.environ.get("PRICE_CACHE_TTL_SECONDS") or 60)
    except (ValueError, TypeError):
        return 60


def _fetch_binance_quote(symbol):
    """Retrieve real-time 24hr ticker from Binance API with fast pooled HTTP."""
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


def get_crypto_quote(symbol):
    """Return live real-time crypto quote, checking cache, Binance, CoinGecko, and fallback."""
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


def list_crypto(query=""):
    """Return the crypto market list refreshed concurrently with latest real-time prices."""
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


def generate_crypto_candles(symbol, current_price, timeframe="5y", days=None):
    """Fetch real historical candlestick data from Binance or fallback to calibrated generator."""
    tf = (timeframe or "5y").lower().strip()
    config = {
        "5y": ("1w", 260),
        "1y": ("1d", 365),
        "1m": ("1d", 30),
        "1w": ("4h", 42),
        "1d": ("15m", 96),
    }
    interval, limit = config.get(tf, ("1d", int(days or 45)))
    cache_key = f"{symbol.upper()}:{tf}"
    cached = _crypto_candle_cache.get(cache_key)
    now = time.time()
    if cached and (now - cached["ts"] < 300):
        return cached["candles"]

    # Try Binance klines
    try:
        ticker_sym = f"{symbol.upper()}USDT"
        url = f"https://api.binance.com/api/v3/klines?symbol={ticker_sym}&interval={interval}&limit={limit}"
        resp = _crypto_session.get(url, timeout=(2.0, 3.0))
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                candles = []
                for item in data:
                    c_time = datetime.fromtimestamp(item[0] / 1000).strftime("%Y-%m-%d") if interval in ("1w", "1d") else int(item[0] / 1000)
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
    count = limit
    candles = []
    is_weekly = (interval == "1w")
    for index in range(count):
        drift = (((seed + index * 19) % 21) - 10) / 170
        open_price = price
        close_price = max(0.0001, open_price * (1 + drift))
        high_price = max(open_price, close_price) * (1.008 + ((seed + index) % 4) / 1000)
        low_price = min(open_price, close_price) * (0.992 - ((seed + index) % 3) / 1000)
        dec = 4 if close_price < 1 else 2
        if is_weekly:
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


# Vercel serverless fallback handler
def handler(*args, **kwargs):
    from app import app
    return app(*args, **kwargs)
